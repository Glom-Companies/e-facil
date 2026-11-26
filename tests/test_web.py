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


def test_recherche_aide_et_demo(client):
    connecter(client, "aicha")
    assert client.get("/recherche?q=Dossou").status_code == 200
    assert "Les mots de la facture" in client.get("/aide").text
    r = client.post("/parametres/demo", data={"csrf": csrf(client.get("/dossiers/nouveau").text)})
    assert "Votre rôle ne permet pas" in r.text
    connecter(client, "admin")
    r = client.post("/parametres/demo", data={"csrf": csrf(client.get("/parametres").text)})
    assert "Démonstration chargée : 5 factures émises, 5 commandes à vérifier." in r.text


def test_journal_filtres_et_integrite(client):
    connecter(client, "admin")
    client.post("/parametres/demo", data={"csrf": csrf(client.get("/parametres").text)})
    connecter(client, "rodrigue")
    r = client.get("/journal?categorie=paiements")
    assert "a enregistré un paiement" in r.text and "s&#39;est connecté" not in r.text
    r = client.get("/journal?verifier=1")
    assert "Journal intègre" in r.text
    assert client.get("/journal?categorie=inconnue&acteur=personne").status_code == 200


def test_connexion_compte_demo_en_un_clic(client):
    page = client.get("/connexion").text
    r = client.post("/connexion", data={"csrf": csrf(page), "demo": "1", "login": "rodrigue"})
    assert r.status_code == 200 and "Se déconnecter" in r.text
    client.post("/deconnexion")
    page = client.get("/connexion").text
    r = client.post("/connexion", data={"csrf": csrf(page), "login": "rodrigue"})
    assert "Se déconnecter" not in r.text  # sans le clic de démonstration, le mot de passe reste exigé


def test_socle_commande_remise_envoi_rectificative(client):
    connecter(client, "admin")
    page = client.get("/parametres").text
    client.post("/parametres", data={"csrf": csrf(page), "couleur": "#1f9184", "conditions_paiement": "",
                                     "pied_de_page": "", "mode_arrondi": "groupe", "taux_tva": "18"})
    connecter(client, "rodrigue")
    page = client.get("/dossiers/nouveau").text
    r = client.post("/dossiers/nouveau", data={
        "csrf": csrf(page), "canal": "WHATSAPP", "extracteur": "regles",
        "texte_commande": "Bjr, c Dossou. Commande BC-2026-200 : 10 cartons de savon, livrer avant le 30/11. "
                          "Paiement à 30 jours. Fais moi une remise de 2.000 F"})
    assert "BC-2026-200" in r.text and "Paiement à 30 jours" in r.text
    did = re.search(r"/dossiers/(\d+)/corriger", r.text).group(1)
    page = client.post(f"/dossiers/{did}/decider", data={"csrf": csrf(r.text), "version": champ(r.text, "version"),
                                                         "cle": "REMISE_A_VALIDER", "choix": "accepter"}).text
    r = client.post(f"/dossiers/{did}/valider", data={"csrf": csrf(page), "version": champ(page, "version"),
                                                      "idem": champ(page, "idem")})
    fid = re.search(r"/factures/(\d+)/emettre", r.text).group(1)
    r = client.post(f"/factures/{fid}/emettre", data={"csrf": csrf(r.text), "idem": champ(r.text, "idem")})
    from app import services as S
    c = db.connecter()
    f = S.facture(c, int(fid))
    brut = 10 * next(a["prix_unitaire_ttc"] for a in S.articles(c) if a["id"] == "A-011")
    assert abs((brut - f["total_ttc"]) - 2000) <= 10  # remise en montant, arrondie au franc par unité
    assert f["contenu"]["commande"]["reference_commande"] == "BC-2026-200"

    r = client.post(f"/factures/{fid}/envoyer", data={"csrf": csrf(r.text), "canal": "WHATSAPP",
                                                      "destinataire": "+229 01 00 00 01 17"})
    assert "Envoyée le" in r.text
    r = client.post(f"/factures/{fid}/avoir", data={"csrf": csrf(r.text), "idem": champ(r.text, "idem"),
                                                    "q:0": "10", "motif": "Erreur de prix", "emettre": "1"})
    r = client.get(f"/factures/{fid}")
    r = client.post(f"/factures/{fid}/rectifier", data={"csrf": csrf(r.text)})
    assert "Facture rectificative" in r.text and f["numero"] in r.text
    assert client.get(f"/factures/{fid}/pdf").status_code == 200


