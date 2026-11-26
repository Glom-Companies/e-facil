"""Canaux de messagerie : WhatsApp (simulé), Telegram (simulé).

Le webhook reçoit les messages au format de l'API WhatsApp Cloud de Meta, signés par HMAC-SHA256
(en-tête X-Hub-Signature-256), comme en production. Le simulateur de téléphone de l'application
fabrique exactement ces messages, les signe et les passe au même point d'entrée : rien n'est contourné.
Les réponses du bot sont enregistrées dans `messages_canal` ; en production, elles partiraient par
l'API Graph (POST /{phone_number_id}/messages).

Sécurité :
- seuls les numéros habilités par l'administrateur, rattachés à un compte, sont traités ; les autres
  reçoivent un refus et la tentative est journalisée ;
- chaque action passe par les mêmes droits que l'interface (une vendeuse ne valide pas) ;
- un message déjà reçu (même identifiant) n'est jamais traité deux fois ;
- débit limité par numéro ; pièces jointes limitées en type et en taille, rangées sous un nom aléatoire.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import time
from pathlib import Path

from . import db as _db
from . import services as S
from . import voix
from . import brouillon as B
from .brouillon import montants_par_ligne
from .db import ecrire_parametre, journaliser, lire_parametre, maintenant, transaction
from .extraction import ErreurExtraction
from .moteur import format_fcfa

SECRET_APP = os.environ.get("WHATSAPP_APP_SECRET") or secrets.token_hex(32)
JETON_VERIFICATION = os.environ.get("WHATSAPP_VERIFY_TOKEN") or secrets.token_urlsafe(16)
TYPES_MEDIA = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "application/pdf": "pdf",
               "audio/ogg": "ogg", "audio/webm": "webm", "audio/mpeg": "mp3", "audio/mp4": "m4a", "audio/wav": "wav"}
TAILLE_MAX_MEDIA = 10 * 1024 * 1024
DEBIT_MAX = 20  # messages par minute et par numéro
_debits: dict[str, list[float]] = {}

AIDE = ("e-FACIL · facturer par message\n"
        "Envoyez la commande du client (texte, note vocale, photo ou PDF) : je vous pose les questions "
        "une par une jusqu'à la facture. Répondez par le numéro du choix, une quantité ou un nom.\n"
        "• STOP : mettre le dossier de côté · REPRENDRE 12 : y revenir · LISTE : brouillons en attente\n"
        "• BL 12 : 10 cartons livrés… ou ASF 12 : prestation réalisée… → rattacher la pièce\n"
        "Raccourcis : VOIR 12 · VALIDER 12 · ENVOYER 12 · PDF 12 · PAYE 12 50000 momo · ANNULER 12")

# Commande -> (code d'anomalie, choix) pour les décisions du responsable.
DECISIONS_CANAL = {
    "livre": ("ECART_COMMANDE_LIVRAISON", "facturer_livre"),
    "total": ("TOTAL_INCOHERENT", "total_recalcule"),
}
MODES_CANAL = {"momo": "MOBILEMONEY", "mobile": "MOBILEMONEY", "mtn": "MOBILEMONEY", "moov": "MOBILEMONEY",
               "cash": "ESPECES", "especes": "ESPECES", "espèces": "ESPECES", "cheque": "CHEQUES", "chèque": "CHEQUES",
               "virement": "VIREMENT", "carte": "CARTEBANCAIRE"}
# Anomalie -> commande proposée dans le résumé.
CONSEILS = {
    "ECART_COMMANDE_LIVRAISON": "LIVRE {d}", "REMISE_A_VALIDER": "REMISE {d} OUI ou NON",
    "PRIX_INHABITUEL": "PRIX {d} CATALOGUE ou PRIX {d} CITE raison", "TOTAL_INCOHERENT": "TOTAL {d}",
    "DOUBLON_PROBABLE": "DOUBLON {d} NON, ou ANNULER {d}", "CLIENT_INCONNU": "CLIENT {d} nom du client",
    "CLIENT_AMBIGU": "CLIENT {d} nom exact", "QUANTITE_MANQUANTE": "QTE {d} {l} quantité",
    "QUANTITE_INVALIDE": "QTE {d} {l} quantité", "ARTICLE_INCONNU": "RETIRER {d} {l} puis AJOUTER {d} quantité article",
}


# --- Numéros ----------------------------------------------------------------------------------

def normaliser_numero(numero: str) -> str:
    """« +229 01 90 00 00 11 » et « 2290190000011 » -> « 2290190000011 »."""
    chiffres = re.sub(r"\D", "", numero or "")
    return chiffres[2:] if chiffres.startswith("00") else chiffres


def affichage(numero: str) -> str:
    n = normaliser_numero(numero)
    return "+" + n[:3] + " " + " ".join(n[i:i + 2] for i in range(3, len(n), 2)) if len(n) > 3 else n


def config(conn) -> dict:
    return lire_parametre(conn, "canaux", None) or S.CANAUX_DEMO


def habilites(conn, plateforme: str = "whatsapp") -> list[dict]:
    """Numéros habilités avec le compte rattaché (nom, rôle)."""
    res = []
    for h in config(conn).get(plateforme, {}).get("habilites", []):
        u = conn.execute("SELECT id, login, nom, role FROM utilisateurs WHERE id = ?", (h["uid"],)).fetchone()
        if u:
            res.append({"numero": affichage(h["numero"]), "cle": normaliser_numero(h["numero"]), **dict(u)})
    return res


def utilisateur_du_numero(conn, numero: str, plateforme: str = "whatsapp") -> dict | None:
    cle = normaliser_numero(numero)
    h = next((h for h in habilites(conn, plateforme) if h["cle"] == cle), None)
    if not h:
        return None
    u = {k: h[k] for k in ("id", "login", "nom", "role")}
    u["mode_solo"] = bool(lire_parametre(conn, "mode_solo", False))
    return u


def enregistrer_habilitation(conn, admin: dict, numero: str, uid: str, plateforme: str = "whatsapp") -> None:
    S.exiger(admin, "parametres.ecrire")
    cle = normaliser_numero(numero)
    if not 8 <= len(cle) <= 15:
        raise S.Refus("Numéro invalide : indiquez l'indicatif, par exemple +229 01 90 00 00 11.")
    if not conn.execute("SELECT 1 FROM utilisateurs WHERE id = ?", (uid,)).fetchone():
        raise S.Refus("Compte introuvable.")
    cfg = config(conn)
    canal = cfg.setdefault(plateforme, {"habilites": []})
    canal["habilites"] = [h for h in canal.get("habilites", []) if normaliser_numero(h["numero"]) != cle]
    canal["habilites"].append({"numero": affichage(cle), "uid": uid})
    with transaction(conn):
        ecrire_parametre(conn, "canaux", cfg)
        journaliser(conn, admin["id"], "NUMERO_HABILITE", f"utilisateur:{uid}", {"plateforme": plateforme,
                                                                                "numero": affichage(cle)})


def retirer_habilitation(conn, admin: dict, numero: str, plateforme: str = "whatsapp") -> None:
    S.exiger(admin, "parametres.ecrire")
    cle = normaliser_numero(numero)
    cfg = config(conn)
    canal = cfg.setdefault(plateforme, {"habilites": []})
    canal["habilites"] = [h for h in canal.get("habilites", []) if normaliser_numero(h["numero"]) != cle]
    with transaction(conn):
        ecrire_parametre(conn, "canaux", cfg)
        journaliser(conn, admin["id"], "NUMERO_RETIRE", "canaux", {"plateforme": plateforme, "numero": affichage(cle)})


# --- Médias (équivalent de l'envoi de média à l'API Graph) -------------------------------------

def _dossier_media() -> Path:
    return _db.dossier_donnees("media_canal")


def deposer_media(octets: bytes, mime: str) -> str:
    mime = (mime or "").split(";")[0].strip().lower()
    if mime not in TYPES_MEDIA:
        raise S.Refus("Type de fichier non accepté (photo, PDF ou note vocale).")
    if not octets or len(octets) > TAILLE_MAX_MEDIA:
        raise S.Refus("Fichier vide ou trop lourd (10 Mo au plus).")
    media_id = secrets.token_hex(12)
    d = _dossier_media()
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{media_id}.{TYPES_MEDIA[mime]}").write_bytes(octets)
    return media_id


def lire_media(media_id: str) -> tuple[bytes, str] | None:
    if not re.fullmatch(r"[0-9a-f]{24}", media_id or ""):
        return None
    for mime, ext in TYPES_MEDIA.items():
        f = _dossier_media() / f"{media_id}.{ext}"
        if f.is_file():
            return f.read_bytes(), mime
    return None


# --- Webhook ----------------------------------------------------------------------------------

def signer(corps: bytes) -> str:
    return "sha256=" + hmac.new(SECRET_APP.encode(), corps, hashlib.sha256).hexdigest()


def recevoir(conn, corps: bytes, signature: str | None) -> int:
    """Point d'entrée du webhook. Vérifie la signature, puis traite chaque message. Renvoie le nombre traité."""
    if not signature or not hmac.compare_digest(signer(corps), signature):
        raise S.Refus("Signature du webhook invalide.")
    donnees = json.loads(corps)
    n = 0
    for entree in donnees.get("entry", []):
        for changement in entree.get("changes", []):
            for m in changement.get("value", {}).get("messages", []) or []:
                traiter(conn, "whatsapp", m)
                n += 1
    return n


