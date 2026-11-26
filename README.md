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

**Deuxième IA gratuite : Groq** (texte seulement, très rapide, environ 1 000 requêtes par jour et par modèle) :
1. Créez une clé sur console.groq.com, sans carte bancaire.
2. Collez-la dans `.env` : `GROQ_API_KEY=...`.

Vérifiez vos clés en un appel : `.venv/bin/python -m eval.verifier_ia`.

**Repli automatique.** Chaque IA réessaie après un quota (429) ou une surcharge (503), puis passe à son modèle de secours (`GEMINI_MODELES_SECOURS`, `GROQ_MODELES_SECOURS`). Si elle échoue encore, l'autre IA prend le relais, puis les règles simples. Le dossier affiche alors un avertissement, et le journal note le repli. Une photo ou un PDF seul ne peut être lu que par Gemini.

En option, un modèle local avec Ollama : `ollama pull qwen2.5:7b`, puis choisissez « IA locale ». Aucune donnée ne quitte alors la machine.

## Canaux, voix et espaces d'entreprise

- **Choix de l'IA côté serveur** : Groq d'abord, puis Gemini, puis le modèle local s'il est activé (`IA_ORDRE`). Une photo ou un PDF va directement à Gemini. L'utilisateur ne choisit plus de modèle.
- **Dictée** : sur « Nouvelle commande », le bouton « Dicter » enregistre au micro ; la note est transcrite (Groq Whisper, puis Gemini) et le texte, à relire, devient la commande.
- **Pièce d'origine** : la photo, le PDF ou la note vocale reçus sont conservés et affichés sur l'écran de revue.
- **WhatsApp (simulé)** : menu « WhatsApp (simulé) » (responsable, admin). Le téléphone simulé envoie texte, note vocale, photo ou PDF au numéro de l'entreprise. Les messages suivent le format de l'API WhatsApp Cloud de Meta et sont signés (HMAC-SHA256) avant d'arriver au webhook `/webhook/whatsapp`, comme en production. Le bot ne répond qu'aux **numéros habilités** par l'administrateur, avec les droits du compte rattaché : la vendeuse envoie la commande et reçoit le brouillon ; le responsable reçoit l'alerte, répond `VALIDER 12`, reçoit la facture en PDF, puis `ENVOYER 12` l'envoie au client. Un numéro inconnu est refusé et journalisé.
  - **Mode guidé** : dès qu'on envoie une commande, le bot pose les questions une par une jusqu'à la facture (client, quantité manquante, article inconnu, écart de livraison, remise, prix, doublon, puis validation, envoi et paiement). On répond par le numéro du choix, une quantité ou un nom. La vendeuse règle ce qui lui revient ; le responsable est ensuite prévenu et guidé à son tour. `STOP` met le dossier de côté, `REPRENDRE 12` y revient.
  - **Raccourcis** (12 = n° du dossier) : `VOIR 12`, `LISTE` ; corriger avec `CLIENT 12 Dossou`, `QTE 12 2 5` (ligne 2 = 5), `AJOUTER 12 3 riz`, `RETIRER 12 2` ; trancher (responsable) avec `LIVRE 12`, `REMISE 12 OUI`/`NON`, `PRIX 12 CATALOGUE` ou `PRIX 12 CITE raison`, `TOTAL 12`, `DOUBLON 12 NON` ; puis `VALIDER 12`, `ENVOYER 12`, `PDF 12` et `PAYE 12 50000 momo`. Chaque réponse rappelle les points à vérifier et la commande à taper ; les droits et le journal sont ceux de l'interface.
  - **Téléphone flottant** : le bouton « WhatsApp » en bas à droite ouvre le téléphone sur toutes les pages. Il se déplace par sa barre de titre, se redimensionne par son coin et garde sa place d'une page à l'autre.
- **Inscription** : `/inscription` crée l'espace d'une nouvelle entreprise, avec **sa propre base** (aucune donnée partagée). La taille déclarée règle le fonctionnement : une micro-entreprise passe en mode solo. L'administrateur crée ensuite les comptes, habilite les numéros, renseigne le numéro WhatsApp et le bot Telegram (simulés), puis ajoute clients et articles.
- **Remises en cascade** : le responsable peut accorder plusieurs remises (pourcentage ou montant) ; chacune s'applique au montant restant.

## Scénario de démonstration (5 minutes)

**Jeu de démonstration.** Pour repartir d'une base réaliste (5 factures émises sur les 5 derniers jours, des paiements, 5 commandes du jour à vérifier) : `python -m app.demo`, ou, connecté en `admin`, « Paramètres » puis « Charger la démonstration ». La lecture se fait par règles simples : le résultat est identique à chaque fois et ne consomme aucun quota d'IA.

