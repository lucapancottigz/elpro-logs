# 04 — Recette

## 1. Tests automatiques

```
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```
Attendu : `Ran 24 tests … OK`. À lancer dans `build.bat` avant l'empaquetage, comme pour ELPRO Config (arrêt si échec).

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
