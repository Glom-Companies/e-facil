# Mesure sur `test.jsonl` (40 messages)

Empreinte SHA-256 du corpus : `b5dc13d510e7b7e46c0ffe9405f3d224666e1dc4418966b1b02dc8671b3d6eac`  
Date : 2026-11-26T11:51:40  
Modèle Gemini (S1, S2) : `gemini-3.5-flash-lite`  
Modèle Groq (S4, S5) : `openai/gpt-oss-120b`

## Champs extraits

| Configuration | Champs justes | IC 95 % | Valeurs inventées | Vides à tort | Échecs d'appel |
|---|---|---|---|---|---|
| S0 | 361/393 (92%) | 89% à 94% | 2 | 26 | 0 |
| S1 | 391/393 (99%) | 98% à 100% | 0 | 1 | 0 |
| S2 | 390/393 (99%) | 98% à 100% | 0 | 2 | 0 |
| S4 | 391/393 (99%) | 98% à 100% | 0 | 2 | 0 |
| S5 | 390/393 (99%) | 98% à 100% | 0 | 3 | 0 |

## Anomalies détectées (hors doublons)

| Configuration | Détectées | IC 95 % |
|---|---|---|
| S0 | 24/30 (80%) | 63% à 90% |
| S1 | 29/30 (97%) | 83% à 99% |
| S2 | 29/30 (97%) | 83% à 99% |
| S4 | 30/30 (100%) | 89% à 100% |
| S5 | 30/30 (100%) | 89% à 100% |

## Détail par champ

### S0
- anomalie:ARTICLE_INCONNU : detectees 0, total 3
- anomalie:CLIENT_AMBIGU : detectees 2, total 2
- anomalie:CLIENT_INCONNU : detectees 3, total 3
- anomalie:ECART_COMMANDE_LIVRAISON : detectees 5, total 6
- anomalie:INSTRUCTION_SUSPECTE : detectees 2, total 2
- anomalie:PRIX_INHABITUEL : detectees 3, total 4
- anomalie:QUANTITE_INVALIDE : detectees 2, total 2
- anomalie:QUANTITE_MANQUANTE : detectees 3, total 3
- anomalie:REMISE_A_VALIDER : detectees 2, total 2
- anomalie:TOTAL_INCOHERENT : detectees 2, total 3
- client : justes 40, total 40, inventes 0, vides_a_tort 0, attendus_vides 5
- ligne_article : justes 84, total 84, inventes 0, vides_a_tort 0, attendus_vides 0
- mode_paiement : justes 40, total 40, inventes 0, vides_a_tort 0, attendus_vides 0
- prix_cite : justes 67, total 84, inventes 2, vides_a_tort 15, attendus_vides 63
- quantite_commandee : justes 71, total 84, inventes 0, vides_a_tort 9, attendus_vides 3
- quantite_livree : justes 21, total 21, inventes 0, vides_a_tort 0, attendus_vides 0
- sans_anomalie_bloquante : justes 9, total 11
- total_cite : justes 38, total 40, inventes 0, vides_a_tort 2, attendus_vides 35

### S1
- anomalie:ARTICLE_INCONNU : detectees 3, total 3
- anomalie:CLIENT_AMBIGU : detectees 2, total 2
- anomalie:CLIENT_INCONNU : detectees 3, total 3
- anomalie:ECART_COMMANDE_LIVRAISON : detectees 6, total 6
- anomalie:INSTRUCTION_SUSPECTE : detectees 2, total 2
- anomalie:PRIX_INHABITUEL : detectees 4, total 4
- anomalie:QUANTITE_INVALIDE : detectees 2, total 2
- anomalie:QUANTITE_MANQUANTE : detectees 2, total 3
- anomalie:REMISE_A_VALIDER : detectees 2, total 2
- anomalie:TOTAL_INCOHERENT : detectees 3, total 3
- client : justes 40, total 40, inventes 0, vides_a_tort 0, attendus_vides 5
- ligne_article : justes 83, total 84, inventes 0, vides_a_tort 1, attendus_vides 0
- mode_paiement : justes 40, total 40, inventes 0, vides_a_tort 0, attendus_vides 0
- prix_cite : justes 84, total 84, inventes 0, vides_a_tort 0, attendus_vides 63
- quantite_commandee : justes 84, total 84, inventes 0, vides_a_tort 0, attendus_vides 3
- quantite_livree : justes 20, total 21, inventes 0, vides_a_tort 0, attendus_vides 0
- sans_anomalie_bloquante : justes 11, total 11
- total_cite : justes 40, total 40, inventes 0, vides_a_tort 0, attendus_vides 35

