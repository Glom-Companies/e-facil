# e-FACIL : du bon de commande à la facture vérifiable

**e-FACIL** veut dire *e-Facturation Assistée, Contrôlée, Intègre et Lisible*. C'est le prototype de l'équipe **BillGenius** au hackathon **BWAI'2026, cas pratique 2 : automatisation de la facturation**.

Une PME béninoise reçoit une commande par WhatsApp, SMS, e-mail ou photo. Le prototype :
1. lit le message et propose un brouillon. Chaque champ affiche le passage du message dont il vient et un niveau de confiance ; une information absente reste vide ;
2. contrôle le brouillon : client et articles connus, prix habituels, écart entre commande et livraison, doublon, total annoncé, remise, consigne suspecte ;
3. calcule les montants de façon déterministe, selon les règles e-MECeF de la DGI : prix TTC, groupes de taxe, TVA à 18 %, AIB, net à payer ;
4. fait valider la facture par un responsable. Elle reçoit alors un numéro sans trou et devient non modifiable ;
5. l'émet vers une **DGI simulée**, produit le PDF, puis gère les avoirs, les paiements simulés, le journal d'audit et la comptabilité.

> **Simulation.** Aucune facture produite n'a de valeur fiscale. Un logiciel de facturation doit être homologué par la DGI avant tout usage réel (article 162 bis du Code général des impôts). Toutes les données sont fictives.

## Démarrage rapide (Windows, PowerShell)

```powershell
cd facturation-pme
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
copy .env.exemple .env
.\.venv\Scripts\python -m uvicorn app.web:app --port 8000
```

Pour une démonstration déjà remplie (3 factures émises, 5 commandes à vérifier, graphique et contrôles visibles), avant de lancer le serveur :

```powershell
.\.venv\Scripts\python -m app.demo
```

Ouvrir http://localhost:8000. Sous Linux ou macOS, remplacez `.\.venv\Scripts\python` par `.venv/bin/python`.

### Comptes de démonstration

Le mot de passe est `demo2026` pour tous les comptes (variable `DEMO_MOT_DE_PASSE` du fichier `.env`).

| Identifiant | Personne | Rôle |
|---|---|---|
| `aicha` | Aïcha | Vendeuse : saisit les commandes et corrige les brouillons |
| `rodrigue` | Rodrigue | Responsable : tranche les anomalies, valide, émet, crée les avoirs |
| `mireille` | Mireille | Comptable : règle taxes et AIB, consulte la comptabilité |
| `admin` | Admin | Administrateur : paramètres, réinitialisation de la démo |

### Lecture par l'IA (gratuite)

Sans clé, l'application utilise la lecture par **règles simples** (sans IA). Pour activer l'IA :
1. Créez une clé gratuite sur Google AI Studio, sans activer la facturation.
2. Collez-la dans `.env` : `GEMINI_API_KEY=...`.
3. Relancez l'application. Le choix « IA Gemini » devient le choix par défaut.

Sur le palier gratuit, Google peut utiliser les contenus envoyés pour améliorer ses services : **n'envoyez que des données fictives**.

En option, un modèle local avec Ollama : `ollama pull qwen2.5:7b`, puis choisissez « IA locale ». Aucune donnée ne quitte alors la machine.

## Scénario de démonstration (5 minutes)

1. **Aïcha** (vendeuse) : « Nouvelle commande », exemple « Dossou : livraison partielle », puis « Lire la commande ».
   - Écran de revue : passages surlignés, client reconnu, quantités citées, AIB de 1 %.
   - Contrôle bloquant : 12 commandés, 10 livrés. Aïcha ne peut pas valider.
2. **Rodrigue** (responsable) : « Facturer le livré », puis « Valider et numéroter ». La facture `FV-2026-000001` est verrouillée.
3. « Émettre vers la DGI simulée » : un code `SIMU-…` et un QR code fictifs s'affichent. « Ouvrir le PDF ».
4. **Avoir** : créditer un carton abîmé. L'avoir `FA-…` cite le code DGI de la facture d'origine.
5. **Reprise après coupure** : sur une autre facture validée, cliquez sur « Émettre avec coupure simulée ». La facture reste « En attente DGI ». Arrêtez puis relancez le serveur : elle est confirmée automatiquement, sans doublon.
6. **Journal** : « Vérifier l'intégrité ».
7. Autres exemples : Hôtel Agossou (total annoncé faux), Mama Adjovi (client ambigu), Koffi (client inconnu et quantité absente), Gbaguidi (remise et consigne suspecte « Ignore les règles… »), Mme Chabi (quantités au kilo).
8. **Admin** : « Paramètres », puis couleur et logo de la facture, mode solo, et « Réinitialiser la démonstration ».

## Tests

```powershell
.\.venv\Scripts\python -m pytest -q
```

