# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""Point d'entrée de l'application ELPRO Logs."""
import sys, os
BASE = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, 'engine'))

# Le moteur est chargé depuis le dossier `engine/` à l'exécution : PyInstaller ne voit donc pas
# ses dépendances. Les importer ici garantit qu'elles sont embarquées dans l'exécutable.
import io, re, gzip, json, zlib, sqlite3, tarfile, zipfile, hashlib, datetime, threading, csv  # noqa: F401,E401
import secrets, string, copy, zoneinfo, xml.etree.ElementTree  # noqa: F401,E401
import tzdata  # noqa: F401  (heure suisse sous Windows)

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from version import APP_VERSION, APP_COPYRIGHT


def verifier(dossier):
    """`ELPRO Logs.exe --verifier <dossier>` : sans interface, importe les logs de démonstration dans une base
    temporaire et contrôle l'heure suisse, l'import, la synthèse et le journal. Résultat dans
    <dossier>/verification.txt (contrôle de l'exécutable lors de la recette)."""
    import glob, traceback
    import elpro_logs as L
    os.makedirs(dossier, exist_ok=True)
    lignes = []

    def controle(cond, texte):
        lignes.append(('OK ' if cond else 'ÉCHEC ') + texte)

    try:
        controle(L.ZONE is not None, 'fuseau Europe/Zurich disponible (tzdata)')
        controle(L.heure_locale(L.utc_depuis_texte('2026-10-15 11:44:10')) == '15.10.2026 13:44:10',
                 'heure d\'été suisse')
        controle(L.heure_locale(L.utc_depuis_texte('2026-10-26 11:44:10')) == '26.10.2026 12:44:10',
                 'heure d\'hiver suisse')
        base = os.path.join(dossier, 'verification.db')
        for suf in ('', '-wal', '-shm'):
            if os.path.exists(base + suf):
                os.remove(base + suf)
        m = L.Magasin(base)
        with open(os.path.join(BASE, 'examples', 'demo_site_B.json'), encoding='utf-8') as f:
            sid = m.ajouter_config(json.load(f))['systeme_id']
        logs = sorted(glob.glob(os.path.join(BASE, 'examples', 'logs', '*.log')))
        rap = [r for c in logs for r in m.importer_fichier(sid, c)]
        controle(len(rap) == 3 and all(r['statut'] == 'importe' for r in rap), f'import de {len(rap)} logs de démonstration')
        t0, t1 = m.periode(sid)
        controle((L.heure_locale(t0), L.heure_locale(t1)) == ('01.10.2026 02:00:00', '04.10.2026 02:00:00'),
                 f'période {L.heure_locale(t0)} – {L.heure_locale(t1)}')
        sy = m.synthese(sid, t0, t1)
        controle(sy['couverture_pct'] == 100.0, 'couverture 100 %')
        ev = m.evenements(sid, t0, t1)
        controle(len(ev) == 12, f'{len(ev)} événements au journal')
        m.fermer()
        for suf in ('', '-wal', '-shm'):
            if os.path.exists(base + suf):
                os.remove(base + suf)
    except Exception:
        lignes.append(f'ÉCHEC :\n{traceback.format_exc()}')
    with open(os.path.join(dossier, 'verification.txt'), 'w', encoding='utf-8') as f:
        f.write(f'ELPRO Logs {APP_VERSION}\n{APP_COPYRIGHT}\n' + '\n'.join(lignes) + '\n')
    return 0 if all(l.startswith('OK') for l in lignes) else 1


def main():
    if len(sys.argv) in (2, 3) and sys.argv[1] == '--verifier':
        import tempfile     # dossier facultatif : %TEMP%\elpro_logs_verif par défaut
        sys.exit(verifier(sys.argv[2] if len(sys.argv) == 3 else os.path.join(tempfile.gettempdir(), 'elpro_logs_verif')))
    if sys.platform == 'win32':     # icône correcte dans la barre des tâches, même lancé avec python.exe
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('GeoAzimut.ELPROLogs')
    app = QApplication(sys.argv)
    app.setApplicationName('ELPRO Logs')
    app.setOrganizationName('GeoAzimut')
    # logo GeoAzimut : toutes les fenêtres et boîtes de dialogue héritent de cette icône
    app.setWindowIcon(QIcon(os.path.join(BASE, 'resources', 'app_icon.png')))

    import elpro_logs as L
    from ui.main_window import MainWindow
    chemin = L.chemin_base_defaut()
    try:
        magasin = L.Magasin(chemin)
    except Exception as e:          # base d'une version plus récente, fichier verrouillé, disque inaccessible…
        QMessageBox.critical(None, 'ELPRO Logs', f'Impossible d\'ouvrir la base de données :\n{chemin}\n\n{e}\n\n'
                             'Fermez les autres fenêtres d\'ELPRO Logs, ou installez la dernière version.')
        sys.exit(1)
    f = MainWindow(BASE, chemin, magasin)
    f.show()
    autres = [a for a in sys.argv[1:] if os.path.isfile(a)]
    if autres:
        f.deposer(autres)
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
