"""Opérations métier : dossiers, validation, émission simulée, avoirs, paiements, rapports.

Chaque opération qui écrit :
- vérifie le rôle de l'utilisateur (le contrôle n'est jamais laissé à l'interface) ;
- s'exécute dans une transaction exclusive ;
- s'inscrit au journal chaîné.
Les opérations sensibles (validation, émission, avoir, paiement) acceptent une clé d'idempotence :
la rejouer renvoie le même résultat sans rien créer de plus.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import secrets
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from . import brouillon as B
from .db import (connecter, ecrire_parametre, initialiser_schema, journaliser, lire_parametre, maintenant,
                 prochain_numero, transaction)
from .extraction import ErreurExtraction, extraire, normaliser_resultat
from .moteur import ErreurCalcul, Ligne, calculer, lire_quantite

RACINE = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("FACTURATION_DATA", RACINE / "data"))
MOT_DE_PASSE_DEMO = os.environ.get("DEMO_MOT_DE_PASSE", "demo2026")

DROITS = {
    "dossier.ecrire": {"vendeur", "responsable"},
    "dossier.decider": {"responsable"},
    "facture.valider": {"responsable"},
    "facture.emettre": {"responsable"},
    "facture.avoir": {"responsable"},
    "paiement.enregistrer": {"responsable", "comptable"},
    "referentiel.ecrire": {"comptable", "admin"},
    "parametres.ecrire": {"admin"},
    "demo.reinitialiser": {"admin"},
    "compta.lire": {"comptable", "responsable", "admin"},
}

PERSONNALISATION_DEFAUT = {
    "couleur": "#0B6E4F",
    "logo": None,
    "conditions_paiement": "Paiement à réception de facture.",
    "pied_de_page": "Merci de votre confiance.",
    "mode_arrondi": "groupe",
}


class Refus(Exception):
    """Action refusée (droits, état, règle métier). Le message est montré à l'utilisateur."""


class CoupureSimulee(RuntimeError):
    """Interruption volontaire pour démontrer la reprise après coupure."""


def exiger(utilisateur: dict, droit: str) -> None:
    roles = set(DROITS[droit])
    if droit in ("facture.valider", "dossier.decider") and utilisateur.get("mode_solo"):
        roles.add("vendeur")
    if utilisateur["role"] not in roles:
        raise Refus("Votre rôle ne permet pas cette action.")


# --- Mots de passe ---------------------------------------------------------------------

def hacher(mot_de_passe: str, sel: str | None = None) -> tuple[str, str]:
    sel = sel or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode(), bytes.fromhex(sel), 200_000).hex()
    return sel, h


def authentifier(conn, login: str, mot_de_passe: str) -> dict | None:
    u = conn.execute("SELECT * FROM utilisateurs WHERE login = ?", (login.strip().lower(),)).fetchone()
    if not u:
        hacher(mot_de_passe)  # temps constant approximatif
        return None
    _, h = hacher(mot_de_passe, u["sel"])
    return dict(u) if secrets.compare_digest(h, u["hash"]) else None


# --- Référentiels ------------------------------------------------------------------------

def clients(conn) -> list[dict]:
    return [dict(r, alias=json.loads(r["alias"])) for r in conn.execute("SELECT * FROM clients ORDER BY nom")]


def articles(conn) -> list[dict]:
    return [dict(r, alias=json.loads(r["alias"]), quantite_decimale=bool(r["quantite_decimale"]))
            for r in conn.execute("SELECT * FROM articles ORDER BY designation")]


def client(conn, cid: str | None) -> dict | None:
    r = conn.execute("SELECT * FROM clients WHERE id = ?", (cid,)).fetchone() if cid else None
    return dict(r, alias=json.loads(r["alias"])) if r else None


def entreprise(conn) -> dict:
    e = lire_parametre(conn, "entreprise", {})
    e["personnalisation"] = {**PERSONNALISATION_DEFAUT, **lire_parametre(conn, "personnalisation", {})}
    return e


# --- Initialisation et réinitialisation -------------------------------------------------

TABLES = ["parametres", "utilisateurs", "clients", "articles", "dossiers", "factures", "compteurs", "idempotence",
          "journal", "dgi_simulee", "proformas", "paiements"]


def reinitialiser(conn, acteur: str = "systeme") -> None:
    """Remet la démonstration à zéro à partir des fichiers de data/."""
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN IMMEDIATE")
    try:
        for t in TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {t}")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    initialiser_schema(conn)
    charger_donnees(conn, acteur)