def message_meta(numero: str, type_msg: str, texte: str = "", media_id: str | None = None, mime: str | None = None,
                 nom_fichier: str | None = None) -> dict:
    """Construit un message au format de l'API WhatsApp Cloud (ce que Meta envoie au webhook)."""
    m = {"from": normaliser_numero(numero), "id": "wamid." + secrets.token_hex(16), "timestamp": str(int(time.time())),
         "type": type_msg}
    if type_msg == "text":
        m["text"] = {"body": texte}
    elif type_msg in ("image", "audio", "document"):
        m[type_msg] = {"id": media_id, "mime_type": mime}
        if texte:
            m[type_msg]["caption"] = texte
        if nom_fichier:
            m[type_msg]["filename"] = nom_fichier
        if type_msg == "audio":
            m["audio"]["voice"] = True
    return {"object": "whatsapp_business_account",
            "entry": [{"id": "SIMULATION", "changes": [{"field": "messages", "value": {
                "messaging_product": "whatsapp", "metadata": {"display_phone_number": "SIMULATION"},
                "messages": [m]}}]}]}


# --- Bot --------------------------------------------------------------------------------------

def repondre(conn, plateforme: str, numero: str, texte: str, type_msg: str = "text",
             dossier_id: int | None = None, facture_id: int | None = None) -> None:
    with transaction(conn):
        conn.execute("INSERT INTO messages_canal (plateforme, numero, sens, type, texte, dossier_id, facture_id,"
                     " horodatage) VALUES (?,?,?,?,?,?,?,?)",
                     (plateforme, normaliser_numero(numero), "sortant", type_msg, texte, dossier_id, facture_id,
                      maintenant()))


def _trop_rapide(numero: str) -> bool:
    maintenant_s = time.time()
    fenetre = [t for t in _debits.get(numero, []) if maintenant_s - t < 60]
    fenetre.append(maintenant_s)
    _debits[numero] = fenetre
    return len(fenetre) > DEBIT_MAX


