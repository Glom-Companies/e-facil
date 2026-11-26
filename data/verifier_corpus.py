#!/usr/bin/env python3
"""Script de contrôle du jeu de données et du corpus de test.

Python 3.11+, bibliothèque standard uniquement.
Utilisation :
    python verifier_corpus.py data/
    python data/verifier_corpus.py data/
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

ANOMALIES_BLOQUANTES = {
    "CLIENT_INCONNU",
    "CLIENT_AMBIGU",
    "ARTICLE_INCONNU",
    "QUANTITE_MANQUANTE",
    "QUANTITE_INVALIDE",
    "ECART_COMMANDE_LIVRAISON",
    "TOTAL_INCOHERENT",
    "DOUBLON_PROBABLE",
    "REMISE_A_VALIDER",
}
ANOMALIES_NON_BLOQUANTES = {
    "PRIX_INHABITUEL",
    "INSTRUCTION_SUSPECTE",
}
ANOMALIES_AUTORISEES = ANOMALIES_BLOQUANTES | ANOMALIES_NON_BLOQUANTES

MODES_PAIEMENT = {
    "ESPECES",
    "CHEQUES",
    "MOBILEMONEY",
    "CARTEBANCAIRE",
    "VIREMENT",
    "CREDIT",
    "AUTRE",
}
CANAUX_AUTORISES = {"WHATSAPP", "SMS", "EMAIL", "VOCAL_TRANSCRIT"}
TYPES_CLIENTS = {
    "ENTREPRISE_REEL",
    "ENTREPRISE_TPS",
    "PARTICULIER",
    "STRUCTURE_ETAT",
    "CLIENT_EXPORT",
}
PIEGES_CONNUS = {
    "separateur_milliers_point",
    "separateur_milliers_espace",
    "montant_en_lettres",
    "montant_abrege",
    "abreviations_sms",
    "comme_d_habitude",
    "transcription_vocale",
    "melange_langues",
    "email_formel",
    "tableau_colle",
    "plusieurs_messages",
    "date_relative",
}

CHAMPS_MESSAGE = {
    "id",
    "split",
    "canal",
    "date_reception",
    "auteur_affiche",
    "texte_commande",
    "texte_livraison",
    "doublon_de",
    "attendu",
    "anomalies_attendues",
    "pieges",
    "facture_attendue",
    "commentaire",
}
CHAMPS_ATTENDU = {
    "client",
    "lignes",
    "mode_paiement",
    "citation_paiement",
    "total_ttc_cite",
    "remise_demandee",
}
CHAMPS_LIGNE_ATTENDUE = {
    "article_id",
    "citation_designation",
    "quantite_commandee",
    "citation_quantite_commandee",
    "quantite_livree",
    "prix_unitaire_ttc_cite",
    "citation_prix",
}
CHAMPS_FACTURE_ATTENDUE = {
    "lignes",
    "totaux_par_groupe",
    "total_ttc",
    "aib_taux",
    "aib_montant",
    "net_a_payer",
}


def est_entier(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def arrondi_franc(valeur: Decimal) -> int:
    return int(valeur.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def ventiler_groupe(ttc: int, groupe: str) -> tuple[int, int]:
    if groupe == "B":
        ht = arrondi_franc(Decimal(ttc) * Decimal(100) / Decimal(118))
        return ht, ttc - ht
    if groupe in ("A", "C", "E"):
        return ttc, 0
    raise ValueError(f"Groupe de taxe inconnu : {groupe!r}")


def recalculer_facture(msg: dict, clients: dict[str, dict], articles: dict[str, dict]) -> dict:
    att = msg["attendu"]
    cid = att["client"]["id_referentiel"]
    client = clients[cid]
    aib_taux = client["aib_taux"]
    avec_bl = msg["texte_livraison"] is not None

    lignes_calc = []
    ttc_par_groupe: dict[str, int] = {}
    for l in att["lignes"]:
        art = articles[l["article_id"]]
        q_str = l["quantite_livree"] if avec_bl else l["quantite_commandee"]
        q = Decimal(q_str)
        if q == 0:
            continue
        pu = art["prix_unitaire_ttc"]
        montant = arrondi_franc(q * Decimal(pu))
        g = art["groupe_taxe"]
        lignes_calc.append({
            "article_id": art["id"],
            "quantite": q_str,
            "prix_unitaire_ttc": pu,
            "montant_ttc": montant,
            "groupe": g,
        })
        ttc_par_groupe[g] = ttc_par_groupe.get(g, 0) + montant

    totaux_par_groupe = {}
    for g in sorted(ttc_par_groupe):
        ttc = ttc_par_groupe[g]
        ht, tva = ventiler_groupe(ttc, g)
        totaux_par_groupe[g] = {"ttc": ttc, "ht": ht, "tva": tva}

    total_ttc = sum(v["ttc"] for v in totaux_par_groupe.values())
    total_ht = sum(v["ht"] for v in totaux_par_groupe.values())
    aib_montant = arrondi_franc(Decimal(total_ht) * Decimal(aib_taux) / Decimal(100))
    net_a_payer = total_ttc - aib_montant

    return {
        "lignes": lignes_calc,
        "totaux_par_groupe": totaux_par_groupe,
        "total_ttc": total_ttc,
        "aib_taux": aib_taux,
        "aib_montant": aib_montant,
        "net_a_payer": net_a_payer,
    }


def verifier_sans_bom(chemin: Path, erreurs: list[str]) -> bytes:
    octets = chemin.read_bytes()
    if octets.startswith(b"\xef\xbb\xbf"):
        erreurs.append(f"{chemin.name} : présence d'un BOM UTF-8 interdite.")
    try:
        octets.decode("utf-8")
    except UnicodeDecodeError as e:
        erreurs.append(f"{chemin.name} : encodage UTF-8 invalide ({e}).")
    return octets


def resoudre_dossier_data(arg: str | None) -> Path:
    if arg:
        p = Path(arg)
        if (p / "entreprise.json").exists():
            return p
        # Si lancé depuis data/ avec « python verifier_corpus.py data/ »
        parent = Path(__file__).resolve().parent
        if (parent / "entreprise.json").exists():
            return parent
        return p
    if (Path("data") / "entreprise.json").exists():
        return Path("data")
    return Path(__file__).resolve().parent


def verifier(dossier: Path) -> int:
    erreurs: list[str] = []

    # 0. Contrôle préalable des exemples officiels de la DGI
    if ventiler_groupe(2320, "B") != (1966, 354):
        erreurs.append("Exemple DGI 2 320 F invalide.")
    if ventiler_groupe(4020, "B") != (3407, 613):
        erreurs.append("Exemple DGI 4 020 F invalide.")

    # 1. Vérification des fichiers référentiels
    chemin_ent = dossier / "entreprise.json"
    chemin_cli = dossier / "clients.json"
    chemin_art = dossier / "articles.json"
    chemin_dev = dossier / "corpus" / "dev.jsonl"
    chemin_test = dossier / "corpus" / "test.jsonl"

    for ch in (chemin_ent, chemin_cli, chemin_art, chemin_dev, chemin_test):
        if not ch.exists():
            erreurs.append(f"Fichier manquant : {ch}")
    if erreurs:
        for e in erreurs:
            print(f"[ERREUR] {e}", file=sys.stderr)
        return 1

    ent = json.loads(verifier_sans_bom(chemin_ent, erreurs).decode("utf-8"))
    clients_liste = json.loads(verifier_sans_bom(chemin_cli, erreurs).decode("utf-8"))
    articles_liste = json.loads(verifier_sans_bom(chemin_art, erreurs).decode("utf-8"))

    # Contrôle entreprise.json
    for cle in ("raison_sociale", "ifu", "rccm", "adresse", "telephone", "email", "regime_fiscal", "nim_simule", "utilisateurs"):
        if cle not in ent:
            erreurs.append(f"entreprise.json : champ '{cle}' manquant.")
    if not (isinstance(ent.get("ifu"), str) and re.fullmatch(r"99\d{11}", ent["ifu"])):
        erreurs.append("entreprise.json : IFU fictif invalide (doit avoir 13 chiffres et commencer par 99).")

    # Contrôle clients.json
    if len(clients_liste) != 15:
        erreurs.append(f"clients.json : 15 clients attendus, {len(clients_liste)} trouvés.")
    clients: dict[str, dict] = {}
    types_clients_compteur: Counter[str] = Counter()
    alias_compteur: Counter[str] = Counter()

    for c in clients_liste:
        cid = c.get("id")
        if not isinstance(cid, str) or not re.fullmatch(r"C-\d{3}", cid):
            erreurs.append(f"clients.json : id invalide {cid!r}.")
            continue
        if cid in clients:
            erreurs.append(f"clients.json : id en doublon {cid}.")
        clients[cid] = c
        for cle in ("id", "nom", "alias", "type", "ifu", "adresse", "telephone", "aib_taux", "delai_paiement_jours"):
            if cle not in c:
                erreurs.append(f"clients.json ({cid}) : champ '{cle}' manquant.")
        t = c.get("type")
        if t not in TYPES_CLIENTS:
            erreurs.append(f"clients.json ({cid}) : type invalide {t!r}.")
        types_clients_compteur[t] += 1
        ifu = c.get("ifu")
        if t == "PARTICULIER":
            if ifu is not None:
                erreurs.append(f"clients.json ({cid}) : un PARTICULIER doit avoir ifu = null.")
            if c.get("aib_taux") != 0:
                erreurs.append(f"clients.json ({cid}) : un PARTICULIER doit avoir aib_taux = 0.")
        else:
            if not (isinstance(ifu, str) and re.fullmatch(r"99\d{11}", ifu)):
                erreurs.append(f"clients.json ({cid}) : IFU fictif invalide {ifu!r}.")
        if c.get("aib_taux") not in (0, 1, 5) or not est_entier(c.get("aib_taux")):
            erreurs.append(f"clients.json ({cid}) : aib_taux invalide {c.get('aib_taux')!r}.")
        if not isinstance(c.get("alias"), list) or not c.get("alias"):
            erreurs.append(f"clients.json ({cid}) : alias doit être une liste non vide.")
        else:
            for al in set(c["alias"]):
                alias_compteur[al.lower()] += 1

    repartition_attendue = {
        "ENTREPRISE_REEL": 6,
        "ENTREPRISE_TPS": 4,
        "PARTICULIER": 3,
        "STRUCTURE_ETAT": 1,
        "CLIENT_EXPORT": 1,
    }
    for t, attendu_n in repartition_attendue.items():
        if types_clients_compteur[t] != attendu_n:
            erreurs.append(f"clients.json : {attendu_n} {t} attendus, {types_clients_compteur[t]} trouvés.")
    if not any(n >= 2 for n in alias_compteur.values()):
        erreurs.append("clients.json : au moins deux clients doivent partager un alias pour l'ambiguïté.")

    # Contrôle articles.json
    if len(articles_liste) != 25:
        erreurs.append(f"articles.json : 25 articles attendus, {len(articles_liste)} trouvés.")
    articles: dict[str, dict] = {}
    nb_groupe_a = 0
    nb_decimaux = 0
    nb_livraison = 0

    for a in articles_liste:
        aid = a.get("id")
        if not isinstance(aid, str) or not re.fullmatch(r"A-\d{3}", aid):
            erreurs.append(f"articles.json : id invalide {aid!r}.")
            continue
        if aid in articles:
            erreurs.append(f"articles.json : id en doublon {aid}.")
        articles[aid] = a
        for cle in ("id", "designation", "alias", "unite", "prix_unitaire_ttc", "groupe_taxe", "quantite_decimale"):
            if cle not in a:
                erreurs.append(f"articles.json ({aid}) : champ '{cle}' manquant.")
        if not est_entier(a.get("prix_unitaire_ttc")) or a["prix_unitaire_ttc"] <= 0:
            erreurs.append(f"articles.json ({aid}) : prix_unitaire_ttc doit être un entier strictement positif.")
        if a.get("groupe_taxe") == "A":
            nb_groupe_a += 1
            if a.get("a_verifier") is not True:
                erreurs.append(f"articles.json ({aid}) : article en groupe A doit avoir 'a_verifier': true.")
        elif a.get("groupe_taxe") != "B":
            erreurs.append(f"articles.json ({aid}) : groupe_taxe inattendu {a.get('groupe_taxe')!r}.")
        if not isinstance(a.get("quantite_decimale"), bool):
            erreurs.append(f"articles.json ({aid}) : quantite_decimale doit être un booléen.")
        elif a["quantite_decimale"]:
            nb_decimaux += 1
        if a.get("designation") == "Livraison Cotonou" and a.get("unite") == "forfait" and a.get("groupe_taxe") == "B":
            nb_livraison += 1

    if nb_groupe_a != 2:
        erreurs.append(f"articles.json : 2 articles en groupe A attendus, {nb_groupe_a} trouvés.")
    if nb_decimaux != 3:
        erreurs.append(f"articles.json : 3 articles à quantité décimale attendus, {nb_decimaux} trouvés.")
    if nb_livraison != 1:
        erreurs.append(f"articles.json : 1 article service 'Livraison Cotonou' (forfait, groupe B) attendu, {nb_livraison} trouvé.")

    # 2. Lecture et contrôle des fichiers corpus/dev.jsonl et corpus/test.jsonl
    lignes_dev = [l for l in verifier_sans_bom(chemin_dev, erreurs).decode("utf-8").splitlines() if l.strip()]
    lignes_test = [l for l in verifier_sans_bom(chemin_test, erreurs).decode("utf-8").splitlines() if l.strip()]

    if len(lignes_dev) != 20:
        erreurs.append(f"dev.jsonl : 20 messages attendus, {len(lignes_dev)} trouvés.")
    if len(lignes_test) != 40:
        erreurs.append(f"test.jsonl : 40 messages attendus, {len(lignes_test)} trouvés.")

    messages_dev = [json.loads(l) for l in lignes_dev]
    messages_test = [json.loads(l) for l in lignes_test]
    tous_messages = messages_dev + messages_test

    ids_vus: set[str] = set()
    par_split: dict[str, dict[str, dict]] = {"dev": {}, "test": {}}

    for split_attendu, liste in (("dev", messages_dev), ("test", messages_test)):
        for idx, m in enumerate(liste, start=1):
            mid = m.get("id", f"{split_attendu}#{idx}")
            if not isinstance(mid, str):
                erreurs.append(f"{split_attendu} ligne {idx} : id manquant ou non chaîne.")
                continue
            if mid in ids_vus:
                erreurs.append(f"{mid} : identifiant de message en doublon.")
            ids_vus.add(mid)
            par_split[split_attendu][mid] = m

            # Présence exacte des champs de premier niveau
            manquants = CHAMPS_MESSAGE - set(m.keys())
            inconnus = set(m.keys()) - CHAMPS_MESSAGE
            if manquants:
                erreurs.append(f"{mid} : champs manquants {sorted(manquants)}.")
            if inconnus:
                erreurs.append(f"{mid} : champs non prévus {sorted(inconnus)}.")
            if m.get("split") != split_attendu:
                erreurs.append(f"{mid} : split vaut {m.get('split')!r}, attendu {split_attendu!r}.")
            if m.get("canal") not in CANAUX_AUTORISES:
                erreurs.append(f"{mid} : canal invalide {m.get('canal')!r}.")
            try:
                datetime.fromisoformat(m.get("date_reception", ""))
            except ValueError:
                erreurs.append(f"{mid} : date_reception ISO invalide {m.get('date_reception')!r}.")
            if not isinstance(m.get("auteur_affiche"), str) or not m["auteur_affiche"].strip():
                erreurs.append(f"{mid} : auteur_affiche invalide.")
            if not isinstance(m.get("texte_commande"), str) or not m["texte_commande"].strip():
                erreurs.append(f"{mid} : texte_commande vide ou invalide.")
            if m.get("texte_livraison") is not None and (
                not isinstance(m["texte_livraison"], str) or not m["texte_livraison"].strip()
            ):
                erreurs.append(f"{mid} : texte_livraison doit être null ou une chaîne non vide.")
            if not isinstance(m.get("commentaire"), str) or not m["commentaire"].strip():
                erreurs.append(f"{mid} : commentaire vide ou invalide.")

            texte_cmd = m.get("texte_commande", "")
            texte_bl = m.get("texte_livraison")

            # Contrôle du bloc attendu
            att = m.get("attendu")
            if not isinstance(att, dict):
                erreurs.append(f"{mid} : 'attendu' doit être un objet.")
                continue
            if set(att.keys()) != CHAMPS_ATTENDU:
                erreurs.append(f"{mid} : clés de 'attendu' invalides ({sorted(att.keys())}).")

            # Client attendu
            cl = att.get("client", {})
            if not isinstance(cl, dict) or set(cl.keys()) != {"id_referentiel", "citation"}:
                erreurs.append(f"{mid} : structure attendu.client invalide.")
            else:
                cid = cl["id_referentiel"]
                cit_c = cl["citation"]
                if cid is not None and cid not in clients:
                    erreurs.append(f"{mid} : client.id_referentiel {cid!r} inconnu de clients.json.")
                if cid is not None and not cit_c:
                    erreurs.append(f"{mid} : client.citation obligatoire quand id_referentiel est non null.")
                if cit_c is not None:
                    if not isinstance(cit_c, str) or not cit_c or cit_c not in texte_cmd:
                        erreurs.append(
                            f"{mid} : client.citation {cit_c!r} n'est pas une sous-chaîne exacte de texte_commande."
                        )

            # Lignes attendues
            lignes = att.get("lignes")
            if not isinstance(lignes, list) or not lignes:
                erreurs.append(f"{mid} : attendu.lignes doit être une liste non vide.")
                lignes = []
            for i_l, l in enumerate(lignes, start=1):
                if not isinstance(l, dict) or set(l.keys()) != CHAMPS_LIGNE_ATTENDUE:
                    erreurs.append(f"{mid} ligne {i_l} : clés invalides {sorted(l.keys()) if isinstance(l, dict) else l}.")
                    continue
                aid = l["article_id"]
                if aid is not None and aid not in articles:
                    erreurs.append(f"{mid} ligne {i_l} : article_id {aid!r} inconnu de articles.json.")
                cit_d = l["citation_designation"]
                if not isinstance(cit_d, str) or not cit_d or cit_d not in texte_cmd:
                    erreurs.append(
                        f"{mid} ligne {i_l} : citation_designation {cit_d!r} absente de texte_commande."
                    )
                qc = l["quantite_commandee"]
                cit_qc = l["citation_quantite_commandee"]
                if qc is None:
                    if cit_qc is not None:
                        erreurs.append(f"{mid} ligne {i_l} : citation_quantite_commandee doit être null si quantite_commandee est null.")
                else:
                    if not isinstance(qc, str):
                        erreurs.append(f"{mid} ligne {i_l} : quantite_commandee doit être une chaîne ({qc!r}).")
                    if not isinstance(cit_qc, str) or not cit_qc or cit_qc not in texte_cmd:
                        erreurs.append(
                            f"{mid} ligne {i_l} : citation_quantite_commandee {cit_qc!r} absente de texte_commande."
                        )
                ql = l["quantite_livree"]
                if texte_bl is None:
                    if ql is not None:
                        erreurs.append(f"{mid} ligne {i_l} : quantite_livree doit être null sans bon de livraison.")
                else:
                    if ql is not None and not isinstance(ql, str):
                        erreurs.append(f"{mid} ligne {i_l} : quantite_livree doit être une chaîne ou null.")

                pu_cite = l["prix_unitaire_ttc_cite"]
                cit_pu = l["citation_prix"]
                if pu_cite is None:
                    if cit_pu is not None:
                        erreurs.append(f"{mid} ligne {i_l} : citation_prix doit être null si prix_unitaire_ttc_cite est null.")
                else:
                    if not est_entier(pu_cite):
                        erreurs.append(f"{mid} ligne {i_l} : prix_unitaire_ttc_cite doit être un entier ({pu_cite!r}).")
                    if not isinstance(cit_pu, str) or not cit_pu or cit_pu not in texte_cmd:
                        erreurs.append(
                            f"{mid} ligne {i_l} : citation_prix {cit_pu!r} absente de texte_commande."
                        )

            # Mode de paiement
            mp = att.get("mode_paiement")
            cit_mp = att.get("citation_paiement")
            if mp is None:
                if cit_mp is not None:
                    erreurs.append(f"{mid} : citation_paiement doit être null si mode_paiement est null.")
            else:
                if mp not in MODES_PAIEMENT:
                    erreurs.append(f"{mid} : mode_paiement invalide {mp!r}.")
                if not isinstance(cit_mp, str) or not cit_mp or cit_mp not in texte_cmd:
                    erreurs.append(f"{mid} : citation_paiement {cit_mp!r} absente de texte_commande.")

            # Total TTC cité
            tot_cite = att.get("total_ttc_cite")
            if tot_cite is not None and not est_entier(tot_cite):
                erreurs.append(f"{mid} : total_ttc_cite doit être un entier ou null ({tot_cite!r}).")

            # Remise demandée
            rem = att.get("remise_demandee")
            if rem is not None:
                if not isinstance(rem, dict) or set(rem.keys()) != {"type", "valeur", "citation"}:
                    erreurs.append(f"{mid} : structure remise_demandee invalide.")
                else:
                    if rem["type"] not in ("POURCENTAGE", "MONTANT"):
                        erreurs.append(f"{mid} : remise_demandee.type invalide {rem['type']!r}.")
                    if not est_entier(rem["valeur"]) or rem["valeur"] <= 0:
                        erreurs.append(f"{mid} : remise_demandee.valeur doit être un entier positif.")
                    if not isinstance(rem["citation"], str) or not rem["citation"] or rem["citation"] not in texte_cmd:
                        erreurs.append(f"{mid} : remise_demandee.citation {rem['citation']!r} absente de texte_commande.")

            # Anomalies attendues
            anom = m.get("anomalies_attendues")
            if not isinstance(anom, list):
                erreurs.append(f"{mid} : anomalies_attendues doit être une liste.")
                anom = []
            for code in anom:
                if code not in ANOMALIES_AUTORISEES:
                    erreurs.append(f"{mid} : code d'anomalie inconnu {code!r}.")
            if len(anom) != len(set(anom)):
                erreurs.append(f"{mid} : doublon dans anomalies_attendues {anom}.")

            # Pièges
            pieges = m.get("pieges")
            if not isinstance(pieges, list):
                erreurs.append(f"{mid} : pieges doit être une liste.")
            else:
                for p in pieges:
                    if p not in PIEGES_CONNUS:
                        erreurs.append(f"{mid} : piège inconnu {p!r}.")

            # Cohérence logique doublon_de
            doublon_de = m.get("doublon_de")
            if "DOUBLON_PROBABLE" in anom:
                if not doublon_de or doublon_de not in par_split[split_attendu] or doublon_de == mid:
                    erreurs.append(
                        f"{mid} : DOUBLON_PROBABLE exige un doublon_de présent plus haut dans le même fichier ({split_attendu})."
                    )
                else:
                    orig = par_split[split_attendu][doublon_de]
                    dt_cur = datetime.fromisoformat(m["date_reception"])
                    dt_orig = datetime.fromisoformat(orig["date_reception"])
                    delta_h = (dt_cur - dt_orig).total_seconds() / 3600
                    if not (0 <= delta_h <= 72):
                        erreurs.append(f"{mid} : doublon_de {doublon_de} hors fenêtre de 72 h ({delta_h:.1f} h).")
                    if orig["attendu"]["client"]["id_referentiel"] != att["client"]["id_referentiel"]:
                        erreurs.append(f"{mid} : doublon_de {doublon_de} n'a pas le même client.")
                    sig_cur = sorted((l["article_id"], l["quantite_commandee"]) for l in att["lignes"])
                    sig_orig = sorted((l["article_id"], l["quantite_commandee"]) for l in orig["attendu"]["lignes"])
                    if sig_cur != sig_orig:
                        erreurs.append(f"{mid} : doublon_de {doublon_de} n'a pas les mêmes lignes commandées.")
            else:
                if doublon_de is not None:
                    erreurs.append(f"{mid} : doublon_de doit être null sans DOUBLON_PROBABLE.")

            # Cohérence logique des autres anomalies avec attendu
            ensemble_anom = set(anom)
            if (rem is not None) != ("REMISE_A_VALIDER" in ensemble_anom):
                erreurs.append(f"{mid} : incohérence entre remise_demandee et REMISE_A_VALIDER.")

            cid_att = att["client"]["id_referentiel"]
            if cid_att is None:
                if not ({"CLIENT_INCONNU", "CLIENT_AMBIGU"} & ensemble_anom):
                    erreurs.append(f"{mid} : client.id_referentiel est null sans CLIENT_INCONNU ni CLIENT_AMBIGU.")
            else:
                if {"CLIENT_INCONNU", "CLIENT_AMBIGU"} & ensemble_anom:
                    erreurs.append(f"{mid} : client.id_referentiel renseigné alors que CLIENT_INCONNU ou CLIENT_AMBIGU est présent.")

            art_inc_reel = any(l["article_id"] is None for l in lignes)
            if art_inc_reel != ("ARTICLE_INCONNU" in ensemble_anom):
                erreurs.append(f"{mid} : incohérence entre article_id=null et ARTICLE_INCONNU.")

            qte_manq_reel = any(l["article_id"] is not None and l["quantite_commandee"] is None for l in lignes)
            if qte_manq_reel != ("QUANTITE_MANQUANTE" in ensemble_anom):
                erreurs.append(f"{mid} : incohérence entre quantite_commandee=null et QUANTITE_MANQUANTE.")

            qte_inv_reel = False
            for l in lignes:
                if l["article_id"] is not None and l["quantite_commandee"] is not None:
                    art_o = articles[l["article_id"]]
                    try:
                        qd = Decimal(l["quantite_commandee"])
                        if qd <= 0 or qd != qd.quantize(Decimal("0.001")):
                            qte_inv_reel = True
                        elif not art_o["quantite_decimale"] and qd != qd.to_integral_value():
                            qte_inv_reel = True
                    except InvalidOperation:
                        qte_inv_reel = True
            if qte_inv_reel != ("QUANTITE_INVALIDE" in ensemble_anom):
                erreurs.append(f"{mid} : incohérence entre quantité commandée et QUANTITE_INVALIDE.")

            ecart_reel = any(
                l["quantite_livree"] is not None
                and l["quantite_commandee"] is not None
                and Decimal(l["quantite_livree"]) != Decimal(l["quantite_commandee"])
                for l in lignes
            )
            if ecart_reel != ("ECART_COMMANDE_LIVRAISON" in ensemble_anom):
                erreurs.append(f"{mid} : incohérence entre quantités commandées/livrées et ECART_COMMANDE_LIVRAISON.")

            prix_inhab_reel = False
            for l in lignes:
                if l["article_id"] and l["prix_unitaire_ttc_cite"] is not None:
                    pu_cat = Decimal(articles[l["article_id"]]["prix_unitaire_ttc"])
                    ecart_p = abs(Decimal(l["prix_unitaire_ttc_cite"]) - pu_cat) / pu_cat
                    if ecart_p > Decimal("0.15"):
                        prix_inhab_reel = True
            if prix_inhab_reel != ("PRIX_INHABITUEL" in ensemble_anom):
                erreurs.append(f"{mid} : incohérence entre prix cité (>15%) et PRIX_INHABITUEL.")

            if tot_cite is not None and not art_inc_reel and not qte_manq_reel and not qte_inv_reel:
                tot_cmd_recalc = sum(
                    arrondi_franc(Decimal(l["quantite_commandee"]) * Decimal(articles[l["article_id"]]["prix_unitaire_ttc"]))
                    for l in lignes
                )
                tot_incoh_reel = tot_cite != tot_cmd_recalc
                if tot_incoh_reel != ("TOTAL_INCOHERENT" in ensemble_anom):
                    erreurs.append(
                        f"{mid} : incohérence entre total_ttc_cite ({tot_cite}) et total recalculé ({tot_cmd_recalc}) pour TOTAL_INCOHERENT."
                    )
            elif "TOTAL_INCOHERENT" in ensemble_anom and tot_cite is None:
                erreurs.append(f"{mid} : TOTAL_INCOHERENT présent alors que total_ttc_cite est null.")

            # Facture attendue
            fa = m.get("facture_attendue")
            a_bloquante = bool(ensemble_anom & ANOMALIES_BLOQUANTES)
            if a_bloquante:
                if fa is not None:
                    erreurs.append(
                        f"{mid} : facture_attendue doit être null car anomalie bloquante présente ({sorted(ensemble_anom & ANOMALIES_BLOQUANTES)})."
                    )
            else:
                if not isinstance(fa, dict):
                    erreurs.append(f"{mid} : facture_attendue obligatoire (aucune anomalie bloquante).")
                else:
                    if set(fa.keys()) != CHAMPS_FACTURE_ATTENDUE:
                        erreurs.append(f"{mid} : clés de facture_attendue invalides ({sorted(fa.keys())}).")
                    recalc = recalculer_facture(m, clients, articles)
                    if fa != recalc:
                        erreurs.append(
                            f"{mid} : écart sur facture_attendue.\n  Attendu   : {fa}\n  Recalculé : {recalc}"
                        )

    # 3. Vérification des formulations distinctes entre dev et test
    textes_dev = {m["texte_commande"].strip().lower() for m in messages_dev}
    for m in messages_test:
        if m["texte_commande"].strip().lower() in textes_dev:
            erreurs.append(f"{m['id']} : texte_commande réutilisé depuis dev.jsonl.")

    # 4. Vérification des quotas (section 7)
    def compter_situations(msgs: list[dict]) -> dict[str, int]:
        c: dict[str, int] = Counter()
        for m in msgs:
            anom = set(m["anomalies_attendues"])
            att = m["attendu"]
            cid = att["client"]["id_referentiel"]
            if not anom and m["facture_attendue"] is not None:
                c["AUCUNE_ANOMALIE"] += 1
                if cid and clients[cid]["aib_taux"] in (1, 5):
                    c["CLIENT_AIB_SANS_ANOMALIE"] += 1
            for code in anom:
                c[code] += 1
            # Article à quantité décimale (avec décimale effective, ex. « 2.5 »)
            a_qte_dec = False
            for l in att["lignes"]:
                aid = l["article_id"]
                qc = l["quantite_commandee"]
                if aid and articles[aid]["quantite_decimale"] and qc:
                    try:
                        qd = Decimal(qc)
                        if qd != qd.to_integral_value():
                            a_qte_dec = True
                    except InvalidOperation:
                        pass
            if a_qte_dec:
                c["ARTICLE_QUANTITE_DECIMALE"] += 1
        return c

    quotas_min = [
        ("AUCUNE_ANOMALIE", "Aucune anomalie (facture attendue complète)", 14, 4, 9),
        ("ECART_COMMANDE_LIVRAISON", "ECART_COMMANDE_LIVRAISON", 8, 2, 5),
        ("CLIENT_INCONNU", "CLIENT_INCONNU", 4, 1, 2),
        ("CLIENT_AMBIGU", "CLIENT_AMBIGU", 3, 1, 2),
        ("ARTICLE_INCONNU", "ARTICLE_INCONNU", 4, 1, 2),
        ("QUANTITE_MANQUANTE", "QUANTITE_MANQUANTE", 4, 1, 2),
        ("QUANTITE_INVALIDE", "QUANTITE_INVALIDE", 2, 1, 1),
        ("PRIX_INHABITUEL", "PRIX_INHABITUEL", 5, 1, 3),
        ("TOTAL_INCOHERENT", "TOTAL_INCOHERENT", 4, 1, 2),
        ("DOUBLON_PROBABLE", "DOUBLON_PROBABLE", 3, 1, 2),
        ("REMISE_A_VALIDER", "REMISE_A_VALIDER", 3, 1, 2),
        ("INSTRUCTION_SUSPECTE", "INSTRUCTION_SUSPECTE", 3, 1, 2),
        ("CLIENT_AIB_SANS_ANOMALIE", "Client avec AIB 1 % ou 5 % sans anomalie", 4, 1, 2),
        ("ARTICLE_QUANTITE_DECIMALE", "Article à quantité décimale (« 2,5 kg »)", 3, 1, 2),
    ]

    c_dev = compter_situations(messages_dev)
    c_test = compter_situations(messages_test)
    c_tot = compter_situations(tous_messages)

    for cle, libelle, min_tot, min_dev, min_test in quotas_min:
        if c_tot[cle] < min_tot:
            erreurs.append(f"Quota global insuffisant pour '{libelle}' : {c_tot[cle]} < {min_tot}.")
        if c_dev[cle] < min_dev:
            erreurs.append(f"Quota dev insuffisant pour '{libelle}' : {c_dev[cle]} < {min_dev}.")
        if c_test[cle] < min_test:
            erreurs.append(f"Quota test insuffisant pour '{libelle}' : {c_test[cle]} < {min_test}.")

    if erreurs:
        print(f"ÉCHEC : {len(erreurs)} erreur(s) détectée(s) :", file=sys.stderr)
        for e in erreurs:
            print(f"  - {e}", file=sys.stderr)
        return 1

    # 5. Affichage du rapport final et de l'empreinte SHA-256 de test.jsonl
    sha256_test = hashlib.sha256(chemin_test.read_bytes()).hexdigest()
    nb_factures_calc = sum(1 for m in tous_messages if m["facture_attendue"] is not None)

    print("=== VÉRIFICATION DU CORPUS ET DES RÉFÉRENTIELS : SUCCÈS ===")
    print(f"Entreprise : {ent['raison_sociale']} (IFU {ent['ifu']}, régime {ent['regime_fiscal']})")
    print(f"Clients    : {len(clients_liste)} ({dict(types_clients_compteur)})")
    print(f"Articles   : {len(articles_liste)} (groupe B : {len(articles_liste) - nb_groupe_a}, groupe A à vérifier : {nb_groupe_a}, décimaux : {nb_decimaux})")
    print(f"Messages   : {len(tous_messages)} (dev : {len(messages_dev)}, test : {len(messages_test)})")
    print(f"Factures recalculées au franc près : {nb_factures_calc} (exemples DGI 2 320 F -> 1 966 + 354 ; 4 020 F -> 3 407 + 613 : OK)")
    print()
    print("--- Répartition des situations et anomalies (Quotas section 7) ---")
    print(f"{'Situation':<44} | {'Min':>3} | {'Dev':>3} | {'Test':>4} | {'Total':>5}")
    print("-" * 70)
    for cle, libelle, min_tot, _, _ in quotas_min:
        print(f"{libelle:<44} | {min_tot:>3} | {c_dev[cle]:>3} | {c_test[cle]:>4} | {c_tot[cle]:>5}")

    print()
    print("--- Répartition des canaux ---")
    canaux_dev = Counter(m["canal"] for m in messages_dev)
    canaux_test = Counter(m["canal"] for m in messages_test)
    canaux_tot = Counter(m["canal"] for m in tous_messages)
    for canal in ("WHATSAPP", "SMS", "EMAIL", "VOCAL_TRANSCRIT"):
        pct = 100 * canaux_tot[canal] / len(tous_messages)
        print(f"  {canal:<16} : dev={canaux_dev[canal]:>2}, test={canaux_test[canal]:>2}, total={canaux_tot[canal]:>2} ({pct:.1f} %)")

    print()
    print("--- Répartition des pièges de forme ---")
    pieges_dev = Counter(p for m in messages_dev for p in m["pieges"])
    pieges_test = Counter(p for m in messages_test for p in m["pieges"])
    pieges_tot = Counter(p for m in tous_messages for p in m["pieges"])
    for p in sorted(PIEGES_CONNUS):
        print(f"  {p:<28} : dev={pieges_dev[p]:>2}, test={pieges_test[p]:>2}, total={pieges_tot[p]:>2}")

    print()
    print(f"SHA-256 test.jsonl : {sha256_test}")
    return 0


if __name__ == "__main__":
    cible = resoudre_dossier_data(sys.argv[1] if len(sys.argv) > 1 else None)
    sys.exit(verifier(cible))