### S2
- anomalie:ARTICLE_INCONNU : detectees 3, total 3
- anomalie:CLIENT_AMBIGU : detectees 2, total 2
- anomalie:CLIENT_INCONNU : detectees 3, total 3
- anomalie:ECART_COMMANDE_LIVRAISON : detectees 6, total 6
- anomalie:INSTRUCTION_SUSPECTE : detectees 2, total 2
- anomalie:PRIX_INHABITUEL : detectees 4, total 4
- anomalie:QUANTITE_INVALIDE : detectees 2, total 2
- anomalie:QUANTITE_MANQUANTE : detectees 2, total 3
- anomalie:REMISE_A_VALIDER : detectees 2, total 2
- anomalie:TOTAL_INCOHERENT : detectees 3, total 3
- client : justes 40, total 40, inventes 0, vides_a_tort 0, attendus_vides 5
- ligne_article : justes 83, total 84, inventes 0, vides_a_tort 1, attendus_vides 0
- mode_paiement : justes 40, total 40, inventes 0, vides_a_tort 0, attendus_vides 0
- prix_cite : justes 83, total 84, inventes 0, vides_a_tort 1, attendus_vides 63
- quantite_commandee : justes 84, total 84, inventes 0, vides_a_tort 0, attendus_vides 3
- quantite_livree : justes 20, total 21, inventes 0, vides_a_tort 0, attendus_vides 0
- sans_anomalie_bloquante : justes 11, total 11
- total_cite : justes 40, total 40, inventes 0, vides_a_tort 0, attendus_vides 35

### S4
- anomalie:ARTICLE_INCONNU : detectees 3, total 3
- anomalie:CLIENT_AMBIGU : detectees 2, total 2
- anomalie:CLIENT_INCONNU : detectees 3, total 3
- anomalie:ECART_COMMANDE_LIVRAISON : detectees 6, total 6
- anomalie:INSTRUCTION_SUSPECTE : detectees 2, total 2
- anomalie:PRIX_INHABITUEL : detectees 4, total 4
- anomalie:QUANTITE_INVALIDE : detectees 2, total 2
- anomalie:QUANTITE_MANQUANTE : detectees 3, total 3
- anomalie:REMISE_A_VALIDER : detectees 2, total 2
- anomalie:TOTAL_INCOHERENT : detectees 3, total 3
- client : justes 39, total 40, inventes 0, vides_a_tort 1, attendus_vides 5
- ligne_article : justes 84, total 84, inventes 0, vides_a_tort 0, attendus_vides 0
- mode_paiement : justes 40, total 40, inventes 0, vides_a_tort 0, attendus_vides 0
- prix_cite : justes 83, total 84, inventes 0, vides_a_tort 1, attendus_vides 63
- quantite_commandee : justes 84, total 84, inventes 0, vides_a_tort 0, attendus_vides 3
- quantite_livree : justes 21, total 21, inventes 0, vides_a_tort 0, attendus_vides 0
- sans_anomalie_bloquante : justes 10, total 11
- total_cite : justes 40, total 40, inventes 0, vides_a_tort 0, attendus_vides 35

### S5
- anomalie:ARTICLE_INCONNU : detectees 3, total 3
- anomalie:CLIENT_AMBIGU : detectees 2, total 2
- anomalie:CLIENT_INCONNU : detectees 3, total 3
- anomalie:ECART_COMMANDE_LIVRAISON : detectees 6, total 6
- anomalie:INSTRUCTION_SUSPECTE : detectees 2, total 2
- anomalie:PRIX_INHABITUEL : detectees 4, total 4
- anomalie:QUANTITE_INVALIDE : detectees 2, total 2
- anomalie:QUANTITE_MANQUANTE : detectees 3, total 3
- anomalie:REMISE_A_VALIDER : detectees 2, total 2
- anomalie:TOTAL_INCOHERENT : detectees 3, total 3
- client : justes 39, total 40, inventes 0, vides_a_tort 1, attendus_vides 5
- ligne_article : justes 84, total 84, inventes 0, vides_a_tort 0, attendus_vides 0
- mode_paiement : justes 40, total 40, inventes 0, vides_a_tort 0, attendus_vides 0
- prix_cite : justes 82, total 84, inventes 0, vides_a_tort 2, attendus_vides 63
- quantite_commandee : justes 84, total 84, inventes 0, vides_a_tort 0, attendus_vides 3
- quantite_livree : justes 21, total 21, inventes 0, vides_a_tort 0, attendus_vides 0
- sans_anomalie_bloquante : justes 10, total 11
- total_cite : justes 40, total 40, inventes 0, vides_a_tort 0, attendus_vides 35
