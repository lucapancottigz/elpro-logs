# 03 — Stockage

## Emplacement

Un seul fichier pour tous les systèmes : par défaut `Documents\ELPRO Logs\elpro_logs.db`. **Il peut être dans un dossier synchronisé (OneDrive, kDrive…) et utilisé sur plusieurs PC** (v1.5).

ELPRO Logs n'ouvre jamais ce fichier directement. Au démarrage, il le copie dans `%LOCALAPPDATA%\ELPRO Logs\travail\` et travaille sur cette copie. Après chaque modification (import, récupération, configuration…), il réécrit le fichier d'un seul coup ; le synchroniseur ne voit jamais de fichier incomplet ni de fichier `-wal`/`-shm`. À la fermeture, la copie locale est effacée. Si le fichier ne peut pas être réécrit (dossier absent), la copie locale est gardée et enregistrée au prochain démarrage.

Chaque enregistrement porte un numéro. Si un autre PC a enregistré entre-temps, rien n'est écrasé : l'application recharge la version de l'autre PC, ou, si ce PC a aussi des modifications, demande quoi garder (les deux par défaut : la version de ce PC est enregistrée à côté, sous le nom `elpro_logs (copie <PC> <date>).db`).

Mot de passe des centrales : gardé pour chaque PC séparément (chiffré par Windows) ; à saisir une fois sur chaque PC. L'adresse et l'utilisateur sont communs.

**L'emplacement est réglable** (v1.3) : *Fichier › Emplacement des données › Déplacer vers un autre dossier…* (voir `02_Ecrans.md` § 9). Le chemin choisi est mémorisé (`QSettings`, clé `base/chemin`). Si ce dossier n'est plus accessible au démarrage (clé USB retirée, lecteur réseau absent), l'application le signale et ne crée **jamais** de base vide à sa place. Un dossier réseau fonctionne mais est plus lent (l'application avertit avant d'y déplacer la base) ; un dossier synchronisé n'est plus déconseillé (v1.5).

**Sauvegarde** : *Fichier › Emplacement des données › Faire une copie de sauvegarde…*, application ouverte (copie cohérente par l'API de sauvegarde SQLite, puis vérifiée). Ou copier `elpro_logs.db` application fermée. Pour utiliser la base sur un autre PC : la mettre dans un dossier synchronisé (ou la copier), installer ELPRO Logs sur l'autre PC, puis *Ouvrir une base existante…*.

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
| Colonne sans numéro (entrée d'un seul registre, ex. `ANA`) | Premier registre de l'entrée (v1.4.1) |
| Config au format 1 (ELPRO Config < 1.6.1) avec une entrée en tension AI3/AI4 | Enregistrée telle quelle ; mesures lues avec l'échelle programmée dans la radio (étalonnage, sinon 0-5 V). Après reprogrammation : nouvelle version de config (format 2) à partir de la date de reprogrammation (v1.4.1) |
| Relecture d'un fichier déjà importé (*Relire tous les logs de la centrale*) | Seuls les registres sans aucun point sur la période du fichier sont ajoutés ; le reste, la couverture et la liste des fichiers ne changent pas (v1.4.1) |

## Tables

| Table | Contenu |
|---|---|
| `meta` | `format` = 1 (version du format de base) ; v1.5 : `generation`, `publie_par`, `publie_le`, `ouvert_par`, `ouvert_depuis` (enregistrements du fichier partagé) |
| `systemes` | id, clé (`system_name`), nom, n° de série de la centrale, ordre |
| `configs` | versions du `.elpro.json` (compressé), `valable_depuis` |
| `profils` | liste de log propre à un système (rare) |
| `acces` | connexion à la centrale : adresse, utilisateur, ancien mot de passe commun (v1.4 et avant), dernière récupération |
| `mdp_postes` | mot de passe des centrales par poste (PC\compte), chiffré par Windows (v1.5) |
| `fichiers` | logs importés : nom, empreinte, n° de série, période, lignes |
| `couverture` | plages continues de données |
| `blocs` | points (registre, mois) compressés |

L'interface n'accède **jamais** directement aux tables : uniquement par `L.Magasin`.
