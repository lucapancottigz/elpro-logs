# 01 — Architecture

## Technologies imposées

| Élément | Choix | Version | Licence |
|---|---|---|---|
| Langage | Python | 3.11 (64 bits) | PSF |
| Interface | PySide6 (Qt) | ≥ 6.6 | LGPL v3 |
| Graphiques | **pyqtgraph** | ≥ 0.13 | MIT |
| Fuseau horaire | **tzdata** (nécessaire à `zoneinfo` sous Windows) | récente | Apache 2.0 |
| Base de données | sqlite3 (bibliothèque standard) | — | domaine public |
| Empaquetage | PyInstaller + Inno Setup, comme ELPRO Config | — | — |
| Système cible | Windows 10 / 11, hors ligne | — | — |

**Ne pas utiliser QtCharts** : il n'est pas sous LGPL (GPL ou licence commerciale). pyqtgraph est rapide sur de longues séries et sous licence MIT.

```
py -3.11 -m venv venv
venv\Scripts\activate
pip install PySide6 pyqtgraph tzdata pyinstaller
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

`THIRD_PARTY_NOTICES.md` : Python, PySide6/Qt, pyqtgraph, tzdata.

## Dépôt

Nouveau dépôt **`lucapancottigz/elpro-logs`**, même organisation que `elpro-config` : branche `main`, une branche `claude/…` et une PR par version, publication par `gh release` (Luca suit une procédure pas à pas). Première version : **1.0.0**.

**Tu n'as pas accès au dépôt `elpro-config`.** Luca a copié ses fichiers (uniquement les fichiers suivis par git, aucune donnée réelle) dans le dossier **`_reference_elpro_config/`** de ce dépôt. Reprends-y, en remplaçant « ELPRO Config » par « ELPRO Logs » et `elpro_config` par `elpro_logs` :

| Fichier de référence | Devient |
|---|---|
| `build.bat` | `build.bat` (tests du moteur, PyInstaller, Inno Setup, copie sans numéro, `SHA256SUMS.txt`) |
| `installer/elpro_config.iss` | `installer/elpro_logs.iss` (**nouvel `AppId`**, `AppPublisher` = `GeoAzimut`) |
| `version.py`, génération de la ressource de version Windows | idem, `APP_VERSION = '1.0.0'` |
| `LICENSE`, `README.md`, `CHANGELOG.md`, `THIRD_PARTY_NOTICES.md`, `.gitignore` | idem, adaptés (+ `*.db`, `*.db-wal`, `*.db-shm` dans `.gitignore`) |
| `resources/app_icon.ico`, `app_icon.png` | copiés tels quels |
| Fenêtre « À propos », mention de copyright dans la barre d'état (`ui/`) | même présentation |

Les noms exacts peuvent différer légèrement : fie-toi au contenu de `_reference_elpro_config/`. **Supprime ce dossier dans ta PR** une fois l'infrastructure reprise. Fichiers publiés : `ELPRO_Logs_Setup.exe`, `ELPRO_Logs_Setup_<version>.exe`, `SHA256SUMS.txt`.

`AppId` de l'installateur : un **nouveau** GUID (ne pas reprendre celui d'ELPRO Config, sinon les deux applications se désinstallent l'une l'autre). AppUserModelID : `GeoAzimut.ELPROLogs`.

## Arborescence finale

```
elpro_logs/
├─ app.py                  ← point d'entrée (à écrire)
├─ version.py
├─ ui/                     ← interface (à écrire)
│  ├─ __init__.py
│  ├─ main_window.py      ← QMainWindow, menus, un onglet par système
│  ├─ system_tab.py       ← barre d'infos + barre de période + 4 sous-onglets
│  ├─ overview_view.py    ← Vue globale : frise des états + tableau de synthèse
│  ├─ detail_view.py      ← Détail : arbre de sélection + graphiques
│  ├─ journal_view.py     ← Journal des événements
│  ├─ files_view.py       ← Fichiers importés, versions de config, liste de log
│  ├─ workers.py          ← QThread : import, calculs longs
│  └─ dialogs.py          ← rapport d'import, aide « liste de log », à propos
├─ engine/                 ← fourni, NE PAS MODIFIER
├─ tools/, examples/, tests/  ← fournis
└─ resources/app_icon.ico, app_icon.png   ← reprendre ceux d'ELPRO Config
```

## Fonctions du moteur à appeler

```python
import elpro_logs as L

