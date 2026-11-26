"""Extracteur Groq et repli entre IA. Aucun appel réseau : la requête HTTP est remplacée par un faux."""
import io
import json
import urllib.error
from email.message import Message

import pytest

from app import extraction as E
from app import services as S
from tests.test_extraction_gemini import COMMANDE, REPONSE_OK


def reponse_groq(contenu: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": contenu}}]}


def erreur_http(code: int, corps: str = "", retry_after: str | None = None) -> urllib.error.HTTPError:
    entetes = Message()
    if retry_after:
        entetes["retry-after"] = retry_after
    return urllib.error.HTTPError(E.GROQ_URL, code, "erreur", entetes, io.BytesIO(corps.encode()))


@pytest.fixture
def faux_groq(monkeypatch, tmp_path):
    """Remplace l'appel HTTP ; renvoie une fonction qui fixe le scénario {modèle: [réponses ou exceptions]}."""
    monkeypatch.setattr(E, "CACHE", tmp_path / "cache.json")
    monkeypatch.setattr(E.time, "sleep", lambda s: None)
    monkeypatch.setenv("GROQ_API_KEY", "cle-de-test")
    monkeypatch.setenv("GROQ_MODELE", "principal")
    monkeypatch.setenv("GROQ_MODELES_SECOURS", "secours")
    monkeypatch.setenv("GROQ_ATTENTE_MAX", "60")
    appels: list[dict] = []

    def installer(scenario: dict) -> list[dict]:
        suites = {m: list(r) for m, r in scenario.items()}

        def faux_post(url, corps, cle_api, delai):
            appels.append(corps)
            suite = suites[corps["model"]].pop(0)
            if isinstance(suite, Exception):
                raise suite
            return suite
        monkeypatch.setattr(E, "_post_json", faux_post)
        return appels
    return installer


def test_groq_succes_et_requete(faux_groq):
    appels = faux_groq({"principal": [reponse_groq(REPONSE_OK)]})
    r = E.extraire_groq(COMMANDE)
    assert r["modele"] == "principal" and r["lignes"][0]["quantite"]["valeur"] == "12"
    corps = appels[0]
    assert corps["temperature"] == 0 and corps["response_format"] == {"type": "json_object"}
    assert "schéma JSON" in corps["messages"][0]["content"]
    assert COMMANDE in corps["messages"][1]["content"]


def test_groq_quota_respecte_retry_after(faux_groq, monkeypatch):
    pauses = []
    monkeypatch.setattr(E.time, "sleep", pauses.append)
    faux_groq({"principal": [erreur_http(429, "Rate limit reached", retry_after="2"), reponse_groq(REPONSE_OK)]})
    assert E.extraire_groq(COMMANDE)["modele"] == "principal"
    assert pauses == [2.5]


def test_groq_surcharge_bascule_sur_secours(faux_groq, monkeypatch):
    monkeypatch.setenv("GROQ_ATTENTE_MAX", "5")
    faux_groq({"principal": [erreur_http(503)] * 6, "secours": [reponse_groq(REPONSE_OK)]})
    assert E.extraire_groq(COMMANDE)["modele"] == "secours"


def test_groq_reseau_coupe_puis_succes(faux_groq):
    faux_groq({"principal": [urllib.error.URLError("hors ligne"), reponse_groq(REPONSE_OK)]})
    assert E.extraire_groq(COMMANDE)["modele"] == "principal"


def test_groq_json_invalide_puis_secours(faux_groq):
    faux_groq({"principal": [reponse_groq("pas du json"), {"choices": []}], "secours": [reponse_groq(REPONSE_OK)]})
    assert E.extraire_groq(COMMANDE)["modele"] == "secours"


def test_groq_cle_refusee_message_lisible(faux_groq, monkeypatch):
    monkeypatch.setenv("GROQ_MODELES_SECOURS", "")
    faux_groq({"principal": [erreur_http(401, '{"error": {"message": "Invalid API Key"}}')]})
    with pytest.raises(E.ErreurExtraction, match="Groq a refusé la requête \\(401\\)"):
        E.extraire_groq(COMMANDE)


def test_groq_sans_cle(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(E.ErreurExtraction, match="GROQ_API_KEY"):
        E.extraire_groq(COMMANDE)


def test_groq_ne_lit_pas_les_photos():
    with pytest.raises(E.ErreurExtraction, match="ne lit que du texte"):
        E.extraire("groq", "", [], [], b"\x89PNG", "image/png")


def test_ia_disponibles_selon_les_cles(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("GROQ_API_KEY", "y")
    assert E.ia_disponibles() == ["gemini", "groq"]
    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert E.ia_disponibles() == ["groq"]


# --- Chaîne de repli de l'application : IA choisie, autre IA, règles ---------------------

@pytest.fixture
def conn(tmp_path):
    c = S.ouvrir(tmp_path / "test.db")
    yield c
    c.close()


def vendeur(conn):
    return dict(conn.execute("SELECT * FROM utilisateurs WHERE login = 'aicha'").fetchone())


def echec(message):
    def f(*a, **k):
        raise E.ErreurExtraction(message)
    return f


def test_gemini_echoue_groq_prend_le_relais(conn, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("GROQ_API_KEY", "y")
    monkeypatch.setattr(E, "extraire_gemini", echec("Gemini : quota gratuit atteint."))
    monkeypatch.setattr(E, "extraire_groq", lambda texte: dict(json.loads(REPONSE_OK), modele="principal"))
    did = S.creer_dossier(conn, vendeur(conn), "WHATSAPP", COMMANDE, None, "gemini")
    d = S.dossier(conn, did)
    assert d["extracteur"] == "groq"
    assert "IA Groq" in d["brouillon"]["repli_ia"] and "quota" in d["brouillon"]["repli_ia"]


def test_toutes_les_ia_echouent_regles(conn, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("GROQ_API_KEY", "y")
    monkeypatch.setattr(E, "extraire_gemini", echec("Gemini indisponible."))
    monkeypatch.setattr(E, "extraire_groq", echec("Groq indisponible."))
    did = S.creer_dossier(conn, vendeur(conn), "WHATSAPP", COMMANDE, None, "groq")
    d = S.dossier(conn, did)
    assert d["extracteur"] == "regles"
    assert "Groq indisponible" in d["brouillon"]["repli_ia"] and "Gemini indisponible" in d["brouillon"]["repli_ia"]


def test_photo_seule_groq_non_essaye(conn, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("GROQ_API_KEY", "y")
    monkeypatch.setattr(E, "extraire_gemini", echec("Gemini indisponible."))
    monkeypatch.setattr(E, "extraire_groq", lambda *a: pytest.fail("Groq ne doit pas recevoir une photo"))
    with pytest.raises(S.Refus, match="Gemini indisponible"):
        S.creer_dossier(conn, vendeur(conn), "PHOTO", "", None, "gemini", b"\x89PNG", "image/png", "bc.png")
