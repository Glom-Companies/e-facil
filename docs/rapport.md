# e-FACIL : du bon de commande à la facture vérifiable

**Rapport technique · Hackathon BWAI'2026, cas pratique 2 (automatisation de la facturation) · Équipe BillGenius**

Prototype de démonstration. Toutes les données sont fictives ; l'émission vers la DGI, les messages et les paiements sont simulés. Aucune facture produite n'a de valeur fiscale.

## 1. Besoin

Dans beaucoup de PME béninoises, la commande arrive par WhatsApp, SMS, e-mail ou photo d'un bon papier, puis elle est ressaisie dans Excel ou sur un carnet. Cette ressaisie produit des erreurs de quantité, de prix ou de client, des doublons, des factures qui ne correspondent pas à la livraison et des taxes mal calculées. L'enjeu est aussi légal : une vente doit faire l'objet d'une facture normalisée (e-MECeF), et le droit comptable OHADA interdit de modifier une écriture validée.

e-FACIL transforme un message commercial en **projet de facture vérifiable**, le fait valider par une personne habilitée, puis simule son émission, son envoi et son encaissement. La règle de conception est simple : **l'IA lit, le code calcule et contrôle, l'humain décide.**

## 2. Parcours

1. **Réception** : la vendeuse colle le message, dicte la commande, joint une photo ou un PDF, ou transfère la commande au numéro WhatsApp de l'entreprise (simulé, format de l'API WhatsApp Cloud, messages signés).
2. **Lecture** : l'IA extrait client, lignes, quantités, prix cités, remise, total annoncé, mode et conditions de paiement. Chaque valeur porte **la citation exacte** du message dont elle vient et un indicateur de confiance. Une valeur absente reste vide.
3. **Livraison** : le bon de livraison est rattaché ; les quantités livrées sont comparées aux quantités commandées.
4. **Contrôles et calcul** : le moteur recalcule tout et liste les anomalies (section 4).
5. **Revue** : l'écran de revue surligne la source de chaque champ ; la vendeuse corrige ; le responsable tranche les anomalies. Par WhatsApp, le bot pose les mêmes questions une par une.
6. **Validation** : la facture reçoit un numéro unique, sans trou, et devient non modifiable, y compris dans la base.
7. **Émission simulée** vers une DGI fictive qui recalcule les totaux et renvoie un code et un QR code ; PDF sur le modèle e-MECeF, avec la mention SIMULATION.
8. **Après l'émission** : envoi au client (simulé), paiements Mobile money ou espèces avec reçu, avoir lié au code DGI d'origine, facture rectificative, export comptable, rapport Z, journal d'audit.

Quatre rôles se partagent ce parcours : vendeuse, responsable, comptable, administrateur. Un mode solo couvre la micro-entreprise d'une seule personne.

## 3. Architecture

Application web Python (FastAPI, gabarits Jinja2), base SQLite par entreprise, PDF ReportLab, fonctionnement hors ligne des écrans (aucune ressource chargée depuis internet).

| Module | Rôle |
|---|---|
| `moteur.py` | Calculs purs en décimal exact : lignes, groupes de taxe, TVA, AIB, remises, net à payer. Indépendant de l'IA et de l'interface. |
| `extraction.py` | Lecteurs interchangeables : règles simples (sans IA), Groq, Gemini (photo et PDF), modèle local. Nouvel essai sur quota ou surcharge, modèle de secours, puis repli sur les règles. |
| `brouillon.py` | Vérification des citations, rapprochement avec les référentiels, détection des anomalies. |
| `services.py` | Opérations métier, droits par rôle, transactions, idempotence, DGI simulée, avoirs, paiements. |
| `db.py` | Schéma, déclencheurs d'immutabilité, numérotation sans trou, journal chaîné par empreintes SHA-256. |
| `canaux.py` | Webhook WhatsApp (signature HMAC), numéros habilités, bot guidé. |
| `web.py`, `pdf.py` | Interface responsive (session, protection CSRF) et facture PDF. |

L'IA ne calcule aucun montant, n'attribue aucun numéro et ne valide rien. Le fournisseur d'IA se change par un paramètre ; sans clé, tout le parcours fonctionne avec les règles simples.

