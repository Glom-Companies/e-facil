"""Robustesse de l'extraction Gemini : quotas, surcharge, JSON invalide, modèle de secours, repli sur les règles.

Aucun appel réseau : le client Gemini est remplacé par un faux client qui rejoue des réponses prévues.
"""
import json

import pytest
from google.genai import errors

from app import extraction as E
from app import services as S

COMMANDE = "Bjr Aïcha, c Dossou. Envoie moi 12 cartons de savon et 5 sacs de riz stp. Je paie momo"

REPONSE_OK = json.dumps({
    "transcription": None,
    "client": {"valeur": "Dossou", "citation": "Dossou"},
    "lignes": [{"designation": {"valeur": "cartons de savon", "citation": "cartons de savon"},
                "quantite": {"valeur": "12", "citation": "12"},
                "prix_unitaire_ttc": {"valeur": None, "citation": None}}],
    "mode_paiement": {"valeur": "MOBILEMONEY", "citation": "momo"},
    "total_cite": {"valeur": None, "citation": None},
    "remise_demandee": None,
    "instructions_suspectes": [],
})


def erreur_api(code: int, message: str = "") -> errors.APIError:
    statut = {429: "RESOURCE_EXHAUSTED", 503: "UNAVAILABLE", 400: "INVALID_ARGUMENT"}[code]
    return errors.APIError(code, {"error": {"code": code, "message": message, "status": statut}})


class FauxClient:
    """Rejoue, pour chaque modèle, une liste de réponses (texte JSON) ou d'exceptions."""

    def __init__(self, scenario: dict):
        self.scenario = {m: list(r) for m, r in scenario.items()}
        self.appels: list[str] = []
        self.models = self

    def generate_content(self, model, contents, config):
        self.appels.append(model)
        suite = self.scenario[model].pop(0)
        if isinstance(suite, Exception):
            raise suite
        return type("Reponse", (), {"text": suite})()


@pytest.fixture
def faux_gemini(monkeypatch, tmp_path):
    """Installe un faux client ; renvoie une fonction qui fixe le scénario."""
    monkeypatch.setattr(E, "CACHE", tmp_path / "cache.json")
    monkeypatch.setattr(E.time, "sleep", lambda s: None)
    monkeypatch.setenv("GEMINI_API_KEY", "cle-de-test")
    monkeypatch.setenv("GEMINI_MODELE", "principal")
    monkeypatch.setenv("GEMINI_MODELES_SECOURS", "secours")
    monkeypatch.setenv("GEMINI_ATTENTE_MAX", "60")
    from google import genai

    def installer(scenario: dict) -> FauxClient:
        client = FauxClient(scenario)
        monkeypatch.setattr(genai, "Client", lambda **kw: client)
        return client
    return installer


def test_quota_puis_succes(faux_gemini):
    client = faux_gemini({"principal": [erreur_api(429, "Please retry in 3.2s."), REPONSE_OK]})
    r = E.extraire_gemini(COMMANDE)
    assert r["modele"] == "principal" and r["client"]["valeur"] == "Dossou"
    assert client.appels == ["principal", "principal"]


def test_delai_conseille_lu_dans_l_erreur():
    assert E._delai_conseille(erreur_api(429, "Please retry in 25.65s.")) == pytest.approx(25.65)
    assert E._delai_conseille(erreur_api(503, "high demand")) is None


def test_surcharge_persistante_bascule_sur_secours(faux_gemini, monkeypatch):
    monkeypatch.setenv("GEMINI_ATTENTE_MAX", "5")
    client = faux_gemini({"principal": [erreur_api(503)] * 6, "secours": [REPONSE_OK]})
    r = E.extraire_gemini(COMMANDE)
    assert r["modele"] == "secours"
    assert client.appels[-1] == "secours"


def test_json_invalide_reessaye_une_fois(faux_gemini):
    client = faux_gemini({"principal": ["{pas du json", REPONSE_OK]})
    assert E.extraire_gemini(COMMANDE)["modele"] == "principal"
    assert len(client.appels) == 2


def test_json_invalide_deux_fois_puis_secours(faux_gemini):
    faux_gemini({"principal": ["{", '{"client": 3}'], "secours": [REPONSE_OK]})
    assert E.extraire_gemini(COMMANDE)["modele"] == "secours"


def test_erreur_definitive_message_lisible(faux_gemini, monkeypatch):
    monkeypatch.setenv("GEMINI_MODELES_SECOURS", "")
    faux_gemini({"principal": [erreur_api(400, "clé invalide")]})
    with pytest.raises(E.ErreurExtraction, match="refusé la requête"):
        E.extraire_gemini(COMMANDE)


def test_quota_epuise_message_lisible(faux_gemini, monkeypatch):
    monkeypatch.setenv("GEMINI_MODELES_SECOURS", "")
    monkeypatch.setenv("GEMINI_ATTENTE_MAX", "10")
    faux_gemini({"principal": [erreur_api(429, "Please retry in 30s.")]})
    with pytest.raises(E.ErreurExtraction, match="quota gratuit"):
        E.extraire_gemini(COMMANDE)


def test_cache_evite_un_second_appel(faux_gemini):
    client = faux_gemini({"principal": [REPONSE_OK]})
    E.extraire_gemini(COMMANDE)
    E.extraire_gemini(COMMANDE)
    assert client.appels == ["principal"]


# --- Repli de l'application sur les règles ----------------------------------------------

@pytest.fixture
def conn(tmp_path):
    c = S.ouvrir(tmp_path / "test.db")
    yield c
    c.close()


def vendeur(conn):
    return dict(conn.execute("SELECT * FROM utilisateurs WHERE login = 'aicha'").fetchone())


def test_echec_ia_repli_sur_regles(conn, monkeypatch):
    def echec(*a, **k):
        raise E.ErreurExtraction("Gemini (principal) : quota gratuit atteint.")
    monkeypatch.setattr(E, "extraire_gemini", echec)
    did = S.creer_dossier(conn, vendeur(conn), "WHATSAPP", COMMANDE, None, "gemini")
    d = S.dossier(conn, did)
    assert d["extracteur"] == "regles"
    assert "quota gratuit" in d["brouillon"]["repli_ia"]
    assert d["brouillon"]["lignes"], "les règles doivent avoir lu les articles"
    journal = conn.execute("SELECT details FROM journal WHERE action = 'DOSSIER_CREE'").fetchone()[0]
    assert '"extracteur_demande": "gemini"' in journal


def test_echec_ia_sur_photo_seule_refuse(conn, monkeypatch):
    def echec(*a, **k):
        raise E.ErreurExtraction("Gemini indisponible.")
    monkeypatch.setattr(E, "extraire_gemini", echec)
    with pytest.raises(S.Refus, match="Gemini indisponible"):
        S.creer_dossier(conn, vendeur(conn), "PHOTO", "", None, "gemini", b"\x89PNG", "image/png", "bc.png")
