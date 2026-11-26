"""Facture PDF sur le modèle de la facture normalisée e-MECeF, avec la mention SIMULATION.

Aucun logo officiel n'est reproduit (règle R-18). Le bloc de sécurité est fictif.
"""
from __future__ import annotations

import base64
import io
from datetime import datetime

from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .moteur import format_fcfa

TITRES = {"FV": "FACTURE DE VENTE", "FA": "FACTURE D'AVOIR", "PF": "FACTURE PRO FORMA"}
LIBELLES_PAIEMENT = {"ESPECES": "Espèces", "CHEQUES": "Chèque", "MOBILEMONEY": "Mobile money",
                     "CARTEBANCAIRE": "Carte bancaire", "VIREMENT": "Virement", "CREDIT": "Crédit", "AUTRE": "Autre"}
GROUPES = {"A": "A - Exonéré", "B": "B - Taxable 18 %", "C": "C - Exportation", "D": "D - Régime d'exception 18 %",
           "E": "E - Régime TPS"}


def _f(n: int) -> str:
    return format_fcfa(n).replace(" ", " ").replace(" ", " ")


def _date(iso: str | None) -> str:
    if not iso:
        return ""
    return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")


def _couleur(hexa: str | None):
    try:
        return colors.HexColor(hexa or "#0B6E4F")
    except Exception:
        return colors.HexColor("#0B6E4F")


