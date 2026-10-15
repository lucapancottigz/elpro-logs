# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""Point d'entrée de l'application ELPRO Config."""
import sys, os
BASE = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, 'engine'))

# Le moteur est chargé depuis le dossier `engine/` à l'exécution : PyInstaller ne voit donc pas
# ses dépendances. Les importer ici garantit qu'elles sont embarquées dans l'exécutable.
import tarfile, secrets, string, datetime, xml.etree.ElementTree  # noqa: F401,E401
import openpyxl, openpyxl.styles, openpyxl.utils  # noqa: F401,E401
import reportlab.platypus, reportlab.lib.pagesizes, reportlab.pdfbase.ttfonts  # noqa: F401,E401

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from version import APP_VERSION, APP_COPYRIGHT


def verifier(dossier):
    """`ELPRO Config.exe --verifier <dossier>` : produit les 4 exports des deux projets d'exemple, sans interface,
    et écrit le résultat dans <dossier>/verification.txt (contrôle de l'exécutable lors de la recette)."""
    import json, traceback
    import elpro_engine as M, views as V, export_excel as XL, export_pdf as PDF
    os.makedirs(dossier, exist_ok=True)
    lignes = []
    for nom in ('demo_site_A', 'demo_site_B'):
        try:
            with open(os.path.join(BASE, 'examples', f'{nom}.json'), encoding='utf-8') as f:
                projet = json.load(f)
            plan, fichiers = M.generer_tout(projet, os.path.join(dossier, nom))
            base, titre = M.base_nom_fichier(plan), f"{plan['systeme']['nom_projet']} — V{plan['version_config']}"
            fichiers.append(PDF.ecrire_pdf(V.donnees_pdf(plan), os.path.join(dossier, nom, f'{base}_Compte_rendu.pdf'),
                                           titre))
            fichiers.append(XL.ecrire_excel(V.donnees_excel(plan), os.path.join(dossier, nom, f'{base}_Adresses.xlsx'),
                                            titre))
            lignes += [f'OK {nom} : {os.path.basename(c)} ({os.path.getsize(c)} octets)' for c in fichiers]
        except Exception:
            lignes.append(f'ÉCHEC {nom} :\n{traceback.format_exc()}')
    with open(os.path.join(dossier, 'verification.txt'), 'w', encoding='utf-8') as f:
        f.write(f'ELPRO Config {APP_VERSION}\n{APP_COPYRIGHT}\n' + '\n'.join(lignes) + '\n')
    return 0 if all(l.startswith('OK') for l in lignes) else 1


def main():
    if len(sys.argv) in (2, 3) and sys.argv[1] == '--verifier':
        import tempfile     # dossier facultatif : %TEMP%\elpro_verif par défaut
        sys.exit(verifier(sys.argv[2] if len(sys.argv) == 3 else os.path.join(tempfile.gettempdir(), 'elpro_verif')))
    if sys.platform == 'win32':     # icône correcte dans la barre des tâches, même lancé avec python.exe
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('GeoAzimut.ELPROConfig')
    app = QApplication(sys.argv)
    app.setApplicationName('ELPRO Config')
    app.setOrganizationName('GeoAzimut')
    # logo GeoAzimut : toutes les fenêtres et boîtes de dialogue héritent de cette icône
    app.setWindowIcon(QIcon(os.path.join(BASE, 'resources', 'app_icon.png')))
    f = MainWindow(BASE)
    f.show()
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        f.ouvrir_fichier(sys.argv[1])
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
