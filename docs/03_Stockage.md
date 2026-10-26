# 03 — Stockage

## Emplacement

Un seul fichier pour tous les systèmes : par défaut `Documents\ELPRO Logs\elpro_logs.db` (`L.chemin_base_defaut()`). Pendant l'utilisation, SQLite crée aussi `elpro_logs.db-wal` et `elpro_logs.db-shm` : ne pas les supprimer.

**L'emplacement est réglable** (v1.3) : *Fichier › Emplacement des données › Déplacer vers un autre dossier…* (voir `02_Ecrans.md` § 9). Le chemin choisi est mémorisé (`QSettings`, clé `base/chemin`). Si ce dossier n'est plus accessible au démarrage (clé USB retirée, lecteur réseau absent), l'application le signale et ne crée **jamais** de base vide à sa place. Un dossier réseau ou synchronisé (OneDrive, Dropbox…) est déconseillé : l'application avertit avant d'y déplacer la base ; sur un dossier réseau, le moteur utilise le journal classique de SQLite au lieu de WAL.

**Sauvegarde** : *Fichier › Emplacement des données › Faire une copie de sauvegarde…*, application ouverte (copie cohérente par l'API de sauvegarde SQLite, puis vérifiée). Ou copier `elpro_logs.db` application fermée. Pour passer à un autre PC : installer ELPRO Logs, copier le fichier, puis *Ouvrir une base existante…*.

## Principe

La centrale écrit une ligne toutes les 30 s avec 310 valeurs, mais presque toutes restent identiques d'une ligne à l'autre. La base ne garde donc que :

- la valeur de chaque registre **au début de chaque plage continue** de données ;
- puis **uniquement les changements** de valeur.

Ces points sont regroupés **par registre et par mois**, codés en entiers variables différentiels puis compressés (zlib). Une table « couverture » enregistre les plages où des données existent : hors de ces plages, l'application affiche « pas de données », jamais la dernière valeur connue.

Les fichiers `.log` d'origine ne sont pas conservés : toutes leurs valeurs sont dans la base, colonnes non utilisées comprises.

## Taille

Mesures sur des logs simulés d'un site de 9 radios (RSSI et batterie qui changent à chaque lecture, cas défavorable) :

| Durée | Fichiers .log | Base |
|---|---|---|
| 30 jours | 0,96 Mo | 0,53 Mo |
| 1 an | 11,1 Mo | 5,5 Mo |

Ordre de grandeur : **5 à 6 Mo par site et par an**. Les valeurs réelles varient moins que la simulation ; la base sera en pratique plus petite.

## Règles d'import (déjà dans le moteur)

| Situation | Comportement |
|---|---|
| Même fichier importé deux fois | Refusé (`deja_importe`, empreinte SHA-256 du contenu) |
| Lignes dont l'horodatage est déjà couvert (fichier renommé, rollover forcé) | Lignes ignorées, le reste est importé |
| Fichiers importés dans le désordre | Résultat identique à un import dans l'ordre |
| Écart de plus d'1,5 intervalle entre deux lignes | Trou de données |
| Log d'une autre radio (n° de série différent) | Rien n'est importé sans confirmation |
| Colonne au nom inconnu | Ignorée, avertissement |

## Tables

| Table | Contenu |
|---|---|
| `meta` | `format` = 1 (version du format de base) |
| `systemes` | id, clé (`system_name`), nom, n° de série de la centrale, ordre |
| `configs` | versions du `.elpro.json` (compressé), `valable_depuis` |
| `profils` | liste de log propre à un système (rare) |
| `fichiers` | logs importés : nom, empreinte, n° de série, période, lignes |
| `couverture` | plages continues de données |
| `blocs` | points (registre, mois) compressés |

L'interface n'accède **jamais** directement aux tables : uniquement par `L.Magasin`.
