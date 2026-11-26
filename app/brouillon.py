"""Du résultat d'extraction au brouillon contrôlé.

1. Vérification des citations (règle R-02) : une valeur dont la citation n'est pas dans la source est rejetée.
2. Rapprochement avec les référentiels clients et articles.
3. Détection des anomalies (règles R-10 à R-12).
4. Préparation des lignes facturables pour le moteur.
"""
from __future__ import annotations

import difflib
from decimal import Decimal

from .moteur import ErreurCalcul, Ligne, calculer, lire_quantite
from .texte import citation_presente, lire_montant, lire_quantite_texte, normaliser

SEUIL_PRIX_INHABITUEL = Decimal("0.15")
FENETRE_DOUBLON_HEURES = 72

LIBELLES = {
    "CLIENT_INCONNU": "Client introuvable dans vos clients",
    "CLIENT_AMBIGU": "Plusieurs clients correspondent",
    "ARTICLE_INCONNU": "Article introuvable dans votre catalogue",
    "QUANTITE_MANQUANTE": "Quantité absente du message",
    "QUANTITE_INVALIDE": "Quantité impossible",
    "ECART_COMMANDE_LIVRAISON": "Quantité livrée différente de la commande",
    "PRIX_INHABITUEL": "Prix cité inhabituel",
    "TOTAL_INCOHERENT": "Total cité différent du total recalculé",
    "DOUBLON_PROBABLE": "Commande déjà reçue récemment",
    "REMISE_A_VALIDER": "Remise demandée par le client",
    "INSTRUCTION_SUSPECTE": "Consigne suspecte dans le message",
    "CALCUL_IMPOSSIBLE": "Calcul impossible",
}
BLOQUANTES = {"CLIENT_INCONNU", "CLIENT_AMBIGU", "ARTICLE_INCONNU", "QUANTITE_MANQUANTE", "QUANTITE_INVALIDE",
              "ECART_COMMANDE_LIVRAISON", "TOTAL_INCOHERENT", "DOUBLON_PROBABLE", "REMISE_A_VALIDER",
              "CALCUL_IMPOSSIBLE"}
# Anomalies levées par une décision du responsable (les autres se corrigent en modifiant le brouillon).
DECISIONS = {"ECART_COMMANDE_LIVRAISON", "TOTAL_INCOHERENT", "DOUBLON_PROBABLE", "REMISE_A_VALIDER", "PRIX_INHABITUEL"}


# --- Vérification des citations -----------------------------------------------------

def _verifier(champ: dict, source: str, rejets: list, nom: str, verifier: bool, lecture=None) -> dict:
    """Garde la valeur seulement si sa citation existe dans la source et porte bien cette valeur."""
    valeur, citation = champ.get("valeur"), champ.get("citation")
    if valeur in (None, ""):
        return {"valeur": None, "citation": None}
    if not verifier:
        return {"valeur": valeur, "citation": citation}
    if not citation_presente(citation, source):
        rejets.append({"champ": nom, "valeur": valeur, "citation": citation, "raison": "citation absente de la source"})
        return {"valeur": None, "citation": None}
    if lecture is not None:
        relu, attendu = lecture(citation), lecture(str(valeur))
        if relu is not None and attendu is not None and str(relu) != str(attendu):
            rejets.append({"champ": nom, "valeur": valeur, "citation": citation,
                           "raison": f"la citation indique {relu}, pas {valeur}"})
            return {"valeur": None, "citation": None}
    return {"valeur": valeur, "citation": citation}


# --- Rapprochement avec les référentiels --------------------------------------------

