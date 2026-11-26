# Mesure sur `dev.jsonl` (20 messages)

Empreinte SHA-256 du corpus : `2b648540a351c429a855724eb44d7db6b6b5d559cd8d58839b93b71990961fda`  
Date : 2026-11-26T01:50:49

## Champs extraits

| Configuration | Champs justes | IC 95 % | Valeurs inventées | Vides à tort | Échecs d'appel |
|---|---|---|---|---|---|
| S0 | 190/205 (93%) | 88% à 96% | 2 | 12 | 0 |

## Anomalies détectées (hors doublons)

| Configuration | Détectées | IC 95 % |
|---|---|---|
| S0 | 13/17 (76%) | 53% à 90% |

## Détail par champ

### S0
- anomalie:ARTICLE_INCONNU : detectees 0, total 2
- anomalie:CLIENT_AMBIGU : detectees 1, total 1
- anomalie:CLIENT_INCONNU : detectees 2, total 2
- anomalie:ECART_COMMANDE_LIVRAISON : detectees 2, total 3
- anomalie:INSTRUCTION_SUSPECTE : detectees 1, total 1
- anomalie:PRIX_INHABITUEL : detectees 2, total 2
- anomalie:QUANTITE_INVALIDE : detectees 1, total 1
- anomalie:QUANTITE_MANQUANTE : detectees 2, total 2
- anomalie:REMISE_A_VALIDER : detectees 1, total 1
- anomalie:TOTAL_INCOHERENT : detectees 1, total 2
- client : justes 20, total 20, inventes 0, vides_a_tort 0, attendus_vides 3
- ligne_article : justes 44, total 45, inventes 1, vides_a_tort 0, attendus_vides 0
- mode_paiement : justes 20, total 20, inventes 0, vides_a_tort 0, attendus_vides 1
- prix_cite : justes 37, total 44, inventes 1, vides_a_tort 6, attendus_vides 33
- quantite_commandee : justes 38, total 44, inventes 0, vides_a_tort 5, attendus_vides 2
- quantite_livree : justes 12, total 12, inventes 0, vides_a_tort 0, attendus_vides 0
- sans_anomalie_bloquante : justes 3, total 5
- total_cite : justes 19, total 20, inventes 0, vides_a_tort 1, attendus_vides 17
