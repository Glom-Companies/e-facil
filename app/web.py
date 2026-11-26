"""Interface web (FastAPI + Jinja2). Toutes les règles sont appliquées par app.services."""
from __future__ import annotations

import base64
from datetime import date
import json
import os
import secrets
import uuid
from pathlib import Path

from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape
from starlette.middleware.sessions import SessionMiddleware

from . import services as S
from .brouillon import LIBELLES, montants_par_ligne
from .db import ecrire_parametre, lire_parametre, transaction, verifier_journal, journaliser
from .extraction import EXTRACTEURS, ia_disponibles
from .moteur import format_fcfa
from .pdf import LIBELLES_PAIEMENT, generer
from .texte import localiser

ICI = Path(__file__).resolve().parent
RACINE = ICI.parent


def _charger_env() -> None:
    env = RACINE / ".env"
    if env.exists():
        for ligne in env.read_text(encoding="utf-8").splitlines():
            if "=" in ligne and not ligne.lstrip().startswith("#"):
                cle, val = ligne.split("=", 1)
                os.environ.setdefault(cle.strip(), val.strip())


_charger_env()

app = FastAPI(title="e-FACIL - prototype BillGenius, BWAI'2026", docs_url=None, redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SECRET_SESSION") or secrets.token_hex(32),
                   same_site="strict", max_age=8 * 3600)
app.mount("/static", StaticFiles(directory=ICI / "static"), name="static")
modeles = Jinja2Templates(directory=ICI / "templates")

ROLES = {"vendeur": "Vendeur", "responsable": "Responsable", "comptable": "Comptable", "admin": "Administrateur"}
STATUTS = {"BROUILLON": "Brouillon", "VALIDE": "Validé", "SUPPRIME": "Supprimé", "VALIDEE": "Validée",
           "EN_ATTENTE_DGI": "En attente DGI", "CONFIRMEE": "Confirmée", "ANNULEE": "Annulée"}
CANAUX = {"WHATSAPP": "WhatsApp", "SMS": "SMS", "EMAIL": "E-mail", "VOCAL_TRANSCRIT": "Note vocale transcrite",
          "PAPIER": "Papier ou photo", "AUTRE": "Autre"}
AIDE = {
    "TTC": "Toutes taxes comprises : le prix que paie le client.",
    "HT": "Hors taxes : le prix sans la TVA.",
    "TVA": "Taxe sur la valeur ajoutée, 18 % au Bénin. Elle est déjà comprise dans le prix TTC.",
    "AIB": "Acompte sur impôt : certains clients retiennent 1 % ou 5 % du montant hors taxes et le versent aux impôts. "
           "Ils vous paient donc un peu moins : c'est le « net à payer ».",
    "groupe": "Catégorie fiscale de l'article, réglée une fois par la comptable : A exonéré, B TVA 18 %, "
              "C exportation, E petite entreprise (TPS).",
    "IFU": "Identifiant fiscal unique, 13 chiffres.",
    "avoir": "Document qui annule ou réduit une facture déjà émise. Une facture validée ne se modifie jamais.",
    "proforma": "Document informatif, avant la vente. Il n'a aucune valeur comptable ni fiscale.",
}


def fcfa(n):
    return "—" if n is None else Markup(escape(format_fcfa(int(n))))


def date_fr(iso):
    if not iso:
        return ""
    return f"{iso[8:10]}/{iso[5:7]}/{iso[0:4]} {iso[11:16]}".strip()


def aide(terme, texte=None):
    return Markup(f'<span class="aide" tabindex="0" role="note" title="{escape(AIDE[terme])}" '
                  f'aria-label="{escape(AIDE[terme])}">{escape(texte or terme)}<sup>?</sup></span>')


def surligner(texte: str, citations: list[tuple[str, str]]) -> Markup:
    """Entoure les passages cités par l'extraction, sans jamais injecter de HTML du message."""
    zones = []
    for citation, etiquette in citations:
        pos = localiser(citation, texte or "")
        if pos and not any(pos[0] < f and pos[1] > d for d, f, _ in zones):
            zones.append((pos[0], pos[1], etiquette))
    zones.sort()
    morceaux, i = [], 0
    for d, f, etiquette in zones:
        morceaux.append(escape(texte[i:d]))
        morceaux.append(Markup(f'<mark title="{escape(etiquette)}">') + escape(texte[d:f]) + Markup("</mark>"))
        i = f
    morceaux.append(escape(texte[i:]))
    return Markup("").join(morceaux)


