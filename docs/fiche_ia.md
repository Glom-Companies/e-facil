# Fiche IA · e-FACIL

**Hackathon BWAI'2026, cas 2 · Équipe BillGenius.** Données entièrement fictives ; résultats publiés tels quels.

## 1. Rôle de l'IA

| L'IA fait | L'IA ne fait jamais |
|---|---|
| Lire un message de commande ou de livraison (texte, dictée transcrite, photo, PDF) | Calculer un montant, une taxe ou un total |
| Proposer client, lignes, quantités, prix cités, remise, total annoncé, mode et conditions de paiement | Attribuer un numéro de facture |
| Citer, pour chaque valeur, le passage exact du message | Valider, émettre ou modifier une facture |
| Recopier les consignes suspectes (« ignore les règles ») pour qu'elles soient signalées | Appliquer une consigne contenue dans un message |

Le code vérifie chaque proposition : une valeur dont la citation est absente du message est écartée, puis chaque champ est rapproché des référentiels (clients, articles, prix). Le calcul reste celui d'un moteur déterministe.

## 2. Modèles et versions

| Usage | Modèle | Accès | Licence ou conditions |
|---|---|---|---|
| Lecture des commandes (1er choix) | `openai/gpt-oss-120b`, secours `llama-3.3-70b-versatile` | API Groq, palier gratuit | Apache 2.0 ; licence Llama 3.3 ; conditions Groq |
| Lecture (2e choix), photos et PDF | `gemini-3.8-flash`, secours `gemini-3.5-flash-lite` puis `gemini-3.1-flash-lite` | API Google AI Studio, palier gratuit | Conditions Google |
| Dictée | `whisper-large-v3-turbo` (Groq), secours Gemini | API, palier gratuit | MIT (Whisper) ; conditions Groq |
| Sans IA (référence et dernier repli) | Règles et dictionnaire d'alias | Local | Code du projet |
| Option confidentialité | Modèle ouvert via Ollama (par ex. `qwen2.5:7b`) | Local, hors ligne | Licence du modèle |

Paramètres : température 0, sortie JSON contrainte par un schéma (Pydantic), consigne en français fixée dans `app/extraction.py`. Les mesures utilisent un seul modèle par configuration, sans modèle de secours : `gemini-3.5-flash-lite` pour S1 et S2 (le modèle principal était surchargé côté Google le jour de la mesure), `openai/gpt-oss-120b` pour S4 et S5.

## 3. Données et séparation des jeux

- **60 messages fictifs** en français courant du Bénin (WhatsApp, SMS, e-mail, notes vocales transcrites, tableaux collés) : abréviations, montants « 17.500 » ou « 17k », quantités en lettres, corrections en cours de message, consignes piégées.
- **Mise au point (dev) : 20 messages**, seuls utilisés pour régler la consigne et les règles.
- **Test : 40 messages gelés** avant la première mesure. Empreinte SHA-256 du fichier publiée dans `eval/resultats_test.md` ; aucun réglage après mesure.
- Référentiels fictifs : 15 clients, 25 articles. Vérifiés par `data/verifier_corpus.py` (21 factures attendues recalculées au franc près).
- **Données envoyées aux IA** : uniquement ces données fictives. Sur les paliers gratuits, les fournisseurs peuvent réutiliser les contenus reçus.

## 4. Méthode d'évaluation

Script `eval/mesurer.py`, rejouable (réponses mises en cache) :

