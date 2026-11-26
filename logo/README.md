# Logo e-FACIL

Une facture avec une coche : la facture vérifiée. Couleurs de l'interface : sarcelle `#1F9184`, nuit `#191C1F`, blanc.

| Fichier | Usage |
|---|---|
| `icone.svg` | Favicon, marque dans la barre latérale, puces |
| `icone-512.png` | Icône haute résolution (diapositives, réseaux) |
| `logo-clair.svg` / `logo-clair.png` | Logo complet sur fond clair |
| `logo-sombre.svg` / `logo-sombre.png` | Logo complet sur fond sombre (barre latérale, page de connexion) |

Les PNG ont un fond transparent (1072 × 256 et 512 × 512).

## Intégration dans l'application
1. Copier `icone.svg` dans `app/static/img/icone.svg`.
2. Favicon, dans `app/templates/base.html` (balise `<head>`) :
   ```html
   <link rel="icon" type="image/svg+xml" href="/static/img/icone.svg">
   ```
3. Barre latérale et page de connexion : garder le texte « e-<span>FACIL</span> » déjà en HTML (police Inter chargée par la page), et placer l'icône devant :
   ```html
   <a class="logo" href="/"><img src="/static/img/icone.svg" alt="" width="34" height="34" style="margin-right:.6rem">e-<span>FACIL</span></a>
   ```

Ne pas utiliser `logo-*.svg` dans une balise `<img>` : une image SVG ne charge pas les polices web, le texte s'afficherait dans une autre police. Pour un logo complet en image, prendre les PNG.