def traiter(conn, plateforme: str, m: dict) -> None:
    numero, mid, type_msg = normaliser_numero(m.get("from", "")), m.get("id"), m.get("type", "text")
    contenu = m.get(type_msg) or {}
    texte = (contenu.get("body") if type_msg == "text" else contenu.get("caption")) or ""
    with transaction(conn):
        if mid and conn.execute("SELECT 1 FROM messages_canal WHERE message_id = ?", (mid,)).fetchone():
            return  # message rejoué par la plateforme : déjà traité
        conn.execute("INSERT INTO messages_canal (message_id, plateforme, numero, sens, type, texte, media, horodatage)"
                     " VALUES (?,?,?,?,?,?,?,?)", (mid, plateforme, numero, "entrant", type_msg, texte[:4000],
                                                   contenu.get("id"), maintenant()))
    if _trop_rapide(numero):
        return
    u = utilisateur_du_numero(conn, numero, plateforme)
    if not u:
        with transaction(conn):
            journaliser(conn, "anonyme", "CANAL_REFUSE", f"numero:{affichage(numero)}", {"plateforme": plateforme})
        repondre(conn, plateforme, numero, "Ce numéro n'est pas autorisé à utiliser e-FACIL. "
                                           "Demandez à l'administrateur de votre entreprise de l'ajouter.")
        return
    try:
        _executer(conn, plateforme, numero, u, type_msg, texte, contenu)
    except (S.Refus, ErreurExtraction) as e:
        repondre(conn, plateforme, numero, str(e).replace("[quota] ", ""))


def _executer(conn, plateforme, numero, u, type_msg, texte, contenu) -> None:
    commande = texte.strip()
    if type_msg == "text":
        if re.fullmatch(r"(?i)(aide|help|menu|\?)", commande):
            repondre(conn, plateforme, numero, AIDE)
            return
        m = re.fullmatch(r"(?i)reprendre\s*n?°?\s*(\d+)", commande)
        if m:
            did = int(m.group(1))
            S.verifier_acces_dossier(conn, u, did)
            _annoncer(conn, plateforme, numero, did, "Dossier", suite=False)
            guider(conn, plateforme, numero, u, did)
            return
        m = re.fullmatch(r"(?i)liste", commande)
        if m:
            _liste(conn, plateforme, numero, u)
            return
        m = re.fullmatch(r"(?is)(voir|etat|état|client|qte|quantite|quantité|ajouter|retirer|livre|livré|total|remise"
                         r"|prix|doublon|paye|payé|paiement|pdf)\s*n?°?\s*(\d+)\s*(.*)", commande)
        if m:
            verbe, did, reste = m.group(1).lower(), int(m.group(2)), m.group(3).strip()
            S.verifier_acces_dossier(conn, u, did)
            _commande_dossier(conn, plateforme, numero, u, verbe, did, reste)
            return
        m = re.fullmatch(r"(?i)(valider|ok|annuler|envoyer)\s*n?°?\s*(\d+)", commande)
        if m:
            S.verifier_acces_dossier(conn, u, int(m.group(2)))
            {"valider": _valider, "ok": _valider, "annuler": _annuler, "envoyer": _envoyer}[m.group(1).lower()](
                conn, plateforme, numero, u, int(m.group(2)))
            return
        m = re.fullmatch(r"(?is)(?:bl|livraison|asf|attestation)\s*n?°?\s*(\d+)\s*[:\-]?\s*(.+)", commande)
        if m:
            did = int(m.group(1))
            S.verifier_acces_dossier(conn, u, did)
            d = S.dossier(conn, did)
            S.ajouter_livraison(conn, u, did, d["version"], m.group(2).strip(), S.extracteur_auto(False))
            _annoncer(conn, plateforme, numero, did, "Pièce d'exécution rattachée au dossier", suite=False)
            guider(conn, plateforme, numero, u, did)
            return
        session = _session(conn, plateforme, numero)
        if session.get("q") and _repondre_guide(conn, plateforme, numero, u, session, commande):
            return
    octets = mime = None
    if type_msg in ("audio", "image", "document"):
        media = lire_media(contenu.get("id", ""))
        if not media:
            raise S.Refus("Pièce jointe introuvable : renvoyez-la.")
        octets, mime = media
    S.exiger(u, "dossier.ecrire")
    if type_msg == "audio":
        transcrit, moteur = voix.transcrire(octets, mime)
        did = S.creer_dossier(conn, u, "WHATSAPP", transcrit, None, S.extracteur_auto(False))
        S.enregistrer_piece(did, octets, mime)
        repondre(conn, plateforme, numero, f"Note vocale transcrite : « {transcrit} »")
    elif type_msg in ("image", "document"):
        did = S.creer_dossier(conn, u, "WHATSAPP", commande, None, S.extracteur_auto(True), octets, mime,
                              contenu.get("filename") or ("photo" if type_msg == "image" else "document"))
    else:
        if len(commande) < 3:
            repondre(conn, plateforme, numero, AIDE)
            return
        did = S.creer_dossier(conn, u, "WHATSAPP", commande, None, S.extracteur_auto(False))
    with transaction(conn):
        conn.execute("UPDATE messages_canal SET dossier_id = ? WHERE id = (SELECT MAX(id) FROM messages_canal "
                     "WHERE numero = ? AND sens = 'entrant')", (did, numero))
    _annoncer(conn, plateforme, numero, did, "Brouillon", suite=False)
    guider(conn, plateforme, numero, u, did)  # questions une par une, puis le responsable est prévenu


# --- Mode guidé : le bot pose les questions une par une jusqu'à la facture ---------------------

MODES_CHOIX = [("MOBILEMONEY", "Mobile money"), ("ESPECES", "Espèces"), ("CHEQUES", "Chèque"),
               ("VIREMENT", "Virement"), ("CARTEBANCAIRE", "Carte bancaire")]
OUI = {"1", "oui", "o", "ok", "yes", "d'accord", "dac"}
NON = {"2", "non", "n", "no"}


def _cle_session(plateforme, numero) -> str:
    return f"session_canal:{plateforme}:{normaliser_numero(numero)}"


def _session(conn, plateforme, numero) -> dict:
    return lire_parametre(conn, _cle_session(plateforme, numero), None) or {}


def _memoriser_session(conn, plateforme, numero, session: dict | None) -> None:
    with transaction(conn):
        if session:
            ecrire_parametre(conn, _cle_session(plateforme, numero), session)
        else:
            conn.execute("DELETE FROM parametres WHERE cle = ?", (_cle_session(plateforme, numero),))


def _peut(u, droit) -> bool:
    try:
        S.exiger(u, droit)
        return True
    except S.Refus:
        return False