modeles.env.filters.update(fcfa=fcfa, date_fr=date_fr)
def version_css() -> str:
    """Date de modification de la feuille de style : le navigateur la recharge dès qu'elle change."""
    return str(int((RACINE / "app" / "static" / "app.css").stat().st_mtime))


modeles.env.globals.update(version_css=version_css, aide=aide, ROLES=ROLES, STATUTS=STATUTS, CANAUX=CANAUX, PAIEMENTS=LIBELLES_PAIEMENT,
                           LIBELLES=LIBELLES, EXTRACTEURS=EXTRACTEURS)


def conn():
    return S.ouvrir()


@app.on_event("startup")
def demarrage():
    c = conn()
    reprises = S.reprendre(c)
    if reprises:
        print(f"Reprise après interruption : factures {reprises} terminées.")
    c.close()


# --- Session, droits, protection CSRF ------------------------------------------------

def utilisateur(request: Request, c) -> dict | None:
    uid = request.session.get("uid")
    if not uid:
        return None
    r = c.execute("SELECT id, login, nom, role FROM utilisateurs WHERE id = ?", (uid,)).fetchone()
    if not r:
        return None
    u = dict(r)
    u["mode_solo"] = bool(lire_parametre(c, "mode_solo", False))
    return u


def jeton_csrf(request: Request) -> str:
    if "csrf" not in request.session:
        request.session["csrf"] = secrets.token_urlsafe(24)
    return request.session["csrf"]


def verifier_csrf(request: Request, jeton: str) -> None:
    if not jeton or not secrets.compare_digest(jeton, request.session.get("csrf", "")):
        raise S.Refus("Formulaire expiré. Rechargez la page.")


def page(request: Request, nom: str, c, u, **ctx):
    if u:
        ctx.setdefault("nb_brouillons", c.execute("SELECT COUNT(*) FROM dossiers WHERE statut = 'BROUILLON'").fetchone()[0])
    ctx.update(request=request, u=u, csrf=jeton_csrf(request), entreprise=S.entreprise(c),
               flash=request.session.pop("flash", None), erreur=request.session.pop("erreur", None),
               idem=str(uuid.uuid4()))
    return modeles.TemplateResponse(request, nom, ctx)


def retour(request: Request, url: str, flash: str | None = None, erreur: str | None = None):
    if flash:
        request.session["flash"] = flash
    if erreur:
        request.session["erreur"] = erreur
    return RedirectResponse(url, status_code=303)


async def action(request: Request, url_ok, url_erreur, fonction, message=None):
    """Exécute une action de formulaire : contrôle de session et CSRF, puis message ou erreur."""
    c = conn()
    try:
        u = utilisateur(request, c)
        if not u:
            return RedirectResponse("/connexion", status_code=303)
        form = await request.form()
        verifier_csrf(request, form.get("csrf", ""))
        res = await fonction(c, u, form)
        cible = url_ok(res) if callable(url_ok) else url_ok
        return retour(request, cible, flash=message(res) if callable(message) else message)
    except S.Refus as e:
        return retour(request, url_erreur, erreur=str(e))
    finally:
        c.close()


# --- Connexion -------------------------------------------------------------------------

@app.get("/connexion", response_class=HTMLResponse)
def connexion(request: Request):
    c = conn()
    try:
        comptes = [dict(r) for r in c.execute("SELECT login, nom, role FROM utilisateurs ORDER BY id")]
        return page(request, "connexion.html", c, None, comptes=comptes)
    finally:
        c.close()


@app.post("/connexion")
async def connexion_post(request: Request, login: str = Form(...), mot_de_passe: str = Form(...),
                         csrf: str = Form("")):
    c = conn()
    try:
        verifier_csrf(request, csrf)
        u = S.authentifier(c, login, mot_de_passe)
        if not u:
            with transaction(c):
                journaliser(c, "anonyme", "CONNEXION_REFUSEE", f"login:{login[:40]}", {})
            return retour(request, "/connexion", erreur="Identifiant ou mot de passe incorrect.")
        request.session.clear()
        request.session["uid"] = u["id"]
        with transaction(c):
            journaliser(c, u["id"], "CONNEXION", f"utilisateur:{u['id']}", {})
        return retour(request, "/", flash=f"Bonjour {u['nom']}.")
    except S.Refus as e:
        return retour(request, "/connexion", erreur=str(e))
    finally:
        c.close()


