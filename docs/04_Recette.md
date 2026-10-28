# 04 — Recette

## 1. Tests automatiques

```
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```
Attendu : `Ran 47 tests … OK` (34 tests du moteur + 13 de la récupération, v1.4). À lancer dans `build.bat` avant l'empaquetage, comme pour ELPRO Config (arrêt si échec).

## 2. Jeu de démonstration

Base vide (renommer temporairement `Documents\ELPRO Logs` s'il existe), puis :

1. Ajouter `examples\demo_site_B.json` ;
2. Importer les 3 fichiers de `examples\logs\`.

| # | Contrôle | Attendu | OK |
|---|---|---|---|
| R1 | Rapport d'import | 3 × « Importé — 2880 lignes importées. » | |
| R2 | Bandeau | `Radio n° 99000000001 · Config V1.0 · Données du 01.10.2026 02:00:00 au 04.10.2026 02:00:00 · 3 fichiers` | |
| R3 | Réimporter les 3 fichiers | 3 × « Déjà importé » | |
| R4 | Fermer et relancer l'application | L'onglet « Demo Site B » s'ouvre seul, données présentes | |
| R5 | Ajouter `demo_site_A.json` | 2ᵉ onglet ; relancer : les 2 onglets s'ouvrent dans le même ordre | |

### Vue globale (période « Tout »)

| # | Contrôle | Attendu | OK |
|---|---|---|---|
| G1 | Données disponibles | 100 %, aucun trou | |
| G2 | Frise B-SM2 | Rouge le 01.10 de 12:01 à 14:04 environ, vert ailleurs | |
| G3 | Frise B-SM3 | Jaune le 02.10 de 16:05 à 22:06 environ (batterie basse) | |
| G4 | Frise B-BASE | Jaune le 01.10 de 05:00 à 05:30 (coupure secteur) | |
| G5 | Ligne Système | Rouge 12:01–14:04 le 01.10, jaune aux deux autres moments | |
| G6 | Période « 7 jours » puis zoom sur le 01.10 de 11:00 à 15:00 par clic-glisser | La perte de B-SM2 occupe le centre ; **↶** revient à la période précédente | |
| G7 | Tableau B-SM2 | Dispo comm 97,14 % (orange) · 1 perte · 2 h 03 min | |
| G8 | Tableau B-SM3 | Batterie min 11,15 V (rouge) · Batterie basse 6 h 01 min · Radar max 281,2 cm (orange) | |
| G9 | Tableau B-BASE | Coupures secteur 1 (30 min) · Dispo comm vide | |

### Détail

| # | Contrôle | Attendu | OK |
|---|---|---|---|
| D1 | Double-clic sur B-SM3 dans la frise | Détail ouvert, canaux de B-SM3 cochés | |
| D2 | Graphique Batteries | Chute sous la ligne 11,5 V le 02.10 après-midi | |
| D3 | Graphique Radars | Unité cm, ligne de seuil à 250 cm, pic à ~281 cm le 02.10 | |
| D4 | Bouton « Même donnée, toutes les stations » sur une batterie | 9 courbes de batterie | |
| D5 | Cocher B-SM2 COMFLAG + RSSI, zoom le 01.10 de 11:00 à 15:00 | Couloir COMFLAG rouge 12:01–14:04 ; fond rouge pâle sur le graphique RSSI ; RSSI plat pendant la perte | |
| D6 | Curseur sur le 01.10 à 13:00 | Panneau : COMFLAG B-SM2 = 1 | |
| D7 | Famille « Registres non attribués » cochée | Nœud « Autres registres » visible avec les colonnes non utilisées | |
| D8 | Export CSV de 2 canaux sur 1 h | 121 lignes (en-tête + 120), heure suisse, séparateur `;`, s'ouvre dans Excel | |

### Journal

| # | Contrôle | Attendu | OK |
|---|---|---|---|
| J1 | Période « Tout » | **12 événements**, le premier : `01.10.2026 05:00:00 · B-BASE · Coupure secteur · 30 min 00 s` | |
| J2 | Perte de comm | `01.10.2026 12:01:00 · B-SM2 · Perte de communication · 2 h 03 min`, puis `Communication rétablie` à 14:04:30 | |
| J3 | Filtre station B-BASE + famille Secteur | 2 lignes : Coupure secteur, Secteur rétabli | |
| J4 | Double-clic sur « Batterie basse » | Détail de B-SM3 du 02.10 15:05 au 17:05 | |

### Trous, versions, série

| # | Contrôle | Attendu | OK |
|---|---|---|---|
| T1 | Base vide, n'importer que le 1ᵉʳ et le 3ᵉ log | Frise grise le 02.10 ; journal : « Début d'absence de données (1 j 0 h 00 min) » puis « Reprise des données » | |
| T2 | Puis importer le 2ᵉ log | Plus de gris ; résultat identique à R1–J4 | |
| T3 | Système › Mettre à jour la configuration avec `demo_site_B.json` modifié (nom d'un périphérique) | Onglet Fichiers : 2 versions ; bandeau jaune si la période chevauche les deux | |
| T4 | Importer dans Demo Site A un log de Demo Site B | Question « autre radio » ; Non → rien d'importé | |
| T5 | Changement d'heure | Période du 24.10 au 27.10 (logs générés avec `python tools\make_demo_logs.py examples\demo_site_B.json <dossier> 30`) : pas de décalage ni de doublon d'une heure dans les graphiques | |

### Installation

| # | Contrôle | Attendu | OK |
|---|---|---|---|
| I1 | Installer sur un PC sans Python | L'application démarre, heure suisse correcte (test R2) | |
| I2 | ELPRO Config et ELPRO Logs installés ensemble | Deux entrées distinctes dans Paramètres › Applications ; désinstaller l'une ne touche pas l'autre | |
| I3 | Désinstaller ELPRO Logs | `Documents\ELPRO Logs\elpro_logs.db` **reste** (données de l'utilisateur) | |

## 3. Récupération depuis la centrale et période par défaut (v1.1)

Automatique : `tests_ui\ui_acceptance.py` simule la centrale avec `FausseCentrale` (`tests/test_remote.py`) et vérifie le dialogue de connexion, le bouton, la progression, l'annulation et les cas `ok`, `rien_de_nouveau`, `acces_refuse`, `injoignable`, `mauvaise_centrale`, `non_configure`, ainsi que Tout récupérer.

Les contrôles R2 et G1 portent sur la période « Tout » : avec les 3 jours de démo, la période par défaut est déjà toute la période (P2).

Sur Windows, avec la vraie centrale d'un site (tunnel WireGuard activé) — **ne jamais écrire dans le dépôt le nom, l'adresse ou le n° de série d'un vrai site** :

| # | Contrôle | Attendu | OK |
|---|---|---|---|
| W1 | Connexion à la centrale : adresse du tunnel, user, mot de passe → Tester | « Connecté à <nom de la centrale> (n° <série>) » | |
| W2 | Récupérer les logs (1ʳᵉ fois) | Environ 160 fichiers importés, progression visible ; environ 7 jours de données | |
| W3 | Récupérer à nouveau | « Aucun nouveau fichier sur la centrale. » (ou 1–2 fichiers si plus d'une heure a passé) | |
| W4 | Tunnel WireGuard désactivé → Récupérer | Message « Centrale injoignable … Le tunnel WireGuard est-il activé ? » | |
| W5 | Mauvais mot de passe | Message « La centrale refuse … » + bouton Connexion à la centrale | |
| W6 | Saisir volontairement l'adresse de la centrale d'un **autre** site → Récupérer | Message « La centrale connectée est … » ; Non → rien d'importé | |
| W6b | Configurer 2 systèmes, puis **Tout récupérer** | Une ligne de rapport par système, les deux onglets à jour | |
| W6c | Ouvrir l'application | Période affichée : la dernière semaine de données (= bouton **7 jours**) | |
| P1 | Système avec plus de 7 jours de données : relancer l'application | Période = dernière semaine (même jour, même heure) | |
| P2 | Système avec 3 jours de démo | Période = les 3 jours entiers (R2 de 1.0 inchangé) | |
| W7 | Fermer, relancer | Adresse et utilisateur conservés ; mot de passe non redemandé | |
| W8 | `elpro_logs.db` ouvert avec un éditeur de texte | Le mot de passe n'apparaît pas en clair | |

## 4. Imports groupés et coupures (v1.2)

Automatique : `tests_ui\ui_acceptance.py` vérifie l'import groupé de 3 fichiers dans le désordre (même résultat), un lot impossible à écrire (chaque fichier en erreur, rien de gardé) et une récupération coupée en plein fichier (`fc.coupes`, les fichiers précédents sont gardés).

Sur Windows :

| # | Contrôle | Attendu | OK |
|---|---|---|---|
| V1 | Importer à la main une vingtaine de `.log` d'un coup | Nettement plus rapide qu'en 1.1 ; résultat identique | |
| V2 | Pendant une récupération, couper le tunnel WireGuard | « Centrale injoignable … Arrêt après k fichier(s) … » ; les k fichiers sont dans l'onglet Fichiers ; relancer le tunnel puis Récupérer : la suite arrive | |
| V3 | Tout récupérer avec une centrale injoignable en premier | Les centrales suivantes sont récupérées ; une ligne de rapport par système | |

## 5. Barre d'outils et emplacement des données (v1.3)

Automatique : `tests_ui\ui_acceptance.py` vérifie « Tout récupérer » comme entrée cliquable de la barre de menus entre Système et Aide (même action que dans Fichier, `Ctrl+Maj+R`, aucune barre d'outils, absent des onglets, v1.3.1), les boutons grisés pendant un import ou une récupération, le déplacement de la base dans un dossier temporaire (onglets rechargés, ancien fichier supprimé, chemin mémorisé), le refus d'écraser une base existante, la relance (même base, systèmes et connexion), la copie de sauvegarde et son ouverture, la base introuvable au démarrage (fenêtre de choix, aucune base vide créée, Réessayer une fois le dossier revenu) et une base endommagée (sans Réessayer).

Sur Windows :

| # | Contrôle | Attendu | OK |
|---|---|---|---|
| E1 | « Tout récupérer » (v1.3.1) | Dans la barre de menus, entre Système et Aide ; un clic lance la récupération (pas de menu déroulant) ; grisé sans connexion configurée ; aucune barre d'outils ; toujours dans Fichier et sur `Ctrl+Maj+R` | |
| E2 | Fichier › Emplacement des données › Déplacer vers un autre dossier (ex. `D:\ELPRO Logs`) | Base copiée, onglets rechargés à l'identique ; question « Supprimer l'ancien fichier ? » | |
| E3 | Fermer et relancer | La base du nouvel emplacement s'ouvre, tous les systèmes et connexions sont là (mot de passe non redemandé) | |
| E4 | Renommer temporairement le dossier choisi en E2, relancer | Fenêtre « base introuvable » ; Quitter ; remettre le nom ; relancer : tout revient | |
| E5 | Faire une copie de sauvegarde | Fichier créé ; « Ouvrir une base existante » sur cette copie : mêmes systèmes | |
| E6 | Déplacer vers un dossier OneDrive ou un lecteur réseau | Avertissement affiché avant de continuer | |

## 6. Mesures et consignes analogiques (v1.4)

Automatique : `tests_ui\ui_acceptance.py` vérifie que la colonne « Mesures » est masquée pour un système sans E/S analogique (chiffres de la vue globale inchangés : G1–G9), puis ajoute `demo_site_A` avec une entrée analogique AI2 sur A-SM1 (échelle 0–10 bar), importe un log avec les colonnes `ANA`, `ANA_FAIL`, `AO` et `BATTTV` (aucune « colonne ignorée »), et contrôle la colonne « Mesures » (`0 – 5,625 bar`), le Détail (famille « Mesures et consignes analogiques » cochée, graphique en bar) et le second tableau de l'aide « Liste de log » (Copier copie les deux).

Sur Windows :

| # | Contrôle | Attendu | OK |
|---|---|---|---|
| A1 | Systèmes existants | S'ouvrent comme avant, mêmes chiffres en vue globale | |
| A2 | Ajouter un système dont le `.elpro.json` a une entrée analogique (ex. `demo_site_A` + entrée analogique AI2 sur A-SM1, échelle 0–10 bar) | Détail : famille « Mesures et consignes analogiques », courbe en bar | |
| A3 | Importer un log contenant des colonnes `ANA01`, `ANA_FAIL02`, `AO01`, `BATTTV01` | Aucune « colonne ignorée » | |
| A4 | Vue globale | Colonne « Mesures » présente seulement pour ce système | |
| A5 | Aide › Liste de log | Second tableau `ANA / ANA_FAIL / AO` ; Copier copie les deux | |
