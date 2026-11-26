# Brief : jeu de données de démonstration et corpus de test

> À donner tel quel à votre assistant de développement. Le résultat doit pouvoir être déposé sans retouche dans le dossier `data/` du prototype. **Respecte exactement les noms de fichiers, de champs et de codes.** Le moteur de facturation les lit directement.

## 1. Contexte en 6 lignes

- Hackathon BWAI'2026, cas 2 « automatisation de la facturation » pour les PME béninoises.
- Le prototype reçoit un **bon de commande** (message WhatsApp ou SMS collé, e-mail) et éventuellement un **bon de livraison**. L'IA en extrait les champs, puis le moteur contrôle et calcule. Un humain valide.
- Ton travail : produire **l'entreprise fictive, ses référentiels clients et articles, et 60 messages réalistes avec la réponse attendue**.
- Ces messages servent à deux choses : la démo, et **la mesure de l'IA** (comparaison règles simples / IA / IA avec contrôles).
- **Tout est fictif.** Aucun nom, IFU, téléphone ou e-mail d'une personne ou entreprise réelle. Aucune marque déposée dans les désignations.
- Monnaie : franc CFA (XOF), **montants entiers**, pas de centimes.

## 2. Fichiers à produire

```
data/
  entreprise.json
  clients.json
  articles.json
  corpus/
    dev.jsonl        (20 messages, servent à mettre au point les prompts)
    test.jsonl       (40 messages, gelés, jamais montrés pendant la mise au point)
    LISEZMOI.md      (répartition des pièges, empreinte SHA-256 de test.jsonl)
  verifier_corpus.py (script de contrôle, voir section 7)
```

Encodage UTF-8, sans BOM. Un objet JSON par ligne dans les `.jsonl`.

## 3. L'entreprise fictive (`entreprise.json`)

Un grossiste en produits alimentaires et boissons à Cotonou, au régime du réel, donc ses ventes sont en **groupe B (TVA 18 %)**. Il propose aussi une prestation de livraison.

```json
{
  "raison_sociale": "SÈNA DISTRIBUTION SARL",
  "ifu": "9900000000001",
  "rccm": "RB/COT/26 B 00000",
  "adresse": "Lot 000, Akpakpa, Cotonou",
  "telephone": "+229 01 00 00 00 00",
  "email": "contact@sena-distribution.example",
  "regime_fiscal": "REEL",
  "nim_simule": "SIMU000001",
  "utilisateurs": [
    {"id": "U-01", "nom": "Aïcha", "role": "vendeur"},
    {"id": "U-02", "nom": "Rodrigue", "role": "responsable"},
    {"id": "U-03", "nom": "Mireille", "role": "comptable"},
    {"id": "U-04", "nom": "Admin", "role": "admin"}
  ]
}
```

Garde ces valeurs. Les IFU fictifs ont **13 chiffres et commencent par `99`**, pour qu'on les reconnaisse comme faux.

## 4. Référentiels

### `clients.json` (15 clients)

```json
{
  "id": "C-001",
  "nom": "Ets Dossou et Frères",
  "alias": ["Dossou", "Ets Dossou", "tonton Dossou"],
  "type": "ENTREPRISE_REEL",
  "ifu": "9900000000017",
  "adresse": "Marché Dantokpa, Cotonou",
  "telephone": "+229 01 00 00 01 17",
  "aib_taux": 1,
  "delai_paiement_jours": 30
}
```

- **`type`** vaut `ENTREPRISE_REEL`, `ENTREPRISE_TPS`, `PARTICULIER`, `STRUCTURE_ETAT` ou `CLIENT_EXPORT`. Répartition :
  - 6 `ENTREPRISE_REEL` ;
  - 4 `ENTREPRISE_TPS` (petites boutiques, revendeuses de marché) ;
  - 3 `PARTICULIER`, avec `ifu` à `null` ;
  - 1 `STRUCTURE_ETAT` (une cantine scolaire publique, par exemple) ;
  - 1 `CLIENT_EXPORT` (un acheteur au Togo ou au Niger).