def charger_donnees(conn, acteur: str = "systeme") -> None:
    ent = json.loads((DATA / "entreprise.json").read_text(encoding="utf-8"))
    cls = json.loads((DATA / "clients.json").read_text(encoding="utf-8"))
    arts = json.loads((DATA / "articles.json").read_text(encoding="utf-8"))
    with transaction(conn):
        ecrire_parametre(conn, "entreprise", {k: v for k, v in ent.items() if k != "utilisateurs"})
        for u in ent["utilisateurs"]:
            sel, h = hacher(MOT_DE_PASSE_DEMO)
            login = B.normaliser(u["nom"]).replace(" ", "")
            conn.execute("INSERT INTO utilisateurs (id, login, nom, role, sel, hash) VALUES (?,?,?,?,?,?)",
                         (u["id"], login, u["nom"], u["role"], sel, h))
        for c in cls:
            conn.execute("INSERT INTO clients VALUES (?,?,?,?,?,?,?,?,?)",
                         (c["id"], c["nom"], json.dumps(c["alias"], ensure_ascii=False), c["type"], c.get("ifu"),
                          c.get("adresse"), c.get("telephone"), int(c.get("aib_taux", 0)),
                          int(c.get("delai_paiement_jours", 0))))
        for a in arts:
            conn.execute("INSERT INTO articles VALUES (?,?,?,?,?,?,?)",
                         (a["id"], a["designation"], json.dumps(a["alias"], ensure_ascii=False), a["unite"],
                          int(a["prix_unitaire_ttc"]), a["groupe_taxe"], int(bool(a.get("quantite_decimale")))))
        journaliser(conn, acteur, "DEMO_REINITIALISEE", "base", {"clients": len(cls), "articles": len(arts)})


def ouvrir(chemin=None):
    conn = connecter(chemin)
    existe = conn.execute("SELECT name FROM sqlite_master WHERE name = 'utilisateurs'").fetchone()
    if not existe:
        reinitialiser(conn)
    else:
        initialiser_schema(conn)
    return conn


# --- Dossiers de vente ---------------------------------------------------------------------

def _charger_dossier(conn, did: int) -> dict:
    r = conn.execute("SELECT * FROM dossiers WHERE id = ?", (did,)).fetchone()
    if not r:
        raise Refus("Dossier introuvable.")
    d = dict(r)
    d["brouillon"] = json.loads(d["brouillon"])
    d["extraction"] = json.loads(d["extraction"]) if d["extraction"] else None
    return d


def dossier(conn, did: int) -> dict:
    d = _charger_dossier(conn, did)
    d["anomalies"] = analyser(conn, d)
    d["totaux"] = totaux_brouillon(conn, d)
    return d


def _doublons(conn, d: dict) -> list[int]:
    sig = B.signature(d["brouillon"])
    if not sig[0]:
        return []
    limite = (datetime.fromisoformat(d["cree_le"]) - timedelta(hours=B.FENETRE_DOUBLON_HEURES)).isoformat()
    res = []
    for r in conn.execute("SELECT id, brouillon FROM dossiers WHERE id < ? AND statut != 'SUPPRIME' AND cree_le >= ?",
                          (d["id"], limite)):
        if B.signature(json.loads(r["brouillon"])) == sig:
            res.append(r["id"])
    return res


def _aib(conn, d: dict) -> int:
    c = client(conn, d["brouillon"]["client"].get("id"))
    return int(c["aib_taux"]) if c else 0


def analyser(conn, d: dict) -> list[dict]:
    mode = entreprise(conn)["personnalisation"]["mode_arrondi"]
    return B.anomalies(d["brouillon"], clients(conn), articles(conn), _doublons(conn, d), _aib(conn, d), mode)


def totaux_brouillon(conn, d: dict) -> dict | None:
    try:
        lignes = B.lignes_facturables(d["brouillon"], articles(conn))
        mode = entreprise(conn)["personnalisation"]["mode_arrondi"]
        return calculer(lignes, _aib(conn, d), mode).en_dict() if lignes else None
    except (ErreurCalcul, ValueError, TypeError):
        return None