Les 36 tests couvrent :
- les **exemples officiels de la DGI** (2 320 F donnent 1 966 + 354 ; 3 × 1 340 F donnent 3 407 + 613) et une facture réelle observée (groupe E, AIB 1 %) ;
- des **tests de propriétés** (Hypothesis) sur les calculs ;
- les **scénarios de recette** du cahier des charges : validations concurrentes, idempotence, immutabilité jusque dans la base, avoirs, reprise après coupure, journal falsifié, consigne suspecte, citation inventée ;
- le **parcours web** complet, avec la protection CSRF et les droits.

## Mesure de l'IA

```powershell
.\.venv\Scripts\python -m eval.mesurer data\corpus\test.jsonl --configs S0 S1 S2
```

| Configuration | Description |
|---|---|
| S0 | Règles simples, sans IA (point de comparaison) |
| S1 | IA Gemini seule, sans vérification |
| S2 | IA Gemini avec vérification des citations et des référentiels (démo) |
| S3 | IA locale (Ollama) avec vérifications |

Le script compte les champs justes, les valeurs inventées, les champs laissés vides à tort et les anomalies détectées, avec des intervalles de confiance de Wilson. Les résultats sont écrits dans `eval/resultats_<corpus>.md`, et les réponses de l'IA sont mises en cache. Le format du corpus est décrit dans `data/corpus/exemple.jsonl`.

## Architecture

```
app/
  moteur.py      calculs purs : lignes, groupes de taxe, TVA, AIB, net à payer (Decimal, jamais de float)
  texte.py       lecture des montants (« 17.500 », « 17k ») et des quantités, citations
  extraction.py  extracteurs interchangeables : règles, Gemini, Ollama ; sortie structurée avec citations
  brouillon.py   vérification des citations, rapprochement des référentiels, anomalies
  services.py    opérations métier, droits, transactions, idempotence, DGI simulée, avoirs, paiements
  db.py          SQLite : schéma, déclencheurs d'immutabilité, numérotation sans trou, journal chaîné
  pdf.py         facture PDF sur le modèle e-MECeF, mention SIMULATION
  web.py         interface FastAPI + Jinja2 (responsive), session, protection CSRF
data/            entreprise, clients, articles et exemples fictifs ; corpus de test
eval/            mesure de l'IA
tests/           tests automatisés
```

## Règles appliquées

| Règle | Origine |
|---|---|
| Aucune valeur inventée ; une valeur dont la citation est absente du message est écartée | TDR, choix |
| Prix saisis TTC. HT = arrondi(TTC ÷ 1,18) par groupe de taxe ; TVA = TTC − HT | Annexe e-MECeF (DGI, 2022) |
| AIB 0, 1 ou 5 % selon la fiche client ; net à payer = TTC − AIB | CGI, annexe e-MECeF |
| On facture le livré ; un écart avec la commande bloque jusqu'à la décision du responsable | TDR |
| Numéro attribué à la validation seulement, sans trou ; facture validée non modifiable, y compris dans la base | OHADA (AUDCIF art. 20 et 22), TDR |
| Correction par avoir citant le code DGI d'origine ; total des avoirs ≤ facture | Guide DGI |
| Journal en ajout seul, chaîné par empreintes SHA-256 | OHADA (chemin de révision), TDR |
| Mention SIMULATION ; aucun logo officiel | Choix |

Paramètres modifiables : seuil de prix inhabituel (15 %), fenêtre de doublon (72 h), arrondi par groupe ou par ligne.

## Limites connues

- L'émission DGI est simulée ; l'API e-MCF réelle et l'homologation ne sont pas traitées.
- L'arrondi par groupe est déduit des exemples de la DGI et du fonctionnement décrit d'e-MCF ; il reste à confirmer sur la documentation officielle de l'API.
- L'AIB à 3 %, les factures d'acompte, de solde et récurrentes ne sont pas pris en charge.
- Les comptes de l'export comptable (411, 701, 4431) sont à faire confirmer par un comptable.
- La lecture des photos et PDF n'est disponible qu'avec Gemini.

## Licences

| Composant | Licence |
|---|---|
| FastAPI, Uvicorn, Pydantic, python-multipart | MIT, BSD, MIT, Apache 2.0 |
| Jinja2, MarkupSafe, itsdangerous, Starlette | BSD |
| ReportLab (version libre) | BSD |
| Tabler (feuille de style, chargée depuis jsDelivr) | MIT |
| pytest / Hypothesis | MIT / MPL 2.0 |
| google-genai (SDK) | Apache 2.0 |
| Modèle Gemini (API Google AI Studio) | Conditions d'utilisation de Google |
| Ollama / modèle local (option) | MIT / licence du modèle choisi |

Données : entièrement fictives.
