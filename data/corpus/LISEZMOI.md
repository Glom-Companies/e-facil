# Jeu de données de démonstration et corpus d'évaluation (`data/corpus/`)

Ce dossier contient le corpus fictif de 60 messages commerciaux (`dev.jsonl` et `test.jsonl`) ainsi que la documentation de contrôle destinée à la démonstration et à l'évaluation quantitative du prototype (comparaison **S0 Règles simples** / **S1 IA seule** / **S2 IA avec contrôles**).

## 1. Gel du corpus de test et empreinte SHA-256

> **test.jsonl est gelé depuis le 26/11 01:35**

- **Fichier gelé** : `data/corpus/test.jsonl` (40 messages, `T-001` à `T-040`, encodage UTF-8 sans BOM, fins de ligne LF)
- **Empreinte SHA-256 (`test.jsonl`)** : `b5dc13d510e7b7e46c0ffe9405f3d224666e1dc4418966b1b02dc8671b3d6eac`
- **Fichier de mise au point** : `data/corpus/dev.jsonl` (20 messages, `D-001` à `D-020`) — aucune formulation de `dev.jsonl` n'est réutilisée dans `test.jsonl`.

---

## 2. Synthèse des référentiels (`data/`)

- **`entreprise.json`** : `SÈNA DISTRIBUTION SARL` (IFU fictif `9900000000001`, régime `REEL`, NIM simulé `SIMU000001`, 4 utilisateurs : Aïcha vendeur, Rodrigue responsable, Mireille comptable, Admin).
- **`clients.json`** (15 clients fictifs, `C-001` à `C-015`, tous les IFU commencent par `99` sur 13 chiffres) :
  - 6 `ENTREPRISE_REEL` (dont 4 à AIB 1 % : `C-001`, `C-002`, `C-007`, `C-009` ; et 2 à AIB 5 % : `C-005`, `C-010`) ;
  - 4 `ENTREPRISE_TPS` (`C-003`, `C-004`, `C-011`, `C-012`, AIB 0 %), dont deux clientes partageant l'alias `"Mama Adjovi"` (`C-003` à Godomey et `C-004` à Fidjrossè) ;
  - 3 `PARTICULIER` (`C-008`, `C-013`, `C-014`, `ifu: null`, AIB 0 %) ;
  - 1 `STRUCTURE_ETAT` (`C-006`, Cantine scolaire publique de Bohicon, AIB 0 %) ;
  - 1 `CLIENT_EXPORT` (`C-015`, Société Lomé Négoce Distribution, Togo, AIB 0 %).
- **`articles.json`** (25 articles génériques sans marque, `A-001` à `A-025`, prix unitaires TTC entiers en XOF) :
  - 23 articles en **groupe `B`** (TVA 18 %), dont 1 prestation de service (`A-014` `"Livraison Cotonou"`, unité `forfait`, 5 000 F TTC) ;
  - 2 produits de base en **groupe `A`** (exonéré, marqués `"a_verifier": true`) : `A-007` (`"Farine de blé sac de 50 kg"`) et `A-008` (`"Maïs grain (au kilo)"`) ;
  - 3 articles à **quantité décimale** (`"quantite_decimale": true`, au plus 3 décimales) : `A-008` (`"Maïs grain (au kilo)"`), `A-012` (`"Gari (au kilo)"`) et `A-013` (`"Huile de palme (au litre)"`).

---

## 3. Répartition réelle des situations et anomalies

Chaque message peut cumuler plusieurs situations ou anomalies. Tous les quotas minimaux sont respectés au global et au prorata (1/3 dans `dev.jsonl`, 2/3 dans `test.jsonl`).