def creer_dossier(conn, u: dict, canal: str, texte_commande: str, texte_livraison: str | None,
                  extracteur: str, octets: bytes | None = None, mime: str | None = None,
                  nom_fichier: str | None = None) -> int:
    exiger(u, "dossier.ecrire")
    texte_commande = (texte_commande or "").strip()
    if not texte_commande and not octets:
        raise Refus("Collez le message de commande ou joignez un document.")
    cls, arts = clients(conn), articles(conn)
    try:
        brut = normaliser_resultat(extraire(extracteur, texte_commande, cls, arts, octets, mime))
    except ErreurExtraction as e:
        raise Refus(str(e))
    if not texte_commande and brut.get("transcription"):
        texte_commande = brut["transcription"].strip()
    br = B.construire(brut, texte_commande, cls, arts, verifier=True)
    extraction_bl = None
    if texte_livraison and texte_livraison.strip():
        try:
            extraction_bl = normaliser_resultat(extraire(extracteur, texte_livraison, cls, arts))
        except ErreurExtraction as e:
            raise Refus(str(e))
        br = B.integrer_livraison(br, extraction_bl, texte_livraison, arts)
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO dossiers (canal, texte_commande, texte_livraison, piece_jointe, cree_par, cree_le, extracteur,"
            " extraction, brouillon) VALUES (?,?,?,?,?,?,?,?,?)",
            (canal, texte_commande, texte_livraison or None, nom_fichier, u["id"], maintenant(), extracteur,
             json.dumps({"commande": brut, "livraison": extraction_bl}, ensure_ascii=False),
             json.dumps(br, ensure_ascii=False)))
        did = cur.lastrowid
        journaliser(conn, u["id"], "DOSSIER_CREE", f"dossier:{did}",
                    {"canal": canal, "extracteur": extracteur, "lignes": len(br["lignes"]),
                     "valeurs_rejetees": len(br["rejets"])})
    return did


def _enregistrer_brouillon(conn, u: dict, did: int, version: int, br: dict, action: str, details: dict) -> None:
    with transaction(conn):
        n = conn.execute("UPDATE dossiers SET brouillon = ?, version = version + 1 WHERE id = ? AND version = ?"
                         " AND statut = 'BROUILLON'", (json.dumps(br, ensure_ascii=False), did, version)).rowcount
        if n != 1:
            raise Refus("Ce dossier a été modifié entre-temps ou n'est plus un brouillon. Rechargez la page.")
        journaliser(conn, u["id"], action, f"dossier:{did}", details)


def ajouter_livraison(conn, u: dict, did: int, version: int, texte: str, extracteur: str) -> None:
    exiger(u, "dossier.ecrire")
    d = _charger_dossier(conn, did)
    try:
        brut = normaliser_resultat(extraire(extracteur, texte, clients(conn), articles(conn)))
    except ErreurExtraction as e:
        raise Refus(str(e))
    br = B.integrer_livraison(d["brouillon"], brut, texte, articles(conn))
    with transaction(conn):
        n = conn.execute("UPDATE dossiers SET brouillon = ?, texte_livraison = ?, version = version + 1 WHERE id = ?"
                         " AND version = ? AND statut = 'BROUILLON'",
                         (json.dumps(br, ensure_ascii=False), texte, did, version)).rowcount
        if n != 1:
            raise Refus("Ce dossier a été modifié entre-temps. Rechargez la page.")
        journaliser(conn, u["id"], "LIVRAISON_AJOUTEE", f"dossier:{did}", {"lignes_livrees": len(brut["lignes"])})


def corriger(conn, u: dict, did: int, version: int, champs: dict) -> None:
    """Corrections manuelles du brouillon. Chaque champ modifié est journalisé (avant/après)."""
    exiger(u, "dossier.ecrire")
    d = _charger_dossier(conn, did)
    br = d["brouillon"]
    modifs = []
    arts = {a["id"]: a for a in articles(conn)}

    if "client_id" in champs and champs["client_id"] != (br["client"].get("id") or ""):
        nouveau = champs["client_id"] or None
        if nouveau and not client(conn, nouveau):
            raise Refus("Client inconnu.")
        modifs.append({"champ": "client", "avant": br["client"].get("id"), "apres": nouveau})
        br["client"].update(id=nouveau, source="manuel", confiance="manuelle")
    if "mode_paiement" in champs and champs["mode_paiement"] != (br["mode_paiement"].get("valeur") or ""):
        modifs.append({"champ": "mode de paiement", "avant": br["mode_paiement"].get("valeur"),
                       "apres": champs["mode_paiement"] or None})
        br["mode_paiement"] = {"valeur": champs["mode_paiement"] or None, "citation": None, "source": "manuel"}

    for l in br["lignes"]:
        for cle, champ in (("article_id", "article"), ("quantite_commandee", "quantité commandée"),
                           ("quantite_livree", "quantité livrée")):
            k = f"{l['cle']}:{cle}"
            if k not in champs:
                continue
            v = (champs[k] or "").strip() or None
            if cle != "article_id" and v is not None:
                v = v.replace(",", ".")
                try:
                    Decimal(v)
                except Exception:
                    raise Refus(f"Quantité illisible : {v}")
                v = format(Decimal(v).normalize(), "f")
            if cle == "quantite_livree" and v is None and l.get("quantite_livree") is None:
                continue
            if v != l.get(cle):
                modifs.append({"champ": f"{l['cle']} {champ}", "avant": l.get(cle), "apres": v})
                l[cle] = v
                l["source"] = "manuel"
                if cle == "article_id":
                    l["prix_catalogue"] = arts[v]["prix_unitaire_ttc"] if v in arts else None
                    l["confiance_article"] = "manuelle"
        if champs.get(f"{l['cle']}:supprimer"):
            modifs.append({"champ": f"{l['cle']} supprimée", "avant": l.get("article_id"), "apres": None})
            l["supprimee"] = True
    br["lignes"] = [l for l in br["lignes"] if not l.get("supprimee")]

    if champs.get("nouvel_article"):
        aid = champs["nouvel_article"]
        if aid not in arts:
            raise Refus("Article inconnu.")
        cle = f"m{len(br['lignes']) + 1}{secrets.token_hex(2)}"
        q = (champs.get("nouvelle_quantite") or "").strip().replace(",", ".") or None
        br["lignes"].append({"cle": cle, "article_id": aid, "confiance_article": "manuelle",
                             "designation_citee": None, "citation_designation": None,
                             "quantite_commandee": q, "citation_quantite": None,
                             "quantite_livree": None if not br.get("livraison") else q, "citation_livree": None,
                             "prix_cite": None, "citation_prix": None,
                             "prix_catalogue": arts[aid]["prix_unitaire_ttc"], "source": "manuel"})
        modifs.append({"champ": "ligne ajoutée", "avant": None, "apres": f"{aid} × {q}"})

    if not modifs:
        return
    _enregistrer_brouillon(conn, u, did, version, br, "BROUILLON_CORRIGE", {"modifications": modifs})


