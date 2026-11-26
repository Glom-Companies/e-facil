# Livingstone : chef d'équipe, corpus de test, pitch

## Mission
Débloquer l'équipe, fournir le corpus de test à Merveilleux, préparer et porter le pitch de 13:45, et faire la remise finale.

## Tâches

### Tout de suite (avant 02:15)
- [ ] Inviter Merveilleux, Précieux et Merveille sur le dépôt : GitHub, puis *Settings*, *Collaborators*, *Add people*. Donner à Merveilleux le droit de fusionner.
- [ ] Leur envoyer leur fiche et le lien du dépôt.
- [ ] Créer une **clé Gemini gratuite** sur Google AI Studio, sans activer la facturation. La transmettre **en privé** à Merveilleux, et à Précieux pour ses tests, jamais dans Git ni dans le groupe.

### Corpus et référentiels
- [ ] Référentiels complétés (`data/clients.json`, puis `data/articles.json`), au format de [`docs/brief_corpus_donnees.md`](../docs/brief_corpus_donnees.md).
- [ ] `data/corpus/dev.jsonl` (20 messages) livré à Merveilleux vers **04:00**.
- [ ] `data/corpus/test.jsonl` (40 messages) **gelé vers 06:00**, avec son empreinte dans `data/corpus/LISEZMOI.md`, et le script `data/verifier_corpus.py` sans erreur.

### Pitch (13:45)
- [ ] Présentation : problème, solution en une phrase, démo en direct, preuves de fiabilité, mesure de l'IA, limites et suite.
- [ ] Démo de secours : la vidéo et des captures d'écran. Sans clé ni internet, l'application fonctionne avec la lecture par règles.
- [ ] Répéter avec le chronomètre.

### Remise (avant 09:00)
- [ ] Récupérer l'empreinte du commit `v1.0` auprès de Merveilleux.
- [ ] Rendre le dépôt accessible au jury, en le passant public ou en invitant les jurés, selon la consigne.
- [ ] Remettre : lien du dépôt et empreinte, rapport PDF, fiche IA, vidéo.

## Réponses courtes aux questions du jury
- **L'IA se trompe ?** Elle ne fait que proposer, avec la citation de la source. Le code écarte toute valeur absente du message. Les contrôles bloquent. Un responsable valide.
- **Conforme DGI ?** C'est une simulation qui reproduit les règles de calcul et le cycle e-MECeF. Avant un usage réel, le logiciel doit être homologué (article 162 bis du CGI) : c'est notre prochaine étape.
- **Coût ?** Zéro pour le prototype : palier gratuit de Gemini ou modèle local. Le calcul n'utilise pas d'IA.
- **Sans internet ?** Saisie, revue et brouillons fonctionnent ; l'extraction passe par le modèle local ou par les règles. L'émission attend la connexion, comme l'exige la DGI.
- **Données ?** Uniquement fictives pour le prototype. Le modèle local permet de garder les données réelles dans l'entreprise.
