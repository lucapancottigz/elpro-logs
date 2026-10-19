# Historique des versions

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/). Numérotation [SemVer](https://semver.org/lang/fr/).

## [1.1.0] — 2026-10-19

### Ajouté
- Récupération automatique des logs depuis la centrale (à travers le tunnel WireGuard) : bouton **Récupérer les logs** (`Ctrl+R`) dans chaque onglet, **Tout récupérer** (`Ctrl+Maj+R`) pour toutes les centrales configurées, progression fichier par fichier et annulation. L'identité de la centrale est toujours vérifiée avant de télécharger.
- **Système › Connexion à la centrale…** : adresse, utilisateur, mot de passe (chiffré par Windows, jamais enregistré en clair), bouton Tester la connexion.
- Ligne « Dernière récupération » sous le bandeau de chaque système, et bandeau de rappel quand les dernières données ont plus de 5 jours (la centrale ne garde qu'environ une semaine de logs).

### Modifié
- Période affichée à l'ouverture : la dernière semaine de données (même jour, même heure ; toute la période s'il y a moins d'une semaine). Le bouton **7 jours** affiche cette période ; elle suit les nouvelles données après un import ou une récupération, sauf si une autre période a été choisie.

## [1.0.0] — 2026-10-15

Première version.

### Ajouté
- Ajout d'un système à partir du `.elpro.json` produit par ELPRO Config ; tous les systèmes ajoutés se rouvrent au démarrage (un onglet par système).
- Import des fichiers `.log` de la centrale ELPRO 415U-2-C4 (et `.zip`, `.csv`) dans une base locale unique (`Documents\ELPRO Logs\elpro_logs.db`) : progression, annulation, rapport d'import, refus des fichiers déjà importés, confirmation pour un log d'une autre radio.
- Barre de période en heure suisse : Tout, 24 h, 7 jours, 30 jours, dates libres, ◀ ▶, retour à la période précédente.
- Vue globale : chiffres clés, frise des états par station et du système, tableau de synthèse par station.
- Détail : sélection par station et par type de donnée, graphiques empilés à axe commun (états binaires, batteries, RSSI, radars), curseur avec valeurs, statistiques.
- Journal des événements avec filtres et export CSV.
- Onglet Fichiers : logs importés, versions de configuration, liste de log.
- Mise à jour de la configuration d'un système (avec date de mise en service), liste de log propre à une centrale (export XML), renommage et suppression d'un système.
- Export CSV des valeurs des canaux cochés.
- Installateur Windows pour tous les utilisateurs ; la base de données est conservée à la désinstallation.

### Corrigé (recette Windows)
- Frise de la Vue globale : la bulle d'information ne clignote plus ; elle n'est mise à jour qu'en passant sur un autre segment et reste affichée tant que la souris est dans le segment survolé.
- Thème sombre de Windows : texte foncé imposé partout où l'application impose un fond coloré (lignes du Journal, cellules mises en évidence du tableau de synthèse, cartes des chiffres clés, logs partiellement importés de l'onglet Fichiers).

[1.1.0]: https://github.com/lucapancottigz/elpro-logs/releases/tag/v1.1.0
[1.0.0]: https://github.com/lucapancottigz/elpro-logs/releases/tag/v1.0.0