def decider(conn, u: dict, did: int, version: int, cle: str, choix: str, justification: str = "") -> None:
    """Décision du responsable sur une anomalie : écart, prix, total, doublon, remise."""
    exiger(u, "dossier.decider")
    d = _charger_dossier(conn, did)
    code = cle.split(":")[0]
    if code not in B.DECISIONS:
        raise Refus("Cette anomalie se corrige en modifiant le brouillon.")
    if code == "PRIX_INHABITUEL" and choix == "prix_cite" and len(justification.strip()) < 5:
        raise Refus("Expliquez pourquoi le prix cité s'applique (au moins quelques mots).")
    decision = {"choix": choix, "justification": justification.strip() or None, "par": u["id"], "le": maintenant()}
    if code == "REMISE_A_VALIDER":
        decision["acceptee"] = choix == "accepter"
    if code == "PRIX_INHABITUEL":
        decision["appliquer_prix_cite"] = choix == "prix_cite"
    d["brouillon"]["decisions"][cle] = decision
    _enregistrer_brouillon(conn, u, did, version, d["brouillon"], "ANOMALIE_TRANCHEE",
                           {"anomalie": cle, "choix": choix, "justification": decision["justification"]})


def supprimer_dossier(conn, u: dict, did: int, version: int) -> None:
    exiger(u, "dossier.ecrire")
    with transaction(conn):
        n = conn.execute("UPDATE dossiers SET statut = 'SUPPRIME', version = version + 1 WHERE id = ? AND version = ?"
                         " AND statut = 'BROUILLON'", (did, version)).rowcount
        if n != 1:
            raise Refus("Seul un brouillon peut être supprimé.")
        journaliser(conn, u["id"], "DOSSIER_SUPPRIME", f"dossier:{did}", {})


# --- Idempotence -------------------------------------------------------------------------

def _deja_fait(conn, cle: str | None, action: str):
    if not cle:
        return None
    r = conn.execute("SELECT action, resultat FROM idempotence WHERE cle = ?", (cle,)).fetchone()
    if r:
        if r["action"] != action:
            raise Refus("Clé d'idempotence déjà utilisée pour une autre action.")
        return json.loads(r["resultat"])
    return None


def _memoriser(conn, cle: str | None, action: str, resultat) -> None:
    if cle:
        conn.execute("INSERT INTO idempotence (cle, action, resultat, cree_le) VALUES (?,?,?,?)",
                     (cle, action, json.dumps(resultat), maintenant()))


# --- Validation ---------------------------------------------------------------------------

def _instantane_client(c: dict) -> dict:
    return {k: c.get(k) for k in ("id", "nom", "ifu", "adresse", "telephone", "type", "aib_taux")}


