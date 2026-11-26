# Vidéo de démonstration e-FACIL : scénario minuté (2 min 45 s)

Ce scénario sert à tourner la capture vidéo demandée par les TDR (section 6). Il montre le parcours complet du cas 2 : une commande WhatsApp devient une facture vérifiée, validée par un humain, émise de façon simulée, puis payée.

## Préparer le tournage (5 minutes)

1. Lancer l'application : `.venv/bin/python -m uvicorn app.web:app --port 8000`.
2. Se connecter en `admin`, puis **Paramètres** et **Charger la démonstration**. La base contient alors 5 factures sur 5 jours et 5 commandes à vérifier.
3. Écran en 1440 × 900, zoom du navigateur à 100 %, notifications coupées, onglets inutiles fermés.
4. Enregistrer l'écran avec l'outil de votre choix (OBS, enregistreur de Windows ou de GNOME). La voix off peut être enregistrée à part.
5. **Aucune donnée réelle à l'écran** : toutes les données de démonstration sont fictives. Ne pas montrer le fichier `.env`.

## Plan par plan

| Temps | À l'écran | Voix off |
|---|---|---|
| 0:00 – 0:12 | Page de connexion e-FACIL | « Au Bénin, beaucoup de PME reçoivent leurs commandes par WhatsApp et les ressaisissent à la main dans Excel. Résultat : erreurs de quantité, oublis de taxe, factures qui ne correspondent pas à la livraison. » |
| 0:12 – 0:20 | Clic sur le compte **Rodrigue (responsable)**, tableau de bord | « e-FACIL transforme ce message en facture vérifiable. Règle d'or : l'IA lit, le code calcule et contrôle, l'humain décide. » |
| 0:20 – 0:45 | Bouton **WhatsApp** en bas à droite. Choisir le téléphone d'**Aïcha (vendeuse)**. Envoyer : « Bjr c Koffi, envoie 6 cartons de sucre et des sacs de farine. Cash » | « La vendeuse transfère la commande du client sur le numéro de l'entreprise. L'IA en extrait le client, les articles et les quantités. Chaque valeur est rattachée au passage exact du message. » |
| 0:45 – 1:05 | Le bot demande le client : répondre « Gbaguidi ». Il demande la quantité de farine : répondre « 8 » | « Rien n'est inventé : le client est inconnu et la quantité de farine manque. Le bot pose les questions une par une, la vendeuse répond en un mot. » |
| 1:05 – 1:25 | Passer au téléphone de **Rodrigue** : résumé du brouillon et « 1. Valider et émettre ». Répondre « 1 ». Le PDF arrive | « Le responsable est prévenu. Il vérifie le total recalculé par le moteur, conforme aux exemples officiels de la DGI, puis valide. La facture reçoit un numéro unique et devient non modifiable. » |
| 1:25 – 1:40 | Répondre « 2 » (paiement), « 50000 », « 1 » (Mobile money). Puis cliquer « Ouvrir le dossier » dans le téléphone | « Le paiement Mobile money est simulé et un reçu est produit. Tout est aussi visible dans l'application. » |
| 1:40 – 2:00 | Page du dossier : passages surlignés dans le message, champs encadrés, contrôles ; puis la facture et son PDF (mention SIMULATION, code DGI fictif, QR code) | « Sur l'écran de revue, chaque champ montre sa source. Les anomalies bloquent la validation tant qu'un humain ne les a pas tranchées. » |
| 2:00 – 2:15 | Ouvrir un brouillon « Dossou » : contrôle « 12 commandés, 10 livrés », bouton « Facturer le livré » | « On facture ce qui est livré : un écart entre commande et livraison est signalé et bloque la facture. » |
| 2:15 – 2:30 | **Comptabilité** (cartes de trésorerie, rapport Z en ticket, comptes en T équilibrés), puis **Journal d'audit** et « Vérifier l'intégrité » | « Le journal est chaîné par empreintes : toute modification de la base est détectée. Les écritures proposées sont équilibrées. » |
| 2:30 – 2:45 | Tableau de bord : bloc « L'IA lit, le code vérifie, l'humain décide » | « Nous avons mesuré l'apport de l'IA sur 40 messages de test gelés, avec une méthode sans IA comme référence : les résultats sont dans notre fiche IA. Coût du prototype : zéro franc. » |

## Conseils

- Aller lentement sur les écrans de contrôle : le jury doit pouvoir lire les messages d'anomalie.
- Si l'IA en ligne est lente, la lecture bascule automatiquement sur une autre IA, puis sur les règles. On peut le dire à l'écran : c'est une fonction, pas une panne.
- Si un message court (« 1 ») ne déclenche pas la bonne action, c'est qu'une autre question attend une réponse : taper `STOP` puis recommencer.
- Durée cible : entre 2 min 30 et 2 min 50. Couper les temps d'attente au montage.
