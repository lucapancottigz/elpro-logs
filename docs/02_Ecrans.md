# 02 — Écrans

Toutes les dates affichées et saisies sont en **heure suisse**, au format `JJ.MM.AAAA HH:MM:SS` (ou `JJ.MM.AAAA HH:MM` quand la place manque). Les durées s'affichent avec `L.duree_texte()`.

## 1. Fenêtre principale

Titre : `ELPRO Logs`. Barre d'état : `© 2026 Geoazimut SàRL — geoazimut.com` à droite, taille de la base à gauche (`L.Magasin.taille_fichier()`, en Mo).

**Un onglet par système** (`QTabWidget`), tous ouverts au démarrage, dans l'ordre de `m.systemes()`. Titre de l'onglet = `nom`. Les onglets ne se ferment pas (pas de croix) : pour retirer un système, menu *Système › Supprimer ce système*.

S'il n'y a encore aucun système : page d'accueil avec un grand bouton **« Ajouter un système (.elpro.json)… »** et une phrase : « Ajoutez d'abord un système avec le fichier .elpro.json créé par ELPRO Config, puis importez les fichiers .log de sa centrale. »

### Menus

| Menu | Entrée | Action |
|---|---|---|
| Fichier | Ajouter un système (.elpro.json)… | Choix du fichier → `m.ajouter_config(json)`. Statut `nouveau` : nouvel onglet, sélectionné. `version` : voir *Mettre à jour la configuration*. `identique` : « Ce système est déjà dans l'application. » et l'onglet est sélectionné. `ValueError` : afficher le message. |
| Fichier | Importer des logs… (`Ctrl+I`) | Pour le système de l'onglet actif. Sélection multiple de `.log`, `.zip`, `.csv`. Voir § 7. |
| Fichier | Tout récupérer (`Ctrl+Maj+R`, aussi dans la barre de menus entre Système et Aide) | `R.recuperer_tout(...)` dans un `QThread` ; progression « <système> — fichier n / total » ; Annuler arrête après le fichier en cours. Rapport : une ligne par système (Système, Résultat, Nouveaux fichiers, Message), `alerte` en orange sous la ligne. Une centrale `mauvaise_centrale` n'est pas forcée. Puis rafraîchir tous les onglets. Grisé si aucun système n'a de connexion configurée. (v1.1) |
| Fichier | Exporter en CSV… | Exporte les canaux cochés dans l'onglet Détail sur la période affichée (`m.exporter_csv`). Grisé hors de l'onglet Détail ou si rien n'est coché. |
| Fichier | Emplacement des données… | Voir § 9. (v1.3) |
| Fichier | Quitter | — |
| Système | Récupérer les logs (`Ctrl+R`) | Voir § 8. (v1.1) |
| Système | Connexion à la centrale… | Voir § 8. (v1.1) |
| Système | Mettre à jour la configuration (.elpro.json)… | Boîte : « À partir de quand cette configuration est-elle en service ? » avec un champ date/heure (par défaut : maintenant). → `m.ajouter_config(json, valable_depuis)`. Si le `system_name` du fichier est différent de celui de l'onglet : refuser (« Ce fichier décrit un autre système »). |
| Système | Liste de log de la centrale (XML)… | Rare : seulement si la centrale n'a pas la liste standard. Choix de l'export XML de la radio → `m.definir_profil(sid, L.lire_profil_xml(chemin))`. Entrée « Revenir à la liste standard » → `m.definir_profil(sid, None)`. Ne s'applique qu'aux imports suivants. |
| Système | Renommer… | `m.renommer` |
| Système | Supprimer ce système… | Double confirmation (« Toutes les valeurs importées de ce système seront effacées. ») → `m.supprimer_systeme(sid)` puis `m.compacter_base()`. |
| Aide | Liste de log à configurer sur la centrale | Fenêtre avec `L.REGLAGES_STANDARD` et le tableau `L.LISTE_STANDARD` (Nom, 1er registre, Nombre), bouton Copier. |
| Aide | À propos | Comme ELPRO Config : nom, version, copyright, site, licences tierces. |