def _score(a: str, b: str) -> float:
    a, b = normaliser(a), normaliser(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if f" {b} " in f" {a} " or f" {a} " in f" {b} ":
        return 0.92
    return difflib.SequenceMatcher(None, a, b).ratio()


def trouver_clients(nom_cite: str | None, clients: list[dict]) -> tuple[list[str], str]:
    """Renvoie (identifiants candidats, confiance)."""
    if not nom_cite:
        return [], "absente"
    scores = []
    for c in clients:
        s = max(_score(nom_cite, x) for x in c["alias"] + [c["nom"]])
        scores.append((s, c["id"]))
    meilleurs = [cid for s, cid in scores if s >= 0.92]
    if meilleurs:
        return meilleurs, "elevee" if len(meilleurs) == 1 else "ambigue"
    approchants = sorted([(s, cid) for s, cid in scores if s >= 0.8], reverse=True)
    if approchants:
        return [approchants[0][1]], "moyenne"
    return [], "faible"


def trouver_article(designation: str | None, articles: list[dict]) -> tuple[str | None, str]:
    if not designation:
        return None, "absente"
    meilleur = max(((max(_score(designation, x) for x in a["alias"] + [a["designation"]]), a["id"]) for a in articles),
                   default=(0, None))
    if meilleur[0] >= 0.92:
        return meilleur[1], "elevee"
    if meilleur[0] >= 0.75:
        return meilleur[1], "moyenne"
    return None, "faible"


# --- Construction du brouillon ----------------------------------------------------------

def construire(extraction: dict, texte: str, clients: list[dict], articles: list[dict], verifier: bool = True) -> dict:
    rejets: list = []
    client = _verifier(extraction["client"], texte, rejets, "client", verifier)
    candidats, conf_client = trouver_clients(client["valeur"], clients)
    paiement = _verifier(extraction["mode_paiement"], texte, rejets, "mode de paiement", verifier)
    total = _verifier(extraction["total_cite"], texte, rejets, "total cité", verifier, lire_montant)
    remise = extraction.get("remise_demandee")
    if remise and verifier and not citation_presente(remise.get("citation"), texte):
        rejets.append({"champ": "remise", "valeur": remise.get("valeur"), "citation": remise.get("citation"),
                       "raison": "citation absente de la source"})
        remise = None

    lignes = []
    for i, l in enumerate(extraction["lignes"], start=1):
        des = _verifier(l["designation"], texte, rejets, f"ligne {i} désignation", verifier)
        qte = _verifier(l["quantite"], texte, rejets, f"ligne {i} quantité", verifier, lire_quantite_texte)
        prix = _verifier(l["prix_unitaire_ttc"], texte, rejets, f"ligne {i} prix", verifier, lire_montant)
        if des["valeur"] is None and qte["valeur"] is None:
            continue
        article_id, conf = trouver_article(des["valeur"], articles)
        art = next((a for a in articles if a["id"] == article_id), None)
        lignes.append({
            "cle": f"l{i}",
            "article_id": article_id,
            "confiance_article": conf,
            "designation_citee": des["valeur"],
            "citation_designation": des["citation"],
            "quantite_commandee": lire_quantite_texte(qte["valeur"]) if qte["valeur"] is not None else None,
            "citation_quantite": qte["citation"],
            "quantite_livree": None,
            "citation_livree": None,
            "prix_cite": int(prix["valeur"]) if prix["valeur"] is not None else None,
            "citation_prix": prix["citation"],
            "prix_catalogue": art["prix_unitaire_ttc"] if art else None,
            "source": "extraction",
        })
    return {
        "client": {"id": candidats[0] if len(candidats) == 1 else None, "candidats": candidats,
                   "nom_cite": client["valeur"], "citation": client["citation"], "confiance": conf_client,
                   "source": "extraction"},
        "lignes": lignes,
        "mode_paiement": {"valeur": paiement["valeur"], "citation": paiement["citation"]},
        "total_cite": {"valeur": total["valeur"], "citation": total["citation"]},
        "remise_demandee": remise,
        "instructions_suspectes": extraction.get("instructions_suspectes") or [],
        "rejets": rejets,
        "decisions": {},
        "livraison": None,
    }


def integrer_livraison(brouillon: dict, extraction_bl: dict, texte_bl: str, articles: list[dict], verifier: bool = True) -> dict:
    """Rattache les quantités livrées aux lignes commandées, par article."""
    rejets = brouillon.setdefault("rejets", [])
    livrees: dict[str, dict] = {}
    for i, l in enumerate(extraction_bl["lignes"], start=1):
        des = _verifier(l["designation"], texte_bl, rejets, f"livraison ligne {i} désignation", verifier)
        qte = _verifier(l["quantite"], texte_bl, rejets, f"livraison ligne {i} quantité", verifier, lire_quantite_texte)
        article_id, _ = trouver_article(des["valeur"], articles)
        if article_id and qte["valeur"] is not None:
            livrees[article_id] = {"q": lire_quantite_texte(qte["valeur"]), "citation": qte["citation"]}
    for ligne in brouillon["lignes"]:
        info = livrees.get(ligne["article_id"])
        ligne["quantite_livree"] = info["q"] if info else "0"
        ligne["citation_livree"] = info["citation"] if info else None
    brouillon["livraison"] = {"recue": True}
    return brouillon


# --- Lignes facturables et totaux ---------------------------------------------------

def prix_retenu(ligne: dict, decisions: dict) -> int | None:
    d = decisions.get(f"PRIX_INHABITUEL:{ligne['cle']}")
    if d and d.get("appliquer_prix_cite") and ligne.get("prix_cite"):
        return ligne["prix_cite"]
    return ligne.get("prix_catalogue")


def lignes_facturables(brouillon: dict, articles: list[dict], quantites: str = "facturees") -> list[Ligne]:
    """quantites : « facturees » (livrées si un bon de livraison existe) ou « commandees »."""
    index = {a["id"]: a for a in articles}
    remise = brouillon.get("remise_demandee")
    d_remise = brouillon.get("decisions", {}).get("REMISE_A_VALIDER")
    taux_remise = Decimal(str(remise["valeur"])) if (remise and d_remise and d_remise.get("acceptee")
                                                      and remise.get("type") == "POURCENTAGE") else Decimal(0)
    return [x for _, x in _lignes_avec_cle(brouillon, index, taux_remise, quantites)]


def _lignes_avec_cle(brouillon: dict, index: dict, taux_remise: Decimal, quantites: str):
    """(clé de la ligne du brouillon, Ligne facturable), dans l'ordre du brouillon."""
    for l in brouillon["lignes"]:
        art = index.get(l["article_id"])
        if not art:
            continue
        q = l["quantite_commandee"]
        if quantites == "facturees" and l.get("quantite_livree") is not None:
            q = l["quantite_livree"]
        if q is None or Decimal(str(q)) == 0:
            continue
        pu = prix_retenu(l, brouillon.get("decisions", {}))
        if taux_remise:
            pu = int((Decimal(pu) * (100 - taux_remise) / 100).quantize(Decimal(1), rounding="ROUND_HALF_UP"))
        yield l.get("cle"), Ligne(art["designation"], lire_quantite(q), pu, art["groupe_taxe"], art["id"])


def montants_par_ligne(brouillon: dict, articles: list[dict]) -> dict:
    """Montant TTC de chaque ligne du brouillon, par clé (deux lignes du même article restent distinctes)."""
    index = {a["id"]: a for a in articles}
    remise = brouillon.get("remise_demandee")
    d_remise = brouillon.get("decisions", {}).get("REMISE_A_VALIDER")
    taux_remise = Decimal(str(remise["valeur"])) if (remise and d_remise and d_remise.get("acceptee")
                                                      and remise.get("type") == "POURCENTAGE") else Decimal(0)
    return {cle: ligne.montant_ttc for cle, ligne in _lignes_avec_cle(brouillon, index, taux_remise, "facturees")}


def anomalies(brouillon: dict, clients: list[dict], articles: list[dict], doublons: list[int] | None = None,
              aib_taux: int = 0, mode_arrondi: str = "groupe") -> list[dict]:
    res = []
    dec = brouillon.get("decisions", {})

    def ajouter(code, message, ligne=None, cle_decision=None):
        cle = cle_decision or code
        decision = dec.get(cle)
        res.append({"code": code, "titre": LIBELLES[code], "message": message, "ligne": ligne,
                    "bloquante": code in BLOQUANTES, "cle_decision": cle if code in DECISIONS else None,
                    "resolue": bool(decision), "decision": decision})

    c = brouillon["client"]
    if not c.get("id"):
        if len(c.get("candidats") or []) > 1:
            noms = ", ".join(next(x["nom"] for x in clients if x["id"] == i) for i in c["candidats"])
            ajouter("CLIENT_AMBIGU", f"« {c.get('nom_cite')} » peut désigner : {noms}. Choisissez le bon client.")
        else:
            cite = c.get("nom_cite")
            ajouter("CLIENT_INCONNU", f"« {cite} » ne correspond à aucun client. Choisissez un client ou créez sa fiche."
                    if cite else "Le message ne nomme pas le client. Choisissez-le.")

    index = {a["id"]: a for a in articles}
    if not brouillon["lignes"]:
        ajouter("ARTICLE_INCONNU", "Aucun article reconnu dans le message. Ajoutez au moins une ligne.")
    for l in brouillon["lignes"]:
        nom = l.get("designation_citee") or l["cle"]
        art = index.get(l.get("article_id"))
        if not art:
            ajouter("ARTICLE_INCONNU", f"« {nom} » ne correspond à aucun article. Choisissez l'article.", l["cle"])
            continue
        q = l.get("quantite_commandee")
        if q is None:
            ajouter("QUANTITE_MANQUANTE", f"{art['designation']} : le message ne donne pas de quantité. Saisissez-la.", l["cle"])
        else:
            try:
                qd = lire_quantite(q)
                if not art.get("quantite_decimale") and qd != qd.to_integral_value():
                    raise ErreurCalcul(f"{art['designation']} se vend à l'unité, pas en {q}.")
            except ErreurCalcul as e:
                ajouter("QUANTITE_INVALIDE", f"{art['designation']} : {e}", l["cle"])
        livree = l.get("quantite_livree")
        if livree is not None and q is not None and Decimal(str(livree)) != Decimal(str(q)):
            ajouter("ECART_COMMANDE_LIVRAISON",
                    f"{art['designation']} : {q} commandé(s), {livree} livré(s). La facture portera sur le livré.",
                    l["cle"], f"ECART_COMMANDE_LIVRAISON:{l['cle']}")
        if l.get("prix_cite") and art:
            ecart = abs(Decimal(l["prix_cite"]) - art["prix_unitaire_ttc"]) / art["prix_unitaire_ttc"]
            if ecart > SEUIL_PRIX_INHABITUEL:
                ajouter("PRIX_INHABITUEL",
                        f"{art['designation']} : le client cite {l['prix_cite']:,} F, le catalogue indique "
                        f"{art['prix_unitaire_ttc']:,} F ({ecart:.0%} d'écart). Le prix du catalogue s'applique sauf décision."
                        .replace(",", " "), l["cle"], f"PRIX_INHABITUEL:{l['cle']}")

    total = brouillon.get("total_cite", {}).get("valeur")
    if total:
        try:
            recalc = calculer(lignes_facturables(brouillon, articles, "commandees"), 0, mode_arrondi).total_ttc
            if recalc != total:
                ajouter("TOTAL_INCOHERENT", f"Le client annonce {total:,} F ; le total recalculé de sa commande est "
                        f"{recalc:,} F. Seul le total recalculé sera facturé.".replace(",", " "))
        except ErreurCalcul:
            pass
    if doublons:
        ajouter("DOUBLON_PROBABLE", "Même client et mêmes articles que le dossier n° "
                + ", ".join(str(d) for d in doublons) + " reçu il y a moins de 72 h.")
    if brouillon.get("remise_demandee"):
        r = brouillon["remise_demandee"]
        unite = "%" if r.get("type") == "POURCENTAGE" else " F"
        ajouter("REMISE_A_VALIDER", f"Le client demande une remise de {r.get('valeur'):g}{unite}. "
                "Elle ne s'applique qu'avec l'accord du responsable.")
    for s in brouillon.get("instructions_suspectes") or []:
        ajouter("INSTRUCTION_SUSPECTE", f"« {s} » : consigne ignorée, elle n'a aucun effet sur la facture.")

    if not any(a["bloquante"] and not a["resolue"] for a in res):
        try:
            calculer(lignes_facturables(brouillon, articles), aib_taux, mode_arrondi)
        except ErreurCalcul as e:
            ajouter("CALCUL_IMPOSSIBLE", str(e))
    return res


def signature(brouillon: dict) -> tuple:
    """Empreinte client + lignes commandées, pour détecter les doublons."""
    return (brouillon["client"].get("id"),
            tuple(sorted((l.get("article_id") or "", str(l.get("quantite_commandee"))) for l in brouillon["lignes"])))
