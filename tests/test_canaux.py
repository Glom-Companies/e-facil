"""Bot WhatsApp simulé : numéros habilités, droits, signature, rejeu (lecture par règles, sans IA réelle)."""
import json

import pytest

from app import canaux, db
from app import services as S


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "CHEMIN_BASE", tmp_path / "canaux.db")
    monkeypatch.setattr(canaux, "_debits", {})  # limite de débit propre à chaque test
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
    assert "Brouillon n° 1" in canaux.conversation(conn, aicha)[-2]["texte"]
    assert "responsable" in derniere(conn, aicha)
    assert "Valider et émettre" in derniere(conn, rodrigue)  # le responsable est prévenu et guidé

    envoyer(conn, aicha, "VALIDER 1")
    assert "rôle ne permet pas" in derniere(conn, aicha)
    envoyer(conn, rodrigue, "VALIDER 1")
    pdf = next(m for m in reversed(canaux.conversation(conn, rodrigue)) if m["type"] == "document")
    assert pdf["facture_id"] and S.facture(conn, pdf["facture_id"])["statut"] == "CONFIRMEE"
    assert "que faire" in derniere(conn, rodrigue)  # puis le bot propose l'envoi et le paiement
    envoyer(conn, rodrigue, "ENVOYER 1")
    assert "envoyée à Ets Dossou" in derniere(conn, rodrigue)


def textes(c, numero, n=3):
    return " | ".join(m["texte"] or "" for m in canaux.conversation(c, numero)[-n:])


def test_parcours_guide_par_whatsapp(conn):
    """Commencer une facture, puis répondre aux questions jusqu'à la facture payée, sans numéro de dossier."""
    aicha, rodrigue = "+229 01 90 00 00 11", "+229 01 90 00 00 12"
    envoyer(conn, aicha, "Bjr, c Koffi. 12 cartons de savon et des sacs de riz. Je paie momo")
    assert "Quel est le client" in derniere(conn, aicha)
    envoyer(conn, aicha, "Mama Adjovi")
    assert "Plusieurs clients" in derniere(conn, aicha)
    envoyer(conn, aicha, "3")
    assert "chiffre de 1 à 2" in derniere(conn, aicha)  # choix hors liste
    envoyer(conn, aicha, "1")
    assert "Client : Boutique Mama Adjovi" in textes(conn, aicha) and "Quelle quantité" in derniere(conn, aicha)
    envoyer(conn, aicha, "cinq")
    assert "Répondez par un nombre" in derniere(conn, aicha)
    envoyer(conn, aicha, "5")
    assert "le responsable va le valider" in derniere(conn, aicha).lower()

    # Le responsable est prévenu et guidé : validation, envoi, paiement en deux fois.
    assert "1. Valider et émettre" in derniere(conn, rodrigue)
    envoyer(conn, rodrigue, "1")
    fid = next(m["facture_id"] for m in reversed(canaux.conversation(conn, rodrigue)) if m["facture_id"])
    assert S.facture(conn, fid)["statut"] == "CONFIRMEE" and "que faire" in derniere(conn, rodrigue)
    envoyer(conn, rodrigue, "1")
    assert "envoyée à" in textes(conn, rodrigue)
    envoyer(conn, rodrigue, "2")
    assert "Combien" in derniere(conn, rodrigue)
    envoyer(conn, rodrigue, "50 000")
    envoyer(conn, rodrigue, "2")  # espèces
    assert "Paiement de 50" in textes(conn, rodrigue) and "Reste à payer" in textes(conn, rodrigue)
    envoyer(conn, rodrigue, "2")
    envoyer(conn, rodrigue, "tout")
    envoyer(conn, rodrigue, "1")  # mobile money
    assert "Facture soldée" in textes(conn, rodrigue)
    f = S.facture(conn, fid)
    assert f["reste_a_payer"] == 0 and {p["mode"] for p in f["paiements"]} == {"ESPECES", "MOBILEMONEY"}
    envoyer(conn, rodrigue, "2")  # « Terminer » (le paiement n'est plus proposé)
    assert "terminé" in derniere(conn, rodrigue)


def test_guide_decisions_et_reprise(conn):
    """Écart de livraison et remise tranchés en répondant 1 ou 2 ; STOP met de côté, REPRENDRE y revient."""
    aicha, rodrigue = "+229 01 90 00 00 11", "+229 01 90 00 00 12"
    envoyer(conn, aicha, "C'est Gbaguidi import. 10 sacs de farine et 6 cartons de sucre. Remise de 5 % stp")
    assert "responsable tranchera" in derniere(conn, aicha)
    assert "1. Accorder la remise" in derniere(conn, rodrigue)
    envoyer(conn, rodrigue, "STOP")
    assert "mis de côté" in derniere(conn, rodrigue)
    envoyer(conn, rodrigue, "REPRENDRE 1")
    assert "1. Accorder la remise" in derniere(conn, rodrigue)
    envoyer(conn, rodrigue, "oui")
    assert "1. Valider et émettre" in derniere(conn, rodrigue)
    envoyer(conn, rodrigue, "2")
    assert "VALIDER 1 quand vous voulez" in derniere(conn, rodrigue)
    envoyer(conn, rodrigue, "BL 1 : 8 sacs de farine, 6 cartons de sucre")
    assert "8 livré(s)" in derniere(conn, rodrigue) and "1. Facturer le livré" in derniere(conn, rodrigue)
    envoyer(conn, rodrigue, "1")
    assert "1. Valider et émettre" in derniere(conn, rodrigue)
    # Un long message pendant une question ouvre une nouvelle commande.
    envoyer(conn, rodrigue, "Bjr c Dossou, 12 cartons de savon et 5 sacs de riz, je paie momo")
    assert "nouvelle commande" in textes(conn, rodrigue, 6)
    assert conn.execute("SELECT COUNT(*) FROM dossiers").fetchone()[0] == 2


def test_raccourcis_par_commande(conn):
    """Les commandes directes restent disponibles, avec les droits de l'interface."""
    aicha, rodrigue = "+229 01 90 00 00 11", "+229 01 90 00 00 12"
    envoyer(conn, aicha, "Bjr, c Dossou. 12 cartons de savon et 5 sacs de riz. Je paie momo")
    envoyer(conn, aicha, "BL 1 : 10 cartons de savon, 5 sacs de riz")
    envoyer(conn, aicha, "LIVRE 1")
    assert "rôle ne permet pas" in derniere(conn, aicha)
    envoyer(conn, rodrigue, "VOIR 1")
    assert "LIVRE 1" in derniere(conn, rodrigue)
    envoyer(conn, rodrigue, "LIVRE 1")
    envoyer(conn, rodrigue, "QTE 1 1 10")
    assert "Quantité corrigée" in derniere(conn, rodrigue)
    envoyer(conn, rodrigue, "AJOUTER 1 2 riz")
    envoyer(conn, rodrigue, "RETIRER 1 3")
    assert "Ligne retirée" in derniere(conn, rodrigue)
    envoyer(conn, rodrigue, "VALIDER 1")
    envoyer(conn, rodrigue, "PAYE 1 50 000 cash")
    assert "Paiement de 50" in derniere(conn, rodrigue)
    envoyer(conn, rodrigue, "PDF 1")
    assert canaux.conversation(conn, rodrigue)[-1]["type"] == "document"
    envoyer(conn, rodrigue, "LISTE")
    assert "Aucun brouillon" in derniere(conn, rodrigue)
