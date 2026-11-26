"""Persistance SQLite : schéma, déclencheurs d'immutabilité, transactions, journal chaîné."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from contextvars import ContextVar
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CHEMIN_BASE = Path(os.environ.get("FACTURATION_BASE", RACINE / "instance" / "facturation.db"))

SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS parametres (cle TEXT PRIMARY KEY, valeur TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS utilisateurs (
  id TEXT PRIMARY KEY, login TEXT UNIQUE NOT NULL, nom TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('vendeur','responsable','comptable','admin')),
  sel TEXT NOT NULL, hash TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS clients (
  id TEXT PRIMARY KEY, nom TEXT NOT NULL, alias TEXT NOT NULL, type TEXT NOT NULL,
  ifu TEXT, adresse TEXT, telephone TEXT, aib_taux INTEGER NOT NULL DEFAULT 0,
  delai_paiement_jours INTEGER NOT NULL DEFAULT 0);

CREATE TABLE IF NOT EXISTS articles (
  id TEXT PRIMARY KEY, designation TEXT NOT NULL, alias TEXT NOT NULL, unite TEXT NOT NULL,
  prix_unitaire_ttc INTEGER NOT NULL, groupe_taxe TEXT NOT NULL,
  quantite_decimale INTEGER NOT NULL DEFAULT 0);

CREATE TABLE IF NOT EXISTS dossiers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  canal TEXT NOT NULL, texte_commande TEXT NOT NULL, texte_livraison TEXT,
  piece_jointe TEXT, cree_par TEXT NOT NULL, cree_le TEXT NOT NULL,
  statut TEXT NOT NULL DEFAULT 'BROUILLON' CHECK (statut IN ('BROUILLON','VALIDE','SUPPRIME')),
  extracteur TEXT, extraction TEXT, brouillon TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1, facture_id INTEGER);

CREATE TABLE IF NOT EXISTS factures (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  type TEXT NOT NULL CHECK (type IN ('FV','FA')),
  numero TEXT UNIQUE NOT NULL,
  dossier_id INTEGER, facture_origine_id INTEGER,
  contenu TEXT NOT NULL, total_ttc INTEGER NOT NULL, net_a_payer INTEGER NOT NULL,
  valide_par TEXT NOT NULL, valide_le TEXT NOT NULL,
  statut TEXT NOT NULL CHECK (statut IN ('VALIDEE','EN_ATTENTE_DGI','CONFIRMEE','ANNULEE')),
  uid_dgi TEXT, code_dgi TEXT, qr TEXT, compteurs TEXT, horodatage_dgi TEXT, motif_annulation TEXT,
  accuse_client_le TEXT, accuse_client_canal TEXT);

CREATE TABLE IF NOT EXISTS compteurs (serie TEXT PRIMARY KEY, dernier INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS idempotence (
  cle TEXT PRIMARY KEY, action TEXT NOT NULL, resultat TEXT NOT NULL, cree_le TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS journal (
  id INTEGER PRIMARY KEY AUTOINCREMENT, horodatage TEXT NOT NULL, acteur TEXT NOT NULL,
  action TEXT NOT NULL, objet TEXT NOT NULL, details TEXT NOT NULL,
  hash_precedent TEXT NOT NULL, hash TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS dgi_simulee (
  uid TEXT PRIMARY KEY, numero_facture TEXT NOT NULL, type TEXT NOT NULL,
  totaux TEXT NOT NULL, code TEXT, compteur TEXT, horodatage TEXT,
  statut TEXT NOT NULL CHECK (statut IN ('EN_ATTENTE','CONFIRMEE','ANNULEE')));

CREATE TABLE IF NOT EXISTS proformas (
  id INTEGER PRIMARY KEY AUTOINCREMENT, numero TEXT UNIQUE NOT NULL, dossier_id INTEGER NOT NULL,
  contenu TEXT NOT NULL, cree_par TEXT NOT NULL, cree_le TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS paiements (
  id INTEGER PRIMARY KEY AUTOINCREMENT, facture_id INTEGER NOT NULL, montant INTEGER NOT NULL,
  mode TEXT NOT NULL, reference TEXT, recu_numero TEXT UNIQUE NOT NULL,
  enregistre_par TEXT NOT NULL, enregistre_le TEXT NOT NULL);

-- Messages des canaux (WhatsApp simulé, Telegram simulé) : entrants et réponses du bot.
CREATE TABLE IF NOT EXISTS messages_canal (
  id INTEGER PRIMARY KEY AUTOINCREMENT, message_id TEXT UNIQUE, plateforme TEXT NOT NULL, numero TEXT NOT NULL,
  sens TEXT NOT NULL CHECK (sens IN ('entrant','sortant')), type TEXT NOT NULL, texte TEXT, media TEXT,
  dossier_id INTEGER, facture_id INTEGER, horodatage TEXT NOT NULL);

-- Une facture validée ne change plus (OHADA art. 20 et 22).
CREATE TRIGGER IF NOT EXISTS facture_contenu_immuable
BEFORE UPDATE OF type, numero, dossier_id, facture_origine_id, contenu, total_ttc, net_a_payer,
                 valide_par, valide_le ON factures
BEGIN SELECT RAISE(ABORT, 'Facture validée : modification interdite'); END;

CREATE TRIGGER IF NOT EXISTS facture_transitions
BEFORE UPDATE OF statut ON factures
WHEN NEW.statut <> OLD.statut AND NOT (
  (OLD.statut = 'VALIDEE' AND NEW.statut = 'EN_ATTENTE_DGI') OR
  (OLD.statut = 'EN_ATTENTE_DGI' AND NEW.statut IN ('CONFIRMEE','ANNULEE')))
BEGIN SELECT RAISE(ABORT, 'Changement d''état interdit'); END;

CREATE TRIGGER IF NOT EXISTS facture_dgi_definitif
BEFORE UPDATE OF uid_dgi, code_dgi, qr, compteurs, horodatage_dgi ON factures
WHEN (OLD.code_dgi IS NOT NULL AND NEW.code_dgi IS NOT OLD.code_dgi)
  OR (OLD.uid_dgi IS NOT NULL AND NEW.uid_dgi IS NOT OLD.uid_dgi)
BEGIN SELECT RAISE(ABORT, 'Données DGI définitives : modification interdite'); END;

CREATE TRIGGER IF NOT EXISTS facture_jamais_supprimee
BEFORE DELETE ON factures
BEGIN SELECT RAISE(ABORT, 'Une facture ne se supprime pas'); END;

CREATE TRIGGER IF NOT EXISTS journal_ajout_seul_maj
BEFORE UPDATE ON journal BEGIN SELECT RAISE(ABORT, 'Journal en ajout seul'); END;
CREATE TRIGGER IF NOT EXISTS journal_ajout_seul_suppr
BEFORE DELETE ON journal BEGIN SELECT RAISE(ABORT, 'Journal en ajout seul'); END;

CREATE TRIGGER IF NOT EXISTS paiement_immuable
BEFORE UPDATE ON paiements BEGIN SELECT RAISE(ABORT, 'Paiement enregistré : modification interdite'); END;
"""


