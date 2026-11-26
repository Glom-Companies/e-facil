"""Charge un jeu de démonstration réaliste : des factures émises sur plusieurs jours et des commandes à vérifier.

Usage : python -m app.demo   (efface la base de démonstration puis la remplit)

Lecture par règles simples uniquement : aucun appel à l'IA, résultat identique à chaque fois.
Les factures sont réparties sur les derniers jours (dates fictives, relatives à aujourd'hui) pour
que le tableau de bord montre une activité ; toutes les opérations passent par les services normaux
(contrôles, validation, émission simulée, journal chaîné).
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timedelta

from . import db
from . import services as S

RACINE = S.RACINE


@contextmanager
def _horloge(jours_avant: int, heure: int, minute: int = 0):
    """Fait dater les opérations du jour voulu (aujourd'hui - jours_avant, à l'heure donnée)."""
    instant = (datetime.now() - timedelta(days=jours_avant)).replace(hour=heure, minute=minute, second=0, microsecond=0)
    origine_s, origine_db = S.maintenant, db.maintenant
    S.maintenant = db.maintenant = lambda: instant.isoformat(timespec="seconds")
    try:
        yield
    finally:
        S.maintenant, db.maintenant = origine_s, origine_db


def charger(conn=None) -> dict:
    """Réinitialise la base puis la remplit. Renvoie un résumé (factures émises, commandes à vérifier)."""
    propre = conn is None
    conn = conn or db.connecter()
    S.reinitialiser(conn)
    u = lambda login: dict(conn.execute("SELECT * FROM utilisateurs WHERE login = ?", (login,)).fetchone())  # noqa: E731
    aicha, rodrigue = u("aicha"), u("rodrigue")
    version = lambda did: conn.execute("SELECT version FROM dossiers WHERE id = ?", (did,)).fetchone()[0]  # noqa: E731
    exemples = json.loads((RACINE / "data" / "exemples.json").read_text(encoding="utf-8"))

    def facturer(texte, canal, livraison=None, decisions=()):
        did = S.creer_dossier(conn, aicha, canal, texte, livraison, "regles")
        for code, choix in decisions:
            for a in S.dossier(conn, did)["anomalies"]:
                if a["code"] == code and a["cle_decision"] and not a["resolue"]:
                    S.decider(conn, rodrigue, did, version(did), a["cle_decision"], choix)
        fid = S.valider(conn, rodrigue, did, version(did))
        S.emettre(conn, rodrigue, fid)
        return fid

    # Factures émises, une ou deux par jour sur les cinq derniers jours.
    with _horloge(5, 9, 12):
        f1 = facturer("Bjr c Houngbédji, 10 packs d'eau minérale et 4 cartons de jus. Paiement par chèque", "SMS")
    with _horloge(4, 10, 40):
        facturer("Bonjour, ici la cantine de Bohicon : 6 sacs de riz et 2 sacs de farine. Virement.", "EMAIL")
    with _horloge(3, 11, 5):
        f3 = facturer("Mme Chabi : 2,5 kg de gari et 3 litres d'huile rouge, je paie momo", "VOCAL_TRANSCRIT")
    with _horloge(2, 15, 30):
        f4 = facturer("C'est Sossou du restaurant. Envoie 3 cartons de sardines et 5 cartons de pâtes. Je paie cash",
                      "WHATSAPP")
    with _horloge(1, 9, 50):
        facturer("Kpadonou ici : 4 sacs de farine, 2 cartons de sucre et 1 livraison. Virement fin de semaine", "WHATSAPP")

    # Paiements simulés : un partiel, deux complets.
    with _horloge(3, 11, 20):
        S.enregistrer_paiement(conn, rodrigue, f3, S.facture(conn, f3)["reste_a_payer"], "MOBILEMONEY", "MM-TEST-0001")
    with _horloge(3, 16, 0):
        S.enregistrer_paiement(conn, rodrigue, f1, S.facture(conn, f1)["reste_a_payer"] // 2, "CHEQUES", "CHQ-TEST-0001")
    with _horloge(1, 17, 45):
        S.enregistrer_paiement(conn, rodrigue, f4, S.facture(conn, f4)["reste_a_payer"], "ESPECES", "ESP-TEST-0001")

    # Commandes du jour à vérifier : les exemples de la page « Nouvelle commande ».
    for e in exemples[:5]:
        S.creer_dossier(conn, aicha, e["canal"], e["commande"], e.get("livraison") or None, "regles")

    resume = {"factures": conn.execute("SELECT COUNT(*) FROM factures").fetchone()[0],
              "a_verifier": conn.execute("SELECT COUNT(*) FROM dossiers WHERE statut = 'BROUILLON'").fetchone()[0]}
    if propre:
        conn.close()
    return resume


if __name__ == "__main__":
    r = charger()
    print(f"Démonstration chargée : {r['factures']} factures émises, {r['a_verifier']} commandes à vérifier.")