- **`aib_taux`** vaut 0, 1 ou 5. Mets 1 pour la plupart des entreprises au réel, 5 pour un ou deux clients, 0 pour les particuliers.
- **`alias`** liste la façon dont les gens les appellent vraiment dans les messages. **Deux clients doivent partager un alias** (deux « Mama Adjovi » par exemple), pour créer une ambiguïté.
- Noms et lieux plausibles au Bénin : Dossou, Houngbédji, Adjovi, Agossou, Sossou, Gbaguidi, Chabi, Orou, Akpovi, Kpadonou… Lieux : Dantokpa, Akpakpa, Cadjèhoun, Fidjrossè, Godomey, Abomey-Calavi, Porto-Novo, Parakou, Bohicon.

### `articles.json` (25 articles)

```json
{
  "id": "A-003",
  "designation": "Riz parfumé sac de 25 kg",
  "alias": ["riz 25kg", "sac de riz", "riz parfumé"],
  "unite": "sac",
  "prix_unitaire_ttc": 17500,
  "groupe_taxe": "B",
  "quantite_decimale": false
}
```

- **Prix en TTC** (taxes comprises), comme dans e-MECeF, et plausibles sur le marché béninois.
- **`groupe_taxe`** :
  - `B` pour presque tout ;
  - `A` (exonéré) pour 2 produits de base, à marquer `"a_verifier": true`, car on ne connaît pas la liste officielle exacte ;
  - 1 article de service : `"Livraison Cotonou"`, unité `forfait`, groupe `B`.
- **`quantite_decimale`** vaut `true` pour 3 articles vendus au poids ou au litre (kg, litre). Ils acceptent au plus 3 décimales.
- Désignations génériques, **sans marque** : « Huile végétale bidon 5 L », « Savon de ménage carton de 72 », « Eau minérale pack de 12 × 1,5 L », « Sucre en morceaux carton », « Lait concentré sucré carton de 48 »…

## 5. Format d'un message de corpus

Une ligne JSON par message :

```json
{
  "id": "T-007",
  "split": "test",
  "canal": "WHATSAPP",
  "date_reception": "2026-11-20T09:14:00",
  "auteur_affiche": "Tonton Dossou",
  "texte_commande": "Bjr Aïcha, c Dossou. Envoi moi 12 cartons savon et 5 sac riz 25kg comme dab. Le riz c 17.500 non ? Je paie momo",
  "texte_livraison": "BL 0231 du 21/11 - Ets Dossou : savon carton x10 (rupture 2), riz 25kg x5. Reçu par le magasinier.",
  "doublon_de": null,
  "attendu": {
    "client": {
      "id_referentiel": "C-001",
      "citation": "c Dossou"
    },
    "lignes": [
      {
        "article_id": "A-011",
        "citation_designation": "cartons savon",
        "quantite_commandee": "12",
        "citation_quantite_commandee": "12",
        "quantite_livree": "10",
        "prix_unitaire_ttc_cite": null,
        "citation_prix": null
      },
      {
        "article_id": "A-003",
        "citation_designation": "sac riz 25kg",
        "quantite_commandee": "5",
        "citation_quantite_commandee": "5",
        "quantite_livree": "5",
        "prix_unitaire_ttc_cite": 17500,
        "citation_prix": "17.500"
      }
    ],
    "mode_paiement": "MOBILEMONEY",
    "citation_paiement": "momo",
    "total_ttc_cite": null,
    "remise_demandee": null
  },
  "anomalies_attendues": ["ECART_COMMANDE_LIVRAISON"],
  "pieges": ["separateur_milliers_point", "abreviations_sms", "comme_d_habitude"],
  "facture_attendue": null,
  "commentaire": "Le client cite le bon prix ; seule la livraison partielle bloque."
}
```