@app.post("/deconnexion")
def deconnexion(request: Request):
    request.session.clear()
    return RedirectResponse("/connexion", status_code=303)


def avec_utilisateur(fonction):
    async def enveloppe(request: Request, *args, **kwargs):
        c = conn()
        try:
            u = utilisateur(request, c)
            if not u:
                return RedirectResponse("/connexion", status_code=303)
            return await fonction(request, c, u, *args, **kwargs)
        except S.Refus as e:
            return retour(request, "/", erreur=str(e))
        finally:
            c.close()
    enveloppe.__name__ = fonction.__name__
    return enveloppe


# --- Tableau de bord ---------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def accueil(request: Request):
    async def vue(request, c, u):
        brouillons = lister_dossiers(c, "BROUILLON", 30)
        factures = [dict(r, contenu=json.loads(r["contenu"])) for r in
                    c.execute("SELECT * FROM factures ORDER BY id DESC LIMIT 12")]
        stats = {
            "brouillons": len(brouillons),
            "a_valider": sum(1 for d in brouillons if d["bloquantes"] == 0),
            "confirmees": c.execute("SELECT COUNT(*) FROM factures WHERE statut='CONFIRMEE' AND type='FV'").fetchone()[0],
            "ca": c.execute("SELECT COALESCE(SUM(CASE type WHEN 'FV' THEN total_ttc ELSE -total_ttc END),0) "
                            "FROM factures WHERE statut='CONFIRMEE'").fetchone()[0],
        }
        return page(request, "accueil.html", c, u, brouillons=brouillons, factures=factures, stats=stats,
                    st=S.statistiques(c))
    return await avec_utilisateur(vue)(request)


def lister_dossiers(c, etat: str | None, limite: int = 200) -> list[dict]:
    """Dossiers de vente, du plus récent au plus ancien, avec le client et le nombre de blocages."""
    if etat:
        lignes = c.execute("SELECT id FROM dossiers WHERE statut = ? ORDER BY id DESC LIMIT ?", (etat, limite))
    else:
        lignes = c.execute("SELECT id FROM dossiers ORDER BY id DESC LIMIT ?", (limite,))
    res = []
    for r in lignes.fetchall():
        d = S.dossier(c, r["id"])
        cl = S.client(c, d["brouillon"]["client"].get("id"))
        d["client_nom"] = cl["nom"] if cl else (d["brouillon"]["client"].get("nom_cite") or "Client à préciser")
        d["bloquantes"] = sum(1 for a in d["anomalies"] if a["bloquante"] and not a["resolue"])
        res.append(d)
    return res


@app.get("/recherche", response_class=HTMLResponse)
async def recherche(request: Request, q: str = ""):
    async def vue(request, c, u):
        return page(request, "recherche.html", c, u, q=q, res=S.rechercher(c, q))
    return await avec_utilisateur(vue)(request)


@app.get("/aide", response_class=HTMLResponse)
async def aide_page(request: Request):
    async def vue(request, c, u):
        return page(request, "aide.html", c, u, glossaire=AIDE)
    return await avec_utilisateur(vue)(request)


ETATS_DOSSIER = {"BROUILLON": "À vérifier", "VALIDE": "Validés", "SUPPRIME": "Supprimés", "tous": "Tous"}


@app.get("/dossiers", response_class=HTMLResponse)
async def liste_dossiers(request: Request, etat: str = "BROUILLON"):
    async def vue(request, c, u):
        choisi = etat if etat in ETATS_DOSSIER else "BROUILLON"
        comptes = {k: n for k, n in c.execute("SELECT statut, COUNT(*) FROM dossiers GROUP BY statut")}
        comptes["tous"] = sum(comptes.values())
        return page(request, "dossiers.html", c, u, dossiers=lister_dossiers(c, None if choisi == "tous" else choisi),
                    etat=choisi, etats=ETATS_DOSSIER, comptes=comptes)
    return await avec_utilisateur(vue)(request)


# --- Nouveau dossier -------------------------------------------------------------------------

EXEMPLES = json.loads((RACINE / "data" / "exemples.json").read_text(encoding="utf-8")) \
    if (RACINE / "data" / "exemples.json").exists() else []