def test_inscription_espace_separe(client):
    page = client.get("/inscription").text
    r = client.post("/inscription", data={
        "csrf": csrf(page), "raison_sociale": "Ets Houénou et Fils", "ifu": "3200000000099", "adresse": "Cadjèhoun",
        "regime_fiscal": "TPS", "taille": "micro", "admin_nom": "Houénou", "admin_login": "direction",
        "mot_de_passe": "motdepasse-long", "mot_de_passe_2": "motdepasse-long"})
    assert "Espace créé" in r.text and "Mode solo" in r.text and "Ets Houénou" in r.text
    for url in ("/", "/dossiers", "/factures", "/referentiels", "/journal?verifier=1", "/parametres", "/comptabilite",
                "/dossiers/nouveau", "/simulateur", "/recherche?q=x"):
        assert client.get(url).status_code == 200, url
    page = client.get("/parametres").text
    client.post("/parametres/utilisateurs", data={"csrf": csrf(page), "nom": "Afi", "login": "afi", "role": "vendeur",
                                                  "mot_de_passe": "afi-motdepasse"})
    assert "Dossou" not in client.get("/referentiels").text  # aucune donnée de SÈNA dans le nouvel espace
    connecter(client, "admin")  # la démonstration SÈNA reste intacte
    assert "SÈNA" in client.get("/").text and "afi" not in client.get("/parametres").text
    page = client.get("/connexion").text
    assert "Ets Houénou" in page
    slug = re.search(r'<option value="([a-z0-9-]+)">Ets Houénou', page).group(1)
    r = client.post("/connexion", data={"csrf": csrf(page), "login": "afi", "mot_de_passe": "afi-motdepasse",
                                        "espace": slug})
    assert "Se déconnecter" in r.text and "Ets Houénou" in r.text


def test_cloisonnement_des_roles(client):
    connecter(client, "rodrigue")
    page = client.get("/dossiers/nouveau").text
    r = client.post("/dossiers/nouveau", data={"csrf": csrf(page), "canal": "SMS", "extracteur": "regles",
                                                "texte_commande": "c Dossou. 3 cartons de savon"})
    did = re.search(r"/dossiers/(\d+)/corriger", r.text).group(1)
    connecter(client, "aicha")
    assert "autre personne" in client.get(f"/dossiers/{did}").text  # dossier d'un autre : refusé
    assert f"/dossiers/{did}" not in client.get("/dossiers?etat=tous").text
    assert "Votre rôle ne permet pas" in client.get("/journal").text
    assert "Chiffre facturé" not in client.get("/").text
    connecter(client, "admin")
    page = client.get("/parametres").text
    client.post("/parametres/roles", data={"csrf": csrf(page), "vendeur": "Commercial", "responsable": "Gérant",
                                           "comptable": "Comptable", "admin": "Administrateur"})
    assert "Commercial" in client.get("/parametres").text


def test_attestation_de_service_fait(client):
    connecter(client, "rodrigue")
    page = client.get("/dossiers/nouveau").text
    assert "Attestation de service fait" in page
    r = client.post("/dossiers/nouveau", data={
        "csrf": csrf(page), "canal": "EMAIL", "extracteur": "regles", "piece_execution": "ASF",
        "texte_commande": "Bjr, c Dossou. 12 cartons de savon", "texte_livraison": "Attestation : 10 cartons de savon"})
    assert "Prestation réalisée différente de la commande" in r.text and "Facturer le réalisé" in r.text
    assert "Bon de livraison" not in r.text