def _choix(texte: str, n: int) -> int | None:
    """« 1 », « 1. », « oui » (= 1), « non » (= 2) -> numéro du choix, ou None."""
    t = texte.strip().lower().rstrip(".)")
    if t in OUI and n >= 1:
        return 1
    if t in NON and n >= 2:
        return 2
    return int(t) if t.isdigit() and 1 <= int(t) <= n else None


def _poser(conn, plateforme, numero, u, did, question: dict, texte: str) -> None:
    _memoriser_session(conn, plateforme, numero, {"did": did, "q": question})
    repondre(conn, plateforme, numero, texte, dossier_id=did)


def guider(conn, plateforme, numero, u, did) -> None:
    """Pose la prochaine question du dossier pour cette personne, ou propose l'étape suivante."""
    d = S.dossier(conn, did)
    arts = {a["id"]: a for a in S.articles(conn)}
    lignes = {l["cle"]: l for l in d["brouillon"]["lignes"]}
    nom_ligne = lambda cle: (arts.get((lignes.get(cle) or {}).get("article_id"), {}).get("designation")  # noqa: E731
                             or (lignes.get(cle) or {}).get("designation_citee") or "cet article")
    decideur = _peut(u, "dossier.decider")

    if d["statut"] == "VALIDE" and d.get("facture_id"):
        f = S.facture(conn, d["facture_id"])
        if f["statut"] != "CONFIRMEE":
            _memoriser_session(conn, plateforme, numero, None)
            return
        options = ["Envoyer la facture au client"]
        if f["reste_a_payer"] > 0 and _peut(u, "paiement.enregistrer"):
            options.append(f"Enregistrer un paiement (reste {format_fcfa(f['reste_a_payer'])})")
        options.append("Terminer")
        _poser(conn, plateforme, numero, u, did, {"type": "apres", "options": options},
               f"Facture {f['numero']} · que faire ?\n" + "\n".join(f"{i}. {o}" for i, o in enumerate(options, 1)))
        return
    if d["statut"] != "BROUILLON":
        _memoriser_session(conn, plateforme, numero, None)
        return

    for a in d["anomalies"]:
        if not a["bloquante"] or a["resolue"]:
            continue
        code, cle = a["code"], a.get("ligne")
        if a["cle_decision"] and not decideur:
            continue  # décision du responsable : on passe aux corrections qui reviennent à la vendeuse
        if code == "CLIENT_AMBIGU":
            cands = d["brouillon"]["client"].get("candidats") or []
            noms = [(S.client(conn, c) or {}).get("nom", c) for c in cands]
            _poser(conn, plateforme, numero, u, did, {"type": "client", "candidats": cands},
                   "Quel client ?\n" + "\n".join(f"{i}. {n}" for i, n in enumerate(noms, 1))
                   + "\nRépondez par le numéro, ou par un autre nom.")
            return
        if code == "CLIENT_INCONNU":
            cite = d["brouillon"]["client"].get("nom_cite")
            _poser(conn, plateforme, numero, u, did, {"type": "client", "candidats": []},
                   (f"Je ne connais pas « {cite} ». " if cite else "") + "Quel est le client ? Répondez par son nom.")
            return
        if code in ("QUANTITE_MANQUANTE", "QUANTITE_INVALIDE") and cle:
            _poser(conn, plateforme, numero, u, did, {"type": "quantite", "ligne": cle},
                   f"Quelle quantité pour « {nom_ligne(cle)} » ? Répondez par un nombre (0 pour retirer la ligne).")
            return
        if code == "ARTICLE_INCONNU":
            if cle:
                cite = (lignes.get(cle) or {}).get("designation_citee") or "cet article"
                _poser(conn, plateforme, numero, u, did, {"type": "article", "ligne": cle},
                       f"« {cite} » n'est pas dans le catalogue. Répondez par le nom de l'article, ou 0 pour retirer la ligne.")
            else:
                _poser(conn, plateforme, numero, u, did, {"type": "ajout"},
                       "Aucun article reconnu. Répondez par la quantité et l'article, par exemple : 5 sacs de riz.")
            return
        if code == "ECART_COMMANDE_LIVRAISON":
            l = lignes.get(cle) or {}
            _poser(conn, plateforme, numero, u, did, {"type": "decision", "cle": a["cle_decision"],
                                                      "choix": ["facturer_livre", None]},
                   f"« {nom_ligne(cle)} » : {l.get('quantite_commandee')} commandé(s), {l.get('quantite_livree')} livré(s).\n"
                   f"1. Facturer le livré ({l.get('quantite_livree')})\n2. Attendre le reste de la livraison")
            return
        if code == "REMISE_A_VALIDER":
            _poser(conn, plateforme, numero, u, did, {"type": "decision", "cle": a["cle_decision"],
                                                      "choix": ["accepter", "refuser"]},
                   f"{a['message']}\n1. Accorder la remise\n2. Refuser")
            return
        if code == "PRIX_INHABITUEL":
            _poser(conn, plateforme, numero, u, did, {"type": "decision", "cle": a["cle_decision"],
                                                      "choix": ["prix_catalogue", "prix_cite"]},
                   f"{a['message']}\n1. Garder le prix du catalogue\n2. Appliquer le prix cité (je vous demanderai pourquoi)")
            return
        if code == "TOTAL_INCOHERENT":
            _poser(conn, plateforme, numero, u, did, {"type": "decision", "cle": a["cle_decision"],
                                                      "choix": ["total_recalcule", None]},
                   f"{a['message']}\n1. Facturer le total recalculé\n2. Plus tard")
            return
        if code == "DOUBLON_PROBABLE":
            _poser(conn, plateforme, numero, u, did, {"type": "doublon", "cle": a["cle_decision"]},
                   f"{a['message']}\n1. Ce n'est pas un doublon, on continue\n2. C'est un doublon : supprimer ce brouillon")
            return

    restantes = [a for a in d["anomalies"] if a["bloquante"] and not a["resolue"]]
    if restantes:  # il ne reste que des décisions du responsable
        _memoriser_session(conn, plateforme, numero, None)
        repondre(conn, plateforme, numero, "C'est tout pour vous. Le responsable tranchera : "
                 + ", ".join(a["titre"].lower() for a in restantes) + ". Il est prévenu.", dossier_id=did)
        _prevenir_responsables(conn, plateforme, numero, u, did)
        return
    if _peut(u, "facture.valider"):
        total = format_fcfa(d["totaux"]["net_a_payer"]) if d.get("totaux") else "à calculer"
        _poser(conn, plateforme, numero, u, did, {"type": "valider"},
               f"Tout est vérifié. Net à payer : {total}.\n1. Valider et émettre la facture\n2. Plus tard")
        return
    _memoriser_session(conn, plateforme, numero, None)
    repondre(conn, plateforme, numero, "Le brouillon est complet. Le responsable va le valider : il est prévenu.",
             dossier_id=did)
    _prevenir_responsables(conn, plateforme, numero, u, did)


