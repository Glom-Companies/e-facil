"""Mesure de l'apport de l'IA sur le corpus (cahier des charges, section 9.3).

Usage :
    python -m eval.mesurer data/corpus/test.jsonl --configs S0 S1 S2
    python -m eval.mesurer data/corpus/dev.jsonl --configs S0 S2 S3

Configurations :
    S0  règles simples, sans IA ;
    S1  IA Gemini seule (aucune vérification des citations) ;
    S2  IA Gemini + vérification des citations et des référentiels (configuration de la démo) ;
    S3  IA locale Ollama + vérifications.

Le format du corpus est décrit dans data/corpus/README.md.
Les appels à l'IA sont mis en cache (instance/cache_extraction.json) : relancer ne coûte rien.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from app import brouillon as B  # noqa: E402
from app.extraction import ErreurExtraction, extraire, normaliser_resultat  # noqa: E402
from app.web import _charger_env  # noqa: E402

CONFIGS = {"S0": ("regles", True), "S1": ("gemini", False), "S2": ("gemini", True), "S3": ("ollama", True)}


def wilson(succes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = succes / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    marge = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - marge), min(1.0, centre + marge))


def egal(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except Exception:
        return str(a).strip().lower() == str(b).strip().lower()


def charger(chemin: Path) -> list[dict]:
    return [json.loads(l) for l in chemin.read_text(encoding="utf-8").splitlines() if l.strip()]


def predire(cas: dict, extracteur: str, verifier: bool, clients, articles) -> dict:
    brut = normaliser_resultat(extraire(extracteur, cas["texte_commande"], clients, articles))
    br = B.construire(brut, cas["texte_commande"], clients, articles, verifier=verifier)
    if cas.get("texte_livraison"):
        brut_bl = normaliser_resultat(extraire(extracteur, cas["texte_livraison"], clients, articles))
        br = B.integrer_livraison(br, brut_bl, cas["texte_livraison"], articles, verifier=verifier)
    return br


def comparer(cas: dict, br: dict, clients, articles, compteurs: dict) -> None:
    att = cas["attendu"]

    def champ(nom, attendu, predit):
        c = compteurs.setdefault(nom, {"justes": 0, "total": 0, "inventes": 0, "vides_a_tort": 0, "attendus_vides": 0})
        c["total"] += 1
        if egal(attendu, predit):
            c["justes"] += 1
        elif attendu is None and predit is not None:
            c["inventes"] += 1
        elif attendu is not None and predit is None:
            c["vides_a_tort"] += 1
        if attendu is None:
            c["attendus_vides"] += 1

    champ("client", att["client"]["id_referentiel"], br["client"].get("id"))
    champ("mode_paiement", att.get("mode_paiement"), br["mode_paiement"].get("valeur"))
    champ("total_cite", att.get("total_ttc_cite"), br["total_cite"].get("valeur"))
    predites = {l["article_id"]: l for l in br["lignes"] if l.get("article_id")}
    attendues = {l["article_id"]: l for l in att["lignes"] if l.get("article_id")}
    for aid, la in attendues.items():
        lp = predites.get(aid, {})
        champ("ligne_article", aid, lp.get("article_id"))
        champ("quantite_commandee", la.get("quantite_commandee"), lp.get("quantite_commandee"))
        if cas.get("texte_livraison"):
            champ("quantite_livree", la.get("quantite_livree"), lp.get("quantite_livree"))
        champ("prix_cite", la.get("prix_unitaire_ttc_cite"), lp.get("prix_cite"))
    for aid in set(predites) - set(attendues):  # lignes inventées
        c = compteurs.setdefault("ligne_article", {"justes": 0, "total": 0, "inventes": 0, "vides_a_tort": 0,
                                                   "attendus_vides": 0})
        c["total"] += 1
        c["inventes"] += 1

    # Anomalies (hors doublon, qui dépend de l'historique des dossiers)
    aib = next((c["aib_taux"] for c in clients if c["id"] == br["client"].get("id")), 0)
    trouvees = {a["code"] for a in B.anomalies(br, clients, articles, None, aib)}
    for code in set(cas.get("anomalies_attendues", [])) - {"DOUBLON_PROBABLE"}:
        a = compteurs.setdefault("anomalie:" + code, {"detectees": 0, "total": 0})
        a["total"] += 1
        a["detectees"] += int(code in trouvees)
    if not cas.get("anomalies_attendues"):
        a = compteurs.setdefault("sans_anomalie_bloquante", {"justes": 0, "total": 0})
        a["total"] += 1
        a["justes"] += int(not any(x in B.BLOQUANTES for x in trouvees))


def main() -> None:
    _charger_env()
    p = argparse.ArgumentParser()
    p.add_argument("corpus", type=Path)
    p.add_argument("--configs", nargs="+", default=["S0", "S2"])
    p.add_argument("--data", type=Path, default=RACINE / "data")
    args = p.parse_args()

    clients = json.loads((args.data / "clients.json").read_text(encoding="utf-8"))
    articles = json.loads((args.data / "articles.json").read_text(encoding="utf-8"))
    corpus = charger(args.corpus)
    empreinte = hashlib.sha256(args.corpus.read_bytes()).hexdigest()
    rapport = {"corpus": str(args.corpus.name), "sha256": empreinte, "messages": len(corpus),
               "date": datetime.now().isoformat(timespec="seconds"), "resultats": {}}

    for nom in args.configs:
        extracteur, verifier = CONFIGS[nom]
        compteurs: dict = {}
        erreurs, debut = 0, time.time()
        for cas in corpus:
            try:
                br = predire(cas, extracteur, verifier, clients, articles)
            except ErreurExtraction as e:
                erreurs += 1
                print(f"[{nom}] {cas['id']} : {e}", file=sys.stderr)
                continue
            comparer(cas, br, clients, articles, compteurs)
        rapport["resultats"][nom] = {"compteurs": compteurs, "erreurs": erreurs,
                                     "secondes_par_message": round((time.time() - debut) / max(1, len(corpus)), 2)}

    sortie = RACINE / "eval" / f"resultats_{args.corpus.stem}.json"
    sortie.write_text(json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [f"# Mesure sur `{args.corpus.name}` ({len(corpus)} messages)", "",
          f"Empreinte SHA-256 du corpus : `{empreinte}`  ", f"Date : {rapport['date']}", "",
          "## Champs extraits", "",
          "| Configuration | Champs justes | IC 95 % | Valeurs inventées | Vides à tort | Échecs d'appel |",
          "|---|---|---|---|---|---|"]
    for nom, r in rapport["resultats"].items():
        cs = [v for k, v in r["compteurs"].items() if "justes" in v and k != "sans_anomalie_bloquante"]
        j, t = sum(c["justes"] for c in cs), sum(c["total"] for c in cs)
        inv, vides = sum(c["inventes"] for c in cs), sum(c["vides_a_tort"] for c in cs)
        lo, hi = wilson(j, t)
        md.append(f"| {nom} | {j}/{t} ({j / max(1, t):.0%}) | {lo:.0%} à {hi:.0%} | {inv} | {vides} | {r['erreurs']} |")
    md += ["", "## Anomalies détectées (hors doublons)", "", "| Configuration | Détectées | IC 95 % |", "|---|---|---|"]
    for nom, r in rapport["resultats"].items():
        an = [v for k, v in r["compteurs"].items() if k.startswith("anomalie:")]
        d, t = sum(a["detectees"] for a in an), sum(a["total"] for a in an)
        lo, hi = wilson(d, t)
        md.append(f"| {nom} | {d}/{t} ({d / max(1, t):.0%}) | {lo:.0%} à {hi:.0%} |")
    md += ["", "## Détail par champ", ""]
    for nom, r in rapport["resultats"].items():
        md.append(f"### {nom}")
        for k, v in sorted(r["compteurs"].items()):
            md.append(f"- {k} : " + ", ".join(f"{a} {b}" for a, b in v.items()))
        md.append("")
    (RACINE / "eval" / f"resultats_{args.corpus.stem}.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md[:16]))


if __name__ == "__main__":
    main()