def valider(conn, u: dict, did: int, version: int, cle_idem: str | None = None) -> int:
    """Brouillon -> facture validée, numérotée et verrouillée. Renvoie l'id de la facture."""
    exiger(u, "facture.valider")
    with transaction(conn):
        fait = _deja_fait(conn, cle_idem, f"valider:{did}")
        if fait:
            return fait["facture_id"]
        d = dict(conn.execute("SELECT * FROM dossiers WHERE id = ?", (did,)).fetchone() or {})
        if not d:
            raise Refus("Dossier introuvable.")
        if d["statut"] == "VALIDE":
            # Validation concurrente ou double clic : la facture existe déjà, on la renvoie.
            _memoriser(conn, cle_idem, f"valider:{did}", {"facture_id": d["facture_id"]})
            return d["facture_id"]
        if d["statut"] != "BROUILLON":
            raise Refus("Ce dossier n'est plus un brouillon.")
        if d["version"] != version:
            raise Refus("Le brouillon a changé depuis votre lecture. Rechargez la page et vérifiez-le.")
        d["brouillon"] = json.loads(d["brouillon"])
        bloquantes = [a for a in analyser(conn, d) if a["bloquante"] and not a["resolue"]]
        if bloquantes:
            raise Refus("Validation impossible : " + "; ".join(a["titre"] for a in bloquantes) + ".")
        ent = entreprise(conn)
        c = client(conn, d["brouillon"]["client"]["id"])
        lignes = B.lignes_facturables(d["brouillon"], articles(conn))
        t = calculer(lignes, int(c["aib_taux"]), ent["personnalisation"]["mode_arrondi"])
        numero = prochain_numero(conn, "FV")
        contenu = {
            "type": "FV", "numero": numero, "date": maintenant(),
            "vendeur": {k: v for k, v in ent.items()},
            "client": _instantane_client(c),
            "totaux": t.en_dict(),
            "mode_paiement": d["brouillon"]["mode_paiement"].get("valeur") or "ESPECES",
            "dossier_id": did,
            "decisions": d["brouillon"].get("decisions", {}),
            "mode_arrondi": ent["personnalisation"]["mode_arrondi"],
        }
        cur = conn.execute(
            "INSERT INTO factures (type, numero, dossier_id, contenu, total_ttc, net_a_payer, valide_par, valide_le,"
            " statut) VALUES ('FV',?,?,?,?,?,?,?,'VALIDEE')",
            (numero, did, json.dumps(contenu, ensure_ascii=False), t.total_ttc, t.net_a_payer, u["id"], maintenant()))
        fid = cur.lastrowid
        conn.execute("UPDATE dossiers SET statut = 'VALIDE', facture_id = ?, version = version + 1 WHERE id = ?",
                     (fid, did))
        journaliser(conn, u["id"], "FACTURE_VALIDEE", f"facture:{fid}",
                    {"numero": numero, "dossier": did, "total_ttc": t.total_ttc, "net_a_payer": t.net_a_payer})
        _memoriser(conn, cle_idem, f"valider:{did}", {"facture_id": fid})
        return fid


# --- DGI simulée et émission -----------------------------------------------------------------

def _dgi_soumettre(conn, uid: str, f: dict) -> dict:
    """La « DGI » recalcule elle-même les totaux à partir des lignes reçues (comme e-MCF)."""
    r = conn.execute("SELECT * FROM dgi_simulee WHERE uid = ?", (uid,)).fetchone()
    if r:
        return json.loads(r["totaux"])
    contenu = json.loads(f["contenu"])
    lignes = [Ligne(l["designation"], lire_quantite(l["quantite"]), l["prix_unitaire_ttc"], l["groupe"])
              for l in contenu["totaux"]["lignes"]]
    t = calculer(lignes, contenu["totaux"]["aib_taux"], contenu.get("mode_arrondi", "groupe")).en_dict()
    totaux = {k: t[k] for k in ("total_ttc", "total_ht", "total_tva", "aib_montant", "net_a_payer")}
    conn.execute("INSERT INTO dgi_simulee (uid, numero_facture, type, totaux, statut) VALUES (?,?,?,?, 'EN_ATTENTE')",
                 (uid, f["numero"], f["type"], json.dumps(totaux)))
    return totaux


def _dgi_confirmer(conn, uid: str, type_doc: str) -> dict:
    r = dict(conn.execute("SELECT * FROM dgi_simulee WHERE uid = ?", (uid,)).fetchone())
    if r["statut"] == "CONFIRMEE":
        return r
    h = hashlib.sha256(uid.encode()).hexdigest().upper()
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    car = "".join(alphabet[int(h[i:i + 2], 16) % len(alphabet)] for i in range(0, 40, 2))
    code = "SIMU-" + "-".join(car[i:i + 4] for i in range(0, 20, 4))
    n_type = conn.execute("SELECT COUNT(*) FROM dgi_simulee WHERE statut = 'CONFIRMEE' AND type = ?",
                          (type_doc,)).fetchone()[0] + 1
    n_total = conn.execute("SELECT COUNT(*) FROM dgi_simulee WHERE statut = 'CONFIRMEE'").fetchone()[0] + 1
    compteur = f"{n_type}/{n_total} {type_doc}"
    conn.execute("UPDATE dgi_simulee SET statut = 'CONFIRMEE', code = ?, compteur = ?, horodatage = ? WHERE uid = ?",
                 (code, compteur, maintenant(), uid))
    return dict(conn.execute("SELECT * FROM dgi_simulee WHERE uid = ?", (uid,)).fetchone())