def _prevenir_responsables(conn, plateforme, numero, u, did) -> None:
    """Prévient les responsables habilités et leur pose directement la première question du dossier."""
    for h in habilites(conn, plateforme):
        if h["role"] != "responsable" or h["cle"] == normaliser_numero(numero):
            continue
        if _session(conn, plateforme, h["cle"]).get("q"):  # déjà en train de traiter un autre dossier
            repondre(conn, plateforme, h["cle"], f"Brouillon n° {did} préparé par {u['nom']} : REPRENDRE {did} "
                     "quand vous aurez fini.", dossier_id=did)
            continue
        repondre(conn, plateforme, h["cle"], f"Brouillon n° {did} préparé par {u['nom']}.\n" + _resume(conn, did),
                 dossier_id=did)
        responsable = utilisateur_du_numero(conn, h["cle"], plateforme)
        if responsable:
            guider(conn, plateforme, h["cle"], responsable, did)


def _repondre_guide(conn, plateforme, numero, u, session, texte) -> bool:
    """Traite la réponse à la question en cours. Renvoie False si le message n'est pas une réponse."""
    did, q = session["did"], session["q"]
    t = texte.strip()
    if re.fullmatch(r"(?i)stop|pause|plus tard|annuler", t):
        _memoriser_session(conn, plateforme, numero, None)
        repondre(conn, plateforme, numero, f"Dossier n° {did} mis de côté. REPRENDRE {did} pour y revenir.", dossier_id=did)
        return True
    S.verifier_acces_dossier(conn, u, did)
    d = S.dossier(conn, did)
    typ = q["type"]
    nombre_choix = {"decision": 2, "doublon": 2, "valider": 2, "apres": len(q.get("options", [])),
                    "mode": len(MODES_CHOIX)}.get(typ)
    if nombre_choix and _choix(t, nombre_choix) is None:
        if len(t) > 25:  # un long message est une nouvelle commande, pas une réponse
            _memoriser_session(conn, plateforme, numero, None)
            repondre(conn, plateforme, numero, f"Je mets le dossier n° {did} de côté (REPRENDRE {did}) et j'ouvre une nouvelle commande.")
            return False
        repondre(conn, plateforme, numero, f"Répondez par un chiffre de 1 à {nombre_choix}, ou STOP.", dossier_id=did)
        return True

    if typ == "client":
        cands = q.get("candidats") or []
        n = _choix(t, len(cands)) if cands else None
        if cands and not n and t.isdigit():
            repondre(conn, plateforme, numero, f"Répondez par un chiffre de 1 à {len(cands)}, ou par un nom.", dossier_id=did)
            return True
        if n:
            cid = cands[n - 1]
        else:
            trouves, _ = B.trouver_clients(t, S.clients(conn))
            if len(trouves) != 1:
                noms = [(S.client(conn, c) or {}).get("nom", c) for c in trouves]
                if trouves:
                    _poser(conn, plateforme, numero, u, did, {"type": "client", "candidats": trouves},
                           "Plusieurs clients correspondent :\n" + "\n".join(f"{i}. {n}" for i, n in enumerate(noms, 1)))
                else:
                    repondre(conn, plateforme, numero, f"Aucun client « {t} ». Réessayez avec un autre nom, "
                             "ou créez sa fiche dans e-FACIL puis REPRENDRE " + str(did) + ".", dossier_id=did)
                return True
            cid = trouves[0]
        S.corriger(conn, u, did, d["version"], {"client_id": cid})
        repondre(conn, plateforme, numero, f"Client : {(S.client(conn, cid) or {}).get('nom')} ✓", dossier_id=did)
    elif typ == "quantite":
        q_txt = t.replace(",", ".")
        if not re.fullmatch(r"\d+(\.\d+)?", q_txt):
            repondre(conn, plateforme, numero, "Répondez par un nombre, par exemple 5 ou 2,5.", dossier_id=did)
            return True
        champ = {f"{q['ligne']}:supprimer": "1"} if float(q_txt) == 0 else {f"{q['ligne']}:quantite_commandee": q_txt}
        S.corriger(conn, u, did, d["version"], champ)
        repondre(conn, plateforme, numero, "Ligne retirée ✓" if float(q_txt) == 0 else f"Quantité : {t} ✓", dossier_id=did)
    elif typ == "article":
        if t == "0":
            S.corriger(conn, u, did, d["version"], {f"{q['ligne']}:supprimer": "1"})
            repondre(conn, plateforme, numero, "Ligne retirée ✓", dossier_id=did)
        else:
            aid, _ = B.trouver_article(t, S.articles(conn))
            if not aid:
                repondre(conn, plateforme, numero, f"« {t} » n'est pas dans le catalogue non plus. Autre nom, ou 0 pour retirer.",
                         dossier_id=did)
                return True
            S.corriger(conn, u, did, d["version"], {f"{q['ligne']}:article_id": aid})
            designation = next(a["designation"] for a in S.articles(conn) if a["id"] == aid)
            repondre(conn, plateforme, numero, f"Article : {designation} ✓", dossier_id=did)
    elif typ == "ajout":
        m = re.fullmatch(r"([\d.,]+)\s+(.+)", t)
        aid = B.trouver_article(m.group(2), S.articles(conn))[0] if m else None
        if not aid:
            repondre(conn, plateforme, numero, "Je n'ai pas compris. Exemple : 5 sacs de riz.", dossier_id=did)
            return True
        S.corriger(conn, u, did, d["version"], {"nouvel_article": aid, "nouvelle_quantite": m.group(1)})
        repondre(conn, plateforme, numero, "Ligne ajoutée ✓", dossier_id=did)
    elif typ == "decision":
        choix = q["choix"][_choix(t, 2) - 1]
        if choix is None:  # « attendre » ou « plus tard »
            _memoriser_session(conn, plateforme, numero, None)
            repondre(conn, plateforme, numero, f"D'accord, le dossier n° {did} attend. Envoyez BL {did} : … à la suite "
                     f"de la livraison, ou REPRENDRE {did}.", dossier_id=did)
            return True
        if choix == "prix_cite":
            _poser(conn, plateforme, numero, u, did, {"type": "raison_prix", "cle": q["cle"]},
                   "Pourquoi le prix cité s'applique-t-il ? (quelques mots, notés au journal)")
            return True
        S.decider(conn, u, did, d["version"], q["cle"], choix)
        repondre(conn, plateforme, numero, "Décision enregistrée ✓", dossier_id=did)
    elif typ == "raison_prix":
        S.decider(conn, u, did, d["version"], q["cle"], "prix_cite", t)
        repondre(conn, plateforme, numero, "Prix cité appliqué, raison notée au journal ✓", dossier_id=did)
    elif typ == "doublon":
        if _choix(t, 2) == 2:
            _memoriser_session(conn, plateforme, numero, None)
            _annuler(conn, plateforme, numero, u, did)
            return True
        S.decider(conn, u, did, d["version"], q["cle"], "pas_un_doublon")
        repondre(conn, plateforme, numero, "Noté : ce n'est pas un doublon ✓", dossier_id=did)
    elif typ == "valider":
        if _choix(t, 2) == 2:
            _memoriser_session(conn, plateforme, numero, None)
            repondre(conn, plateforme, numero, f"D'accord. VALIDER {did} quand vous voulez.", dossier_id=did)
            return True
        _valider(conn, plateforme, numero, u, did)  # pose elle-même la question suivante
        return True
    elif typ == "apres":
        option = q["options"][_choix(t, len(q["options"])) - 1]
        if option.startswith("Envoyer"):
            _envoyer(conn, plateforme, numero, u, did)
        elif option.startswith("Enregistrer"):
            f = S.facture(conn, S.dossier(conn, did)["facture_id"])
            _poser(conn, plateforme, numero, u, did, {"type": "montant"},
                   f"Combien le client a-t-il payé ? Répondez par un montant, ou TOUT ({format_fcfa(f['reste_a_payer'])}).")
            return True
        else:
            _memoriser_session(conn, plateforme, numero, None)
            repondre(conn, plateforme, numero, f"Dossier n° {did} terminé ✓", dossier_id=did)
            return True
    elif typ == "montant":
        f = S.facture(conn, d["facture_id"])
        if t.lower() in ("tout", "tous", "total", "la totalité"):
            montant = f["reste_a_payer"]
        else:
            chiffres = re.sub(r"\D", "", t)
            if not chiffres or int(chiffres) <= 0:
                repondre(conn, plateforme, numero, "Répondez par un montant (ex. 50000) ou TOUT.", dossier_id=did)
                return True
            montant = int(chiffres)
        _poser(conn, plateforme, numero, u, did, {"type": "mode", "montant": montant},
               f"Paiement de {format_fcfa(montant)}, par quel moyen ?\n"
               + "\n".join(f"{i}. {lib}" for i, (_, lib) in enumerate(MODES_CHOIX, 1)))
        return True
    elif typ == "mode":
        mode = MODES_CHOIX[_choix(t, len(MODES_CHOIX)) - 1][0]
        _payer(conn, plateforme, numero, u, did, f"{q['montant']} {next(k for k, v in MODES_CANAL.items() if v == mode)}")
    guider(conn, plateforme, numero, u, did)
    return True


