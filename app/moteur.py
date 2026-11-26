"""Moteur de calcul déterministe des factures.

Règles (cahier des charges, section 7.2) :
- montants en francs CFA entiers, calculs en Decimal, jamais en float ;
- prix saisis TTC ; ligne = quantité × prix TTC, arrondie au franc (0,5 vers le haut) ;
- TTC additionnés par groupe de taxe ; groupes B et D : HT = arrondi(TTC / 1,18), TVA = TTC − HT ;
  groupes A, C et E : TVA nulle ;
- AIB = arrondi(total HT × taux / 100) ; net à payer = TTC − AIB.

Ce module est pur : il ne dépend ni de la base, ni du web, ni de l'IA.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

TAUX_TVA = Decimal("18")
GROUPES_TVA_18 = {"B", "D"}
GROUPES_SANS_TVA = {"A", "C", "E"}
GROUPES_CONNUS = GROUPES_TVA_18 | GROUPES_SANS_TVA
TAUX_AIB_AUTORISES = {0, 1, 5}
MODES_ARRONDI = {"groupe", "ligne"}


class ErreurCalcul(ValueError):
    """Donnée impossible à facturer (quantité invalide, groupe inconnu…)."""


def arrondi_franc(valeur: Decimal) -> int:
    return int(valeur.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def lire_quantite(texte: str | int | Decimal) -> Decimal:
    """Convertit une quantité (« 2,5 », « 3 », Decimal) et vérifie les règles e-MECeF."""
    try:
        q = Decimal(str(texte).strip().replace(",", "."))
    except (InvalidOperation, AttributeError):
        raise ErreurCalcul(f"Quantité illisible : {texte!r}")
    if not q.is_finite() or q <= 0:
        raise ErreurCalcul("La quantité doit être strictement positive.")
    if q != q.quantize(Decimal("0.001")):
        raise ErreurCalcul("La quantité accepte au plus 3 décimales.")
    return Decimal(format(q.normalize(), "f"))  # « 10 » et non « 1E+1 »


@dataclass(frozen=True)
class Ligne:
    designation: str
    quantite: Decimal
    prix_unitaire_ttc: int
    groupe: str
    article_id: str | None = None

    @property
    def montant_ttc(self) -> int:
        return arrondi_franc(self.quantite * Decimal(self.prix_unitaire_ttc))


@dataclass
class TotalGroupe:
    ttc: int = 0
    ht: int = 0
    tva: int = 0


@dataclass
class Totaux:
    lignes: list[dict]
    par_groupe: dict[str, TotalGroupe] = field(default_factory=dict)
    total_ttc: int = 0
    total_ht: int = 0
    total_tva: int = 0
    aib_taux: int = 0
    aib_montant: int = 0
    net_a_payer: int = 0

    def en_dict(self) -> dict:
        return {
            "lignes": self.lignes,
            "par_groupe": {g: vars(t) for g, t in sorted(self.par_groupe.items())},
            "total_ttc": self.total_ttc,
            "total_ht": self.total_ht,
            "total_tva": self.total_tva,
            "aib_taux": self.aib_taux,
            "aib_montant": self.aib_montant,
            "net_a_payer": self.net_a_payer,
        }


def ventiler(ttc: int, groupe: str) -> tuple[int, int]:
    """Renvoie (HT, TVA) pour un montant TTC d'un groupe donné."""
    if groupe in GROUPES_TVA_18:
        ht = arrondi_franc(Decimal(ttc) * 100 / (100 + TAUX_TVA))
        return ht, ttc - ht
    if groupe in GROUPES_SANS_TVA:
        return ttc, 0
    raise ErreurCalcul(f"Groupe de taxe non pris en charge : {groupe!r}")


def calculer(lignes: list[Ligne], aib_taux: int = 0, mode_arrondi: str = "groupe") -> Totaux:
    if not lignes:
        raise ErreurCalcul("Une facture doit contenir au moins une ligne.")
    if aib_taux not in TAUX_AIB_AUTORISES:
        raise ErreurCalcul(f"Taux d'AIB non autorisé : {aib_taux}")
    if mode_arrondi not in MODES_ARRONDI:
        raise ErreurCalcul(f"Mode d'arrondi inconnu : {mode_arrondi}")

    detail = []
    par_groupe: dict[str, TotalGroupe] = {}
    for ligne in lignes:
        if ligne.groupe not in GROUPES_CONNUS:
            raise ErreurCalcul(f"Groupe de taxe non pris en charge : {ligne.groupe!r}")
        if ligne.prix_unitaire_ttc < 0:
            raise ErreurCalcul("Un prix ne peut pas être négatif.")
        montant = ligne.montant_ttc
        detail.append({
            "article_id": ligne.article_id,
            "designation": ligne.designation,
            "quantite": format(ligne.quantite, "f"),
            "prix_unitaire_ttc": ligne.prix_unitaire_ttc,
            "montant_ttc": montant,
            "groupe": ligne.groupe,
        })
        total = par_groupe.setdefault(ligne.groupe, TotalGroupe())
        total.ttc += montant
        if mode_arrondi == "ligne":
            ht, tva = ventiler(montant, ligne.groupe)
            total.ht += ht
            total.tva += tva

    if not any(d["montant_ttc"] > 0 for d in detail):
        raise ErreurCalcul("Au moins une ligne doit avoir un montant supérieur à 0.")

    if mode_arrondi == "groupe":
        for groupe, total in par_groupe.items():
            total.ht, total.tva = ventiler(total.ttc, groupe)

    t = Totaux(lignes=detail, par_groupe=par_groupe)
    t.total_ttc = sum(g.ttc for g in par_groupe.values())
    t.total_ht = sum(g.ht for g in par_groupe.values())
    t.total_tva = sum(g.tva for g in par_groupe.values())
    t.aib_taux = aib_taux
    t.aib_montant = arrondi_franc(Decimal(t.total_ht) * aib_taux / 100)
    t.net_a_payer = t.total_ttc - t.aib_montant
    return t


def format_fcfa(montant: int) -> str:
    """31500 -> « 31 500 F » (espace insécable fine comme séparateur)."""
    signe = "-" if montant < 0 else ""
    return f"{signe}{abs(montant):,}".replace(",", " ") + " F"
