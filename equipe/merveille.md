# Merveille : rapport et vidéo

## Mission
Produire les deux livrables que le jury lira et regardera : le **rapport de 3 à 5 pages** et la **vidéo de 2 à 3 minutes**. Ils doivent montrer des preuves de fiabilité, pas seulement des fonctionnalités.

## À lire d'abord
- Le [cahier des charges](../docs/CDC_facturation_BWAI2026.pdf), en 5 pages, et le [README](../README.md).
- [`docs/brief_video.md`](../docs/brief_video.md) : la structure imposée de la vidéo.
- Livingstone peut te transmettre le rapport de recherche complet (contexte béninois, réglementation, état de l'art), avec ses sources.

## Tâches

### 1. Rapport (plan à 04:00, premier jet à 06:00, version finale à 08:30) : `docs/rapport.md`, puis PDF
Contenu exigé par le TDR, en 3 à 5 pages :
1. **Besoin** : PME béninoises, commandes par WhatsApp, ressaisie, erreurs, facture normalisée obligatoire, amendes.
2. **Parcours** : commande, brouillon contrôlé, validation, émission simulée, avoir. Mettre le schéma des états.
3. **Architecture** : modules, choix techniques, pourquoi l'IA ne calcule jamais.
4. **Contrôles** : le tableau des anomalies et de leur origine (loi, TDR ou choix de l'équipe).
5. **Tests** : 36 tests automatisés, exemples officiels de la DGI, scénarios de recette (concurrence, reprise, falsification).
6. **Comparaison à la référence** : mesure S0 (sans IA), S1 et S2. Chiffres fournis par Merveilleux vers 06:30.
7. **Limites** : simulation, homologation, AIB à 3 %, acompte et solde, arrondi à confirmer.
8. **Coûts** : nul pour le prototype ; estimation en production.
9. **Étapes d'expérimentation** : pilote avec 3 PME (par exemple via la CCIB), homologation DGI, connexion à l'API e-MCF, langues nationales.

Style : français simple, phrases courtes, pas de superlatifs. Ne jamais écrire « conforme », « certifié » ni « homologué ».

### 2. Vidéo (tournage à 07:30, après le gel du code ; montage terminé à 08:30)
- [ ] Suivre `docs/brief_video.md` : script de 350 mots au maximum, storyboard, liste des captures, sous-titres.
- [ ] Écrire le script et le storyboard **dès maintenant** ; ne filmer qu'après le gel du code.
- [ ] Données de démo réinitialisées (compte `admin`, « Réinitialiser la démonstration ») avant de filmer.
- [ ] Montrer au moins une fois l'écran de téléphone.
- [ ] Musique libre de droits uniquement ; crédits dans `docs/credits_video.md`.

## Ne pas faire
- Aucune donnée réelle à l'écran ; ne jamais montrer la vraie facture que l'équipe a reçue.
- Aucun chiffre de performance inventé : « [À REMPLIR] » tant que la mesure n'est pas faite.
- Ne pas dépasser 5 pages ni 3 minutes.

## Consigne pour ton assistant de développement
> Lis `equipe/merveille.md`, `README.md`, `docs/brief_video.md` et le cahier des charges `docs/CDC_facturation_BWAI2026.pdf`. Rédige `docs/rapport.md` (3 à 5 pages une fois en PDF) avec les 9 sections demandées, en français simple et factuel, sans jamais écrire « conforme », « certifié » ni « homologué », et laisse « [À REMPLIR] » pour les chiffres de mesure. Rédige ensuite, selon `docs/brief_video.md`, `video/script.md`, `video/storyboard.md`, `video/captures_a_faire.md` et `video/sous_titres.srt`. Travaille sur la branche `merveille/rapport` et ouvre une *pull request*.