def emettre(conn, u: dict | None, fid: int, cle_idem: str | None = None, simuler_coupure: bool = False) -> dict:
    """VALIDEE -> EN_ATTENTE_DGI -> CONFIRMEE. Chaque étape est enregistrée : une coupure se reprend."""
    acteur = u["id"] if u else "reprise"
    if u:
        exiger(u, "facture.emettre")
    with transaction(conn):
        fait = _deja_fait(conn, cle_idem, f"emettre:{fid}")
        if fait:
            return fait
        f = conn.execute("SELECT * FROM factures WHERE id = ?", (fid,)).fetchone()
        if not f:
            raise Refus("Facture introuvable.")
        if f["statut"] == "VALIDEE":
            uid = str(uuid.uuid4())
            conn.execute("UPDATE factures SET statut = 'EN_ATTENTE_DGI', uid_dgi = ? WHERE id = ?", (uid, fid))
            journaliser(conn, acteur, "EMISSION_DEMANDEE", f"facture:{fid}", {"uid": uid})
        elif f["statut"] in ("CONFIRMEE", "ANNULEE"):
            return {"statut": f["statut"], "code": f["code_dgi"]}
    with transaction(conn):
        f = dict(conn.execute("SELECT * FROM factures WHERE id = ?", (fid,)).fetchone())
        totaux_dgi = _dgi_soumettre(conn, f["uid_dgi"], f)
        if (totaux_dgi["total_ttc"], totaux_dgi["net_a_payer"]) != (f["total_ttc"], f["net_a_payer"]):
            conn.execute("UPDATE dgi_simulee SET statut = 'ANNULEE' WHERE uid = ?", (f["uid_dgi"],))
            conn.execute("UPDATE factures SET statut = 'ANNULEE', motif_annulation = ? WHERE id = ?",
                         ("Totaux différents de ceux recalculés par la DGI simulée", fid))
            journaliser(conn, acteur, "EMISSION_ANNULEE", f"facture:{fid}", {"totaux_dgi": totaux_dgi})
            return {"statut": "ANNULEE", "code": None}
    if simuler_coupure:
        raise CoupureSimulee("Coupure simulée après l'envoi à la DGI, avant la confirmation.")
    with transaction(conn):
        f = dict(conn.execute("SELECT * FROM factures WHERE id = ?", (fid,)).fetchone())
        if f["statut"] == "CONFIRMEE":
            return {"statut": "CONFIRMEE", "code": f["code_dgi"]}
        dgi = _dgi_confirmer(conn, f["uid_dgi"], f["type"])
        qr = f"{dgi['code']};{f['numero']};{f['total_ttc']};{dgi['horodatage']}"
        conn.execute("UPDATE factures SET statut = 'CONFIRMEE', code_dgi = ?, qr = ?, compteurs = ?, horodatage_dgi = ?"
                     " WHERE id = ?", (dgi["code"], qr, dgi["compteur"], dgi["horodatage"], fid))
        journaliser(conn, acteur, "FACTURE_CONFIRMEE", f"facture:{fid}", {"code_dgi": dgi["code"]})
        resultat = {"statut": "CONFIRMEE", "code": dgi["code"]}
        _memoriser(conn, cle_idem, f"emettre:{fid}", resultat)
        return resultat


def reprendre(conn) -> list[int]:
    """Au démarrage : termine les émissions interrompues (aucune facture n'est créée deux fois)."""
    ids = [r["id"] for r in conn.execute("SELECT id FROM factures WHERE statut = 'EN_ATTENTE_DGI' ORDER BY id")]
    for fid in ids:
        emettre(conn, None, fid)
    return ids


# --- Factures, avoirs ------------------------------------------------------------------------

def facture(conn, fid: int) -> dict:
    r = conn.execute("SELECT * FROM factures WHERE id = ?", (fid,)).fetchone()
    if not r:
        raise Refus("Facture introuvable.")
    f = dict(r)
    f["contenu"] = json.loads(f["contenu"])
    f["avoirs"] = [dict(a, contenu=json.loads(a["contenu"])) for a in
                   conn.execute("SELECT * FROM factures WHERE facture_origine_id = ? ORDER BY id", (fid,))]
    f["paiements"] = [dict(p) for p in conn.execute("SELECT * FROM paiements WHERE facture_id = ? ORDER BY id", (fid,))]
    f["deja_avoir"] = sum(a["total_ttc"] for a in f["avoirs"] if a["statut"] != "ANNULEE")
    f["deja_paye"] = sum(p["montant"] for p in f["paiements"])
    f["reste_a_payer"] = f["net_a_payer"] - f["deja_paye"] - (
        sum(a["net_a_payer"] for a in f["avoirs"] if a["statut"] != "ANNULEE"))
    return f