### « Tout récupérer » dans la barre de menus (v1.3.1)

Entrée **cliquable** de la barre de menus, entre **Système** et **Aide** : un clic lance directement la récupération (ce n'est pas un menu déroulant). C'est la même action que *Fichier › Tout récupérer* : même texte, raccourci `Ctrl+Maj+R`, info-bulle « Récupérer les logs de toutes les centrales configurées (Ctrl+Maj+R) » (`menuBar().insertAction(menu_aide.menuAction(), action_tout_recuperer)`). Il n'y a pas de barre d'outils (celle de la 1.3.0 est retirée) et « Tout récupérer » n'apparaît pas dans les onglets. Grisé si aucun système n'a de connexion configurée, ou pendant un import ou une récupération. « Récupérer les logs » (un seul système) reste dans le bandeau de chaque onglet.

**Glisser-déposer** : des `.log`/`.zip`/`.csv` déposés sur la fenêtre sont importés dans le système de l'onglet actif ; un `.elpro.json` déposé ajoute un système.

## 2. Onglet d'un système

De haut en bas :

**Bandeau d'informations** (une ligne, texte gris) :
`Radio n° <serie> · Config V<version> · Données du <t0> au <t1> · <n> fichiers` — si `serie` est vide : `Radio n° —`. S'il n'y a aucune donnée : « Aucun log importé » et un bouton **Importer des logs…**.

Sous le bandeau (v1.1) : bouton **Récupérer les logs** à côté de « Importer des logs… », puis texte gris `Dernière récupération : <heure suisse> — <résultat>` (d'après `m.acces(sid)`) ou « Jamais récupéré ». Si `R.rappel_necessaire(m, sid)` renvoie un texte : bandeau jaune avec ce texte et un bouton **Récupérer les logs** (à l'ouverture et à l'affichage de l'onglet).

**Barre de période** (commune aux 4 sous-onglets) :
- boutons : **Tout**, **7 jours**, **24 h**, **30 jours** (comptés depuis la fin des données, pas depuis maintenant). **7 jours** = `m.periode_par_defaut(sid)` : la dernière semaine de données, du même jour à la même heure ; c'est la **période initiale** à l'ouverture de l'application et à l'ajout d'un système (v1.1). Moins d'une semaine de données : toute la période ;
- **Du** `[QDateTimeEdit]` **Au** `[QDateTimeEdit]` + bouton **Afficher** ;
- boutons **◀** et **▶** : décalent la période de sa propre durée ;
- bouton **↶ Période précédente** (historique des périodes, 20 niveaux).
- Si `m.versions_dans_periode()` renvoie plus d'une version : petit bandeau jaune « La configuration a changé pendant cette période (V1.0 → V1.1). Les libellés sont ceux de la version en vigueur à la fin de la période. »

**Sous-onglets** : Vue globale · Détail · Journal · Fichiers.

## 3. Vue globale

### 3.1 Chiffres clés (une ligne de « cartes »)

D'après `m.synthese(sid, t0, t1)` :

| Carte | Valeur |
|---|---|
| Données disponibles | `couverture_pct` % (+ « n trous » si `trous` non vide) |
| Pertes de communication | somme des `comm.nb_pertes`, durée cumulée |
| Stations avec perte de comm | nombre de stations avec `nb_pertes > 0`, sur le nombre de remotes et repeaters |
| Batteries basses | nombre de stations avec `duree_basse > 0` |
| Coupures secteur | somme des `nb_coupures` |
| Détections | somme des `nb_activations` des canaux `DETECTION` |

### 3.2 Frise des états

Graphique pyqtgraph, axe X = temps, une ligne horizontale par station + une ligne **Système** en haut (`m.etat_systeme`). Chaque ligne est une suite de rectangles colorés selon `L.COULEURS_ETATS[etat]` :

| État | Couleur | Signification (`L.LIBELLES_ETATS`) |
|---|---|---|
| SANS_DONNEES | gris | Pas de données |
| COMM_PERDUE | rouge | Communication perdue (comflag) |
| DEGRADE | orange | Lecture ou envoi en échec |
| ALERTE | jaune | Batterie basse ou secteur absent |
| OK | vert | OK |

- Si la période contient plus de segments que de pixels : afficher `L.Magasin.par_cases(segments, t0, t1, largeur_en_pixels)` (chaque case prend l'état le plus grave). Les incidents courts restent donc toujours visibles.
- Légende sous la frise.
- **Survol** : bulle « Station · État · du … au … (durée) ».
- **Clic-glisser** horizontal : la zone sélectionnée devient la période (zoom).
- **Double-clic sur une ligne de station** : ouvre l'onglet Détail avec cette station cochée (toutes familles sauf « Registres non attribués »), même période.

### 3.3 Tableau de synthèse par station

Une ligne par station, colonnes :

| Colonne | Source (`synthese['stations'][i]`) | Mise en évidence |
|---|---|---|
| Station, Rôle | `station`, `role` | — |
| Dispo comm | `comm.disponibilite_pct` % (vide pour la base) | < 99 % orange, < 95 % rouge |
| Pertes comm | `comm.nb_pertes` | > 0 en gras |
| Durée pertes / plus longue | `comm.duree_pertes`, `comm.plus_longue` | — |
| Batterie min / moy / max | canal `BATTV` : `min`, `moyenne`, `max` (V, 2 décimales) | min < `L.BATTV_BAS` rouge |
| Batterie basse | canal `BATTV` : `duree_basse` | > 0 rouge |
| RSSI min / moy | canal `RSSI` : `min`, `moyenne` (dBm) | min < `L.RSSI_FAIBLE` orange |
| Coupures secteur | canal `MAINV` : `nb_coupures`, `duree_coupures` | > 0 jaune |
| Détections | somme des `nb_activations` des canaux `DETECTION` de la station | — |
| Commandes | somme des `nb_activations` des canaux `COMMANDE` | — |
| Radar max | canal `RADAR` : `max` + unité | ≥ `seuil_haut` orange |

Les valeurs batterie, RSSI et radar sont calculées **hors pertes de communication** (pendant une perte, la centrale garde la dernière valeur reçue). Note sous le tableau : « Valeurs mesurées hors pertes de communication. »

Double-clic sur une ligne : comme sur la frise.

## 4. Détail

Écran en deux parties (`QSplitter`).

### 4.1 À gauche : sélection

- **Filtres par type** (cases à cocher, une par `L.FAMILLES`) : Communication, Échecs de lecture/envoi, Batteries, RSSI, Secteur (MAINV), Détections, Commandes, Radars, Registres non attribués. Par défaut tout coché sauf « Échecs » et « Registres non attribués ». Ils filtrent l'arbre.
- **Arbre** (`QTreeWidget` avec cases) : Station › Famille › Canal (`libelle`, et `nom` en gris). Les canaux de la famille « Registres non attribués » (`catalogue['autres']`) sont sous un nœud « Autres registres » : ce sont les colonnes du log que la configuration n'utilise pas ; elles sont gardées car on veut **toutes** les valeurs.
- Boutons :
  - **Toute la station** : coche tous les canaux visibles de la station sélectionnée ;
  - **Même donnée, toutes les stations** : coche le même genre pour toutes les stations (ex. toutes les batteries) ;
  - **Tout décocher**.
- Coche initiale à l'ouverture d'un système : rien. Maximum conseillé : 30 canaux (au-delà : avertissement, l'affichage reste possible).

### 4.2 À droite : graphiques

Graphiques pyqtgraph **empilés, axe X commun** (zoom et défilement synchronisés), du haut vers le bas :

1. **États binaires** (comflag, échecs, secteur, détections, commandes) : un seul graphique en « couloirs », une ligne par canal, rectangle plein quand la valeur vaut 1 (secteur : plein quand **absent**, valeur 0). Couleurs : comflag et échecs rouge, secteur absent jaune, détections orange, commandes bleu. Source : `m.segments_decodes()`. Libellé à gauche de chaque couloir : `station · libellé`.
2. **Un graphique par unité** pour les valeurs analogiques : Batteries (V), RSSI (dBm), Radars (une échelle par unité : cm, mA…). Une courbe par canal, en escalier, source `m.courbe(sid, canal, t0, t1, n_max=largeur_en_pixels*2)`. `None` = coupure de la courbe (pas de données). Ligne horizontale pointillée : `L.BATTV_BAS` (batteries), `L.RSSI_FAIBLE` (RSSI), `seuil_haut` (radars).
3. Sur tous les graphiques : **fond gris** sur les trous de données (`m.trous`) ; **fond rouge pâle** sur les pertes de comm des stations affichées (segments à 1 du canal COMFLAG de chaque station), pour signaler que les valeurs sont figées.

Interactions :
- molette / clic-glisser : zoom et défilement en X ; bouton **Utiliser cette vue comme période** ;
- **curseur vertical** qui suit la souris : à côté des graphiques, un panneau « Valeurs au JJ.MM.AAAA HH:MM:SS » liste chaque canal affiché et sa valeur à cet instant (texte « pas de données » dans un trou) ;
- légende cliquable (masquer/afficher une courbe).

### 4.3 Sous les graphiques : statistiques des canaux cochés

Tableau tiré de `m.synthese()` : Canal, Station, min, moyenne, max (analogiques), nb d'activations, durée active (binaires).

## 5. Journal

Tableau de `m.evenements(sid, t0, t1, stations, familles)` :

| Colonne | Contenu |
|---|---|
| Date et heure | `L.heure_locale(e['t'])` |
| Station | `e['station']` (vide pour les trous de données) |
| Événement | `e['message']` |
| Durée | `L.duree_texte(e['duree'])` si présent |

- Filtres au-dessus : stations (liste à cocher), familles (`L.FAMILLES` + « Données » pour les trous), gravité.
- Couleur de ligne selon `e['gravite']` : `defaut` rouge pâle, `alarme` orange pâle, `alerte` jaune pâle, `commande` bleu pâle, `info` sans couleur.
- Double-clic : onglet Détail, station de l'événement cochée, période = ±1 h autour de l'événement.
- Bouton **Exporter le journal (CSV)** : séparateur `;`, UTF-8 avec BOM, mêmes colonnes.
- Les échecs de lecture qui commencent ou finissent en même temps qu'une perte de comm ne sont pas listés (le moteur les regroupe) : ne pas les recalculer.

## 6. Fichiers

Trois tableaux :

1. **Logs importés** (`m.fichiers(sid)`) : Fichier, N° de série, Du, Au, Lignes, Lignes gardées, Importé le. Une ligne où `nb_lignes_gardees < nb_lignes` est en gris italique (lignes déjà présentes).
2. **Versions de configuration** (`m.configs(sid)`) : Version, En service depuis (`valable_depuis` = 0 → « origine »), Importée le.
3. **Liste de log** : « Standard GeoAzimut » ou « Propre à cette centrale (XML importé) » + la liste (`m.profil(sid)`).

Boutons : Importer des logs…, Mettre à jour la configuration…, Liste de log (XML)…

## 7. Import des logs

1. Boîte de sélection multiple (dossier mémorisé dans `QSettings`).
2. Fenêtre de progression (une barre par fichier + barre globale), import dans un `QThread`. Bouton Annuler : s'arrête après le fichier en cours.
3. Pour un rapport `serie_differente` : question « <message> Importer quand même dans ce système ? » → si Oui, `importer_fichier(..., forcer_serie=True)`.
4. Rapport final (tableau) : Fichier, Résultat, Détail. Résultats affichés :

| statut | Texte affiché |
|---|---|
| importe | Importé — `message` |
| deja_importe | Déjà importé |
| deja_couvert | Déjà présent (mêmes horodatages) |
| vide | Fichier vide |
| erreur | Erreur — `message` |
| serie_differente (refusé) | Non importé — autre radio |

Les `avertissements` s'affichent sous la ligne du fichier, en orange.

5. Rafraîchir l'onglet ; si la période affichée était « Tout », l'étendre aux nouvelles données.

## 8. Récupération depuis la centrale (v1.1)

### Connexion à la centrale…

| Champ | Contenu |
|---|---|
| Adresse | `acces['adresse']`, sinon vide (adresse WireGuard propre à chaque centrale) |
| Utilisateur | `acces['utilisateur']`, sinon `R.UTILISATEUR_DEFAUT` |
| Mot de passe | masqué ; vide avec le texte gris « (inchangé) » si un mot de passe est déjà enregistré |
| Note | « Activez d'abord le tunnel WireGuard. » |

- **Tester la connexion** (dans un `QThread`) : « Connecté à <nom> (n° <série>) » en vert, ou le message de l'erreur en rouge.
- **Enregistrer** : `m.definir_acces(sid, adresse, utilisateur, R.proteger_mdp(mdp))` ; champ mot de passe vide : le mot de passe enregistré est gardé tel quel.

### Récupérer les logs

- Si `m.acces(sid)` est vide : ouvrir d'abord *Connexion à la centrale…*.
- `R.recuperer(...)` dans un `QThread` (instance `Magasin` dédiée) ; progression « Fichier n / total : nom » + Annuler.
- Puis rafraîchir l'onglet (comme après un import) et afficher selon le statut :

| `statut` | Affichage |
|---|---|
| `ok` | Tableau des imports (comme l'import manuel) + `message` ; `alerte` en orange au-dessus |
| `rien_de_nouveau`, `annule` | Information : `message` |
| `injoignable`, `introuvable`, `erreur` | Erreur : `message` |
| `acces_refuse`, `non_configure` | Erreur : `message` + bouton **Connexion à la centrale…** |
| `mauvaise_centrale` | Question : `message` + « Importer quand même dans ce système ? » (**Non** par défaut). Oui → `R.recuperer(m, sid, forcer=True, …)` |

## 9. Emplacement des données (v1.3)

*Fichier › Emplacement des données…* : boîte de dialogue `EmplacementDonnees` (`ui/dialogs.py`), actions faites par la fenêtre principale. **Tous les boutons sont grisés pendant un import ou une récupération.**

| Élément | Contenu |
|---|---|
| Emplacement actuel | `m.chemin` (sélectionnable) + bouton **Ouvrir le dossier** (Explorateur) |
| Taille | `m.taille_fichier()` en Mo, nombre de systèmes |
| **Déplacer vers un autre dossier…** | Choix d'un dossier → `<dossier>\elpro_logs.db`. Avertissement de `L.avertissement_emplacement()` (réseau, OneDrive…) : « Continuer quand même ? » (Non par défaut). Base déjà présente : « L'ouvrir à la place ? », jamais d'écrasement. `L.copier_base()` dans un `QThread` (barre d'attente), puis ouverture de la copie, clé `base/chemin` enregistrée, onglets rechargés (même onglet actif). Enfin « Supprimer l'ancien fichier ? » (Non par défaut ; Oui supprime aussi `-wal` et `-shm`). Échec : message, l'ancienne base reste active. |
| **Ouvrir une base existante…** | Filtre « Base ELPRO Logs (*.db) » → `L.verifier_base()` ; si valide : « Ouvrir cette base (n systèmes) ? Les systèmes de la base actuelle ne seront plus affichés (ils restent dans son fichier). » ; sinon son message. |
| **Faire une copie de sauvegarde…** | Nom proposé `elpro_logs_sauvegarde_AAAA-MM-JJ.db` → `L.copier_base()` (application ouverte) → « Copie enregistrée (x Mo). » Un fichier existant n'est jamais remplacé. |
| **Revenir à l'emplacement par défaut** | Grisé si la base est déjà à l'emplacement par défaut. Ouvre la base par défaut si elle existe (comme *Ouvrir une base existante*), sinon propose d'y **déplacer** la base actuelle. La clé `base/chemin` est effacée. |

Démarrage avec une base introuvable ou inutilisable : voir `01_Architecture.md`, *Démarrage*.