1. **Aïcha** (vendeuse) : « Nouvelle commande », exemple « Dossou : livraison partielle », puis « Lire la commande ».
   - Écran de revue : passages surlignés, client reconnu, quantités citées, AIB de 1 %.
   - Contrôle bloquant : 12 commandés, 10 livrés. Aïcha ne peut pas valider.
2. **Rodrigue** (responsable) : « Facturer le livré », puis « Valider et numéroter ». La facture `FV-2026-000001` est verrouillée.
3. « Émettre vers la DGI simulée » : un code `SIMU-…` et un QR code fictifs s'affichent. « Ouvrir le PDF ».
4. **Avoir** : créditer un carton abîmé. L'avoir `FA-…` cite le code DGI de la facture d'origine.
5. **Reprise après coupure** : sur une autre facture validée, cliquez sur « Émettre avec coupure simulée ». La facture reste « En attente DGI ». Arrêtez puis relancez le serveur : elle est confirmée automatiquement, sans doublon.
6. **Journal** : « Vérifier l'intégrité ».
7. Autres exemples : Hôtel Agossou (total annoncé faux), Mama Adjovi (client ambigu), Koffi (client inconnu et quantité absente), Gbaguidi (remise et consigne suspecte « Ignore les règles… »), Mme Chabi (quantités au kilo).
8. **Admin** : « Paramètres », puis couleur et logo de la facture, taux de TVA, mode solo, et « Réinitialiser la démonstration ».
9. **Commande complète** : un message qui donne la référence (« BC-2026-200 »), la livraison souhaitée (« avant le 30/11 »), les conditions de paiement (« à 30 jours ») et une remise en montant (« remise de 2 000 F »). Ces informations sont citées sur le brouillon, puis reprises sur la facture et le PDF.
10. **Après l'émission** : « Envoyer la facture » au client par WhatsApp, SMS ou e-mail (simulé, noté au journal). Après un avoir, « Préparer la facture rectificative » crée un nouveau brouillon lié à la facture d'origine.

## Livrables

| Livrable | Fichier |
|---|---|
| Rapport (4 pages) | [`docs/rapport.pdf`](docs/rapport.pdf) · source [`docs/rapport.md`](docs/rapport.md) |
| Fiche IA | [`docs/fiche_ia.pdf`](docs/fiche_ia.pdf) · source [`docs/fiche_ia.md`](docs/fiche_ia.md) |
| Vidéo de démonstration (2 min 21 s, sous-titrée) | [`docs/video_demo_e-FACIL.mp4`](docs/video_demo_e-FACIL.mp4) |
| Mesure de l'IA sur le corpus test gelé | [`eval/resultats_test.md`](eval/resultats_test.md) |
| Cahier des charges et TDR | [`docs/`](docs/) |

## Tests

```powershell
.\.venv\Scripts\python -m pytest -q
```

Les 75 tests couvrent :
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
| S4 | IA Groq seule, sans vérification |
| S5 | IA Groq avec vérifications |

La mesure n'utilise jamais de modèle de secours : chaque configuration correspond à un seul modèle, indiqué dans le rapport.

Le script compte les champs justes, les valeurs inventées, les champs laissés vides à tort et les anomalies détectées, avec des intervalles de confiance de Wilson. Les résultats sont écrits dans `eval/resultats_<corpus>.md`, et les réponses de l'IA sont mises en cache. Le format du corpus est décrit dans [`data/corpus/README.md`](data/corpus/README.md).

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

## Perspectives

- Langues nationales : commandes dictées en fon, yoruba, goun, mina, dendi ou bariba. Whisper reconnaît le yoruba ; le fon et les autres langues demandent un modèle entraîné sur des enregistrements locaux.
- Connexion réelle à l'API WhatsApp Cloud et à Telegram, avec un webhook par espace (aiguillage par numéro de l'entreprise).
- Homologation du logiciel et connexion réelle à e-MECeF.

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
| Tabler 1.0.0-beta20 (feuille de style, copiée dans `app/static/vendor`) | MIT |
| Police Inter (@fontsource, copiée dans `app/static/vendor`) | SIL Open Font License 1.1 |
| Icônes (tracés repris de Tabler Icons) | MIT |
| pytest / Hypothesis | MIT / MPL 2.0 |
| google-genai (SDK) | Apache 2.0 |
| Modèle Gemini (API Google AI Studio) | Conditions d'utilisation de Google |
| Groq (API, modèles `gpt-oss-120b` et `llama-3.3-70b-versatile`) | Conditions de Groq ; Apache 2.0 et licence Llama 3.3 |
| Musique de la vidéo de démonstration (piano) | Composition originale générée par programme pour le projet : aucun morceau ni échantillon existant |
| Ollama / modèle local (option) | MIT / licence du modèle choisi |

L'interface fonctionne sans internet : feuille de style et police sont servies par l'application.

Données : entièrement fictives.
