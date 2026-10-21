# Application « ELPRO Logs » — dossier de réalisation

ELPRO Logs affiche l'historique des logs enregistrés par les centrales d'alarme ELPRO 415U-2-C4. C'est une **application séparée** d'ELPRO Config, avec son propre dépôt, son propre installateur et ses propres versions.

Elle sert à :

1. ajouter un système en important son `.elpro.json` (produit par ELPRO Config), **une seule fois** ;
2. importer les fichiers `.log` de la centrale ; les valeurs sont stockées dans une base locale et restent disponibles ;
3. rouvrir automatiquement, au démarrage, **tous** les systèmes déjà ajoutés ;
4. montrer l'état global du système sur toute la période des logs ;
5. permettre la lecture en détail : par station, par type de donnée, sur une période choisie.

**Tu n'as pas besoin de connaître les radios ELPRO.** Tout ce qui touche aux logs, aux registres, au stockage et aux calculs est déjà codé et testé dans `engine/`. Ton travail consiste à :

1. construire l'interface Windows ;
2. la brancher sur les fonctions du moteur ;
3. empaqueter et publier comme ELPRO Config.

## Contenu du dossier

| Élément | Rôle | Le modifier ? |
|---|---|---|
| `00_LISEZMOI.md` | Ce fichier | — |
| `01_Architecture.md` | Technologies, arborescence, appels au moteur, threads, empaquetage, dépôt | — |
| `02_Ecrans.md` | Chaque écran, chaque contrôle, chaque bouton | — |
| `03_Stockage.md` | Format de la base, emplacement, taille, sauvegarde | — |
| `04_Recette.md` | Tests automatiques et checklist de validation | — |
| `engine/elpro_logs.py` | Lecture des `.log`, base de données, calculs, journal, export CSV | **NON** |
| `engine/elpro_remote.py` | Récupération des logs depuis la centrale (v1.1) | **NON** |
| `engine/elpro_engine.py` | Copie du moteur d'ELPRO Config v1.9 (signification des registres) | **NON** |
| `tools/make_demo_logs.py` | Génère des `.log` fictifs au format exact des radios | **NON** |
| `examples/demo_site_A.json`, `demo_site_B.json` | Projets fictifs. `demo_site_B` contient un radar avec une échelle en cm | **NON** |
| `examples/logs/*.log` | 3 jours de logs fictifs de `demo_site_B` (comprend une perte de comm, une coupure secteur, une détection, une commande, un passage de seuil radar, une batterie basse) | **NON** |
| `tests/test_logs.py`, `tests/test_remote.py` | Tests automatiques du moteur (27 tests) et de la récupération (13 tests), v1.2 | **NON** |
| `_reference_elpro_config/` | Copie des fichiers d'ELPRO Config (infrastructure à reprendre, voir `01_Architecture.md`) | À supprimer dans la PR |

## Règles de travail

Ce sont les mêmes que pour ELPRO Config.

1. **Ne modifie jamais** `engine/`, `tools/`, `examples/`, `tests/`. Si quelque chose te semble faux, **arrête-toi et signale-le**.
2. L'interface ne contient **aucune règle métier** : aucun calcul de tension, de seuil, d'état ou de durée. Elle appelle le moteur et affiche ce qu'il renvoie. Les libellés, unités, couleurs d'état et seuils viennent tous de `elpro_logs`.
3. Avant chaque livraison : `.\venv\Scripts\python.exe -m unittest discover -s tests -v` doit afficher `OK`.
4. Textes de l'interface en **français**.
5. **Noms de fichiers et de dossiers de code en anglais** (ex. `build.bat`, `ui/main_window.py`) ; **commentaires et docstrings en français** ; documentation en français.
6. **Aucune donnée réelle dans le dépôt** : ni `.elpro.json` de site, ni `.log`, ni base `.db`. Seuls les exemples fictifs de `examples/` y vont. Ajouter `*.db`, `*.db-wal`, `*.db-shm` au `.gitignore`.
7. Copyright : « © 2026 Geoazimut SàRL. Tous droits réservés. », licence propriétaire identique à celle d'ELPRO Config (fichier `LICENSE` à reprendre tel quel en changeant le nom du logiciel).

## Ordre de réalisation

| Étape | Livrable | Contrôle |
|---|---|---|
| 1 | Environnement Python + lancement des tests | 24 tests `OK` |
| 2 | Fenêtre principale, base ouverte au démarrage, ajout d'un système (`.elpro.json`) | Le système reste après redémarrage |
| 3 | Import des logs (thread, progression, rapport) | Les 3 logs de démo s'importent ; un 2ᵉ import dit « déjà importé » |
| 4 | Barre de période | Préréglages et dates libres en heure suisse |
| 5 | Onglet « Vue globale » (frise + tableau de synthèse) | Perte de comm de B-SM2 visible le 01.10 de 12:01 à 14:04 |
| 6 | Onglet « Détail » (arbre de sélection + graphiques) | Batterie de B-SM3 sous 11,5 V le 02.10 |
| 7 | Onglet « Journal » | 12 événements sur les 3 jours de démo |
| 8 | Onglet « Fichiers », mises à jour de config, liste de log XML, export CSV | — |
| 9 | Infrastructure reprise de `_reference_elpro_config/` : `build.bat`, installateur, `version.py`, `CHANGELOG.md`, `LICENSE`, `README.md` ; puis suppression de ce dossier | Installateur fonctionnel |
| 10 | Recette (`04_Recette.md`) | Toutes les cases cochées |