def creer_avoir(conn, u: dict, fid: int, quantites: dict[int, str], motif: str, cle_idem: str | None = None) -> int:
    """Avoir (FA) sur une facture confirmée. quantites : index de ligne -> quantité à créditer."""
    exiger(u, "facture.avoir")
    if len((motif or "").strip()) < 3:
        raise Refus("Indiquez le motif de l'avoir.")
    with transaction(conn):
        fait = _deja_fait(conn, cle_idem, f"avoir:{fid}")
        if fait:
            return fait["facture_id"]
        f = conn.execute("SELECT * FROM factures WHERE id = ?", (fid,)).fetchone()
        if not f or f["type"] != "FV" or f["statut"] != "CONFIRMEE":
            raise Refus("Un avoir ne se crée que sur une facture de vente confirmée.")
        contenu = json.loads(f["contenu"])
        lignes = []
        for i, l in enumerate(contenu["totaux"]["lignes"]):
            q = (quantites.get(i) or "").strip()
            if not q or Decimal(q.replace(",", ".")) == 0:
                continue
            qd = lire_quantite(q)
            if qd > Decimal(l["quantite"]):
                raise Refus(f"{l['designation']} : on ne peut pas créditer plus que la quantité facturée.")
            lignes.append(Ligne(l["designation"], qd, l["prix_unitaire_ttc"], l["groupe"], l.get("article_id")))
        if not lignes:
            raise Refus("Choisissez au moins une ligne à créditer.")
        t = calculer(lignes, contenu["totaux"]["aib_taux"], contenu.get("mode_arrondi", "groupe"))
        deja = conn.execute("SELECT COALESCE(SUM(total_ttc), 0) FROM factures WHERE facture_origine_id = ?"
                            " AND statut != 'ANNULEE'", (fid,)).fetchone()[0]
        if deja + t.total_ttc > f["total_ttc"]:
            raise Refus(f"Le total des avoirs dépasserait la facture ({f['total_ttc'] - deja} F restants).")
        numero = prochain_numero(conn, "FA")
        avoir = {
            "type": "FA", "numero": numero, "date": maintenant(), "vendeur": contenu["vendeur"],
            "client": contenu["client"], "totaux": t.en_dict(), "mode_paiement": contenu["mode_paiement"],
            "reference": {"numero": f["numero"], "code_dgi": f["code_dgi"]}, "motif": motif.strip(),
            "mode_arrondi": contenu.get("mode_arrondi", "groupe"),
        }
        cur = conn.execute(
            "INSERT INTO factures (type, numero, facture_origine_id, contenu, total_ttc, net_a_payer, valide_par,"
            " valide_le, statut) VALUES ('FA',?,?,?,?,?,?,?,'VALIDEE')",
            (numero, fid, json.dumps(avoir, ensure_ascii=False), t.total_ttc, t.net_a_payer, u["id"], maintenant()))
        aid = cur.lastrowid
        journaliser(conn, u["id"], "AVOIR_CREE", f"facture:{aid}",
                    {"numero": numero, "facture_origine": f["numero"], "code_dgi_origine": f["code_dgi"],
                     "total_ttc": t.total_ttc, "motif": motif.strip()})
        _memoriser(conn, cle_idem, f"avoir:{fid}", {"facture_id": aid})
        return aid


def accuser_reception(conn, u: dict, fid: int, canal: str) -> None:
    exiger(u, "dossier.ecrire")
    with transaction(conn):
        n = conn.execute("UPDATE factures SET accuse_client_le = ?, accuse_client_canal = ? WHERE id = ?"
                         " AND accuse_client_le IS NULL AND statut = 'CONFIRMEE'", (maintenant(), canal, fid)).rowcount
        if n != 1:
            raise Refus("Accusé déjà enregistré, ou facture pas encore confirmée.")
        journaliser(conn, u["id"], "ACCUSE_CLIENT", f"facture:{fid}", {"canal": canal, "simule": True})