| Situation / Code d'anomalie | Bloquante | Quota min | `dev.jsonl` (20) | `test.jsonl` (40) | Total (60) |
|---|---|---:|---:|---:|---:|
| Aucune anomalie (`facture_attendue` complète) | — | 14 | 5 | 11 | **16** |
| `ECART_COMMANDE_LIVRAISON` | oui | 8 | 3 | 6 | **9** |
| `CLIENT_INCONNU` | oui | 4 | 2 | 3 | **5** |
| `CLIENT_AMBIGU` | oui | 3 | 1 | 2 | **3** |
| `ARTICLE_INCONNU` | oui | 4 | 2 | 3 | **5** |
| `QUANTITE_MANQUANTE` | oui | 4 | 2 | 3 | **5** |
| `QUANTITE_INVALIDE` | oui | 2 | 1 | 2 | **3** |
| `PRIX_INHABITUEL` (> 15 % d'écart catalogue) | non | 5 | 2 | 4 | **6** |
| `TOTAL_INCOHERENT` | oui | 4 | 2 | 3 | **5** |
| `DOUBLON_PROBABLE` (< 72 h dans le même split) | oui | 3 | 1 | 2 | **3** |
| `REMISE_A_VALIDER` | oui | 3 | 1 | 2 | **3** |
| `INSTRUCTION_SUSPECTE` | non | 3 | 1 | 2 | **3** |
| Client avec AIB 1 % ou 5 % sans anomalie | — | 4 | 3 | 6 | **9** |
| Article à quantité décimale (« 2,5 kg ») | — | 3 | 2 | 4 | **6** |

> Note : 21 messages au total ne comportent aucune anomalie bloquante (les 16 messages sans aucune anomalie + 2 messages avec `PRIX_INHABITUEL` seul + 3 messages avec `INSTRUCTION_SUSPECTE` seule) et disposent tous d'une `facture_attendue` recalculée au franc près selon les règles e-MECeF.

---

## 4. Répartition réelle des canaux et des pièges de forme

### Canaux de réception

| Canal | `dev.jsonl` (20) | `test.jsonl` (40) | Total (60) | Proportion |
|---|---:|---:|---:|---:|
| `WHATSAPP` | 12 | 24 | **36** | 60,0 % |
| `SMS` | 3 | 6 | **9** | 15,0 % |
| `EMAIL` | 3 | 6 | **9** | 15,0 % |
| `VOCAL_TRANSCRIT` | 2 | 4 | **6** | 10,0 % |

### Pièges de forme (`pieges`)

| Piège | `dev.jsonl` | `test.jsonl` | Total |
|---|---:|---:|---:|
| `abreviations_sms` | 11 | 17 | **28** |
| `date_relative` | 7 | 9 | **16** |
| `melange_langues` | 4 | 8 | **12** |
| `montant_abrege` | 4 | 7 | **11** |
| `email_formel` | 3 | 6 | **9** |
| `separateur_milliers_espace` | 2 | 7 | **9** |
| `separateur_milliers_point` | 4 | 4 | **8** |
| `comme_d_habitude` | 2 | 4 | **6** |
| `transcription_vocale` | 2 | 4 | **6** |
| `plusieurs_messages` | 2 | 3 | **5** |
| `tableau_colle` | 1 | 4 | **5** |
| `montant_en_lettres` | 1 | 3 | **4** |

---

## 5. Remarques sur le schéma (section 10 du brief)

Conformément à la consigne *« Ne crée pas de nouveaux codes d'anomalie ni de nouveaux noms de champs. S'il en manque un, signale-le dans `LISEZMOI.md` »*, aucun champ ni code supplémentaire n'a été introduit. Pour information :
- Le schéma de `attendu` (section 5) prévoit `total_ttc_cite` (entier ou `null`) et `quantite_livree` (chaîne ou `null`) sans champs `citation_total` ni `citation_quantite_livree` dédiés dans le corpus, tandis que l'extracteur du prototype (`app/extraction.py`) retourne un couple `{valeur, citation}` pour `total_cite` et pour les quantités du bon de livraison.
- De même, les textes d'injection (`INSTRUCTION_SUSPECTE`) sont signalés via `anomalies_attendues` dans le corpus, sans champ `instructions_suspectes` additionnel dans `attendu`.

---

## 6. Sortie finale de `python verifier_corpus.py data/`

```text
=== VÉRIFICATION DU CORPUS ET DES RÉFÉRENTIELS : SUCCÈS ===
Entreprise : SÈNA DISTRIBUTION SARL (IFU 9900000000001, régime REEL)
Clients    : 15 ({'ENTREPRISE_REEL': 6, 'ENTREPRISE_TPS': 4, 'STRUCTURE_ETAT': 1, 'PARTICULIER': 3, 'CLIENT_EXPORT': 1})
Articles   : 25 (groupe B : 23, groupe A à vérifier : 2, décimaux : 3)
Messages   : 60 (dev : 20, test : 40)
Factures recalculées au franc près : 21 (exemples DGI 2 320 F -> 1 966 + 354 ; 4 020 F -> 3 407 + 613 : OK)

--- Répartition des situations et anomalies (Quotas section 7) ---
Situation                                    | Min | Dev | Test | Total
----------------------------------------------------------------------
Aucune anomalie (facture attendue complète)  |  14 |   5 |   11 |    16
ECART_COMMANDE_LIVRAISON                     |   8 |   3 |    6 |     9
CLIENT_INCONNU                               |   4 |   2 |    3 |     5
CLIENT_AMBIGU                                |   3 |   1 |    2 |     3
ARTICLE_INCONNU                              |   4 |   2 |    3 |     5
QUANTITE_MANQUANTE                           |   4 |   2 |    3 |     5
QUANTITE_INVALIDE                            |   2 |   1 |    2 |     3
PRIX_INHABITUEL                              |   5 |   2 |    4 |     6
TOTAL_INCOHERENT                             |   4 |   2 |    3 |     5
DOUBLON_PROBABLE                             |   3 |   1 |    2 |     3
REMISE_A_VALIDER                             |   3 |   1 |    2 |     3
INSTRUCTION_SUSPECTE                         |   3 |   1 |    2 |     3
Client avec AIB 1 % ou 5 % sans anomalie     |   4 |   3 |    6 |     9
Article à quantité décimale (« 2,5 kg »)     |   3 |   2 |    4 |     6

--- Répartition des canaux ---
  WHATSAPP         : dev=12, test=24, total=36 (60.0 %)
  SMS              : dev= 3, test= 6, total= 9 (15.0 %)
  EMAIL            : dev= 3, test= 6, total= 9 (15.0 %)
  VOCAL_TRANSCRIT  : dev= 2, test= 4, total= 6 (10.0 %)

--- Répartition des pièges de forme ---
  abreviations_sms             : dev=11, test=17, total=28
  comme_d_habitude             : dev= 2, test= 4, total= 6
  date_relative                : dev= 7, test= 9, total=16
  email_formel                 : dev= 3, test= 6, total= 9
  melange_langues              : dev= 4, test= 8, total=12
  montant_abrege               : dev= 4, test= 7, total=11
  montant_en_lettres           : dev= 1, test= 3, total= 4
  plusieurs_messages           : dev= 2, test= 3, total= 5
  separateur_milliers_espace   : dev= 2, test= 7, total= 9
  separateur_milliers_point    : dev= 4, test= 4, total= 8
  tableau_colle                : dev= 1, test= 4, total= 5
  transcription_vocale         : dev= 2, test= 4, total= 6

SHA-256 test.jsonl : b5dc13d510e7b7e46c0ffe9405f3d224666e1dc4418966b1b02dc8671b3d6eac
```
