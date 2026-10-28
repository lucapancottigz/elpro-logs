# Historique des versions

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/). Numérotation [SemVer](https://semver.org/lang/fr/).

## [1.4.0] — 2026-10-27

### Ajouté
- Mesures et consignes analogiques (ELPRO Config 1.5+) : les colonnes `ANA` (mesures, registres 353nn), `ANA_FAIL` (échecs de lecture, 158xx) et `AO` (consignes, 450nn) des logs sont reconnues et affichées dans l'unité de l'entrée (échelle de l'entrée). Nouvelle famille « Mesures et consignes analogiques » dans le Détail, le Journal et la synthèse ; un échec de lecture analogique compte comme « Lecture ou envoi en échec » sur la frise.
- Vue globale : colonne **« Mesures »** (min – max de chaque mesure analogique de la station sur la période), affichée seulement si le système a au moins une mesure analogique.
- Aide › Liste de log : second tableau des entrées à ajouter si le site a des entrées ou sorties analogiques (`ANA`, `ANA_FAIL`, `AO`) ; Copier copie les deux tableaux.

### Corrigé
- Colonnes `BATTTV` (faute de frappe présente dans la liste de log d'une centrale en service) reconnues comme tensions batterie : elles étaient ignorées.

### Interne
- Moteur Logs v1.4 ; copie du moteur d'ELPRO Config v2.3 (noms à 15 caractères, E/S analogiques, étalonnage) ; 47 tests automatiques.

## [1.3.1] — 2026-10-26

### Modifié
- **Tout récupérer** est une entrée cliquable de la barre de menus, entre **Système** et **Aide** : un clic lance directement la récupération. Même raccourci (`Ctrl+Maj+R`), toujours aussi dans le menu Fichier, grisé dans les mêmes cas. La barre d'outils ajoutée en 1.3.0 est retirée.

### Corrigé
- Avertissement Python `invalid escape sequence '\p'` au chargement du moteur (texte d'aide de la détection des dossiers réseau).

## [1.3.0] — 2026-10-22

### Ajouté
- **Fichier › Emplacement des données…** : voir où se trouve la base et sa taille, **Ouvrir le dossier**, **Déplacer vers un autre dossier…** (copie vérifiée, puis proposition de supprimer l'ancien fichier ; jamais d'écrasement d'une base existante ; avertissement pour un dossier réseau ou synchronisé comme OneDrive), **Ouvrir une base existante…**, **Revenir à l'emplacement par défaut**. L'emplacement choisi est mémorisé.
- **Copie de sauvegarde** de la base, application ouverte (même boîte de dialogue).
- Démarrage : si la base de l'emplacement choisi est introuvable (clé USB retirée, lecteur réseau absent…), une fenêtre propose Réessayer, Ouvrir une autre base, Utiliser l'emplacement par défaut ou Quitter. Aucune base vide n'est créée à sa place. Une base endommagée ou d'une version plus récente est signalée de la même façon.

### Modifié
- **Tout récupérer** est maintenant dans la barre d'outils principale, en haut de la fenêtre, avec son icône et son texte, visible sur tous les onglets ; grisé pendant un import ou une récupération.

### Corrigé
- Import atomique par fichier : un fichier dont l'import plante n'est jamais enregistré comme importé, même au milieu d'un import groupé ; les autres fichiers sont gardés.

## [1.2.0] — 2026-10-21

### Corrigé
- Coupure en plein téléchargement (centrale ou tunnel qui coupe) : la récupération s'arrête proprement avec « Centrale injoignable … Arrêt après k fichier(s) importé(s) sur n ; relancez la récupération pour la suite. ». Les fichiers importés avant la coupure sont gardés. **Tout récupérer** continue avec les centrales suivantes au lieu de s'arrêter avec un rapport vide, et la date de récupération est toujours notée.
- Une batterie lue à 0,00 V apparaissait verte sur la frise alors que le journal et la synthèse la signalaient basse : une seule règle partout.

### Amélioré
- Import de plusieurs fichiers (à la main ou depuis la centrale) en un seul lot : chaque bloc de la base n'est réécrit qu'une fois. Une récupération hebdomadaire en fin de mois passe d'environ 56 s à 3 s sur le site de démo. Le lot est tout ou rien : si son écriture échoue, aucun fichier n'est gardé et chaque fichier est signalé en erreur.
- Vue globale : l'état des stations n'est plus calculé deux fois.

### Interne
- Seuils de disponibilité de la communication (95 / 99 %) lus dans le moteur (`L.DISPO_ROUGE`, `L.DISPO_ORANGE`).
- Code mort de l'ancienne période par défaut retiré du moteur.
- Copie du moteur d'ELPRO Config mise à jour en v1.9.
- 40 tests automatiques ; recette de l'interface : import groupé, lot impossible à écrire, récupération coupée en plein fichier.

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
