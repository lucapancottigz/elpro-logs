# Passation — ELPRO Logs

Document de reprise pour le nouveau programmeur. À lire en entier avant toute modification, puis à garder dans `docs/PASSATION.md`.

---

## 1. En une minute

**ELPRO Logs** est une application Windows de Geoazimut SàRL. Elle affiche l'historique enregistré par les centrales d'alarme **ELPRO 415U-2-C4** :
1. on ajoute un système une fois, avec son `.elpro.json` (produit par l'application sœur **ELPRO Config**) ;
2. on importe ses fichiers `.log`, à la main ou par **récupération automatique** à travers WireGuard ;
3. toutes les valeurs sont stockées dans une base locale compacte ;
4. tous les systèmes se rouvrent automatiquement au démarrage.

Vues : frise d'état global, synthèse par station, détail par station, type de donnée et période, journal d'événements, export CSV.

| Élément | Valeur |
|---|---|
| Dépôt | `lucapancottigz/elpro-logs` (**public**) |
| Dernière version | **1.3.0** (moteur `elpro_logs` v1.3 + `elpro_remote` v1.2) |
| Langage / interface | Python 3.11+ / PySide6 / **pyqtgraph** (pas QtCharts, pour une question de licence) / tzdata |
| Distribution | Installateur Inno Setup (`AppId` propre, différent de celui d'ELPRO Config) dans les Releases GitHub |
| Licence | Propriétaire : « © 2026 Geoazimut SàRL. Tous droits réservés. », geoazimut.com |

---

## 2. Qui fait quoi

| Rôle | Responsabilité |
|---|---|
| **Le propriétaire** (Geoazimut) | Besoins, tests sous Windows et sur les vraies centrales (WireGuard), fusion des PR, releases. Les opérations GitHub (fusion, release) suivent une procédure écrite pas à pas : fournis toujours des commandes PowerShell exactes, une par une, avec le résultat attendu. |
| **Ingénieur** (session Claude séparée) | Écrit et teste le **moteur** (`engine/`), les tests et les spécifications ; livre des **compléments** (zip + `COMPLEMENT_Vx.md`) et les procédures de test du propriétaire. |
| **Programmeur** (toi) | Interface, intégration, `docs/`, empaquetage, **une PR par version** sur une branche `claude/...`. Tu n'as accès qu'à ce dépôt. |

---

## 3. Règles de travail (non négociables)

1. **Ne modifie pas `engine/`, `tools/`, `examples/` ni `tests/`.** Si quelque chose y semble faux, **signale-le** : la correction passe par l'ingénieur.
2. **Aucune règle métier dans l'interface** : pas de conversion de tension, de seuil, d'état ou de durée. Libellés, unités, couleurs d'état et seuils viennent de `elpro_logs`.
3. **Aucune donnée réelle dans le dépôt**, qui est public : pas de `.elpro.json` ou de `.log` de site, pas de base `.db`, pas de nom de site, d'adresse WireGuard ni de n° de série réel. `.gitignore` contient `*.db`, `*.db-wal` et `*.db-shm`.
4. Noms de fichiers de code en anglais ; commentaires, documentation et interface en français.
5. Avant toute livraison : **`Ran 44 tests … OK`** (`tests/`), plus la recette de l'interface (`tests_ui/`) : `Recette interface : OK`. `build.bat` vérifie aussi l'exécutable (`app.py --verifier`).
6. Ne change pas l'`AppId` ni `AppPublisher` de l'installateur. AppUserModelID : `GeoAzimut.ELPROLogs`.

---

## 4. Architecture

```
elpro-logs/
├─ app.py (dont --verifier), version.py, build.bat, requirements.txt
├─ ui/                  ← main_window, system_tab, overview_view, detail_view, journal_view,
│                         files_view, workers (QThread), dialogs, common
├─ engine/
│  ├─ elpro_logs.py     ← lecture des .log, base SQLite, calculs, journal, export CSV, période par défaut
│  ├─ elpro_remote.py   ← récupération HTTP sur la centrale, mot de passe chiffré (DPAPI)
│  └─ elpro_engine.py   ← COPIE du moteur d'ELPRO Config (v1.9) : signification des registres
├─ tools/make_demo_logs.py  ← génère des .log fictifs au format exact de la radio
├─ examples/            ← demo_site_A/B.json (fictifs ; B a un radar en cm) + logs/ (3 jours de B)
├─ tests/               ← test_logs.py (31) + test_remote.py (13, avec une fausse centrale HTTP)
├─ tests_ui/            ← recette automatique de l'interface
├─ installer/           ← elpro_logs.iss + génération de la ressource de version
└─ docs/                ← 00_LISEZMOI, 01_Architecture, 02_Ecrans, 03_Stockage, 04_Recette
```

**Points d'architecture :**
- **Heures :** le moteur travaille **uniquement en secondes UTC**, comme les radios. L'interface affiche et saisit en **heure suisse** avec `L.heure_locale()` et `L.utc_depuis_locale()`. L'axe des dates est calculé en Python : l'axe de pyqtgraph avec décalage horaire faisait planter PySide6 à partir de la 6.10.
- **Threads :** l'import, la récupération et les calculs longs tournent dans un `QThread`, chacun avec **sa propre instance `L.Magasin`** (une connexion SQLite ne se partage pas entre threads).
- **Base :** un seul fichier qui contient tous les systèmes, par défaut `Documents\ELPRO Logs\elpro_logs.db` ; son emplacement se règle dans Fichier › Emplacement des données (clé `QSettings` `base/chemin`, v1.3) et une base introuvable au démarrage n'est jamais recréée vide. Il **n'est pas supprimé** à la désinstallation. Sauvegarde : Fichier › Emplacement des données › Faire une copie de sauvegarde (application ouverte), ou copier le fichier application fermée.
- **Copie du moteur d'ELPRO Config :** si l'ingénieur change le plan de registres dans ELPRO Config, il livrera ici aussi une nouvelle copie d'`elpro_engine.py`.

---

## 5. Le format des logs (constaté sur radio, firmware 2.59)

- **Fichier `.log` :** gzip, puis tar, contenant `data.csv` et `logfile.chk`. `data.csv` commence par `TimeStamp: …`, `Unit Serial Number: …` et une ligne vide, puis l'en-tête `Timestamp,<NOM><nn>,…,` et une ligne par enregistrement. Les **horodatages sont en UTC**.
- **Colonnes :** la colonne `<NOM><nn>` correspond au registre (premier registre de l'entrée NOM) + nn − 1. La correspondance entre noms d'entrée et premiers registres est dans `PROFIL_STANDARD`, alias compris. Un nom inconnu est ignoré avec un avertissement. Une seule colonne MAINV signale une ancienne liste : elle est ignorée avec un avertissement.
- **Liste de log standard à configurer sur chaque centrale :**
  - `L.LISTE_STANDARD`, soit 16 entrées et 310 colonnes, consultable dans Aide › Liste de log ;
  - **Scan Rate 30 s, Records per File 2880.**
- **Durée des fichiers :** la radio coupe en pratique un fichier vers **1 h 10**, à cause d'une limite de taille, avant d'atteindre 2880 lignes. Ce n'est pas gênant.
- **Conservation :** la centrale garde environ **160 fichiers, soit environ 7 jours** (à confirmer sur la durée). D'où le rappel jaune au bout de 5 jours sans nouvelles données.

**Stockage :**
- Seuls les **changements de valeur** sont gardés, plus la valeur de chaque registre au début de chaque plage continue de données.
- Ces points sont regroupés par registre et par mois, en varint différentiel compressé par zlib (table `blocs`).
- Les plages avec données sont dans la table `couverture`. Hors couverture, l'application affiche « pas de données », jamais la dernière valeur.
- Ordre de grandeur : environ 5 Mo par site et par an.
- Les imports en double ou qui se chevauchent sont gérés : empreinte SHA-256 et lignes déjà couvertes ignorées. Les imports dans le désordre donnent le même résultat.

---

## 6. Récupération automatique (v1.1)

- **Réseau :** **un seul tunnel WireGuard**, activé à la main par l'utilisateur, avec **une adresse différente par centrale**. L'adresse est saisie par système dans Système › Connexion à la centrale ; elle n'est jamais écrite dans le code.
- **Pages de la centrale :**
  - authentification HTTP du navigateur, gérée en Basic et en Digest ;
  - `/operator/main.asp` : « Device Name » et « Serial Number » ;
  - `/operator/Datalogs/` : la liste des fichiers terminés, nommés `AAAAMMJJhhmmss-<Device>-DAT.log` (heure UTC de fermeture). Le fichier en cours n'y figure pas.
- **Vérification d'identité :** **avant de télécharger quoi que ce soit**, le moteur compare la centrale connectée au système, par son n° de série s'il est connu, sinon par le nom de la base. Une adresse erronée ne fait donc jamais importer les logs d'un autre site.
- **Mot de passe :** chiffré par Windows (DPAPI, lié au compte Windows), jamais en clair dans la base.
- **API :**

  ```python
  R.recuperer(m, sid, forcer=False, progression, annuler)
  R.recuperer_tout(m, ...)
  R.rappel_necessaire(m, sid)
  ```

  Statuts possibles : `ok`, `rien_de_nouveau`, `injoignable`, `acces_refuse`, `introuvable`, `mauvaise_centrale`, `non_configure`, `annule`, `erreur`.
- **Période par défaut :** `m.periode_par_defaut(sid)` donne la dernière semaine de données, même jour de la semaine et même heure, en heure suisse, changement d'heure compris. S'il y a moins de 7 jours de données, c'est toute la période. Le bouton « 7 jours » donne la même période.

---

## 7. Construire, tester, publier

**Environnement Windows de test :** Python peut ne pas être dans le PATH ; ne suppose pas l’existence de `py` et donne la commande complète de création du venv avec le chemin de `python.exe`. Le message Qt `propagateSizeHints()` pendant la recette est sans gravité.

**Publication par le propriétaire :** il suit une procédure `Test_ELPRO_Logs_x.y.md` fournie par l'ingénieur :
1. `gh pr checkout N`, puis `.\build.bat` ;
2. les tests sous Windows, avec une vraie centrale à travers WireGuard pour tout ce qui touche à la récupération ;
3. `gh pr merge N --merge`, puis `main` et un nouveau `.\build.bat` ;
4. les notes de version tirées du `CHANGELOG.md` ;
5. `gh release create vx.y.z` avec `ELPRO_Logs_Setup.exe`, `ELPRO_Logs_Setup_<v>.exe` et `SHA256SUMS.txt` ;
6. la vérification de l'empreinte.

**À chaque version :** `version.py`, `CHANGELOG.md`, `docs/`, README, et une PR qui dit clairement **ce qui reste à tester sous Windows ou sur une vraie centrale**.

---

## 8. Historique

| Version | Contenu principal |
|---|---|
| 1.0.0 | Systèmes, import des logs, base compacte, vue globale, détail, journal, fichiers, export CSV, installateur |
| 1.0.0 (corrections avant publication) | Bulle de la frise stable ; texte lisible sur fond coloré en thème sombre Windows |
| 1.1.0 | Connexion à la centrale, Récupérer les logs, Tout récupérer, rappel après 5 jours, période par défaut d'une semaine |
| 1.2.0 | Corrections de la relecture : coupure en plein téléchargement, batterie à 0 V, imports groupés (`m.lot()`), seuils de disponibilité dans le moteur ; code mort retiré ; ELPRO Config v1.9 |
| 1.3.0 | « Tout récupérer » dans la barre d'outils principale ; emplacement des données (déplacer, ouvrir une autre base, copie de sauvegarde, défaut) ; base introuvable au démarrage jamais recréée ; import atomique par fichier |
| 1.3.1 | « Tout récupérer » : entrée cliquable de la barre de menus entre Système et Aide, barre d'outils retirée ; avertissement Python `\p` corrigé dans `engine/elpro_logs.py` |

---

## 9. Dette connue et chantiers ouverts

1. **Conservation des logs sur la centrale** : environ 160 fichiers, à confirmer. Selon le résultat, le seuil du rappel (`RETENTION_JOURS` dans `elpro_remote.py`) pourra être ajusté par l'ingénieur.
2. **Anciennes listes de log** : les fichiers produits avant la liste standard s'importent, mais leur colonne MAINV unique est ignorée. Il est possible de les rattacher avec Système › Liste de log (XML).
3. **Liens avec ELPRO Config** : si ELPRO Config génère un jour directement le XML des radios, avec le DataLog activé automatiquement, aucune modification ne sera nécessaire ici tant que la liste standard reste la même.

---

## 10. Pour démarrer

1. Clone le dépôt et lis `docs/00` à `docs/04`, le `CHANGELOG.md` et ce document.
2. Crée le venv et lance les tests : `Ran 44 tests … OK`, puis la recette de l'interface : `Recette interface : OK`.
3. Lance l'application :
   - ajoute `examples/demo_site_B.json` ;
   - importe `examples/logs/*.log` ;
   - le journal doit montrer **12 événements**, dont la perte de communication de B-SM2 le 01.10 de 12:01 à 14:04, heure suisse.
4. Attends le prochain complément de l'ingénieur.
