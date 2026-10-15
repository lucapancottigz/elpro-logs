# Composants tiers

ELPRO Logs est © 2026 Geoazimut SàRL, tous droits réservés (voir `LICENSE`). Les composants ci-dessous ne sont pas la propriété de Geoazimut SàRL.

ELPRO Logs utilise les composants suivants. Chacun reste soumis à sa propre licence.

| Composant | Usage | Licence |
|---|---|---|
| Python 3.11 (dont `sqlite3` / SQLite) | Langage, environnement d'exécution et base de données locale | PSF License (SQLite : domaine public) |
| PySide6 (Qt for Python) / Qt 6 | Interface graphique | LGPL v3 |
| pyqtgraph | Graphiques (frise des états, courbes) | MIT |
| NumPy (dépendance de pyqtgraph) | Calcul des tableaux de points des graphiques | BSD |
| tzdata | Fuseau horaire Europe/Zurich (heure suisse été/hiver sous Windows) | Apache 2.0 |
| PyInstaller | Construction de l'exécutable | GPL v2 avec exception pour les programmes construits |
| Inno Setup 6 | Construction de l'installateur | Licence Inno Setup (libre) |

**Qt / PySide6 (LGPL v3).** Les bibliothèques Qt sont livrées sous forme de fichiers séparés (DLL) dans le dossier d'installation. Elles ne sont pas modifiées et peuvent être remplacées par l'utilisateur. Les textes de licence et le code source de Qt sont disponibles sur https://www.qt.io/licensing et https://code.qt.io. Le module Qt Charts (non disponible sous LGPL) n'est pas utilisé.