## 4. Contrôles

| Contrôle | Effet |
|---|---|
| Citation absente du message | Valeur écartée et affichée dans « Valeurs écartées » |
| Client inconnu ou ambigu, article inconnu, quantité manquante ou invalide | Validation bloquée jusqu'à correction |
| Écart entre quantité commandée et livrée | Bloquant : le responsable décide (on facture le livré) |
| Total annoncé différent du total recalculé | Bloquant : seul le total recalculé peut être facturé |
| Prix cité à plus de 15 % du catalogue | Le prix du catalogue s'applique, sauf décision justifiée |
| Même client et mêmes lignes en moins de 72 h | Doublon probable, bloquant |
| Remise demandée | Jamais appliquée sans l'accord du responsable |
| Consigne glissée dans un message (« ignore les règles ») | Traitée comme une donnée, signalée, sans effet |
| Double clic, validations simultanées, coupure pendant l'émission | Une seule facture, reprise sans doublon au redémarrage |
| Modification manuelle de la base | Refusée par les déclencheurs ; le journal altéré est détecté |

Les seuils (15 %, 72 h), le taux de TVA et le mode d'arrondi sont paramétrables.

## 5. Protocole et résultats des tests

### 5.1 Fiabilité métier (sans IA)

**74 tests automatisés, tous verts** (`python -m pytest -q`), sans aucun appel à une IA réelle :

| Domaine | Tests | Ce qui est prouvé |
|---|---|---|
| Moteur de calcul | 18 | Exemples officiels de la DGI reproduits au franc près (2 320 F → 1 966 + 354 ; 3 × 1 340 F → 3 407 + 613), facture réelle observée, tests de propriétés (Hypothesis) |
| Scénarios de recette | 20 | Validations concurrentes, idempotence, immutabilité dans la base, avoirs plafonnés, reprise après coupure, journal falsifié détecté, consigne suspecte, citation inventée écartée, jeu de démonstration rejouable, comptes en T équilibrés |
| Interface web | 10 | Parcours complet, protection CSRF, droits par rôle, recherche, journal |
| Lecture par IA | 22 | Quotas, surcharge, JSON invalide, modèle de secours, repli d'une IA à l'autre puis sur les règles |
| Canal WhatsApp | 4 | Signature, numéros habilités, rejeu, parcours guidé complet jusqu'au paiement |

### 5.2 Apport de l'IA

