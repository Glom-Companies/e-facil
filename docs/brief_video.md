# Brief : vidéo de démonstration (2 à 3 minutes)

> À donner tel quel à votre assistant de développement. Il doit produire **le script, le storyboard et la liste des captures**, que l'équipe tourne ensuite. L'application n'est pas encore finie : les chiffres et certains écrans sont des **emplacements `[À REMPLIR]`** que l'équipe complétera.

## 1. Ce que la vidéo doit prouver au jury

- Hackathon BWAI'2026, cas 2 « automatisation de la facturation » pour les PME béninoises.
- Grille du jury sur 100 : utilité 15, **fiabilité métier 25**, automatisation et IA 15, sécurité 15, qualité technique 20, présentation 10.
- Le TDR précise qu'une interface plus élaborée ou un modèle payant ne donnent **aucun avantage automatique**. La vidéo doit donc **montrer des preuves** de fiabilité, pas seulement une jolie interface.

Les preuves à montrer, dans cet ordre de priorité :
1. Un message de commande (WhatsApp) devient un **brouillon** où chaque champ montre **d'où il vient** et **à quel point il est sûr**. Ce qui manque reste vide.
2. Les **anomalies bloquent la validation** : quantité livrée différente de la commande, client inconnu, prix inhabituel.
3. **Un humain valide.** Le numéro de facture n'apparaît qu'à ce moment-là, sans trou dans la numérotation.
4. **Une facture validée ne se modifie plus.** Une correction passe par un **avoir** lié à la facture.
5. Un **double clic** ou deux validations simultanées ne créent **qu'une seule facture**. Après une **coupure** (application fermée en plein travail), on reprend sans doublon.
6. Le **journal** retrace tout et sa vérification d'intégrité passe.
7. **La mesure de l'IA** : tableau comparant règles simples, IA seule et IA avec contrôles sur 40 messages de test.
8. Les **limites honnêtes** : simulation, pas d'homologation DGI à ce stade.

## 2. Personnages et données (fictifs, identiques au jeu de données)

- Entreprise : **SÈNA DISTRIBUTION SARL**, grossiste alimentaire et boissons à Akpakpa, Cotonou.
- Utilisateurs :
  - **Aïcha**, vendeuse : reçoit les commandes ;
  - **Rodrigue**, responsable : valide ;
  - **Mireille**, comptable : reçoit les écritures.
- Client de la démo : **Ets Dossou et Frères**, au marché Dantokpa. Il commande 12 cartons de savon et 5 sacs de riz, mais seulement 10 cartons sont livrés.
- **Aucune donnée réelle à l'écran.** Pas de vraie facture, pas de vrai IFU, pas de vrai numéro de téléphone. La mention « SIMULATION » doit rester visible sur les factures montrées.
- **Pas de logo de la DGI** ni d'imitation d'un document officiel authentique.

## 3. Structure imposée (environ 2 min 45)

| Temps | Séquence | Contenu | Image |
|---|---|---|---|
| 0:00–0:15 | Le problème | Une PME reçoit ses commandes par WhatsApp, ressaisit tout dans Excel, se trompe de quantité ou de prix. Au Bénin, une facture normalisée minorée expose à de lourdes amendes. | Motion design (option) ou plans de téléphone et de cahier |
| 0:15–0:30 | La solution en une phrase | « Du message de commande à une facture vérifiable : l'IA lit, le code calcule, l'humain décide. » Schéma en 4 étapes : source → brouillon contrôlé → validation → émission simulée. | Schéma animé |
| 0:30–1:30 | Démo du parcours | Aïcha colle le message → écran de revue (passages surlignés, indicateurs de confiance, champ manquant vide) → anomalie « commandé 12, livré 10 » → elle choisit « facturer le livré » → Rodrigue valide → numéro attribué → PDF de la facture → émission simulée. | Capture d'écran réelle |
| 1:30–2:05 | Fiabilité | Double clic sur « Valider » : une seule facture. Tentative de modifier une facture validée : refus. Création d'un avoir. Application coupée puis relancée : reprise sans doublon. Journal et vérification d'intégrité « OK ». | Capture réelle, avec incrustations courtes |
| 2:05–2:30 | Mesure de l'IA | Tableau : champs justes, valeurs inventées, anomalies détectées, pour les règles simples, l'IA seule et l'IA avec contrôles. Chiffres `[À REMPLIR]`. | Graphique simple |
| 2:30–2:45 | Limites et suite | Simulation, homologation DGI nécessaire avant tout usage réel, prochaines étapes (PDF et photos, lien avec le recouvrement). Nom de l'équipe et lien du dépôt. | Plan fixe |

## 4. Livrables attendus de toi

1. **`video/script.md`** : la voix off complète, séquence par séquence, avec le minutage.
   - **350 mots au maximum**, en français simple et direct, phrases courtes, sans jargon non expliqué.
   - Quand un sigle apparaît (TVA, TTC, AIB), une demi-phrase l'explique, ou on l'évite.
   - Ton calme et professionnel : pas de superlatifs, pas de « révolutionnaire », pas de « grâce à l'IA ».
2. **`video/storyboard.md`** : un tableau plan par plan (numéro, durée, ce qu'on voit, ce qu'on entend, texte incrusté éventuel, transition).
3. **`video/captures_a_faire.md`** : la liste exacte des captures d'écran et vidéo à enregistrer dans l'application. Pour chaque capture : l'écran, l'état des données nécessaire avant de filmer (« base réinitialisée, message T-007 collé »…), l'action filmée et sa durée. C'est cette liste qui permet de préparer les données de démo.
4. **`video/sous_titres.srt`** : les sous-titres en français, calés sur le script.
5. **`video/motion_design.md`** (option, seulement pour 0:00–0:30) : description des animations (formes, textes, durées) réalisables en moins de 2 heures avec un outil gratuit.

## 5. Contraintes techniques

- Format final : MP4, 1920 × 1080, 30 images par seconde, durée entre 2 min 00 et 3 min 00.
- Capture d'écran : OBS Studio ou équivalent gratuit, navigateur en plein écran, zoom 125 % pour la lisibilité. Masquer les favoris et les onglets personnels.
- Montrer au moins une fois **l'affichage sur téléphone** (l'interface est responsive).
- Musique : seulement libre de droits. Note le titre, l'auteur et la licence dans `video/credits.md`, car le TDR exige de déclarer les composants et licences.
- Voix off enregistrée au calme. Sous-titres incrustés ou fournis à côté.
- Typographie et couleurs des incrustations identiques à celles de l'interface. Pas d'effets tape-à-l'œil.

## 6. Ce qu'il ne faut pas faire

- Ne pas affirmer que la solution est « conforme », « certifiée » ou « homologuée DGI ». Dire « simulation » et « prépare l'homologation ».
- Ne pas inventer de chiffres de performance. Laisser `[À REMPLIR]` jusqu'à la mesure réelle.
- Ne pas montrer de vraies données personnelles.
- Ne pas dépasser 3 minutes.
