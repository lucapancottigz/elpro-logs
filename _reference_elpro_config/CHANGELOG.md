# Historique des versions

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/). Numérotation [SemVer](https://semver.org/lang/fr/).

## [1.3.0] — 2026-10-09

### Ajouté
- Radar : échelle facultative (mesure à 4 mA, mesure à 20 mA, unité ; 0–1000 cm par défaut). Les seuils se saisissent dans l'unité et le tableau de bord affiche le radar en cm ; le registre garde la valeur brute 4–20 mA.
- Remarques du moteur après génération : boîte « Configuration générée avec des remarques » (la génération reste valide).

### Modifié
- Tableau de bord de la base : toutes les alarmes et tous les radars, une seule commande de chaque genre (1 feu rouge, 1 orange clignotant, 1 orange fixe, 1 vert, 1 sirène…), tous les BATTV, MAINV, RSSI et comflags. Limite ELPRO de 50 éléments : au-delà, les RSSI sont retirés du tableau de bord (registres 351xx toujours disponibles) et une remarque est affichée.

### Corrigé
- Tableau de bord : les noms de registres et de tags font 16 caractères au plus et sont uniques. Les noms plus longs étaient remplacés sur la radio par `DIn1`, `DOut5`… Libellés de feu raccourcis : `ORANGE_CLI` → `OR_CLI`, `ORANGE_FIXE` → `OR_FIXE`.

## [1.2.0] — 2026-10-09

### Modifié
- Numérotation des commandes : autres signalisations en 431–440 (comme avant la 1.1.0), feu vert déplacé en 441–450. Les sites existants gardent leurs adresses.
- Les registres d'échec (152xx–157xx, 15501) ne figurent plus dans la liste des registres (page 2, PDF, Excel). Ils restent utilisés par les radios.

## [1.1.0] — 2026-10-09

### Ajouté
- Version de configuration incrémentée à chaque génération, version dans le nom de tous les fichiers générés.
- Feu à 4 sorties (rouge, orange clignotant, orange fixe, vert).
- Tous les périphériques sur la base, radar compris.

### Modifié
- Numérotation des commandes — vert 431–440, autres signalisations 441–450.
- Accents retirés des noms de fichiers.

## [1.0.1] — 2026-10-07

### Modifié
- Passage sous licence propriétaire Geoazimut SàRL ; mentions de copyright dans l'application et l'installateur.

### Ajouté
- Mentions de copyright Geoazimut SàRL : fenêtre « À propos », barre d'état, propriétés de l'exécutable, installateur (page « Contrat de licence »), compte rendu PDF et fichier Excel.

## 1.0.0 — 2026-10-06

Première version publique (retirée, remplacée par la 1.0.1).

### Ajouté
- Saisie d'un projet radio ELPRO 415U-2-C4 : système, radios (base, remotes, repeaters), amonts, IP, périphériques.
- Calcul automatique du plan de registres standard GeoAzimut, du polling et du fail-safe.
- Logique IO Plus de la base (comflags) et des remotes équipées d'un radar, livrée désactivée.
- Visualisation de la configuration générée, présentée comme dans CConfig.
- Exports : `.cdb` (CConfig), `.sconf` (IO Plus), compte rendu PDF, liste d'adresses Excel.
- Import d'un `.cdb` existant.
- Deux projets de démonstration fictifs (`demo_site_A`, `demo_site_B`).
- Installateur Windows pour tous les utilisateurs, avec icône sur le bureau et raccourci dans le menu Démarrer (au choix).

[1.3.0]: https://github.com/lucapancottigz/elpro-config/releases/tag/v1.3.0
[1.2.0]: https://github.com/lucapancottigz/elpro-config/releases/tag/v1.2.0
[1.1.0]: https://github.com/lucapancottigz/elpro-config/releases/tag/v1.1.0
[1.0.1]: https://github.com/lucapancottigz/elpro-config/releases/tag/v1.0.1
