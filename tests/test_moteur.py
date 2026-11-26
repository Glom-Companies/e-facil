from decimal import Decimal

import pytest
from hypothesis import given, strategies as st

from app.moteur import ErreurCalcul, Ligne, calculer, lire_quantite, ventiler


def L(q, pu, g="B"):
    return Ligne("article", lire_quantite(q), pu, g)


# --- Exemples officiels de la DGI (annexe e-MECeF, avril 2022) ---------------

def test_exemple_dgi_2320():
    t = calculer([L("1", 2320)])
    assert (t.total_ttc, t.total_ht, t.total_tva) == (2320, 1966, 354)


def test_exemple_dgi_3_x_1340():
    t = calculer([L("3", 1340)])
    assert (t.total_ttc, t.total_ht, t.total_tva) == (4020, 3407, 613)


def test_facture_reelle_groupe_e_avec_aib():
    # Structure de la facture réelle observée : groupe E, TTC 31 500, AIB 1 %.
    t = calculer([L("1", 31500, "E")], aib_taux=1)
    assert (t.total_ttc, t.total_tva, t.aib_montant, t.net_a_payer) == (31500, 0, 315, 31185)


# --- Règles -------------------------------------------------------------------

def test_quantite_decimale_et_arrondi_ligne():
    t = calculer([L("2.5", 1333)])  # 3332,5 -> 3333
    assert t.lignes[0]["montant_ttc"] == 3333


@pytest.mark.parametrize("q", ["0", "-1", "1.2345", "abc", ""])
def test_quantites_invalides(q):
    with pytest.raises(ErreurCalcul):
        lire_quantite(q)


def test_quantite_avec_virgule():
    assert lire_quantite("2,5") == Decimal("2.5")


def test_groupe_inconnu_refuse():
    with pytest.raises(ErreurCalcul):
        calculer([L("1", 1000, "Z")])


def test_facture_vide_ou_nulle_refusee():
    with pytest.raises(ErreurCalcul):
        calculer([])
    with pytest.raises(ErreurCalcul):
        calculer([L("1", 0)])


def test_aib_non_autorise():
    with pytest.raises(ErreurCalcul):
        calculer([L("1", 1000)], aib_taux=3)


def test_groupes_mixtes():
    t = calculer([L("2", 17500, "B"), L("1", 5000, "A")], aib_taux=1)
    assert t.par_groupe["B"].ttc == 35000
    assert t.par_groupe["B"].ht == 29661 and t.par_groupe["B"].tva == 5339
    assert t.par_groupe["A"].ht == 5000 and t.par_groupe["A"].tva == 0
    assert t.total_ttc == 40000
    assert t.aib_montant == round((29661 + 5000) / 100)
    assert t.net_a_payer == t.total_ttc - t.aib_montant


def test_mode_par_ligne_peut_differer_du_mode_par_groupe():
    lignes = [L("1", 1001), L("1", 1001), L("1", 1001)]
    g = calculer(lignes, mode_arrondi="groupe")
    l = calculer(lignes, mode_arrondi="ligne")
    assert g.total_ttc == l.total_ttc == 3003
    assert g.total_ht + g.total_tva == l.total_ht + l.total_tva == 3003


# --- Propriétés ---------------------------------------------------------------

montants = st.integers(min_value=1, max_value=50_000_000)
quantites = st.decimals(min_value=Decimal("0.001"), max_value=Decimal("10000"), places=3)
groupes = st.sampled_from(["A", "B", "C", "D", "E"])


@given(montants, groupes)
def test_ventilation_conserve_le_ttc(ttc, g):
    ht, tva = ventiler(ttc, g)
    assert ht + tva == ttc and ht >= 0 and tva >= 0


@given(st.lists(st.tuples(quantites, st.integers(0, 2_000_000), groupes), min_size=1, max_size=15),
       st.sampled_from([0, 1, 5]), st.sampled_from(["groupe", "ligne"]))
def test_proprietes_totaux(lignes, aib, mode):
    objets = [Ligne("x", q, pu, g) for q, pu, g in lignes]
    try:
        t = calculer(objets, aib_taux=aib, mode_arrondi=mode)
    except ErreurCalcul:
        assert all(o.montant_ttc == 0 for o in objets)
        return
    assert t.total_ttc == sum(d["montant_ttc"] for d in t.lignes)
    assert t.total_ht + t.total_tva == t.total_ttc
    assert all(isinstance(v, int) for v in (t.total_ttc, t.total_ht, t.total_tva, t.aib_montant))
    assert 0 <= t.aib_montant <= t.total_ht
    assert t.net_a_payer == t.total_ttc - t.aib_montant
    for g, tot in t.par_groupe.items():
        if g in ("A", "C", "E"):
            assert tot.tva == 0


def test_montants_par_ligne_deux_lignes_du_meme_article():
    """Deux lignes du même article (lecture en double) gardent chacune leur propre montant."""
    from app.brouillon import montants_par_ligne
    articles = [{"id": "A-001", "designation": "Riz", "prix_unitaire_ttc": 17500, "groupe_taxe": "B"}]
    base = {"article_id": "A-001", "prix_cite": None, "prix_catalogue": 17500, "quantite_livree": None}
    br = {"lignes": [dict(base, cle="l1", quantite_commandee="5"), dict(base, cle="l2", quantite_commandee="2"),
                     dict(base, cle="l3", quantite_commandee=None)], "decisions": {}}
    assert montants_par_ligne(br, articles) == {"l1": 87500, "l2": 35000}