@app.get("/dossiers/nouveau", response_class=HTMLResponse)
async def nouveau(request: Request):
    async def vue(request, c, u):
        defaut = (ia_disponibles() or ["regles"])[0]
        return page(request, "nouveau.html", c, u, exemples=EXEMPLES, extracteur_defaut=defaut)
    return await avec_utilisateur(vue)(request)


@app.post("/dossiers/nouveau")
async def nouveau_post(request: Request):
    async def f(c, u, form):
        fichier: UploadFile | None = form.get("document") if hasattr(form.get("document"), "read") else None
        octets, mime, nom = None, None, None
        if fichier and fichier.filename:
            octets = await fichier.read()
            if len(octets) > 8 * 1024 * 1024:
                raise S.Refus("Document trop lourd (8 Mo au plus).")
            mime, nom = fichier.content_type, fichier.filename
            if mime not in ("image/jpeg", "image/png", "image/webp", "application/pdf"):
                raise S.Refus("Formats acceptés : photo JPEG, PNG, WEBP ou PDF.")
        return S.creer_dossier(c, u, form.get("canal", "WHATSAPP"), form.get("texte_commande", ""),
                               form.get("texte_livraison", ""), form.get("extracteur", "regles"), octets, mime, nom)
    return await action(request, lambda did: f"/dossiers/{did}", "/dossiers/nouveau", f,
                        "Brouillon créé. Vérifiez chaque champ avant de le proposer à la validation.")


# --- Revue d'un dossier ------------------------------------------------------------------

@app.get("/dossiers/{did}", response_class=HTMLResponse)
async def revue(request: Request, did: int):
    async def vue(request, c, u):
        d = S.dossier(c, did)
        br = d["brouillon"]
        cit_cmd, cit_bl = [], []
        if br["client"].get("citation"):
            cit_cmd.append((br["client"]["citation"], "Client"))
        for l in br["lignes"]:
            if l.get("citation_designation"):
                cit_cmd.append((l["citation_designation"], "Article"))
            if l.get("citation_quantite"):
                cit_cmd.append((l["citation_quantite"], "Quantité commandée"))
            if l.get("citation_prix"):
                cit_cmd.append((l["citation_prix"], "Prix cité"))
            if l.get("citation_livree"):
                cit_bl.append((l["citation_livree"], "Quantité livrée"))
        for cle, lib in (("mode_paiement", "Paiement"), ("total_cite", "Total cité")):
            if br[cle].get("citation"):
                cit_cmd.append((br[cle]["citation"], lib))
        if br.get("remise_demandee"):
            cit_cmd.append((br["remise_demandee"].get("citation"), "Remise demandée"))
        arts = S.articles(c)
        index = {a["id"]: a for a in arts}
        facture_id = d.get("facture_id")
        montants = montants_par_ligne(br, arts) if d.get("totaux") else {}
        return page(request, "dossier.html", c, u, d=d, br=br, clients=S.clients(c), articles=arts, index=index,
                    montants=montants,
                    source_commande=surligner(d["texte_commande"], cit_cmd),
                    source_livraison=surligner(d["texte_livraison"] or "", cit_bl),
                    client_choisi=S.client(c, br["client"].get("id")),
                    bloquantes=[a for a in d["anomalies"] if a["bloquante"] and not a["resolue"]],
                    proformas=[dict(r) for r in c.execute("SELECT * FROM proformas WHERE dossier_id = ?", (did,))],
                    facture_id=facture_id)
    return await avec_utilisateur(vue)(request)


@app.post("/dossiers/{did}/corriger")
async def corriger(request: Request, did: int):
    async def f(c, u, form):
        champs = {k: v for k, v in form.items() if k not in ("csrf", "version")}
        S.corriger(c, u, did, int(form["version"]), champs)
    return await action(request, f"/dossiers/{did}", f"/dossiers/{did}", f, "Modifications enregistrées.")


@app.post("/dossiers/{did}/livraison")
async def livraison(request: Request, did: int):
    async def f(c, u, form):
        if not form.get("texte_livraison", "").strip():
            raise S.Refus("Collez le texte du bon de livraison.")
        S.ajouter_livraison(c, u, did, int(form["version"]), form["texte_livraison"], form.get("extracteur", "regles"))
    return await action(request, f"/dossiers/{did}", f"/dossiers/{did}", f, "Bon de livraison rattaché.")


