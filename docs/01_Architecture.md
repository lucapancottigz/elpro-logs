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

e = L.Espace(chemin)                          # v1.5 : fichier partagé (choisi) + copie de travail locale
info = e.ouvrir(creer=False)                  # {'cree', 'repris', 'ouvert_ailleurs': None | {poste, depuis}}
e.annoncer()                                  # publie « ouvert sur ce PC »
m = L.Magasin(e.travail, creer=False)         # TOUTES les connexions SQLite sur e.travail, jamais sur le partagé

# --- systèmes
m.systemes()                     # [{id, cle, nom, serie, periode:(t0,t1)|None, nb_fichiers}] dans l'ordre
m.ajouter_config(projet)         # dict .elpro.json -> {systeme_id, statut: nouveau|version|identique}
    # v1.4.1 : un fichier au format 1 (ELPRO Config < 1.6.1) est gardé tel quel ; L.echelles_format_1(projet)
    # donne l'échelle réellement programmée de ses entrées en tension AI3/AI4 (utilisée par catalogue)
m.ajouter_config(projet, valable_depuis=t)   # mise à jour de config à partir de t (seconde UTC)
m.configs(sid)                   # versions de config
m.renommer(sid, nom); m.supprimer_systeme(sid); m.compacter_base()
m.definir_profil(sid, L.lire_profil_xml(chemin_xml))   # liste de log non standard (rare) ; None = standard
m.profil(sid)

# --- import
m.importer_fichier(sid, chemin, forcer_serie=False, progression=callback(n, total), completer=False)
    # -> [rapport] ; rapport : fichier, statut, message, avertissements, (t_debut, t_fin)
    # statut : importe | deja_importe | deja_couvert | vide | erreur | serie_differente
    # completer=True (v1.4.1) : un fichier déjà importé ajoute seulement les registres sans aucun point sur sa
    # période (statut complete, « N colonne(s) ajoutée(s) : … ») ; rien à ajouter : deja_importe
with m.lot():                    # imports groupés (v1.2) : chaque bloc réécrit une fois, une seule transaction
    for chemin in chemins: m.importer_fichier(sid, chemin)    # chaque fichier en tout ou rien (v1.3)

# --- fichier partagé et copie de travail (v1.5)
e.partage / e.travail                # fichier choisi (affiché) / copie locale (%LOCALAPPDATA%\ELPRO Logs\travail)
e.publier()                          # après CHAQUE modification ; lève L.ConflitPublication, L.PublicationImpossible
e.verifier()                         # 'a_jour' | 'modifie' (un autre PC a publié) | 'absent'
e.recharger()                        # reprend le fichier partagé (Magasin fermés, rien en attente)
e.resoudre(choix)                    # après un conflit : 'les_deux' | 'mienne' | 'autre'
e.fermer(); e.liberer_local()        # fermeture (publie, efface la copie) ; ouverture abandonnée
e.copies_en_conflit(); e.en_attente; e.derniere_publication
L.poste_courant(); L.nom_poste(poste)          # « PC\compte » ; nom du PC seul