def maintenant() -> str:
    return datetime.now().isoformat(timespec="seconds")


# Espace d'entreprise de la requête en cours (une base SQLite par entreprise : aucune donnée partagée).
# Vide = la base de démonstration (CHEMIN_BASE).
ESPACE: ContextVar[str | None] = ContextVar("espace", default=None)


def chemin_espace(slug: str) -> Path:
    if not re.fullmatch(r"[a-z0-9-]{3,48}", slug or ""):
        raise ValueError("Espace invalide")
    return Path(CHEMIN_BASE).parent / "espaces" / f"{slug}.db"


def chemin_courant() -> Path:
    slug = ESPACE.get()
    return chemin_espace(slug) if slug else Path(CHEMIN_BASE)


def dossier_donnees(nom: str) -> Path:
    """Dossier de fichiers (pièces, médias) propre à l'espace courant."""
    base = chemin_courant()
    return base.parent / (nom if base == Path(CHEMIN_BASE) else f"{base.stem}_{nom}")


def connecter(chemin: Path | str | None = None) -> sqlite3.Connection:
    chemin = Path(chemin or chemin_courant())
    chemin.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(chemin, isolation_level=None, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialiser_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


@contextmanager
def transaction(conn: sqlite3.Connection):
    """Transaction exclusive en écriture (BEGIN IMMEDIATE) : sérialise les validations concurrentes."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


# --- Journal chaîné -----------------------------------------------------------

HASH_ORIGINE = "0" * 64


def _empreinte(precedent: str, horodatage: str, acteur: str, action: str, objet: str, details: str) -> str:
    charge = json.dumps([precedent, horodatage, acteur, action, objet, details], ensure_ascii=False)
    return hashlib.sha256(charge.encode("utf-8")).hexdigest()


def journaliser(conn: sqlite3.Connection, acteur: str, action: str, objet: str, details: dict | None = None) -> None:
    """À appeler dans une transaction ouverte."""
    ligne = conn.execute("SELECT hash FROM journal ORDER BY id DESC LIMIT 1").fetchone()
    precedent = ligne["hash"] if ligne else HASH_ORIGINE
    horodatage = maintenant()
    texte = json.dumps(details or {}, ensure_ascii=False, sort_keys=True)
    h = _empreinte(precedent, horodatage, acteur, action, objet, texte)
    conn.execute(
        "INSERT INTO journal (horodatage, acteur, action, objet, details, hash_precedent, hash) VALUES (?,?,?,?,?,?,?)",
        (horodatage, acteur, action, objet, texte, precedent, h),
    )


def verifier_journal(conn: sqlite3.Connection) -> tuple[bool, int | None, int]:
    """Renvoie (intègre, id de la première ligne fautive, nombre de lignes vérifiées)."""
    precedent = HASH_ORIGINE
    n = 0
    for r in conn.execute("SELECT * FROM journal ORDER BY id"):
        n += 1
        attendu = _empreinte(precedent, r["horodatage"], r["acteur"], r["action"], r["objet"], r["details"])
        if r["hash_precedent"] != precedent or r["hash"] != attendu:
            return False, r["id"], n
        precedent = r["hash"]
    return True, None, n


# --- Numérotation sans trou ---------------------------------------------------

def prochain_numero(conn: sqlite3.Connection, serie: str) -> str:
    """À appeler dans la transaction qui crée le document : un rollback annule aussi le numéro."""
    annee = datetime.now().year
    cle = f"{serie}-{annee}"
    conn.execute("INSERT OR IGNORE INTO compteurs (serie, dernier) VALUES (?, 0)", (cle,))
    n = conn.execute("UPDATE compteurs SET dernier = dernier + 1 WHERE serie = ? RETURNING dernier", (cle,)).fetchone()[0]
    return f"{cle}-{n:06d}"


# --- Paramètres ---------------------------------------------------------------

def lire_parametre(conn: sqlite3.Connection, cle: str, defaut=None):
    r = conn.execute("SELECT valeur FROM parametres WHERE cle = ?", (cle,)).fetchone()
    return json.loads(r["valeur"]) if r else defaut


def ecrire_parametre(conn: sqlite3.Connection, cle: str, valeur) -> None:
    conn.execute("INSERT INTO parametres (cle, valeur) VALUES (?, ?) ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur",
                 (cle, json.dumps(valeur, ensure_ascii=False)))
