# Merveilleux : responsable technique (IA, mesure, robustesse, intégration)

## Mission
Tu es le **référent technique** de l'équipe. Tu rends l'IA réelle fiable et mesurée, tu durcis l'application et tu intègres le travail des autres jusqu'au gel du code de 07:30. Tu portes les critères « automatisation et IA » (15 points), « qualité technique » (20) et « sécurité » (15).

## À lire d'abord (15 min)
- Le [README](../README.md) et le [cahier des charges](../docs/CDC_facturation_BWAI2026.pdf).
- Le code, dans cet ordre :
  - `app/moteur.py` : calculs purs ;
  - `app/texte.py` : lecture des montants et des citations ;
  - `app/extraction.py` : extracteurs et consigne de l'IA ;
  - `app/brouillon.py` : vérification des citations et anomalies ;
  - `app/services.py` : transactions, idempotence, DGI simulée ;
  - `app/db.py` : déclencheurs et journal chaîné ;
  - `app/web.py` : interface.
- `tests/` (36 tests verts) et `eval/mesurer.py` (mesure S0 à S3).
- [`docs/brief_corpus_donnees.md`](../docs/brief_corpus_donnees.md) : le format du corpus, que Livingstone produit de son côté.

## Tâches, par priorité

### 1. Faire marcher l'IA réelle (avant 03:30)
- [ ] Récupérer la clé Gemini auprès de Livingstone, en privé, et la mettre dans `.env`. Vérifier le nom du modèle gratuit dans AI Studio (`GEMINI_MODELE`).
- [ ] Tester `extraire_gemini` sur les 6 exemples de `data/exemples.json`. Le code passe un modèle Pydantic en `response_schema` : vérifie que le SDK `google-genai` installé l'accepte et que la réponse se valide. Sinon, corrige.
- [ ] Tester une **photo** et un **PDF** de bon de commande fictifs. La `transcription` doit être renvoyée et les citations retrouvées dedans.
- [ ] Gérer proprement :
  - les quotas gratuits (erreur 429) : nouvel essai avec attente, puis message clair et repli sur les règles ;
  - les délais dépassés ;
  - une réponse JSON invalide.

### 2. Mesurer (dès que `dev.jsonl` arrive, vers 04:00 ; `test.jsonl` gelé vers 06:00)
```powershell
.\.venv\Scripts\python -m eval.mesurer data\corpus\dev.jsonl --configs S0 S1 S2
.\.venv\Scripts\python -m eval.mesurer data\corpus\test.jsonl --configs S0 S1 S2
```
- [ ] Régler la consigne (`CONSIGNE` dans `app/extraction.py`) et le rapprochement (`app/brouillon.py`, `app/texte.py`) **uniquement sur dev**. Ne jamais regarder les erreurs de test avant la mesure finale.
- [ ] Améliorer la méthode par règles (S0) aussi : la comparaison doit être honnête.
- [ ] Ajouter `S3` (Ollama) si un modèle local tourne.
- [ ] Publier `eval/resultats_test.md` tel quel.

### 3. Fiche IA (avant 08:00) : `docs/fiche_ia.md`
1. Rôle de l'IA : lire et citer, jamais calculer ni valider.
2. Modèles et licences.
3. Données envoyées : uniquement fictives ; réutilisation possible sur le palier gratuit.
4. Garde-fous :
   - citation vérifiée par le code ;
   - valeur incohérente avec sa citation écartée ;
   - consignes contenues dans les messages ignorées et signalées ;
   - contrôles bloquants ;
   - validation humaine.
5. Mesure : protocole, empreinte du corpus, tableaux, intervalles de confiance, lecture honnête.
6. Limites et risques.
7. Coût par facture, aujourd'hui et en production.

### 4. Robustesse et sécurité (en parallèle)
- [ ] Revue de sécurité : droits vérifiés côté serveur sur chaque route, CSRF, téléversements (taille, type), échappement HTML, `SECRET_SESSION` obligatoire hors démo, aucun secret dans les journaux.
- [ ] Ajouter des tests pour tout ce que tu corriges. `python -m pytest -q` reste vert.

### 5. Intégration et gel du code
- [ ] Relire et fusionner les *pull requests* de Précieux (interface) et de Merveille (rapport et vidéo). Relancer les tests après chaque fusion.
- [ ] **07:30 : gel du code.** `git tag v1.0`, `git push --tags`, et transmettre l'empreinte (`git rev-parse HEAD`) à Livingstone.

## Règles
- Les règles de calcul (`app/moteur.py`) sont validées par les exemples officiels de la DGI : ne les change pas sans en parler.
- Aucune donnée réelle ; aucun secret dans Git.

## Consigne pour ton assistant de développement
> Lis `equipe/00_PLAN.md`, `equipe/merveilleux.md`, `README.md`, puis tout `app/`, `tests/` et `eval/`. Objectif 1 : faire fonctionner l'extraction Gemini avec la clé du fichier `.env`, en photo et en PDF compris, et gérer quotas, délais et JSON invalide avec un repli propre sur les règles. Objectif 2 : faire tourner `eval/mesurer.py` sur `data/corpus/dev.jsonl`, et améliorer la consigne et le rapprochement **uniquement sur dev**. Objectif 3 : revue de sécurité de `app/web.py` et `app/services.py`, avec un test pour chaque correction. Ne modifie pas les règles de calcul de `app/moteur.py`. Garde `python -m pytest -q` vert. Travaille sur la branche `merveilleux/ia` et ouvre des *pull requests* courtes.
