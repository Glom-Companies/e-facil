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


def test_parcours_complet_par_whatsapp(conn):
    """Tout le parcours sans ouvrir e-FACIL : commande, livraison, correction, décisions, validation, envoi, paiement."""
    aicha, rodrigue = "+229 01 90 00 00 11", "+229 01 90 00 00 12"

    # 1. Commande avec écart de livraison et quantité manquante ; la vendeuse corrige ce qui lui revient.
    envoyer(conn, aicha, "Bjr, c Dossou. 12 cartons de savon et des sacs de riz. Je paie momo")
    resume = derniere(conn, aicha)
    assert "Brouillon n° 1" in resume and "QTE 1 2 quantité" in resume
    envoyer(conn, aicha, "QTE 1 2 5")
    assert "Quantité corrigée" in derniere(conn, aicha)
    envoyer(conn, aicha, "BL 1 : 10 cartons de savon, 5 sacs de riz")
    assert "LIVRE 1" in derniere(conn, aicha)

    # 2. La vendeuse ne tranche pas ; le responsable, si.
    envoyer(conn, aicha, "LIVRE 1")
    assert "rôle ne permet pas" in derniere(conn, aicha)
    envoyer(conn, rodrigue, "VOIR 1")
    assert "LIVRE 1" in derniere(conn, rodrigue)
    envoyer(conn, rodrigue, "VALIDER 1")
    assert "Validation impossible" in derniere(conn, rodrigue)
    envoyer(conn, rodrigue, "LIVRE 1")
    assert "Tout est prêt : VALIDER 1" in derniere(conn, rodrigue)

    # 3. Validation, émission, envoi, paiements partiel puis complet.
    envoyer(conn, rodrigue, "VALIDER 1")
    fid = canaux.conversation(conn, rodrigue)[-1]["facture_id"]
    assert S.facture(conn, fid)["statut"] == "CONFIRMEE"
    envoyer(conn, rodrigue, "ENVOYER 1")
    assert "envoyée à" in derniere(conn, rodrigue)
    envoyer(conn, rodrigue, "PAYE 1 50 000 cash")
    assert "Paiement de 50" in derniere(conn, rodrigue) and "Reste à payer" in derniere(conn, rodrigue)
    envoyer(conn, rodrigue, "PAYE 1 momo")
    assert "Facture soldée" in derniere(conn, rodrigue)
    f = S.facture(conn, fid)
    assert f["reste_a_payer"] == 0 and {p["mode"] for p in f["paiements"]} == {"ESPECES", "MOBILEMONEY"}
    envoyer(conn, rodrigue, "PDF 1")
    assert canaux.conversation(conn, rodrigue)[-1]["type"] == "document"
    envoyer(conn, rodrigue, "QTE 1 1 3")
    assert "ne se modifie plus" in derniere(conn, rodrigue)


def test_corrections_et_decisions_par_whatsapp(conn):
    aicha, rodrigue = "+229 01 90 00 00 11", "+229 01 90 00 00 12"
    # Client inconnu : correction par le nom ; remise demandée : décision du responsable.
    envoyer(conn, aicha, "Slt c Koffi, 10 sacs de farine et 6 cartons de sucre. Remise de 5 % stp")
    assert "CLIENT 1 nom du client" in derniere(conn, aicha)
    envoyer(conn, aicha, "CLIENT 1 Gbaguidi")
    assert "Client corrigé" in derniere(conn, aicha) and "Gbaguidi" in derniere(conn, aicha)
    envoyer(conn, aicha, "CLIENT 1 Mama Adjovi")
    assert "Plusieurs clients" in derniere(conn, aicha)
    envoyer(conn, aicha, "AJOUTER 1 2 riz")
    assert "Ligne ajoutée" in derniere(conn, aicha) and "3. 2 × Riz" in derniere(conn, aicha)
    envoyer(conn, aicha, "RETIRER 1 3")
    assert "Ligne retirée" in derniere(conn, aicha) and "Riz" not in derniere(conn, aicha)
    envoyer(conn, rodrigue, "REMISE 1 peut-être")
    assert "REMISE 1 OUI" in derniere(conn, rodrigue)
    envoyer(conn, rodrigue, "REMISE 1 OUI")
    assert "Tout est prêt : VALIDER 1" in derniere(conn, rodrigue)
    envoyer(conn, rodrigue, "LISTE")
    assert "n° 1" in derniere(conn, rodrigue) and "prêt à valider" in derniere(conn, rodrigue)
    envoyer(conn, rodrigue, "TOTAL 1")
    assert "Rien à trancher" in derniere(conn, rodrigue)