m = L.Magasin(L.chemin_base_defaut())        # Documents\ELPRO Logs\elpro_logs.db (créé si absent)

# --- systèmes
m.systemes()                     # [{id, cle, nom, serie, periode:(t0,t1)|None, nb_fichiers}] dans l'ordre
m.ajouter_config(projet)         # dict .elpro.json -> {systeme_id, statut: nouveau|version|identique}
m.ajouter_config(projet, valable_depuis=t)   # mise à jour de config à partir de t (seconde UTC)
m.configs(sid)                   # versions de config
m.renommer(sid, nom); m.supprimer_systeme(sid); m.compacter_base()
m.definir_profil(sid, L.lire_profil_xml(chemin_xml))   # liste de log non standard (rare) ; None = standard
m.profil(sid)

# --- import
m.importer_fichier(sid, chemin, forcer_serie=False, progression=callback(n, total))
    # -> [rapport] ; rapport : fichier, statut, message, avertissements, (t_debut, t_fin)
    # statut : importe | deja_importe | deja_couvert | vide | erreur | serie_differente
with m.lot():                    # imports groupés (v1.2) : chaque bloc réécrit une fois, une seule transaction
    for chemin in chemins: m.importer_fichier(sid, chemin)    # (tout ou rien si le lot échoue)
m.fichiers(sid)

# --- lecture (toutes les heures en secondes UTC)
m.periode(sid)                   # (t0, t1) de toutes les données, ou None
m.catalogue(sid, t)              # stations -> canaux (config en vigueur à t) + 'autres'
m.versions_dans_periode(sid, t0, t1)
m.couverture(sid, t0, t1); m.trous(sid, t0, t1)
m.etat_stations(sid, t0, t1)     # [{station, role, segments:[(a, b, ETAT)]}]
m.etat_systeme(sid, t0, t1, stations=st)    # [(a, b, ETAT)] pire état ; st = etat_stations déjà calculé
L.Magasin.par_cases(segments, t0, t1, n)     # réduction à n cases (affichage longue période)
m.synthese(sid, t0, t1)          # chiffres clés (voir 02_Ecrans.md)
m.courbe(sid, canal, t0, t1, n_max=2000)     # (xs, ys) en escalier ; None = pas de données
m.segments_decodes(sid, canal, t0, t1)       # [(a, b, valeur)] pour les canaux binaires
m.evenements(sid, t0, t1, stations=None, familles=None)
m.exporter_csv(sid, canaux, t0, t1, chemin)