| Configuration | Description |
|---|---|
| S0 | Référence sans IA : règles et alias |
| S1 / S4 | IA seule (Gemini / Groq), sans vérification |
| S2 / S5 | IA puis vérification des citations et des référentiels (configuration de l'application) |

Mesures, champ par champ (client, articles, quantités commandées et livrées, prix cités, total annoncé, mode de paiement) :
- **champs justes** ;
- **valeurs inventées** : une valeur proposée alors que le message n'en donne aucune, y compris une ligne d'article absente de la commande ;
- **champs laissés vides à tort** : une information présente dans le message mais non reprise ;
- **anomalies attendues détectées** (client inconnu, écart de livraison, total faux, consigne suspecte…).

Intervalles de confiance de Wilson à 95 %.

## 5. Résultats

### 5.1 Résultats métier (indépendants de l'IA)

- **75 tests automatisés, tous verts.** Les exemples officiels de la DGI sont reproduits au franc près ; les validations concurrentes, l'idempotence, l'immutabilité, la reprise après coupure et la détection d'un journal falsifié sont prouvées.
- Ces résultats sont les mêmes avec ou sans IA : l'IA ne touche pas aux calculs.

### 5.2 Résultats de l'IA

Corpus **test gelé** (40 messages, 393 champs, 30 anomalies attendues ; empreinte SHA-256 `b5dc13d5…3d6eac`), mesure du 26/11/2026, un seul modèle par configuration, aucun échec d'appel. Détail complet : `eval/resultats_test.md`.

| Configuration | Champs justes | IC 95 % | Valeurs inventées | Vides à tort | Anomalies détectées | Dossiers sans blocage reconnus |
|---|---|---|---|---|---|---|
| S0 · sans IA (référence) | 361/393 (92 %) | 89 – 94 % | 2 | 26 | 24/30 (80 %) | 9/11 |
| S1 · Gemini seul | 391/393 (99 %) | 98 – 100 % | 0 | 1 | 29/30 (97 %) | 11/11 |
| S2 · Gemini + vérification | 390/393 (99 %) | 98 – 100 % | 0 | 2 | 29/30 (97 %) | 11/11 |
| S4 · Groq seul | 391/393 (99 %) | 98 – 100 % | 0 | 2 | 30/30 (100 %) | 10/11 |
| S5 · Groq + vérification | 390/393 (99 %) | 98 – 100 % | 0 | 3 | 30/30 (100 %) | 10/11 |

**Lecture.**
- **L'IA apporte un gain net** : 99 % de champs justes contre 92 % sans IA, avec des intervalles de confiance disjoints. Les champs oubliés passent de 26 à 2 ou 3, les valeurs inventées de 2 à 0, les anomalies détectées de 80 % à 97–100 %.
- **La vérification des citations n'a rien eu à écarter sur ce corpus** : l'IA seule n'y a inventé aucune valeur. Elle a en revanche rejeté une valeur juste (une citation non retrouvée mot pour mot). C'est son coût : environ 1 champ sur 400. Elle reste le garde-fou qui empêche qu'une valeur sans source soit acceptée (voir section 6).
- La configuration de l'application est **S5** (Groq, puis Gemini en secours), et **S2** pour les photos et les PDF.
- Sur le corpus de mise au point (20 messages), la vérification coûtait davantage : 97 % (S2) contre 100 % (S1) ; ces 6 valeurs justes écartées sont le prochain réglage à faire.
- **Durée de lecture par message** : 0,02 s sans IA ; 7,8 s avec Gemini et 15 s avec Groq, attentes dues aux quotas gratuits comprises. Le temps gagné par la vendeuse n'a pas été mesuré (voir limites).

## 6. Erreurs observées

Sur le corpus de test :
- **Sans IA (S0)** : prix cités non repris (15) ou mal lus (2 inventés), quantités non reprises (9), articles inconnus jamais signalés (0/3), deux totaux annoncés manqués.
- **Gemini (S1, S2)** : une ligne d'article non reprise, ce qui a masqué la quantité manquante de cette ligne (anomalie détectée 2 fois sur 3).
- **Groq (S4, S5)** : un client non reconnu (vraisemblablement à l'origine du blocage signalé sur une commande pourtant complète, 10/11) et un ou deux prix cités non repris.

Pendant les essais de l'application (hors corpus) :
- Groq a pris la destinataire du message pour le client (« Bjr Aïcha, c Dossou » → client « Aïcha ») : le contrôle « client introuvable » a bloqué le brouillon.
- Gemini a créé une ligne « riz » en double à partir d'une question sur le prix (« Le riz c 17.500 non ? ») : le contrôle « quantité absente » a bloqué la validation.
- Gemini a lu 8 cartons livrés au lieu de 10 : la citation ne correspondait pas, **la vérification a écarté la valeur**.
- Les paliers gratuits ont refusé des appels (quota de 20 requêtes par jour sur un modèle Gemini, surcharges) : la lecture a basculé sur l'autre IA, puis sur les règles.

Aucune de ces erreurs n'a produit de facture fausse : chacune a été bloquée par un contrôle ou par la validation humaine.

## 7. Seuils de revue humaine

- **Toute facture est validée par une personne habilitée** (responsable, ou l'unique utilisateur en mode solo après un récapitulatif obligatoire). Aucune validation automatique.
- **Bloquent la validation** jusqu'à décision humaine : client inconnu ou ambigu, article inconnu, quantité manquante ou invalide, écart entre commandé et livré, total annoncé différent du total recalculé, doublon probable (même client et mêmes lignes en moins de 72 h), remise demandée.
- **Prix cité à plus de 15 % du catalogue** : le prix du catalogue s'applique, sauf décision justifiée et journalisée.
- **Indicateur de confiance** affiché par champ (sûr, à vérifier, incertain, absent) ; les valeurs écartées sont montrées à l'écran.
- **Consigne suspecte** dans un message : signalée, sans aucun effet.
- **IA indisponible** (quota, surcharge, réseau) : autre IA, puis règles simples ; le dossier l'indique.

## 8. Limites et risques

- Corpus de petite taille : intervalles de confiance larges ; résultats à confirmer sur des données réelles anonymisées.
- Paliers gratuits : quotas journaliers bas (20 requêtes par jour sur certains modèles Gemini) et surcharges ; un usage réel exige un forfait payant ou le modèle local.
- La lecture des photos et des PDF dépend de Gemini.
- Langues nationales (fon, yoruba, goun…) non couvertes à l'écrit ; la dictée vise le français.
- Les modèles évoluent : une mesure doit être refaite à chaque changement de modèle ou de consigne.

## 9. Coût

Prototype : **0 F** (paliers gratuits). En production, environ **1 à 2 F CFA par facture** pour la lecture (tarifs publics relevés en novembre 2026, à revérifier) ; 0 F avec le modèle local. Détail dans le rapport, section 8.