@app.post("/dossiers/{did}/decider")
async def decider(request: Request, did: int):
    async def f(c, u, form):
        S.decider(c, u, did, int(form["version"]), form["cle"], form["choix"], form.get("justification", ""))
    return await action(request, f"/dossiers/{did}", f"/dossiers/{did}", f, "Décision enregistrée.")


@app.post("/dossiers/{did}/valider")
async def valider(request: Request, did: int):
    async def f(c, u, form):
        return S.valider(c, u, did, int(form["version"]), form.get("idem"))
    return await action(request, lambda fid: f"/factures/{fid}", f"/dossiers/{did}", f,
                        "Facture validée et numérotée. Elle ne peut plus être modifiée.")


@app.post("/dossiers/{did}/supprimer")
async def supprimer(request: Request, did: int):
    async def f(c, u, form):
        S.supprimer_dossier(c, u, did, int(form["version"]))
    return await action(request, "/", f"/dossiers/{did}", f, "Brouillon supprimé.")


@app.post("/dossiers/{did}/proforma")
async def proforma(request: Request, did: int):
    async def f(c, u, form):
        return S.creer_proforma(c, u, did)
    return await action(request, lambda pid: f"/proformas/{pid}/pdf", f"/dossiers/{did}", f)


@app.get("/proformas/{pid}/pdf")
async def proforma_pdf(request: Request, pid: int):
    async def vue(request, c, u):
        r = c.execute("SELECT * FROM proformas WHERE id = ?", (pid,)).fetchone()
        if not r:
            raise S.Refus("Pro forma introuvable.")
        return Response(generer(json.loads(r["contenu"])), media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{r["numero"]}.pdf"'})
    return await avec_utilisateur(vue)(request)


# --- Factures ------------------------------------------------------------------------------

@app.get("/factures", response_class=HTMLResponse)
async def factures(request: Request):
    async def vue(request, c, u):
        liste = [dict(r, contenu=json.loads(r["contenu"])) for r in c.execute("SELECT * FROM factures ORDER BY id DESC")]
        return page(request, "factures.html", c, u, factures=liste)
    return await avec_utilisateur(vue)(request)


@app.get("/factures/{fid}", response_class=HTMLResponse)
async def facture(request: Request, fid: int):
    async def vue(request, c, u):
        f = S.facture(c, fid)
        origine = S.facture(c, f["facture_origine_id"]) if f.get("facture_origine_id") else None
        return page(request, "facture.html", c, u, f=f, origine=origine)
    return await avec_utilisateur(vue)(request)


@app.get("/factures/{fid}/pdf")
async def facture_pdf(request: Request, fid: int, copie: int = 0):
    async def vue(request, c, u):
        f = S.facture(c, fid)
        pdf = generer(f["contenu"], f if f["code_dgi"] else None, copie=bool(copie))
        if copie:
            with transaction(c):
                journaliser(c, u["id"], "COPIE_IMPRIMEE", f"facture:{fid}", {})
        return Response(pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{f["numero"]}.pdf"'})
    return await avec_utilisateur(vue)(request)


@app.post("/factures/{fid}/emettre")
async def emettre(request: Request, fid: int):
    async def f(c, u, form):
        return S.emettre(c, u, fid, form.get("idem"), simuler_coupure=form.get("coupure") == "1")
    try:
        return await action(request, f"/factures/{fid}", f"/factures/{fid}", f,
                            lambda r: "Facture confirmée par la DGI simulée." if r["statut"] == "CONFIRMEE"
                            else "Émission annulée : les totaux ne correspondent pas.")
    except S.CoupureSimulee:
        return retour(request, f"/factures/{fid}", erreur="Coupure simulée : l'application s'est arrêtée pendant "
                      "l'émission. Redémarrez-la : la facture sera terminée automatiquement, sans doublon.")


@app.post("/factures/{fid}/avoir")
async def avoir(request: Request, fid: int):
    async def f(c, u, form):
        quantites = {int(k.split(":")[1]): v for k, v in form.items() if k.startswith("q:")}
        aid = S.creer_avoir(c, u, fid, quantites, form.get("motif", ""), form.get("idem"))
        if form.get("emettre"):
            S.emettre(c, u, aid)
        return aid
    return await action(request, lambda aid: f"/factures/{aid}", f"/factures/{fid}", f, "Avoir créé.")


@app.post("/factures/{fid}/accuse")
async def accuse(request: Request, fid: int):
    async def f(c, u, form):
        S.accuser_reception(c, u, fid, form.get("canal", "WHATSAPP"))
    return await action(request, f"/factures/{fid}", f"/factures/{fid}", f, "Accusé de réception enregistré (simulé).")


@app.post("/factures/{fid}/paiement")
async def paiement(request: Request, fid: int):
    async def f(c, u, form):
        try:
            montant = int(str(form.get("montant", "0")).replace(" ", "").replace(" ", ""))
        except ValueError:
            raise S.Refus("Montant illisible.")
        return S.enregistrer_paiement(c, u, fid, montant, form.get("mode", "ESPECES"), form.get("reference", ""),
                                      form.get("idem"))
    return await action(request, f"/factures/{fid}", f"/factures/{fid}", f, "Paiement enregistré (simulé), reçu émis.")


# --- Comptabilité, journal, référentiels, paramètres -------------------------------------------

@app.get("/comptabilite", response_class=HTMLResponse)
async def comptabilite(request: Request, jour: str = ""):
    async def vue(request, c, u):
        S.exiger(u, "compta.lire")
        actifs = S.jours_avec_activite(c)
        try:
            choisi = date.fromisoformat(jour) if jour else None
        except ValueError:
            choisi = None
        if choisi is None:  # par défaut : aujourd'hui, ou le dernier jour d'activité s'il n'y en a pas aujourd'hui
            aujourd = date.today().isoformat()
            choisi = date.fromisoformat(aujourd if aujourd in actifs or not actifs else actifs[-1])
        iso = choisi.isoformat()
        precedent = max((j for j in actifs if j < iso), default=None)
        suivant = min((j for j in actifs if j > iso), default=None)
        return page(request, "comptabilite.html", c, u, rapport=S.rapport_du_jour(c, choisi), vc=S.vue_comptable(c),
                    precedent=precedent, suivant=suivant, est_aujourdhui=choisi == date.today())
    return await avec_utilisateur(vue)(request)


@app.get("/comptabilite/ecritures.csv")
async def ecritures(request: Request):
    async def vue(request, c, u):
        S.exiger(u, "compta.lire")
        return Response("﻿" + S.export_ecritures_csv(c), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="ecritures_simulees.csv"'})
    return await avec_utilisateur(vue)(request)


# Action du journal -> (phrase, catégorie, icône). La phrase suit le nom de la personne.
ACTIONS_JOURNAL = {
    "CONNEXION": ("s'est connecté(e)", "connexions", "sortie"),
    "CONNEXION_REFUSEE": ("a tenté de se connecter : refusé", "connexions", "alerte"),
    "DOSSIER_CREE": ("a créé un dossier de vente", "ventes", "brouillon"),
    "LIVRAISON_AJOUTEE": ("a rattaché un bon de livraison", "ventes", "brouillon"),
    "BROUILLON_CORRIGE": ("a corrigé un brouillon", "ventes", "brouillon"),
    "ANOMALIE_TRANCHEE": ("a tranché un contrôle", "ventes", "coche"),
    "DOSSIER_SUPPRIME": ("a supprimé un brouillon", "ventes", "alerte"),
    "PROFORMA_CREEE": ("a produit une pro forma", "ventes", "pdf"),
    "FACTURE_VALIDEE": ("a validé et numéroté une facture", "ventes", "cadenas"),
    "EMISSION_DEMANDEE": ("a émis vers la DGI simulée", "ventes", "envoyer"),
    "FACTURE_CONFIRMEE": ("a reçu la confirmation de la DGI simulée", "ventes", "facture-ok"),
    "EMISSION_ANNULEE": ("a vu l'émission annulée par la DGI simulée", "ventes", "alerte"),
    "AVOIR_CREE": ("a créé un avoir", "ventes", "facture"),
    "COPIE_IMPRIMEE": ("a imprimé une copie", "ventes", "pdf"),
    "ACCUSE_CLIENT": ("a enregistré l'accusé de réception du client", "ventes", "coche"),
    "PAIEMENT_ENREGISTRE": ("a enregistré un paiement", "paiements", "argent"),
    "CLIENT_MODIFIE": ("a modifié une fiche client", "administration", "gestion"),
    "ARTICLE_MODIFIE": ("a modifié un article", "administration", "gestion"),
    "PARAMETRES_MODIFIES": ("a modifié les paramètres", "administration", "gestion"),
    "DEMO_REINITIALISEE": ("a réinitialisé la démonstration", "administration", "alerte"),
}
CATEGORIES_JOURNAL = {"": "Tout", "ventes": "Ventes", "paiements": "Paiements", "connexions": "Connexions",
                      "administration": "Administration"}
JOURS_SEMAINE = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]


def _jour_long(iso: str) -> str:
    j = date.fromisoformat(iso[:10])
    if j == date.today():
        return "Aujourd'hui"
    return f"{JOURS_SEMAINE[j.weekday()].capitalize()} {j.day} {MOIS[j.month - 1]} {j.year}"


@app.get("/journal", response_class=HTMLResponse)
async def journal(request: Request, verifier: int = 0, categorie: str = "", acteur: str = ""):
    async def vue(request, c, u):
        noms = {r["id"]: r["nom"] for r in c.execute("SELECT id, nom FROM utilisateurs")}
        numeros = {str(r["id"]): r["numero"] for r in c.execute("SELECT id, numero FROM factures")}
        lignes = []
        for r in c.execute("SELECT * FROM journal ORDER BY id DESC LIMIT 400"):
            l = dict(r)
            phrase, cat, ico = ACTIONS_JOURNAL.get(l["action"], (l["action"].lower().replace("_", " "), "administration", "gestion"))
            if (categorie and cat != categorie) or (acteur and l["acteur"] != acteur):
                continue
            try:
                l["donnees"] = json.loads(l["details"]) if l["details"] else {}
            except ValueError:
                l["donnees"] = {}
            l["details_lisibles"] = json.dumps(l["donnees"], ensure_ascii=False, indent=2)
            genre, _, ident = l["objet"].partition(":")
            l["lien"] = {"dossier": f"/dossiers/{ident}", "facture": f"/factures/{ident}"}.get(genre)
            l["objet_lib"] = {"dossier": f"Dossier {ident}", "facture": numeros.get(ident, f"Facture {ident}"),
                              "utilisateur": noms.get(ident, ident)}.get(genre, l["objet"])
            if genre == "utilisateur" and ident == l["acteur"]:
                l["objet_lib"] = None  # « Rodrigue s'est connecté » : inutile de répéter le nom
            qui = {"anonyme": "Une personne inconnue", "reprise": "Le système (reprise)", "systeme": "Le système"}
            l.update(phrase=phrase, categorie=cat, icone=ico, qui=noms.get(l["acteur"], qui.get(l["acteur"], l["acteur"])),
                     jour=_jour_long(l["horodatage"]), heure=l["horodatage"][11:16])
            lignes.append(l)
        chaine = [dict(r) for r in c.execute("SELECT id, action, hash, hash_precedent FROM journal ORDER BY id DESC LIMIT 4")][::-1]
        aujourdhui = date.today().isoformat()
        stats = {
            "total": c.execute("SELECT COUNT(*) FROM journal").fetchone()[0],
            "jour": c.execute("SELECT COUNT(*) FROM journal WHERE substr(horodatage, 1, 10) = ?", (aujourdhui,)).fetchone()[0],
            "refusees": c.execute("SELECT COUNT(*) FROM journal WHERE action = 'CONNEXION_REFUSEE'").fetchone()[0],
            "corrections": c.execute("SELECT COUNT(*) FROM journal WHERE action IN ('BROUILLON_CORRIGE', 'ANOMALIE_TRANCHEE')").fetchone()[0],
        }
        resultat = verifier_journal(c) if verifier else None
        return page(request, "journal.html", c, u, lignes=lignes, noms=noms, resultat=resultat, chaine=chaine,
                    stats=stats, categories=CATEGORIES_JOURNAL, categorie=categorie, acteur=acteur)
    return await avec_utilisateur(vue)(request)


@app.get("/referentiels", response_class=HTMLResponse)
async def referentiels(request: Request):
    async def vue(request, c, u):
        return page(request, "referentiels.html", c, u, clients=S.clients(c), articles=S.articles(c))
    return await avec_utilisateur(vue)(request)


@app.post("/referentiels/article/{aid}")
async def maj_article(request: Request, aid: str):
    async def f(c, u, form):
        S.exiger(u, "referentiel.ecrire")
        groupe, prix = form.get("groupe_taxe"), int(form.get("prix_unitaire_ttc", "0"))
        if groupe not in ("A", "B", "C", "D", "E") or prix <= 0:
            raise S.Refus("Groupe ou prix invalide.")
        with transaction(c):
            avant = dict(c.execute("SELECT groupe_taxe, prix_unitaire_ttc FROM articles WHERE id=?", (aid,)).fetchone())
            c.execute("UPDATE articles SET groupe_taxe = ?, prix_unitaire_ttc = ? WHERE id = ?", (groupe, prix, aid))
            journaliser(c, u["id"], "ARTICLE_MODIFIE", f"article:{aid}",
                        {"avant": avant, "apres": {"groupe_taxe": groupe, "prix_unitaire_ttc": prix}})
    return await action(request, "/referentiels", "/referentiels", f, "Article mis à jour.")


@app.post("/referentiels/client/{cid}")
async def maj_client(request: Request, cid: str):
    async def f(c, u, form):
        S.exiger(u, "referentiel.ecrire")
        taux = int(form.get("aib_taux", "0"))
        if taux not in (0, 1, 5):
            raise S.Refus("Taux d'AIB invalide.")
        with transaction(c):
            avant = c.execute("SELECT aib_taux FROM clients WHERE id=?", (cid,)).fetchone()[0]
            c.execute("UPDATE clients SET aib_taux = ? WHERE id = ?", (taux, cid))
            journaliser(c, u["id"], "CLIENT_MODIFIE", f"client:{cid}", {"aib_avant": avant, "aib_apres": taux})
    return await action(request, "/referentiels", "/referentiels", f, "Client mis à jour.")


@app.get("/parametres", response_class=HTMLResponse)
async def parametres(request: Request):
    async def vue(request, c, u):
        S.exiger(u, "parametres.ecrire")
        return page(request, "parametres.html", c, u, mode_solo=lire_parametre(c, "mode_solo", False),
                    gemini=bool(os.environ.get("GEMINI_API_KEY")), groq=bool(os.environ.get("GROQ_API_KEY")))
    return await avec_utilisateur(vue)(request)


@app.post("/parametres")
async def parametres_post(request: Request):
    async def f(c, u, form):
        S.exiger(u, "parametres.ecrire")
        perso = {**S.PERSONNALISATION_DEFAUT, **lire_parametre(c, "personnalisation", {})}
        couleur = form.get("couleur", "")
        if not (len(couleur) == 7 and couleur.startswith("#")):
            raise S.Refus("Couleur invalide.")
        perso.update(couleur=couleur, conditions_paiement=form.get("conditions_paiement", "")[:200],
                     pied_de_page=form.get("pied_de_page", "")[:200],
                     mode_arrondi="ligne" if form.get("mode_arrondi") == "ligne" else "groupe")
        logo = form.get("logo")
        if hasattr(logo, "read") and logo.filename:
            octets = await logo.read()
            if logo.content_type not in ("image/png", "image/jpeg") or len(octets) > 500_000:
                raise S.Refus("Logo : PNG ou JPEG de 500 Ko au plus.")
            perso["logo"] = f"data:{logo.content_type};base64," + base64.b64encode(octets).decode()
        if form.get("retirer_logo"):
            perso["logo"] = None
        with transaction(c):
            ecrire_parametre(c, "personnalisation", perso)
            ecrire_parametre(c, "mode_solo", bool(form.get("mode_solo")))
            journaliser(c, u["id"], "PARAMETRES_MODIFIES", "entreprise",
                        {k: v for k, v in perso.items() if k != "logo"} | {"mode_solo": bool(form.get("mode_solo"))})
    return await action(request, "/parametres", "/parametres", f, "Paramètres enregistrés.")


@app.post("/parametres/demo")
async def charger_demo(request: Request):
    async def f(c, u, form):
        S.exiger(u, "demo.reinitialiser")
        from .demo import charger
        return charger(c)
    r = await action(request, "/connexion", "/parametres", f,
                     lambda res: f"Démonstration chargée : {res['factures']} factures émises, {res['a_verifier']} commandes à vérifier.")
    request.session.pop("uid", None)
    return r


@app.post("/parametres/reinitialiser")
async def reinitialiser(request: Request):
    async def f(c, u, form):
        S.exiger(u, "demo.reinitialiser")
        S.reinitialiser(c, u["id"])
    r = await action(request, "/connexion", "/parametres", f, "Démonstration réinitialisée.")
    request.session.pop("uid", None)
    return r