# --- constantes et aides d'affichage
L.ETATS, L.LIBELLES_ETATS, L.COULEURS_ETATS, L.FAMILLES, L.GENRES
L.BATTV_BAS, L.RSSI_FAIBLE, L.DISPO_ROUGE, L.DISPO_ORANGE, L.LISTE_STANDARD, L.REGLAGES_STANDARD
L.heure_locale(t, fmt), L.utc_depuis_locale(a, m, j, h, mi, s), L.duree_texte(s)
```

Un **canal** est un `dict` : `registre`, `nom`, `libelle`, `genre`, `famille`, `station`, `unite`, `binaire` (+ `seuil_haut` pour les radars). L'interface ne le modifie jamais.

## Heures

- Le moteur travaille **uniquement en secondes UTC** (les radios enregistrent en UTC).
- L'interface affiche et saisit **toujours en heure suisse** : `L.heure_locale()` pour afficher, `L.utc_depuis_locale()` pour convertir une saisie. Le changement d'heure été/hiver est géré par le moteur.
- Axe des temps des graphiques : `pyqtgraph.DateAxisItem` avec `utcOffset` réglé sur le décalage suisse, ou étiquettes formatées par `L.heure_locale()`. Vérifier sur une période qui contient le 25.10.2026.

## Threads

- **Import** : dans un `QThread`, avec **sa propre instance** `L.Magasin(chemin)` (une connexion SQLite ne se partage pas entre threads), tous les fichiers dans un seul `with m.lot():` (v1.2). Progression par signal. Annuler = sortir de la boucle (ce qui est importé est gardé). Fermer l'instance à la fin, puis rafraîchir l'onglet.
- **Calculs** `etat_stations`, `synthese`, `evenements` : rapides sur un mois (< 0,5 s) mais quelques secondes sur une année. Les lancer dans un `QThread` (instance `Magasin` dédiée) avec un indicateur « Calcul en cours… » ; garder en cache le dernier résultat par (système, t0, t1).
- Courbes du Détail : `m.courbe()` est rapide (< 0,1 s par canal sur un an) ; appel direct possible.

## Démarrage

1. Ouvrir `L.Magasin(L.chemin_base_defaut())`. Si l'ouverture échoue (base d'une version plus récente, fichier verrouillé) : message clair et fermeture.
2. Créer un onglet par système de `m.systemes()`, dans cet ordre ; sélectionner le dernier onglet actif (`QSettings`).
3. Période initiale de chaque onglet (v1.1) : `m.periode_par_defaut(sid)`, la **dernière semaine de données**, du même jour de la semaine à la même heure (ex. lundi 19.10 09:17 → lundi 12.10 09:17), en heure suisse, changement d'heure compris. Moins d'une semaine de données : toute la période. Aucune donnée : pas de période.
4. Après un import ou une récupération : si la période affichée est la période par défaut (bouton **7 jours**) ou **Tout**, elle est recalculée pour suivre les nouvelles données ; une période choisie à la main reste en place jusqu'à la fermeture.

## Récupération depuis la centrale (v1.1)

Module `engine/elpro_remote.py` (fourni, NE PAS MODIFIER) : connexion HTTP à la centrale à travers le tunnel WireGuard activé à la main, identification (le moteur vérifie toujours le n° de série ou le nom de la centrale), liste et téléchargement des fichiers de log qui ne sont pas encore dans la base, mot de passe chiffré par Windows (DPAPI).

```python
import elpro_remote as R
m.definir_acces(sid, adresse, utilisateur, R.proteger_mdp(mdp)); m.acces(sid)
R.Session(adresse, utilisateur, mdp).identifier()       # {'nom', 'serie'} ; lève R.ErreurCentrale
R.recuperer(m, sid, forcer=False, progression=f(n, total, nom), annuler=f() -> bool)
R.recuperer_tout(m, progression=f(systeme, n, total, nom), annuler=f() -> bool)
R.rappel_necessaire(m, sid)                             # texte si les dernières données ont > 5 jours
```

- Le test de connexion et la récupération tournent dans un `QThread` ; la récupération ouvre **sa propre instance** `L.Magasin`, comme l'import.
- Le mot de passe n'est jamais écrit en clair (ni dans la base, ni dans `QSettings`, ni dans un journal).
- Aucune adresse, aucun nom ni n° de série de vraie centrale dans le dépôt.

## Empaquetage

Comme ELPRO Config (dossier `--onedir`, pas `--onefile`) :

```
pyinstaller --noconfirm --windowed --name "ELPRO Logs" --icon "resources\app_icon.ico" ^
  --add-data "engine;engine" --add-data "resources;resources" --add-data "examples;examples" ^
  --collect-data tzdata app.py
```

`--collect-data tzdata` est obligatoire : sans lui, l'heure suisse n'est pas disponible dans l'exécutable.

## Fichiers de l'utilisateur

| Fichier | Rôle | Écrit par |
|---|---|---|
| `Documents\ELPRO Logs\elpro_logs.db` (+ `-wal`, `-shm` pendant l'utilisation) | Base unique : systèmes, configs, valeurs | le moteur |
| `.elpro.json` | Lu à l'ajout d'un système, puis copié dans la base | ELPRO Config |
| `.log` / `.zip` | Lus à l'import, **non conservés** (toutes les valeurs sont dans la base) | la radio |
| `.csv` | Export des valeurs ou du journal | le moteur / l'interface |
