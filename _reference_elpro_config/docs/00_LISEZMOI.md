# Application « ELPRO Config » — dossier de réalisation

Ce dossier contient tout ce qu'il faut pour réaliser l'application. **Tu n'as pas besoin de connaître les radios ELPRO** : toutes les règles techniques sont déjà codées et testées dans le dossier `engine/`. Ton travail consiste à :

1. construire l'interface Windows (2 pages) ;
2. brancher cette interface sur les fonctions du moteur ;
3. empaqueter le tout en un `.exe`.

## Contenu du dossier

| Élément | Rôle | Le modifier ? |
|---|---|---|
| `00_LISEZMOI.md` | Ce fichier | — |
| `01_Architecture.md` | Technologies, arborescence, appels au moteur, empaquetage | — |
| `02_Page1_Configuration.md` | Écran de saisie : chaque champ, chaque contrôle, chaque bouton | — |
| `03_Modele_de_donnees.md` | Format exact du projet (JSON) que la page 1 produit | — |
| `04_Page2_Visualisation.md` | Écran de visualisation façon CConfig + boutons d'export | — |
| `05_Recette.md` | Tests automatiques et checklist de validation finale | — |
| `engine/elpro_engine.py` | Règles, calculs, écriture `.cdb` / `.sconf`, import `.cdb` | **NON** |
| `engine/views.py` | Données prêtes à afficher (page 2, Excel, PDF) | **NON** |
| `engine/export_excel.py` | Écriture du fichier Excel | Mise en forme seulement |
| `engine/export_pdf.py` | Écriture du compte rendu PDF | Mise en forme seulement |
| `resources/` | Gabarits XML validés dans CConfig, police du PDF, icône de l'application (`app_icon.ico` / `app_icon.png`) | **NON** |
| `examples/*.json` | Deux projets de démonstration fictifs (`demo_site_A`, `demo_site_B`). `demo_site_B` contient un radar sur B-SM3 | **NON** |
| `examples/expected_*.json` | Résultats attendus du moteur pour ces projets | **NON** |
| `tests/test_engine.py` | Tests automatiques du moteur | **NON** |

## Règles de travail

1. **Ne modifie jamais** `elpro_engine.py`, `views.py`, `resources/`, `examples/`, `tests/`. Si quelque chose te semble faux dans ces fichiers, **arrête-toi et signale-le** : ces règles ont été validées sur des radios réelles.
2. L'interface ne contient **aucune règle métier**. Elle saisit des données, appelle le moteur, affiche ce que le moteur renvoie. Les messages d'erreur viennent tous de `elpro_engine.valider()`.
3. Avant chaque livraison : `.\venv\Scripts\python.exe -m unittest discover -s tests -v` doit afficher `OK`.
4. Textes de l'interface en **français**.
5. **Noms de fichiers et de dossiers de code en anglais** (ex. `build.bat`, `ui/main_window.py`) ; **commentaires et docstrings en français** ; documentation (`docs/*.md`) en français.

## Ordre de réalisation

| Étape | Livrable | Contrôle |
|---|---|---|
| 1 | Environnement Python + lancement des tests | 22 tests `OK` |
| 2 | Fenêtre principale avec 2 onglets vides | L'application s'ouvre |
| 3 | Page 1 complète (`02_Page1_Configuration.md`) | Ouvrir `examples/demo_site_A.json` puis l'enregistrer : fichier identique |
| 4 | Bouton « Générer » de la page 1 | Messages d'erreur affichés ; projet valide → page 2 remplie |
| 5 | Page 2 (`04_Page2_Visualisation.md`) | Arbre identique à la structure décrite |
| 6 | Boutons d'export de la page 2 | Les 4 types de fichiers sont créés |
| 7 | Import `.cdb` | Un `.cdb` généré se réimporte : mêmes radios |
| 8 | Empaquetage `.exe` | Fonctionne sur un PC Windows sans Python |
| 9 | Recette (`05_Recette.md`) | Toutes les cases cochées |