# --- emplacement de la base (v1.3)
L.Magasin(chemin, creer=False)       # FileNotFoundError si la base n'existe pas
L.verifier_base(chemin)              # {'ok', 'message', 'nb_systemes', 'format'}
L.verifier_partage(chemin)           # idem sur une copie locale : pour tout fichier choisi par l'utilisateur (v1.5)
L.copier_base(source, destination)   # copie cohérente + vérification ; refuse d'écraser
L.avertissement_emplacement(chemin)  # texte si dossier réseau (plus lent), sinon None ; synchronisé : rien (v1.5)
L.NOM_BASE                           # 'elpro_logs.db'
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
L.BATTV_BAS, L.RSSI_FAIBLE, L.DISPO_ROUGE, L.DISPO_ORANGE, L.LISTE_STANDARD, L.LISTE_ANALOGIQUE (v1.4), L.REGLAGES_STANDARD
L.heure_locale(t, fmt), L.utc_depuis_locale(a, m, j, h, mi, s), L.duree_texte(s)
```

Un **canal** est un `dict` : `registre`, `nom`, `libelle`, `genre`, `famille`, `station`, `unite`, `binaire` (+ `seuil_haut` pour les radars). L'interface ne le modifie jamais.

## Heures

- Le moteur travaille **uniquement en secondes UTC** (les radios enregistrent en UTC).
- L'interface affiche et saisit **toujours en heure suisse** : `L.heure_locale()` pour afficher, `L.utc_depuis_locale()` pour convertir une saisie. Le changement d'heure été/hiver est géré par le moteur.
- Axe des temps des graphiques : `pyqtgraph.DateAxisItem` avec `utcOffset` réglé sur le décalage suisse, ou étiquettes formatées par `L.heure_locale()`. Vérifier sur une période qui contient le 25.10.2026.

## Threads

- Tous les `QThread` (import, récupération, calculs, export) ouvrent leur instance avec **`m.chemin`** de la base en cours (`MainWindow.chemin_base`, la copie de travail), avec `creer=False`, jamais avec `chemin_base_defaut()` (v1.3) ni avec le fichier partagé (`MainWindow.chemin_partage`, v1.5).
- **Import** : dans un `QThread`, avec **sa propre instance** `L.Magasin(chemin)` (une connexion SQLite ne se partage pas entre threads), tous les fichiers dans un seul `with m.lot():` (v1.2). Progression par signal. Annuler = sortir de la boucle (ce qui est importé est gardé). Fermer l'instance à la fin, puis rafraîchir l'onglet.
- **Calculs** `etat_stations`, `synthese`, `evenements` : rapides sur un mois (< 0,5 s) mais quelques secondes sur une année. Les lancer dans un `QThread` (instance `Magasin` dédiée) avec un indicateur « Calcul en cours… » ; garder en cache le dernier résultat par (système, t0, t1).
- Courbes du Détail : `m.courbe()` est rapide (< 0,1 s par canal sur un an) ; appel direct possible.

## Démarrage

1. Ouvrir la base (`ouvrir_base_demarrage()` dans `ui/main_window.py`, v1.3 ; renvoie `(espace, magasin)` depuis la v1.5) : `L.Espace(chemin)` puis `e.ouvrir(creer=…)`, chemin = clé `QSettings` `base/chemin`, sinon `L.chemin_base_defaut()` (seul emplacement créé au besoin). Session précédente non publiée : reprise (« Modifications de la dernière session enregistrées dans le fichier partagé. »), fenêtre de conflit si un autre PC a publié depuis, « Réessayer / Quitter » si le fichier partagé reste inaccessible. Base ouverte sur un autre PC : avertissement « Continuer / Quitter ». Puis `e.annoncer()` et `L.Magasin(e.travail, creer=False)`. **Une base introuvable n'est jamais recréée vide** : fenêtre « La base de données est introuvable… » avec **Réessayer**, **Ouvrir une autre base…**, **Utiliser l'emplacement par défaut** (confirmation : « Vos systèmes et données enregistrés à l'ancien emplacement n'y seront pas. ») et **Quitter**. Base d'une version plus récente ou endommagée : même fenêtre avec le message de `L.verifier_base()`, sans Réessayer.
2. Créer un onglet par système de `m.systemes()`, dans cet ordre ; sélectionner le dernier onglet actif (`QSettings`).
3. Période initiale de chaque onglet (v1.1) : `m.periode_par_defaut(sid)`, la **dernière semaine de données**, du même jour de la semaine à la même heure (ex. lundi 19.10 09:17 → lundi 12.10 09:17), en heure suisse, changement d'heure compris. Moins d'une semaine de données : toute la période. Aucune donnée : pas de période.
4. Après un import ou une récupération : si la période affichée est la période par défaut (bouton **7 jours**) ou **Tout**, elle est recalculée pour suivre les nouvelles données ; une période choisie à la main reste en place jusqu'à la fermeture.

## Fichier partagé (v1.5)

`MainWindow` garde `self.espace` (`L.Espace`) et `self.magasin` (ouvert sur `espace.travail`).

- **Chaque action qui modifie la base** commence par `if not self.synchroniser(): return` (avant toute boîte de dialogue : reprend ce qu'un autre PC a publié) et finit par `self.publier()` : ajouter un système, mettre à jour la configuration, liste de log XML / standard, renommer, supprimer, connexion à la centrale enregistrée, récupérer, relire, tout récupérer, importer (une seule publication), glisser-déposer. L'export CSV et les vues ne publient rien.
- `publier()` : `L.ConflitPublication` → fenêtre de conflit ; `L.PublicationImpossible` → indicateur orange.
- `_surveiller()` toutes les 30 s et à l'activation de la fenêtre (sauf import ou fenêtre modale en cours) : publie ce qui attend, sinon recharge si un autre PC a publié (`recharger_depuis_partage()`), et signale une fois par session chaque copie en conflit créée par le synchroniseur.
- Fermeture : `magasin.fermer()`, puis `espace.fermer()` en boucle (conflit → choix ; impossible → « Réessayer / Fermer quand même », la copie locale est alors gardée).

## Récupération depuis la centrale (v1.1)

Module `engine/elpro_remote.py` (fourni, NE PAS MODIFIER) : connexion HTTP à la centrale à travers le tunnel WireGuard activé à la main, identification (le moteur vérifie toujours le n° de série ou le nom de la centrale), liste et téléchargement des fichiers de log qui ne sont pas encore dans la base, mot de passe chiffré par Windows (DPAPI).

```python
import elpro_remote as R
m.definir_acces(sid, adresse, utilisateur, R.proteger_mdp(mdp) | None)   # v1.5 : mot de passe de CE PC ; None = inchangé
m.acces(sid)                         # + mdp_ce_poste (v1.5) ; mdp = celui de ce PC, sinon l'ancien commun
R.Session(adresse, utilisateur, mdp).identifier()       # {'nom', 'serie'} ; lève R.ErreurCentrale
R.recuperer(m, sid, forcer=False, progression=f(n, total, nom), annuler=f() -> bool, relire=False)
    # relire=True (v1.4.1) : retélécharge TOUS les fichiers encore sur la centrale, importés avec completer=True
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
| `Documents\ELPRO Logs\elpro_logs.db`, ou l'emplacement choisi dans *Fichier › Emplacement des données* (clé `QSettings` `base/chemin`, v1.3), éventuellement dans OneDrive ou kDrive (v1.5) | Base unique : systèmes, configs, valeurs. Réécrite d'un seul coup après chaque modification, jamais ouverte par SQLite | le moteur (`L.Espace`) |
| `%LOCALAPPDATA%\ELPRO Logs\travail\` | Copie de travail de la base (+ `-wal`, `-shm`) pendant l'utilisation ; vide après une fermeture normale (v1.5) | le moteur |
| `.elpro.json` | Lu à l'ajout d'un système, puis copié dans la base | ELPRO Config |
| `.log` / `.zip` | Lus à l'import, **non conservés** (toutes les valeurs sont dans la base) | la radio |
| `.csv` | Export des valeurs ou du journal | le moteur / l'interface |
