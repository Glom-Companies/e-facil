# Plan de l'équipe BillGenius

**Produit : e-FACIL**, pour *e-Facturation Assistée, Contrôlée, Intègre et Lisible*. On transforme un bon de commande reçu par WhatsApp, SMS, e-mail ou photo en une facture vérifiable. Hackathon BWAI'2026, cas 2.

**Échéances (jeudi 26/11) :** tout est prêt à **09:00** au plus tard. **Pitch à 13:45.**

## Où en est-on (01:45)

La base fonctionne et est testée (36 tests verts) :
- lecture des commandes, par règles simples ou par l'IA Gemini (photo et PDF compris), avec la citation source de chaque champ ;
- 11 contrôles, dont l'écart entre commandé et livré, le client inconnu ou ambigu, le prix inhabituel, le doublon, le total faux, la remise et la consigne suspecte ;
- calcul conforme aux exemples de la DGI : prix TTC, groupes de taxe, TVA 18 %, AIB, net à payer ;
- validation par un responsable, numérotation sans trou, verrouillage jusque dans la base, émission DGI simulée, PDF de facture, avoirs, paiements et reçus, journal chaîné, reprise après coupure ;
- interface web responsive : 4 rôles, comptabilité, rapport du jour, export CSV, personnalisation de la facture, mode solo.

Il reste à **affiner, mesurer, prouver et présenter**.

## Qui fait quoi

| Personne | Mission | Fiche |
|---|---|---|
| **Merveilleux** (responsable technique) | IA réelle (Gemini, photo et PDF), mesure, fiche IA, sécurité, intégration des *pull requests*, gel du code | [merveilleux.md](merveilleux.md) |
| **Livingstone** (chef d'équipe) | Clé IA, corpus de test et référentiels, pitch, remise finale | [livingstone.md](livingstone.md) |
| **Précieux** | Interface, parcours de démo, qualité, tests | [precieux.md](precieux.md) |
| **Merveille** | Rapport de 3 à 5 pages, vidéo de 2 à 3 minutes | [merveille.md](merveille.md) |

Les rôles peuvent s'échanger si quelqu'un est plus à l'aise ailleurs. Prévenez le groupe.

## Jalons

| Heure | Ce qui doit être fait |
|---|---|
| 02:15 | Chacun a cloné le dépôt, lancé l'application et vu les 36 tests passer |
| 04:00 | Corpus de mise au point livré (20 messages) ; liste des défauts d'interface ; plan du rapport |
| 06:00 | Corpus de test gelé (40 messages) et première mesure ; corrections d'interface fusionnées ; premier jet du rapport |
| 07:30 | **Gel du code** : étiquette `v1.0`. Plus aucun changement de fonctionnalité, seulement des corrections bloquantes |
| 08:30 | Vidéo montée ; rapport et fiche IA finaux avec les vrais chiffres |
| 09:00 | Tout est remis ou prêt à remettre |
| 13:45 | Pitch |

## Démarrer (tout le monde)

```powershell
git clone https://github.com/Glom-Companies/e-facil.git
cd e-facil
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
copy .env.exemple .env
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m uvicorn app.web:app --port 8000
```

Ouvrir http://localhost:8000. Comptes : `aicha`, `rodrigue`, `mireille` et `admin`, mot de passe `demo2026`. Lisez le [README](../README.md) et le [cahier des charges](../docs/CDC_facturation_BWAI2026.pdf).

## Règles de travail

1. **Une branche par personne** (`merveilleux/ia`, `precieux/interface`, `merveille/rapport`, `livingstone/corpus`), puis une *pull request* vers `main`. Merveilleux relit et fusionne.
2. **Les tests restent verts.** Lancez `python -m pytest -q` avant chaque *pull request*.
3. **Ne touchez pas** à `app/moteur.py`, `app/db.py` ni aux règles de calcul sans en parler au groupe : ils sont validés par les exemples officiels de la DGI.
4. **Aucun secret dans Git.** La clé Gemini va dans `.env`, qui n'est jamais versionné. Ne la collez jamais dans le groupe WhatsApp.
5. **Aucune donnée réelle.** Ni vrais noms, ni vrais IFU, ni vrais numéros, ni la vraie facture reçue. Tout est fictif.
6. **Ne dites jamais** « conforme DGI », « certifié » ou « homologué ». Dites « simulation » et « prépare l'homologation ».
7. Un blocage de plus de 20 minutes se signale tout de suite dans le groupe.

## Ce qui nous distingue (à répéter partout : rapport, vidéo, pitch)

- **L'IA lit, le code calcule, l'humain décide.** L'IA ne calcule jamais un montant.
- **Aucune valeur inventée.** Chaque champ cite le passage du message dont il vient, et le code vérifie la citation.
- **Calculs prouvés** par les exemples officiels de la DGI.
- **Intégrité** : numérotation sans trou, facture verrouillée jusque dans la base, avoir lié au code DGI, journal infalsifiable, reprise après coupure sans doublon.
- **Apport de l'IA mesuré** sur un corpus gelé, face à une méthode sans IA, avec les résultats publiés tels quels.
- **Coût nul**, et une option locale pour la confidentialité.
