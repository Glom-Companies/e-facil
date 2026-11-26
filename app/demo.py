"""Charge un jeu de démonstration réaliste : quelques factures émises et des commandes à vérifier.

Usage : python -m app.demo   (efface la base de démonstration puis la remplit)
Lecture par règles simples uniquement : aucun appel à l'IA, résultat identique à chaque fois.
"""
from __future__ import annotations

import json

from . import services as S
from .db import connecter

RACINE = S.RACINE


def charger() -> None:
    conn = connecter()
    S.reinitialiser(conn)
    u = lambda login: dict(conn.execute("SELECT * FROM utilisateurs WHERE login = ?", (login,)).fetchone())  # noqa: E731
    aicha, rodrigue = u("aicha"), u("rodrigue")
    version = lambda did: conn.execute("SELECT version FROM dossiers WHERE id = ?", (did,)).fetchone()[0]  # noqa: E731
    exemples = json.loads((RACINE / "data" / "exemples.json").read_text(encoding="utf-8"))

    def traiter(texte, livraison, canal, decisions=(), emettre=True):
        did = S.creer_dossier(conn, aicha, canal, texte, livraison, "regles")
        for code, choix in decisions:
            d = S.dossier(conn, did)
            for a in d["anomalies"]:
                if a["code"] == code and a["cle_decision"] and not a["resolue"]:
                    S.decider(conn, rodrigue, did, version(did), a["cle_decision"], choix)
        fid = S.valider(conn, rodrigue, did, version(did))
        if emettre:
            S.emettre(conn, rodrigue, fid)
        return fid

    # Factures déjà émises
    f1 = traiter("Bjr c Houngbédji, 10 packs d'eau minérale et 4 cartons de jus. Paiement par chèque", None, "SMS")
    traiter("Bonjour, ici la cantine de Bohicon : 6 sacs de riz et 2 sacs de farine. Virement.", None, "EMAIL")
    f3 = traiter("Mme Chabi : 2,5 kg de gari et 3 litres d'huile rouge, je paie momo", None, "VOCAL_TRANSCRIT")
    # Un paiement partiel et un paiement complet (simulés)
    S.enregistrer_paiement(conn, rodrigue, f1, S.facture(conn, f1)["reste_a_payer"] // 2, "CHEQUES", "CHQ-TEST-0001")
    S.enregistrer_paiement(conn, rodrigue, f3, S.facture(conn, f3)["reste_a_payer"], "MOBILEMONEY", "MM-TEST-0001")

    # Commandes à vérifier (les exemples de la page « Nouvelle commande »)
    for e in exemples[:5]:
        S.creer_dossier(conn, aicha, e["canal"], e["commande"], e.get("livraison") or None, "regles")
    conn.close()
    print("Démonstration chargée : 3 factures émises, 5 commandes à vérifier.")


if __name__ == "__main__":
    charger()
