"""Vérifie en un appel réel que chaque IA configurée dans .env répond (clé, modèle, quota).

Usage :
    python -m eval.verifier_ia            # toutes les IA dont la clé est renseignée
    python -m eval.verifier_ia groq       # une seule

Un appel par modèle principal, sans cache ni modèle de secours. Message fictif.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from app import extraction as E  # noqa: E402
from app.web import _charger_env  # noqa: E402

MESSAGE = "Bjr, c Dossou. Envoie moi 12 cartons de savon et 5 sacs de riz stp. Je paie momo"


def main() -> int:
    _charger_env()
    noms = sys.argv[1:] or E.ia_disponibles()
    if not noms:
        print("Aucune clé d'IA dans .env (GEMINI_API_KEY, GROQ_API_KEY).")
        return 1
    E.CACHE = RACINE / "instance" / "cache_verification.json"
    E.CACHE.unlink(missing_ok=True)
    echecs = 0
    for nom in noms:
        prefixe = nom.upper() + "_"
        os.environ[prefixe + "MODELES_SECOURS"] = ""
        os.environ[prefixe + "ATTENTE_MAX"] = "15"
        debut = time.time()
        try:
            r = E.normaliser_resultat(E.extraire(nom, MESSAGE, [], []))
        except E.ErreurExtraction as e:
            echecs += 1
            print(f"ÉCHEC {nom} : {e}")
            continue
        lignes = ", ".join(f"{l['quantite']['valeur']} × {l['designation']['valeur']}" for l in r["lignes"])
        print(f"OK    {nom} ({r['modele']}, {time.time() - debut:.1f} s) : client {r['client']['valeur']!r} ;"
              f" {lignes} ; paiement {r['mode_paiement']['valeur']}")
    E.CACHE.unlink(missing_ok=True)
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
