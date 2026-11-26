# Précieux : interface, parcours de démo et qualité

## Mission
Rendre la démo **impeccable et sans surprise**, sur ordinateur comme sur téléphone. Les critères visés sont la présentation (10 points), la qualité technique (20) et l'utilité (15).

## À lire d'abord
- Le [README](../README.md), en particulier le scénario de démonstration.
- `app/web.py` (routes), `app/templates/` (écrans Jinja2), `app/static/app.css`.
- Le design repose sur Tabler (MIT). Gardez-le **sobre** : une seule couleur d'accent, ni dégradés ni emojis, des libellés métier en français simple.

## Tâches

### 1. Passer la démo au peigne fin (avant 04:00)
- [ ] Jouer le scénario du README en entier avec chaque compte : `aicha`, `rodrigue`, `mireille`, `admin`.
- [ ] Le rejouer **en largeur téléphone** (outils de développement du navigateur, 375 px) : rien ne doit déborder et chaque bouton doit rester utilisable.
- [ ] Tester les 6 exemples de la page « Nouvelle commande », puis des messages de votre cru, comme un client le ferait.
- [ ] Noter chaque défaut dans `equipe/defauts.md` avec une priorité : bloquant pour la démo, gênant, ou cosmétique.

### 2. Corriger (avant 06:00)
Pistes déjà repérées :
- [ ] La barre de navigation passe sur deux lignes sur les petits écrans d'ordinateur : raccourcir les libellés ou ajouter `white-space: nowrap`.
- [ ] Tableau des lignes de l'écran de revue sur téléphone : vérifier la lisibilité ; si besoin, empiler chaque ligne en carte.
- [ ] Remplacer `@app.on_event("startup")` par un gestionnaire `lifespan`, pour supprimer l'avertissement de FastAPI.
- [ ] Vérifier que chaque message d'erreur dit quoi faire.
- [ ] Ajouter une page « Aide », reprise du glossaire (TTC, TVA, AIB, groupe, avoir, pro forma), accessible depuis le menu.

### 3. Avec la clé Gemini (à partir de 05:00)
- [ ] Tester la lecture d'une **photo** de bon de commande manuscrit fictif et d'un **PDF** de bon de commande fictif. Ranger les fichiers de test dans `data/documents_demo/`.
- [ ] Vérifier que les citations apparaissent bien surlignées dans la transcription.

### 4. Préparer la démo du pitch (avant 07:30)
- [ ] Écrire `equipe/demo_pitch.md` : les clics exacts, dans l'ordre, pour 3 minutes de démo en direct, avec un « plan B » si l'IA ou internet tombe (lecture par règles).
- [ ] Préparer les captures d'écran demandées par Merveille pour la vidéo.

## Règles
- `python -m pytest -q` doit rester vert. **Ajoutez un test** dans `tests/test_web.py` pour chaque correction de comportement.
- Ne modifiez pas les règles métier (`app/moteur.py`, `app/brouillon.py`, `app/services.py`) sans prévenir le groupe : un changement de règle se discute.
- Aucune donnée réelle dans les captures.

## Consigne pour ton assistant de développement
> Lis `equipe/precieux.md`, le `README.md`, `app/web.py`, `app/templates/` et `app/static/app.css`. Lance l'application (`python -m uvicorn app.web:app --port 8000`) et joue le scénario de démonstration du README, en largeur ordinateur puis téléphone (375 px). Liste les défauts dans `equipe/defauts.md`, puis corrige-les, en commençant par les plus gênants pour la démo. Garde le style sobre de Tabler, sans dégradés ni emojis. Garde `python -m pytest -q` vert et ajoute un test pour chaque correction de comportement. Ne change aucune règle de calcul ni de contrôle. Travaille sur la branche `precieux/interface` et ouvre une *pull request*.