def _commande_dossier(conn, plateforme, numero, u, verbe, did, reste) -> None:
    """Corriger, trancher, consulter, payer : tout le parcours d'un dossier depuis la messagerie."""
    verbe = verbe.replace("é", "e").replace("quantite", "qte")
    if verbe in ("voir", "etat"):
        _annoncer(conn, plateforme, numero, did, "Dossier")
        return
    if verbe in ("paye", "paiement"):
        _payer(conn, plateforme, numero, u, did, reste)
        return
    if verbe == "pdf":
        d = S.dossier(conn, did)
        if not d.get("facture_id"):
            raise S.Refus(f"Le dossier n° {did} n'a pas encore de facture.")
        f = S.facture(conn, d["facture_id"])
        repondre(conn, plateforme, numero, f"{f['numero']}.pdf", type_msg="document", dossier_id=did, facture_id=f["id"])
        return
    d = S.dossier(conn, did)
    if d["statut"] != "BROUILLON":
        raise S.Refus(f"Le dossier n° {did} n'est plus un brouillon : il ne se modifie plus.")
    br, lignes = d["brouillon"], d["brouillon"]["lignes"]

    def ligne(numero_ligne: str) -> dict:
        try:
            return lignes[int(numero_ligne.lstrip("lL")) - 1]
        except (ValueError, IndexError):
            raise S.Refus(f"Ligne introuvable. Le dossier n° {did} a {len(lignes)} ligne(s) : VOIR {did}.")

    if verbe == "client":
        if not reste:
            raise S.Refus(f"Indiquez le client : CLIENT {did} Dossou.")
        candidats, _ = B.trouver_clients(reste, S.clients(conn))
        if not candidats:
            raise S.Refus(f"Aucun client ne correspond à « {reste} ». Créez sa fiche dans e-FACIL.")
        if len(candidats) > 1:
            noms = "\n".join("• " + (S.client(conn, c) or {}).get("nom", c) for c in candidats)
            raise S.Refus(f"Plusieurs clients correspondent :\n{noms}\nPrécisez : CLIENT {did} nom exact.")
        S.corriger(conn, u, did, d["version"], {"client_id": candidats[0]})
        titre = "Client corrigé, dossier"
    elif verbe == "qte":
        m = re.fullmatch(r"[lL]?(\d+)\s+([\d.,]+)", reste)
        if not m:
            raise S.Refus(f"Écrivez : QTE {did} numéro-de-ligne quantité, par exemple QTE {did} 2 5.")
        S.corriger(conn, u, did, d["version"], {f"{ligne(m.group(1))['cle']}:quantite_commandee": m.group(2)})
        titre = "Quantité corrigée, dossier"
    elif verbe == "retirer":
        S.corriger(conn, u, did, d["version"], {f"{ligne(reste)['cle']}:supprimer": "1"})
        titre = "Ligne retirée, dossier"
    elif verbe == "ajouter":
        m = re.fullmatch(r"([\d.,]+)\s+(.+)", reste)
        if not m:
            raise S.Refus(f"Écrivez : AJOUTER {did} quantité article, par exemple AJOUTER {did} 3 riz.")
        aid, _ = B.trouver_article(m.group(2), S.articles(conn))
        if not aid:
            raise S.Refus(f"Article « {m.group(2)} » introuvable dans le catalogue.")
        S.corriger(conn, u, did, d["version"], {"nouvel_article": aid, "nouvelle_quantite": m.group(1)})
        titre = "Ligne ajoutée, dossier"
    else:
        _trancher(conn, u, did, verbe, reste)
        titre = "Décision enregistrée, dossier"
    _annoncer(conn, plateforme, numero, did, titre)