### Règles strictes du champ `attendu`
1. **`attendu` contient ce qu'un humain attentif extrairait, rien de plus.** Si une information n'est pas dans le texte, la valeur est `null`. **On n'invente jamais.** Le prix du catalogue ne va pas dans `prix_unitaire_ttc_cite` si le client ne l'a pas écrit.
2. **Chaque `citation_*` est une sous-chaîne copiée exactement** depuis `texte_commande` (ou `texte_livraison` pour les quantités livrées), à la virgule près. Elle vaut `null` quand la valeur est `null`. Le script de la section 7 le vérifie.
3. **Les quantités sont des chaînes** (`"12"`, `"2.5"`), pour garder les décimales exactes. Les montants sont des entiers.
4. **`quantite_livree`** vaut `null` s'il n'y a pas de bon de livraison.
5. **`id_referentiel`** et **`article_id`** valent `null` si le client ou l'article n'existe pas dans les référentiels (client inconnu, article inconnu).
6. **`mode_paiement`** prend l'une des valeurs `ESPECES`, `CHEQUES`, `MOBILEMONEY`, `CARTEBANCAIRE`, `VIREMENT`, `CREDIT`, `AUTRE`, ou `null`.
7. **`remise_demandee`** vaut `null` ou `{"type": "POURCENTAGE" ou "MONTANT", "valeur": 5, "citation": "..."}`. Une remise demandée n'est **jamais appliquée automatiquement** : elle produit l'anomalie `REMISE_A_VALIDER`.

### `facture_attendue` (seulement pour les messages sans anomalie bloquante)
Elle vaut `null` dès qu'une anomalie bloquante existe. Sinon, elle est calculée sur les **quantités livrées** (ou commandées s'il n'y a pas de bon de livraison) et les **prix du catalogue** :

```json
{
  "lignes": [{"article_id": "A-003", "quantite": "5", "prix_unitaire_ttc": 17500, "montant_ttc": 87500, "groupe": "B"}],
  "totaux_par_groupe": {"B": {"ttc": 87500, "ht": 74153, "tva": 13347}},
  "total_ttc": 87500,
  "aib_taux": 1,
  "aib_montant": 742,
  "net_a_payer": 86758
}
```

Règles de calcul (identiques au moteur) :
- `montant_ttc` d'une ligne = quantité × prix TTC, arrondi au franc le plus proche (0,5 arrondi vers le haut).
- On **additionne les TTC par groupe**. Pour le groupe B : `ht = arrondi(ttc / 1,18)` et `tva = ttc − ht`. Pour les groupes A, C et E : `ht = ttc`, `tva = 0`.
- `aib_montant = arrondi(somme des HT × taux / 100)`. AIB = acompte sur impôt, retenu par certains clients. Si c'est trop incertain, mets `aib_montant` à `null` et écris pourquoi dans `commentaire`.
- `net_a_payer = total_ttc − aib_montant`.
- Utilise `decimal.Decimal` avec `ROUND_HALF_UP` dans le script, **jamais de float**.
- Les deux exemples officiels de la DGI doivent sortir juste : un TTC de 2 320 donne HT 1 966 et TVA 354 ; un TTC de 4 020 donne HT 3 407 et TVA 613.

## 6. Codes d'anomalies (vocabulaire fermé)

