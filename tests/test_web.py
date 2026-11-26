"""Parcours complet à travers l'interface web (navigateur simulé)."""
import re

import pytest
from fastapi.testclient import TestClient

from app import db


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "CHEMIN_BASE", tmp_path / "web.db")
    from app.web import app
    with TestClient(app) as c:
        yield c


def csrf(html: str) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def connecter(c, login):
    c.post("/deconnexion")
    page = c.get("/connexion").text
    r = c.post("/connexion", data={"login": login, "mot_de_passe": "demo2026", "csrf": csrf(page)})
    assert r.status_code == 200 and "Bonjour" in r.text


def champ(html, nom):
    return re.search(rf'name="{nom}" value="([^"]+)"', html).group(1)


def test_parcours_complet(client):
    connecter(client, "aicha")
    page = client.get("/dossiers/nouveau").text
    r = client.post("/dossiers/nouveau", data={
        "csrf": csrf(page), "canal": "WHATSAPP", "extracteur": "regles",
        "texte_commande": "Bjr, c Dossou. 12 cartons de savon et 5 sacs de riz. Je paie momo",
        "texte_livraison": "BL : 10 cartons de savon, 5 sacs de riz"})
    assert r.status_code == 200 and "Brouillon de facture" in r.text
    did = re.search(r"/dossiers/(\d+)/corriger", r.text).group(1)
    assert "<mark" in r.text and "bloque la validation" in r.text
    assert "Valider et numéroter" not in r.text  # la vendeuse ne voit pas le bouton

    # La vendeuse tente quand même de valider : refus côté serveur.
    r2 = client.post(f"/dossiers/{did}/valider", data={"csrf": csrf(r.text), "version": champ(r.text, "version")})
    assert "Votre rôle ne permet pas" in r2.text

    connecter(client, "rodrigue")
    page = client.get(f"/dossiers/{did}").text
    cle = re.search(r'name="cle" value="(ECART[^"]+)"', page).group(1)
    page = client.post(f"/dossiers/{did}/decider", data={"csrf": csrf(page), "version": champ(page, "version"),
                                                         "cle": cle, "choix": "facturer_livre"}).text
    assert "Aucun blocage" in page
    r = client.post(f"/dossiers/{did}/valider", data={"csrf": csrf(page), "version": champ(page, "version"),
                                                      "idem": champ(page, "idem")})
    assert "verrouillé" in r.text and "FV-" in r.text
    fid = re.search(r"/factures/(\d+)/emettre", r.text).group(1)
    r = client.post(f"/factures/{fid}/emettre", data={"csrf": csrf(r.text), "idem": champ(r.text, "idem")})
    assert "SIMU-" in r.text
    pdf = client.get(f"/factures/{fid}/pdf")
    assert pdf.headers["content-type"] == "application/pdf" and pdf.content[:4] == b"%PDF"
    r = client.post(f"/factures/{fid}/avoir", data={"csrf": csrf(r.text), "idem": champ(r.text, "idem"),
                                                    "q:0": "1", "motif": "Carton abîmé", "emettre": "1"})
    assert "FA-" in r.text and "Confirmée" in r.text

    for url in ("/", "/factures", "/journal?verifier=1", "/referentiels", "/comptabilite"):
        assert client.get(url).status_code == 200
    assert "Journal intègre" in client.get("/journal?verifier=1").text
    assert client.get("/comptabilite/ecritures.csv").status_code == 200


def test_csrf_obligatoire(client):
    connecter(client, "aicha")
    r = client.post("/dossiers/nouveau", data={"csrf": "faux", "texte_commande": "x", "extracteur": "regles"})
    assert "Formulaire expiré" in r.text


def test_pages_admin(client):
    connecter(client, "admin")
    page = client.get("/parametres").text
    r = client.post("/parametres", data={"csrf": csrf(page), "couleur": "#7a1f2b", "conditions_paiement": "30 jours",
                                         "pied_de_page": "Merci", "mode_arrondi": "groupe"})
    assert "Paramètres enregistrés" in r.text
    connecter(client, "aicha")
    assert "Votre rôle ne permet pas" in client.get("/parametres").text


def test_liste_des_brouillons(client):
    """La page des dossiers liste les brouillons, filtre par état et refuse un état inconnu sans erreur."""
    connecter(client, "aicha")
    page = client.get("/dossiers/nouveau").text
    client.post("/dossiers/nouveau", data={"csrf": csrf(page), "canal": "SMS", "extracteur": "regles",
                                           "texte_commande": "C'est Gbaguidi import. 10 sacs de farine."})
    r = client.get("/dossiers")
    assert r.status_code == 200 and "Gbaguidi" in r.text and "Brouillons" in r.text
    assert client.get("/dossiers?etat=VALIDE").status_code == 200
    assert client.get("/dossiers?etat=n_importe_quoi").status_code == 200