def _trancher(conn, u, did, verbe, reste) -> None:
    """Décisions du responsable, avec les mêmes droits et le même journal que l'interface."""
    reponse = reste.lower()
    if verbe in DECISIONS_CANAL:
        code, choix = DECISIONS_CANAL[verbe]
        justification = ""
    elif verbe == "remise":
        if reponse not in ("oui", "non"):
            raise S.Refus(f"Répondez REMISE {did} OUI pour l'accorder, ou REMISE {did} NON.")
        code, choix, justification = "REMISE_A_VALIDER", "accepter" if reponse == "oui" else "refuser", ""
    elif verbe == "prix":
        if reponse.startswith("catalogue"):
            code, choix, justification = "PRIX_INHABITUEL", "prix_catalogue", ""
        elif reponse.startswith(("cite", "cité")):
            code, choix, justification = "PRIX_INHABITUEL", "prix_cite", reste.split(None, 1)[1] if " " in reste else ""
        else:
            raise S.Refus(f"Répondez PRIX {did} CATALOGUE, ou PRIX {did} CITE suivi de la raison.")
    elif verbe == "doublon":
        if reponse != "non":
            raise S.Refus(f"Si ce n'est pas un doublon : DOUBLON {did} NON. Sinon : ANNULER {did}.")
        code, choix, justification = "DOUBLON_PROBABLE", "pas_un_doublon", ""
    else:
        raise S.Refus("Commande inconnue. Écrivez AIDE.")
    tranchees = 0
    for a in S.dossier(conn, did)["anomalies"]:
        if a["code"] == code and a["cle_decision"] and not a["resolue"]:
            d = S.dossier(conn, did)  # la version change après chaque décision
            S.decider(conn, u, did, d["version"], a["cle_decision"], choix, justification)
            tranchees += 1
    if not tranchees:
        raise S.Refus(f"Rien à trancher de ce type sur le dossier n° {did}. Écrivez VOIR {did}.")


def _payer(conn, plateforme, numero, u, did, reste) -> None:
    d = S.dossier(conn, did)
    if not d.get("facture_id"):
        raise S.Refus(f"Le dossier n° {did} n'a pas encore de facture émise.")
    f = S.facture(conn, d["facture_id"])
    mode = f["contenu"].get("mode_paiement") or "ESPECES"
    for mot in reste.lower().split():
        if mot in MODES_CANAL:
            mode = MODES_CANAL[mot]
    # « 50 000 », « 50.000 », « 50000 F » : un seul nombre, séparateurs de milliers ignorés.
    m = re.search(r"\d[\d\s.\u00a0\u202f]*", reste)
    montant = int(re.sub(r"\D", "", m.group())) if m else f["reste_a_payer"]
    if montant <= 0:
        raise S.Refus(f"Montant illisible. Écrivez par exemple PAYE {did} 50000 momo.")
    S.enregistrer_paiement(conn, u, f["id"], montant, mode, "WhatsApp", cle_idem=None)
    f = S.facture(conn, f["id"])
    recu = conn.execute("SELECT recu_numero FROM paiements WHERE facture_id = ? ORDER BY id DESC LIMIT 1",
                        (f["id"],)).fetchone()[0]
    suite = "Facture soldée." if f["reste_a_payer"] <= 0 else f"Reste à payer : {format_fcfa(f['reste_a_payer'])}."
    repondre(conn, plateforme, numero, f"Paiement de {format_fcfa(montant)} enregistré sur {f['numero']} (simulé).\n"
             f"Reçu {recu}. {suite}", dossier_id=did, facture_id=f["id"])


def _liste(conn, plateforme, numero, u) -> None:
    lignes = []
    for r in conn.execute("SELECT id FROM dossiers WHERE statut = 'BROUILLON' ORDER BY id DESC LIMIT 10").fetchall():
        try:
            S.verifier_acces_dossier(conn, u, r["id"])
        except S.Refus:
            continue
        d = S.dossier(conn, r["id"])
        nom = (S.client(conn, d["brouillon"]["client"].get("id")) or {}).get("nom") or "client à choisir"
        n = sum(1 for a in d["anomalies"] if a["bloquante"] and not a["resolue"])
        lignes.append(f"• n° {r['id']} · {nom} · " + (f"{n} à vérifier" if n else "prêt à valider"))
    repondre(conn, plateforme, numero, "Brouillons en attente :\n" + "\n".join(lignes) + "\nDétail : VOIR n°"
             if lignes else "Aucun brouillon en attente.")