def generer(contenu: dict, securite: dict | None = None, copie: bool = False) -> bytes:
    """contenu : instantané figé de la facture. securite : code DGI, QR, compteurs, horodatage (si confirmée)."""
    tampon = io.BytesIO()
    c = canvas.Canvas(tampon, pagesize=A4)
    larg, haut = A4
    v = contenu["vendeur"]
    perso = v.get("personnalisation", {})
    accent = _couleur(perso.get("couleur"))
    gris = colors.HexColor("#5b6670")
    marge = 16 * mm
    type_doc = contenu["type"]

    c.setTitle(f"{TITRES.get(type_doc, 'FACTURE')} {contenu['numero']}")

    # Filigrane
    c.saveState()
    c.setFillColor(colors.Color(0.85, 0.1, 0.1, alpha=0.08))
    c.setFont("Helvetica-Bold", 64)
    c.translate(larg / 2, haut / 2)
    c.rotate(35)
    c.drawCentredString(0, 0, "PRO FORMA" if type_doc == "PF" else "SIMULATION")
    c.restoreState()

    # En-tête vendeur
    y = haut - marge
    x_texte = marge
    if perso.get("logo"):
        try:
            entete, donnees = perso["logo"].split(",", 1)
            img = ImageReader(io.BytesIO(base64.b64decode(donnees)))
            c.drawImage(img, marge, y - 18 * mm, width=18 * mm, height=18 * mm, preserveAspectRatio=True, mask="auto")
            x_texte = marge + 22 * mm
        except Exception:
            pass
    c.setFillColor(accent)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(x_texte, y - 4 * mm, v.get("raison_sociale", ""))
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8.5)
    lignes_vendeur = [
        f"IFU : {v.get('ifu', '')}    RCCM : {v.get('rccm', '')}",
        v.get("adresse", ""),
        f"Tél. : {v.get('telephone', '')}    {v.get('email', '')}",
        "SFE simulé - prototype hackathon BWAI'2026",
    ]
    for i, t in enumerate(lignes_vendeur):
        c.drawString(x_texte, y - (9 + 4 * i) * mm, t)

    # Titre et numéro
    c.setFillColor(accent)
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(larg - marge, y - 4 * mm, TITRES.get(type_doc, "FACTURE") + (" - COPIE" if copie else ""))
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 9)
    c.drawRightString(larg - marge, y - 9 * mm, f"N° {contenu['numero']}")
    c.drawRightString(larg - marge, y - 13 * mm, f"Date : {_date(contenu['date'])}")
    if contenu.get("rectifie"):
        c.drawRightString(larg - marge, y - 17 * mm, f"Rectifie la facture : {contenu['rectifie']['numero']}")
        c.setFont("Helvetica", 7.5)
        c.drawRightString(larg - marge, y - 21 * mm, f"Code DGI d'origine : {contenu['rectifie']['code_dgi']}")
    if type_doc == "FA" and contenu.get("reference"):
        c.drawRightString(larg - marge, y - 17 * mm, f"Facture d'origine : {contenu['reference']['numero']}")
        c.setFont("Helvetica", 7.5)
        c.drawRightString(larg - marge, y - 21 * mm, f"Code DGI d'origine : {contenu['reference']['code_dgi']}")

    # Bloc client
    y -= 30 * mm
    cl = contenu["client"]
    c.setStrokeColor(colors.HexColor("#d5dade"))
    c.setFillColor(colors.HexColor("#f5f7f6"))
    c.roundRect(marge, y - 20 * mm, larg - 2 * marge, 20 * mm, 2 * mm, fill=1, stroke=1)
    c.setFillColor(gris)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(marge + 4 * mm, y - 5 * mm, "CLIENT")
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(marge + 4 * mm, y - 10 * mm, cl.get("nom") or "")
    c.setFont("Helvetica", 8.5)
    c.drawString(marge + 4 * mm, y - 14.5 * mm, f"IFU : {cl.get('ifu') or 'non communiqué'}    {cl.get('adresse') or ''}")
    c.drawString(marge + 4 * mm, y - 18.5 * mm, f"Contact : {cl.get('telephone') or ''}")

    # Tableau des articles
    y -= 28 * mm
    colonnes = [marge, marge + 10 * mm, marge + 98 * mm, marge + 118 * mm, marge + 146 * mm]
    c.setFillColor(accent)
    c.rect(marge, y - 6 * mm, larg - 2 * marge, 6 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(colonnes[0] + 2 * mm, y - 4 * mm, "N°")
    c.drawString(colonnes[1], y - 4 * mm, "Désignation")
    c.drawRightString(colonnes[3] - 2 * mm, y - 4 * mm, "Quantité")
    c.drawRightString(colonnes[4] - 2 * mm, y - 4 * mm, "Prix unit. TTC")
    c.drawRightString(larg - marge - 2 * mm, y - 4 * mm, "Montant TTC")
    y -= 6 * mm
    c.setFillColor(colors.black)
    totaux = contenu["totaux"]
    for i, l in enumerate(totaux["lignes"], start=1):
        y -= 6 * mm
        c.setFont("Helvetica", 8.5)
        c.drawString(colonnes[0] + 2 * mm, y + 1.5 * mm, str(i))
        c.drawString(colonnes[1], y + 1.5 * mm, l["designation"][:52])
        c.drawRightString(colonnes[3] - 2 * mm, y + 1.5 * mm, l["quantite"].replace(".", ","))
        c.drawRightString(colonnes[4] - 2 * mm, y + 1.5 * mm, _f(l["prix_unitaire_ttc"]))
        c.drawRightString(larg - marge - 2 * mm, y + 1.5 * mm, f"{_f(l['montant_ttc'])} [{l['groupe']}]")
        c.setStrokeColor(colors.HexColor("#e3e7ea"))
        c.line(marge, y, larg - marge, y)

    # Récapitulatif par groupe
    y -= 9 * mm
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(gris)
    c.drawString(marge, y, "GROUPE DE TAXATION")
    c.drawRightString(marge + 95 * mm, y, "Total TTC")
    c.drawRightString(marge + 125 * mm, y, "Montant HT")
    c.drawRightString(marge + 152 * mm, y, "TVA")
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8.5)
    for g, t in totaux["par_groupe"].items():
        y -= 4.5 * mm
        c.drawString(marge, y, GROUPES.get(g, g).replace("18 %", f"{totaux.get('taux_tva', '18')} %"))
        c.drawRightString(marge + 95 * mm, y, _f(t["ttc"]))
        c.drawRightString(marge + 125 * mm, y, _f(t["ht"]))
        c.drawRightString(marge + 152 * mm, y, _f(t["tva"]))

    # Totaux
    y -= 10 * mm
    xg, xd = larg - marge - 70 * mm, larg - marge
    def total(libelle, valeur, gras=False):
        nonlocal y
        c.setFont("Helvetica-Bold" if gras else "Helvetica", 10 if gras else 9)
        c.drawString(xg, y, libelle)
        c.drawRightString(xd, y, valeur)
        y -= 5 * mm
    total("Total HT", _f(totaux["total_ht"]))
    total(f"TVA {totaux.get('taux_tva', '18')} %", _f(totaux["total_tva"]))
    total("Total TTC", _f(totaux["total_ttc"]), gras=True)
    if totaux.get("aib_taux"):
        total(f"AIB {totaux['aib_taux']} % (retenue)", "- " + _f(totaux["aib_montant"]))
        c.setFillColor(accent)
        total("Net à payer", _f(totaux["net_a_payer"]), gras=True)
        c.setFillColor(colors.black)
    c.setFont("Helvetica", 8.5)
    mentions = [f"Mode de paiement : {LIBELLES_PAIEMENT.get(contenu.get('mode_paiement'), 'Espèces')}"]
    if contenu.get("motif"):
        mentions.append(f"Motif de l'avoir : {contenu['motif'][:80]}")
    commande = contenu.get("commande") or {}
    for cle, lib in (("reference_commande", "Réf. commande"), ("date_livraison", "Livraison souhaitée"),
                     ("conditions_paiement", "Conditions de paiement")):
        if commande.get(cle):
            mentions.append(f"{lib} : {str(commande[cle])[:60]}")
    for i, texte in enumerate(mentions[:4]):
        c.drawString(marge, y + (15 - 4 * i) * mm, texte)

    # Bloc de sécurité (fictif)
    y -= 6 * mm
    hauteur_bloc = 34 * mm
    c.setStrokeColor(colors.HexColor("#b9c1c7"))
    c.setDash(3, 2)
    c.rect(marge, y - hauteur_bloc, larg - 2 * marge, hauteur_bloc, fill=0, stroke=1)
    c.setDash()
    if securite and securite.get("code_dgi"):
        qr = QrCodeWidget(securite.get("qr") or securite["code_dgi"])
        b = qr.getBounds()
        taille = 28 * mm
        d = Drawing(taille, taille, transform=[taille / (b[2] - b[0]), 0, 0, taille / (b[3] - b[1]), 0, 0])
        d.add(qr)
        d.drawOn(c, marge + 3 * mm, y - hauteur_bloc + 3 * mm)
        tx = marge + 36 * mm
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(tx, y - 6 * mm, "ÉLÉMENTS DE SÉCURITÉ (SIMULATION, SANS VALEUR FISCALE)")
        c.setFont("Courier-Bold", 10)
        c.drawString(tx, y - 12 * mm, securite["code_dgi"])
        c.setFont("Helvetica", 8.5)
        c.drawString(tx, y - 17 * mm, f"NIM : {v.get('nim_simule', 'SIMU')}    Compteurs : {securite.get('compteurs', '')}")
        c.drawString(tx, y - 21.5 * mm, f"Heure DGI : {_date(securite.get('horodatage_dgi'))}")
        c.drawString(tx, y - 26 * mm, "Document produit par un prototype : il ne remplace pas une facture normalisée e-MECeF.")
    else:
        c.setFont("Helvetica-Bold", 9)
        c.drawString(marge + 4 * mm, y - 8 * mm, "PRO FORMA : DOCUMENT INFORMATIF SANS VALEUR COMPTABLE NI FISCALE"
                     if type_doc == "PF" else "En attente de confirmation par la DGI (simulée)")
        c.setFont("Helvetica", 8.5)
        c.drawString(marge + 4 * mm, y - 13 * mm, "Aucun code DGI n'est attribué à ce document.")

    # Pied de page
    c.setFont("Helvetica", 7.5)
    c.setFillColor(gris)
    if perso.get("conditions_paiement"):
        c.drawString(marge, 18 * mm, perso["conditions_paiement"][:120])
    if perso.get("pied_de_page"):
        c.drawString(marge, 14 * mm, perso["pied_de_page"][:120])
    c.drawRightString(larg - marge, 10 * mm, "SIMULATION - prototype BWAI'2026 - aucune valeur fiscale")
    c.showPage()
    c.save()
    return tampon.getvalue()
