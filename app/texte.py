"""Outils de lecture des textes de commande : montants, quantités, normalisation, citations."""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation

NOMBRES_EN_LETTRES = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7,
    "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14,
    "quinze": 15, "seize": 16, "vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50,
    "soixante": 60, "cent": 100,
}


def sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def normaliser(s: str) -> str:
    """Minuscules, sans accents, espaces uniques : sert aux comparaisons, jamais à l'affichage."""
    s = sans_accents(s or "").lower().replace("’", "'")
    return re.sub(r"\s+", " ", s).strip()


def citation_presente(citation: str | None, source: str) -> bool:
    """Vrai si la citation figure dans la source (casse, accents et espaces ignorés)."""
    if not citation or not citation.strip():
        return False
    return normaliser(citation) in normaliser(source)


def localiser(citation: str, source: str) -> tuple[int, int] | None:
    """Position (début, fin) de la citation dans la source originale, pour la surligner."""
    if not citation:
        return None
    motif = r"\s+".join(re.escape(m) for m in citation.split())
    m = re.search(motif, source, flags=re.IGNORECASE)
    if m:
        return m.start(), m.end()
    # Repli : comparaison sans accents, position par correspondance caractère à caractère.
    src = sans_accents(source).lower()
    cit = re.sub(r"\s+", " ", sans_accents(citation).lower()).strip()
    motif = r"\s+".join(re.escape(m) for m in cit.split())
    m = re.search(motif, src)
    return (m.start(), m.end()) if m else None


MOTIF_MONTANT = re.compile(
    r"(?P<n>\d{1,3}(?:[.\s  ,]\d{3})+|\d+(?:[.,]\d+)?)\s*(?P<k>k|mille|millions?)?\b",
    re.IGNORECASE,
)


def lire_montant(texte: str | None) -> int | None:
    """« 17.500 », « 17 500 F », « 17500 CFA », « 17k », « 15 mille », « quinze mille » -> entier en F."""
    if texte is None:
        return None
    t = normaliser(str(texte))
    m = MOTIF_MONTANT.search(t)
    if m:
        brut = m.group("n")
        if re.fullmatch(r"\d{1,3}(?:[.\s  ,]\d{3})+", brut):
            valeur = Decimal(re.sub(r"\D", "", brut))  # séparateurs de milliers
        else:
            try:
                valeur = Decimal(brut.replace(",", "."))
            except InvalidOperation:
                return None
        k = (m.group("k") or "").lower()
        if k in ("k", "mille"):
            valeur *= 1000
        elif k.startswith("million"):
            valeur *= 1_000_000
        return int(valeur) if valeur == valeur.to_integral_value() else None
    # Montant en lettres simple : « quinze mille »
    mots = t.replace("-", " ").split()
    total, courant = 0, 0
    trouve = False
    for mot in mots:
        if mot in ("cent", "cents"):  # « cinq cents » = 5 × 100, « cent » seul = 100
            courant = max(courant, 1) * 100
            trouve = True
        elif mot in ("vingt", "vingts") and courant % 100 == 4:  # « quatre-vingt(s) » = 80
            courant += 76
            trouve = True
        elif mot in NOMBRES_EN_LETTRES:
            courant += NOMBRES_EN_LETTRES[mot]
            trouve = True
        elif mot == "mille":  # « mille cinq cents » = 1 500
            total += max(courant, 1) * 1000
            courant = 0
            trouve = True
    return (total + courant) if trouve else None


def lire_quantite_texte(texte: str | None) -> str | None:
    """« 12 », « 2,5 », « douze » -> chaîne décimale (« 12 », « 2.5 »), sinon None."""
    if texte is None:
        return None
    t = normaliser(str(texte))
    m = re.search(r"\d+(?:[.,]\d+)?", t)
    if m:
        return format(Decimal(m.group().replace(",", ".")).normalize(), "f")
    for mot in t.split():
        if mot in NOMBRES_EN_LETTRES:
            return str(NOMBRES_EN_LETTRES[mot])
    return None