def _resume(conn, did: int, conseils: bool = True) -> str:
    d = S.dossier(conn, did)
    br = d["brouillon"]
    arts = {a["id"]: a for a in S.articles(conn)}
    client = (S.client(conn, br["client"].get("id")) or {}).get("nom") or br["client"].get("nom_cite") or "client à choisir"
    lignes = [client]
    montants = montants_par_ligne(br, S.articles(conn)) if d.get("totaux") else {}
    numeros_ligne = {}
    for i, l in enumerate(br["lignes"], start=1):
        numeros_ligne[l.get("cle")] = i
        nom = arts.get(l.get("article_id"), {}).get("designation") or l.get("designation_citee") or "article à choisir"
        q = l.get("quantite_livree") if l.get("quantite_livree") is not None else l.get("quantite_commandee")
        m = montants.get(l.get("cle"))
        lignes.append(f"{i}. {q if q is not None else '?'} × {nom}" + (f" = {format_fcfa(m)}" if m is not None else ""))
    if d.get("totaux"):
        lignes.append(f"Total à payer : {format_fcfa(d['totaux']['net_a_payer'])}")
    a_trancher = [a for a in d["anomalies"] if a["bloquante"] and not a["resolue"]]
    if a_trancher:
        lignes.append(f"À vérifier ({len(a_trancher)}) :")
        for a in a_trancher:
            conseil = CONSEILS.get(a["code"], "à corriger dans e-FACIL").format(d=did, l=numeros_ligne.get(a.get("ligne"), "n°"))
            lignes.append(f"⚠ {a['titre']}" + (f" → {conseil}" if conseils else ""))
    return "\n".join(lignes)


def _annoncer(conn, plateforme, numero, did, titre, suite: bool = True) -> None:
    """Résumé du dossier et prochaine étape du parcours, selon son état et le rôle de la personne."""
    u = utilisateur_du_numero(conn, numero, plateforme) or {}
    decideur = u.get("role") == "responsable" or u.get("mode_solo")
    d = S.dossier(conn, did)
    if d["statut"] == "VALIDE" and d.get("facture_id"):
        f = S.facture(conn, d["facture_id"])
        prochaine = (f"Facture {f['numero']} · reste à payer {format_fcfa(f['reste_a_payer'])}.\n"
                 f"ENVOYER {did} · PAYE {did} montant mode · PDF {did}")
    elif d["statut"] != "BROUILLON":
        prochaine = "Ce dossier n'est plus modifiable."
    elif any(a["bloquante"] and not a["resolue"] for a in d["anomalies"]):
        prochaine = ("Réglez les points ci-dessus, puis VALIDER " + str(did) + "." if decideur
                 else "Corrigez ce qui vous revient ; un responsable tranchera le reste.")
    else:
        prochaine = f"Tout est prêt : VALIDER {did}" if decideur else "Prêt : un responsable va le valider."
    texte = f"{titre} n° {did}\n" + _resume(conn, did, conseils=suite) + ("\n" + prochaine if suite else "")
    repondre(conn, plateforme, numero, texte, dossier_id=did)


def _valider(conn, plateforme, numero, u, did) -> None:
    d = S.dossier(conn, did)
    if d["statut"] == "VALIDE" and d.get("facture_id"):
        fid = d["facture_id"]
    else:
        bloquantes = [a["titre"] for a in d["anomalies"] if a["bloquante"] and not a["resolue"]]
        if bloquantes:
            raise S.Refus(f"Validation impossible, il reste à vérifier :\n{_resume(conn, did)}")
        fid = S.valider(conn, u, did, d["version"], cle_idem=f"canal-valider:{did}")
    res = S.emettre(conn, u, fid, cle_idem=f"canal-emettre:{fid}")
    f = S.facture(conn, fid)
    texte = (f"Facture {f['numero']} validée et émise (DGI simulée).\n"
             f"Net à payer : {format_fcfa(f['net_a_payer'])}\nCode DGI : {f.get('code_dgi') or res.get('statut')}\n"
             f"Pour l'envoyer au client : ENVOYER {did}\nPour un paiement : PAYE {did} montant mode")
    repondre(conn, plateforme, numero, texte, dossier_id=did, facture_id=fid)
    repondre(conn, plateforme, numero, f"{f['numero']}.pdf", type_msg="document", dossier_id=did, facture_id=fid)
    createur = conn.execute("SELECT cree_par FROM dossiers WHERE id = ?", (did,)).fetchone()
    for h in habilites(conn, plateforme):
        if createur and h["id"] == createur["cree_par"] and h["cle"] != normaliser_numero(numero):
            repondre(conn, plateforme, h["cle"], f"Votre brouillon n° {did} est validé : facture {f['numero']}.",
                     dossier_id=did, facture_id=fid)
            repondre(conn, plateforme, h["cle"], f"{f['numero']}.pdf", type_msg="document", dossier_id=did, facture_id=fid)
    guider(conn, plateforme, numero, u, did)


def _annuler(conn, plateforme, numero, u, did) -> None:
    d = S.dossier(conn, did)
    S.supprimer_dossier(conn, u, did, d["version"])
    repondre(conn, plateforme, numero, f"Brouillon n° {did} supprimé.", dossier_id=did)


def _envoyer(conn, plateforme, numero, u, did) -> None:
    d = S.dossier(conn, did)
    if not d.get("facture_id"):
        raise S.Refus(f"Le dossier n° {did} n'a pas encore de facture validée.")
    f = S.facture(conn, d["facture_id"])
    c = S.client(conn, f["contenu"]["client"].get("id")) or {}
    if not c.get("telephone"):
        raise S.Refus("Le client n'a pas de numéro enregistré.")
    S.envoyer_facture(conn, u, f["id"], "WHATSAPP", c["telephone"])
    repondre(conn, plateforme, numero, f"Facture {f['numero']} envoyée à {c['nom']} ({c['telephone']}), simulé.",
             dossier_id=did, facture_id=f["id"])


def conversation(conn, numero: str, plateforme: str = "whatsapp", limite: int = 80) -> list[dict]:
    lignes = conn.execute("SELECT * FROM messages_canal WHERE plateforme = ? AND numero = ? ORDER BY id DESC LIMIT ?",
                          (plateforme, normaliser_numero(numero), limite)).fetchall()
    return [dict(r) for r in reversed(lignes)]