def enregistrer_paiement(conn, u: dict, fid: int, montant: int, mode: str, reference: str,
                         cle_idem: str | None = None) -> int:
    exiger(u, "paiement.enregistrer")
    with transaction(conn):
        fait = _deja_fait(conn, cle_idem, f"paiement:{fid}")
        if fait:
            return fait["paiement_id"]
        f = facture(conn, fid)
        if f["type"] != "FV" or f["statut"] != "CONFIRMEE":
            raise Refus("Seule une facture confirmée peut être payée.")
        if montant <= 0 or montant > f["reste_a_payer"]:
            raise Refus(f"Montant invalide : il reste {f['reste_a_payer']} F à payer.")
        recu = prochain_numero(conn, "RE")
        cur = conn.execute("INSERT INTO paiements (facture_id, montant, mode, reference, recu_numero, enregistre_par,"
                           " enregistre_le) VALUES (?,?,?,?,?,?,?)",
                           (fid, montant, mode, reference or None, recu, u["id"], maintenant()))
        journaliser(conn, u["id"], "PAIEMENT_ENREGISTRE", f"facture:{fid}",
                    {"montant": montant, "mode": mode, "recu": recu, "simule": True})
        _memoriser(conn, cle_idem, f"paiement:{fid}", {"paiement_id": cur.lastrowid})
        return cur.lastrowid


def creer_proforma(conn, u: dict, did: int) -> int:
    exiger(u, "dossier.ecrire")
    d = dossier(conn, did)
    if not d["totaux"]:
        raise Refus("Complétez le brouillon (client, articles, quantités) avant de produire une pro forma.")
    c = client(conn, d["brouillon"]["client"].get("id"))
    with transaction(conn):
        numero = prochain_numero(conn, "PF")
        contenu = {"type": "PF", "numero": numero, "date": maintenant(), "vendeur": entreprise(conn),
                   "client": _instantane_client(c) if c else {"nom": d["brouillon"]["client"].get("nom_cite") or "—"},
                   "totaux": d["totaux"], "mode_paiement": d["brouillon"]["mode_paiement"].get("valeur"),
                   "dossier_id": did}
        cur = conn.execute("INSERT INTO proformas (numero, dossier_id, contenu, cree_par, cree_le) VALUES (?,?,?,?,?)",
                           (numero, did, json.dumps(contenu, ensure_ascii=False), u["id"], maintenant()))
        journaliser(conn, u["id"], "PROFORMA_CREEE", f"dossier:{did}", {"numero": numero})
        return cur.lastrowid


# --- Comptabilité ----------------------------------------------------------------------------

def rapport_du_jour(conn, jour: date | None = None) -> dict:
    jour = (jour or date.today()).isoformat()
    res = {"jour": jour, "par_type": {}, "par_paiement": {}, "par_groupe": {}, "nombre": 0}
    for r in conn.execute("SELECT * FROM factures WHERE statut = 'CONFIRMEE' AND substr(horodatage_dgi, 1, 10) = ?",
                          (jour,)):
        c = json.loads(r["contenu"])
        signe = -1 if r["type"] == "FA" else 1
        res["nombre"] += 1
        t = res["par_type"].setdefault(r["type"], {"nombre": 0, "ttc": 0})
        t["nombre"] += 1
        t["ttc"] += r["total_ttc"]
        p = res["par_paiement"].setdefault(c.get("mode_paiement") or "ESPECES", 0)
        res["par_paiement"][c.get("mode_paiement") or "ESPECES"] = p + signe * r["total_ttc"]
        for g, v in c["totaux"]["par_groupe"].items():
            pg = res["par_groupe"].setdefault(g, {"ttc": 0, "ht": 0, "tva": 0})
            for k in ("ttc", "ht", "tva"):
                pg[k] += signe * v[k]
    return res


def export_ecritures_csv(conn) -> str:
    """Écritures proposées (à faire confirmer par un comptable) : 411 client, 70x produit, 443 TVA collectée."""
    sortie = io.StringIO()
    w = csv.writer(sortie, delimiter=";")
    w.writerow(["date", "piece", "compte", "libelle", "debit", "credit", "code_dgi"])
    for r in conn.execute("SELECT * FROM factures WHERE statut = 'CONFIRMEE' ORDER BY id"):
        c = json.loads(r["contenu"])
        t = c["totaux"]
        libelle = f"{'Facture' if r['type'] == 'FV' else 'Avoir'} {r['numero']} {c['client']['nom']}"
        d, cr = ("debit", "credit") if r["type"] == "FV" else ("credit", "debit")
        lignes = [("411", t["total_ttc"], d), ("701", t["total_ht"], cr), ("4431", t["total_tva"], cr)]
        for compte, montant, sens in lignes:
            if montant:
                w.writerow([r["horodatage_dgi"][:10], r["numero"], compte, libelle,
                            montant if sens == "debit" else "", montant if sens == "credit" else "", r["code_dgi"]])
    return sortie.getvalue()