Protocole : un corpus de **60 messages fictifs** (20 de mise au point, 40 de test gelés avant la mesure ; empreinte SHA-256 publiée), comparé à une **méthode de référence sans IA** (règles et dictionnaire d'alias). Pour chaque configuration, on compte les champs justes, les valeurs inventées, les champs laissés vides à tort et les anomalies détectées, avec des intervalles de confiance de Wilson à 95 %. Les réglages n'ont été faits que sur le corpus de mise au point. Le détail figure dans la fiche IA (`docs/fiche_ia.md`) et dans `eval/resultats_test.md`.

Résultats sur les **40 messages de test gelés** (393 champs, 30 anomalies attendues), sans aucun échec d'appel :

| Configuration | Champs justes (IC 95 %) | Valeurs inventées | Vides à tort | Anomalies détectées |
|---|---|---|---|---|
| S0 · référence sans IA | 92 % (89 – 94 %) | 2 | 26 | 80 % |
| S1 · Gemini seul | 99 % (98 – 100 %) | 0 | 1 | 97 % |
| S2 · Gemini + vérification | 99 % (98 – 100 %) | 0 | 2 | 97 % |
| S4 · Groq seul | 99 % (98 – 100 %) | 0 | 2 | 100 % |
| S5 · Groq + vérification (application) | 99 % (98 – 100 %) | 0 | 3 | 100 % |

Modèles mesurés : `gemini-3.5-flash-lite` et `openai/gpt-oss-120b`, sans modèle de secours.

## 6. Comparaison à la référence

- **Exactitude de la lecture** : 99 % de champs justes avec l'IA contre 92 % avec la méthode de référence, intervalles de confiance disjoints. Les oublis tombent de 26 à 2 ou 3 champs ; la référence rate surtout les prix cités et les quantités écrites librement.
- **Aucune valeur inventée** par les configurations avec IA, contre 2 pour la référence.
- **Détection des anomalies** : 97 à 100 % avec l'IA contre 80 % sans IA. L'objectif du cahier des charges (au moins 90 %) est atteint avec l'IA, pas sans.
- **Calculs** : identiques dans toutes les configurations. Ils ne dépendent pas de l'IA et reproduisent les exemples officiels de la DGI.
- **Coût de la vérification** : sur ce corpus, l'IA n'a rien inventé, la vérification n'a donc rien eu à écarter ; elle a rejeté une valeur juste. Elle a en revanche écarté, pendant les essais, une quantité livrée mal lue (8 au lieu de 10). Nous la gardons : une valeur juste à ressaisir coûte moins qu'une valeur fausse acceptée.
- **Temps** : la lecture prend 8 à 15 s par message avec les IA gratuites (attentes de quota comprises) contre une saisie manuelle que nous n'avons pas chronométrée. Le gain de temps réel reste à mesurer en expérimentation (section 9).

Les erreurs observées et les seuils de revue humaine sont détaillés dans la fiche IA.

## 7. Limites

- **Simulation** : la DGI, WhatsApp, les envois et les paiements sont simulés. L'homologation du logiciel (article 162 bis du CGI) et la connexion à e-MCF ne sont pas traitées.
- **Arrondi** : l'arrondi par groupe de taxe est déduit des exemples de la DGI ; il reste à confirmer sur la documentation officielle de l'API (il est paramétrable).
- **Périmètre fiscal** : AIB à 3 %, factures d'acompte, de solde et récurrentes non couverts. Les comptes de l'export comptable (411, 701, 4431) sont à faire confirmer par un comptable.
- **IA** : les paliers gratuits imposent des quotas (Gemini a refusé des appels pendant nos essais) ; la lecture des photos dépend de Gemini. Le corpus de 40 messages donne des intervalles de confiance larges.
- **Temps gagné** : nous avons mesuré la durée de lecture par message, pas encore le temps total d'une vendeuse avec et sans e-FACIL ; c'est la première mesure à faire en expérimentation.

## 8. Coûts estimatifs d'usage

**Prototype : 0 F.** Paliers gratuits de Groq et de Gemini, logiciels libres, SQLite, aucun serveur payant.

**En production**, une facture demande en général un appel d'IA pour la commande et un pour la livraison. Une requête compte environ 1 400 jetons en entrée (consigne, schéma et message) et 400 à 900 en sortie. Aux tarifs publics relevés en novembre 2026 (à revérifier sur les pages officielles) :

| Modèle | Prix pour 1 million de jetons (entrée / sortie) | Coût estimé par facture |
|---|---|---|
| Groq `gpt-oss-120b` | 0,15 $ / 0,60 $ | environ 0,002 $, soit 1 à 2 F CFA |
| Gemini 3.5 Flash-Lite | 0,30 $ / 2,50 $ | environ 0,003 $, soit 2 F CFA |

Pour une PME qui émet 500 factures par mois, l'IA coûterait de l'ordre de **1 000 F CFA par mois**. L'hébergement (petit serveur virtuel) et l'homologation DGI dominent le coût réel. Le modèle local (Ollama) supprime le coût d'IA et garde les données dans l'entreprise, au prix d'un poste plus puissant.

## 9. Étapes d'une expérimentation

1. **Choisir 2 ou 3 PME pilotes** (distribution, restauration, quincaillerie) avec leur accord écrit sur le traitement des données.
2. **Mesurer la situation de départ** pendant une semaine : temps de saisie par facture, erreurs relevées, factures oubliées.
3. **Remplacer les données fictives** par leurs référentiels (clients, articles, taux d'AIB), validés par leur comptable.
4. **Utiliser e-FACIL en parallèle** de leur méthode actuelle pendant 4 semaines, sans émission réelle, et comparer : temps, erreurs évitées, anomalies signalées à tort.
5. **Préparer l'homologation** auprès de la DGI et la connexion à e-MCF ; ouvrir le vrai numéro WhatsApp Business.
6. **Décider** de la suite à partir des chiffres mesurés, et publier les résultats tels quels.
