"""Bot WhatsApp simulé : numéros habilités, droits, signature, rejeu (lecture par règles, sans IA réelle)."""
import json

import pytest

from app import canaux, db
from app import services as S


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "CHEMIN_BASE", tmp_path / "canaux.db")
    c = S.ouvrir()
    yield c
    c.close()


def envoyer(c, numero, texte, mid=None):
    m = canaux.message_meta(numero, "text", texte)
    if mid:
        m["entry"][0]["changes"][0]["value"]["messages"][0]["id"] = mid
    corps = json.dumps(m).encode()
    canaux.recevoir(c, corps, canaux.signer(corps))


def derniere(c, numero):
    return canaux.conversation(c, numero)[-1]["texte"]


def test_bot_whatsapp(conn):
    aicha, rodrigue, inconnu = "+229 01 90 00 00 11", "+229 01 90 00 00 12", "+229 01 99 99 99 99"
    with pytest.raises(S.Refus):
        canaux.recevoir(conn, b'{"entry": []}', "sha256=faux")

    envoyer(conn, inconnu, "12 cartons de savon")
    assert "pas autorisé" in derniere(conn, inconnu)
    assert conn.execute("SELECT COUNT(*) FROM dossiers").fetchone()[0] == 0

    envoyer(conn, aicha, "Bjr, c Dossou. 12 cartons de savon et 5 sacs de riz. Je paie momo", mid="wamid.1")
    envoyer(conn, aicha, "Bjr, c Dossou. 12 cartons de savon et 5 sacs de riz. Je paie momo", mid="wamid.1")  # rejeu
    assert conn.execute("SELECT COUNT(*) FROM dossiers").fetchone()[0] == 1
    assert "Brouillon n° 1" in derniere(conn, aicha)
    assert "VALIDER 1" in derniere(conn, rodrigue)  # le responsable est prévenu

    envoyer(conn, aicha, "VALIDER 1")
    assert "rôle ne permet pas" in derniere(conn, aicha)
    envoyer(conn, rodrigue, "VALIDER 1")
    msgs = canaux.conversation(conn, rodrigue)
    assert msgs[-1]["type"] == "document" and msgs[-1]["facture_id"]
    assert S.facture(conn, msgs[-1]["facture_id"])["statut"] == "CONFIRMEE"
    envoyer(conn, rodrigue, "ENVOYER 1")
    assert "envoyée à Ets Dossou" in derniere(conn, rodrigue)
