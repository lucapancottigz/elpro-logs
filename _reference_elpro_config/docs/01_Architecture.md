# 01 — Architecture

## Technologies imposées

| Élément | Choix | Version |
|---|---|---|
| Langage | Python | 3.11 (64 bits) |
| Interface | PySide6 (Qt) | ≥ 6.6 |
| PDF | reportlab | ≥ 4.0 |
| Excel | openpyxl | ≥ 3.1 |
| Empaquetage | PyInstaller | ≥ 6.0 |
| Système cible | Windows 10 / 11, hors ligne | — |

Installation :

```
py -3.11 -m venv venv
venv\Scripts\activate
pip install PySide6 reportlab openpyxl pyinstaller
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Arborescence finale

```
elpro_config/
├─ app.py                  ← point d'entrée (à écrire)
├─ ui/                     ← interface (à écrire)
│  ├─ __init__.py
│  ├─ main_window.py      ← QMainWindow + QTabWidget (Page 1 / Page 2)
│  ├─ page_config.py
│  ├─ page_result.py
│  └─ dialogs.py          ← fenêtres d'édition des radios et périphériques
├─ engine/                 ← fourni, NE PAS MODIFIER (sauf mise en forme export_*.py)
├─ resources/              ← fourni
├─ examples/               ← fourni
└─ tests/                  ← fourni
```

## Les seules fonctions du moteur à appeler

```python
import elpro_engine as M, views as V, export_excel as XL, export_pdf as PDF

erreurs = M.valider(projet)                 # list[str] ; vide = valide
plan    = M.calculer_plan(projet)           # dict ; lève ValueError si projet invalide
M.ecrire_cdb(plan, chemin)                  # écrit le .cdb (UTF-16, prêt pour CConfig)
M.ecrire_sconf(plan['stations'][i]['iop'], chemin)   # écrit un .sconf (seulement si iop n'est pas None)
noeuds  = V.vue_page2(plan)                 # contenu de la page 2
XL.ecrire_excel(V.donnees_excel(plan), chemin, plan['systeme']['nom_projet'])
PDF.ecrire_pdf(V.donnees_pdf(plan), chemin, plan['systeme']['nom_projet'])
cle     = M.generer_cle()                   # clé de chiffrement 24 caractères
projet, avertissements = M.importer_cdb(chemin)      # lève M.ProjetProtege si fichier protégé
```

`projet` est un `dict` au format de `03_Modele_de_donnees.md`. `plan` est produit par le moteur ; l'interface ne le modifie jamais.

## Flux de l'application

```
Page 1 (saisie) ──► projet (dict) ──► [Générer] ──► M.valider()
                                                      │ erreurs → boîte de dialogue, on reste en page 1
                                                      ▼ OK
                                                M.calculer_plan() ──► plan (gardé en mémoire)
                                                      ▼
                                   Page 2 affiche V.vue_page2(plan) (lecture seule)
                                   Boutons : .cdb / .sconf / PDF / Excel
```

- Toute modification en page 1 après une génération **efface le plan** et **vide la page 2** (bandeau « Configuration modifiée : cliquer sur Générer »). Les boutons d'export sont alors grisés.
- La page 2 n'est **jamais modifiable**.

## Empaquetage

Dans `app.py`, déterminer le dossier des ressources ainsi (fonctionne en `.exe` et en développement) :

```python
import sys, os
BASE = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, 'engine'))
```

`elpro_engine.RESSOURCES` pointe vers `engine/../resources` : garder exactement cette arborescence dans l'exécutable.

Icône de l'application (logo GeoAzimut) : `resources/app_icon.ico` pour l'exécutable, `resources/app_icon.png` pour les fenêtres. Dans `app.py`, avant de créer la fenêtre :

```python
from PySide6.QtGui import QIcon
if sys.platform == 'win32':     # icône correcte dans la barre des tâches, même lancé avec python.exe
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('GeoAzimut.ELPROConfig')
app.setWindowIcon(QIcon(os.path.join(BASE, 'resources', 'app_icon.png')))
```

Commande :

```
pyinstaller --noconfirm --windowed --name "ELPRO Config" --icon "resources\app_icon.ico" ^
  --add-data "engine;engine" --add-data "resources;resources" --add-data "examples;examples" ^
  app.py
```

Livrer le dossier `dist\ELPRO Config\` complet (zip). Ne pas utiliser `--onefile` (démarrage lent).

## Fichiers de l'utilisateur

| Fichier | Extension | Encodage | Écrit par |
|---|---|---|---|
| Projet de l'application | `.elpro.json` | UTF-8, indenté 2 espaces | l'interface (`json.dump(projet, f, ensure_ascii=False, indent=2)`) |
| Config CConfig | `.cdb` | UTF-16 LE + BOM, CRLF | `M.ecrire_cdb` |
| Logique IO Plus | `.sconf` | tar.gz | `M.ecrire_sconf` |
| Compte rendu | `.pdf` | — | `export_pdf.ecrire_pdf` |
| Liste d'adresses | `.xlsx` | — | `export_excel.ecrire_excel` |