| Code | Quand | Bloquante |
|---|---|---|
| `CLIENT_INCONNU` | Aucun client du référentiel ne correspond | oui |
| `CLIENT_AMBIGU` | Plusieurs clients correspondent (alias partagé) | oui |
| `ARTICLE_INCONNU` | Désignation sans article correspondant, ou trop vague | oui |
| `QUANTITE_MANQUANTE` | Quantité absente (« comme d'habitude » sans chiffre, « envoie du riz ») | oui |
| `QUANTITE_INVALIDE` | Zéro, négative, ou plus de 3 décimales, ou décimale sur un article entier | oui |
| `ECART_COMMANDE_LIVRAISON` | Quantité livrée différente de la quantité commandée | oui |
| `PRIX_INHABITUEL` | Prix cité qui s'écarte de plus de 15 % du catalogue | non (à justifier) |
| `TOTAL_INCOHERENT` | Total cité différent du total recalculé | oui |
| `DOUBLON_PROBABLE` | Même client et mêmes lignes qu'un message de moins de 72 h (`doublon_de` renseigné) | oui |
| `REMISE_A_VALIDER` | Le client demande une remise | oui (validation du responsable) |
| `INSTRUCTION_SUSPECTE` | Le texte contient une consigne adressée au système (« ignore les règles », « mets 0 F ») | non, mais signalée |

## 7. Répartition et pièges

### Quotas minimaux sur les 60 messages
Un message peut cumuler plusieurs pièges. Les quotas sont des minimums, à respecter dans dev et dans test au prorata (environ 1/3 et 2/3).

| Situation | Minimum |
|---|---|
| Aucune anomalie (facture attendue complète) | 14 |
| `ECART_COMMANDE_LIVRAISON` | 8 |
| `CLIENT_INCONNU` | 4 |
| `CLIENT_AMBIGU` | 3 |
| `ARTICLE_INCONNU` | 4 |
| `QUANTITE_MANQUANTE` | 4 |
| `QUANTITE_INVALIDE` | 2 |
| `PRIX_INHABITUEL` | 5 |
| `TOTAL_INCOHERENT` | 4 |
| `DOUBLON_PROBABLE` | 3 (le message d'origine doit être dans le même fichier) |
| `REMISE_A_VALIDER` | 3 |
| `INSTRUCTION_SUSPECTE` | 3 |
| Client avec AIB 1 % ou 5 % sans anomalie | 4 |
| Article à quantité décimale (« 2,5 kg ») | 3 |

### Pièges de forme (`pieges`)
À répartir largement :
- `separateur_milliers_point` (« 17.500 » = 17 500 F), `separateur_milliers_espace`, `montant_en_lettres` (« quinze mille »), `montant_abrege` (« 17k », « 17 500f », « 17500 CFA ») ;
- `abreviations_sms` (« bjr », « stp », « cc », « pr », « qté », « dab ») ;
- `comme_d_habitude` ;
- `transcription_vocale` (phrase orale, sans ponctuation, hésitations) ;
- `melange_langues` : français avec quelques mots locaux courants, sans les inventer (« tantie », « dah », « yovo ») ;
- `email_formel` (commande d'une moyenne entreprise, avec numéro de bon de commande) ;
- `tableau_colle` (bon de commande copié avec des colonnes) ;
- `plusieurs_messages` (commande en 2 ou 3 messages qui se corrigent : « non finalement 6 sacs ») : la dernière correction l'emporte ;
- `date_relative` (« livrer demain matin »).

Canaux : environ 60 % `WHATSAPP`, 15 % `SMS`, 15 % `EMAIL`, 10 % `VOCAL_TRANSCRIT`. Longueurs variées, de 1 à 12 lignes.

## 8. Script `verifier_corpus.py`

Python 3.11, bibliothèque standard seulement. À lancer avec `python verifier_corpus.py data/`. Il doit :
1. valider la présence et le type de tous les champs décrits ;
2. vérifier l'unicité des `id`, et que les `id` de clients et d'articles cités existent (ou sont `null`) ;
3. vérifier que **chaque citation est une sous-chaîne exacte** de son texte source ;
4. vérifier que les codes d'anomalies appartiennent à la liste de la section 6 ;
5. vérifier que `facture_attendue` vaut `null` dès qu'une anomalie bloquante est présente ;
6. **recalculer chaque `facture_attendue`** avec les règles de la section 5 et signaler tout écart ;
7. vérifier les quotas de la section 7 ;
8. afficher l'empreinte SHA-256 de `test.jsonl`.

Le script doit finir sans erreur. Colle sa sortie finale dans `corpus/LISEZMOI.md`.

## 9. Ordre de travail recommandé
1. Écris `entreprise.json`, `clients.json`, `articles.json`.
2. Écris le script de vérification.
3. Écris `dev.jsonl` (20 messages), lance le script et corrige.
4. Écris `test.jsonl` (40 messages) **sans réutiliser les formulations de dev**, lance le script et corrige.
5. Écris `LISEZMOI.md` : répartition réelle des pièges et des anomalies, empreinte SHA-256, et la phrase « test.jsonl est gelé depuis le JJ/MM HH:MM ».
6. Envoie le dossier `data/` complet à l'équipe. **Ne modifie plus `test.jsonl` ensuite.**

## 10. Ce qu'il ne faut pas faire
- Pas de vraies personnes, de vrais IFU, de vrais numéros, ni de marques.
- Pas de montants en float.
- Ne remplis pas `attendu` avec des valeurs devinées depuis le catalogue.
- Ne crée pas de nouveaux codes d'anomalie ni de nouveaux noms de champs. S'il en manque un, signale-le dans `LISEZMOI.md`.
