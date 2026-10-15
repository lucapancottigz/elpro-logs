<p align="center">
  <img src="resources/app_icon.png" alt="Logo GeoAzimut" width="110">
</p>

<h1 align="center">ELPRO Config</h1>

<p align="center">
  Génération automatique de configurations standardisées pour les radios <b>ELPRO 415U-2-C4</b>.
</p>

<p align="center">
  <a href="https://github.com/lucapancottigz/elpro-config/releases/latest/download/ELPRO_Config_Setup.exe">
    <img src="https://img.shields.io/badge/T%C3%A9l%C3%A9charger-Windows%20(64%20bits)-0a7bbb?style=for-the-badge&logo=windows" alt="Télécharger pour Windows">
  </a>
</p>

<p align="center">
  <a href="https://github.com/lucapancottigz/elpro-config/releases/latest"><img src="https://img.shields.io/github/v/release/lucapancottigz/elpro-config?label=version" alt="Dernière version"></a>
  <img src="https://img.shields.io/badge/plateforme-Windows%2010%20%7C%2011-blue" alt="Windows 10 | 11">
  <a href="https://github.com/lucapancottigz/elpro-config/releases"><img src="https://img.shields.io/github/downloads/lucapancottigz/elpro-config/total?label=t%C3%A9l%C3%A9chargements" alt="Téléchargements"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/licence-propri%C3%A9taire-red" alt="Licence propriétaire"></a>
</p>

---

**ELPRO Config** décrit un réseau radio (radios, rôles, périphériques câblés) et produit en un clic tous les fichiers de mise en service selon le standard de configuration GeoAzimut : plan de registres, polling, fail-safe et logique IO Plus.

![Page 1 — saisie du projet](docs/images/page_config.png)

![Page 2 — configuration générée](docs/images/page_result.png)

## Fonctionnalités

- **Saisie du projet** : système, radios (base, remotes, repeaters), amonts, adresses IP et périphériques câblés (câbles, lidars, feux, sirènes, radars…).
- **Plan de registres standard** calculé automatiquement : détections, comflags, registres de défaut, tensions, RSSI, commandes.
- **Version de configuration** `X.Y` incrémentée automatiquement à chaque génération (majeure : radio ou périphérique ajouté/supprimé ; mineure : autre changement), reprise dans le nom de tous les fichiers générés.
- **Polling et fail-safe** : grille de polling régulière, fail-safe sur tous les registres de défaut.
- **Visualisation** de la configuration générée, présentée comme dans le logiciel CConfig.
- **Exports** :
  - fichier projet `.cdb` à ouvrir dans CConfig ;
  - logiques IO Plus `.sconf` (livrées **désactivées**) ;
  - compte rendu PDF ;
  - liste d'adresses Excel.
- **Import** d'un `.cdb` existant (radios, rôles, IP, amonts, clé).
- **Projets** enregistrés au format `.elpro.json`.

## Installation

1. Cliquer sur le bouton **Télécharger** ci-dessus, ou aller dans [Releases](https://github.com/lucapancottigz/elpro-config/releases/latest).
2. Lancer `ELPRO_Config_Setup.exe`. Des droits administrateur sont demandés, car l'application est installée pour tous les utilisateurs du PC.
3. Choisir les raccourcis (bureau, menu Démarrer), puis installer.

> **Avertissement Windows SmartScreen** — L'installateur n'est pas signé numériquement. Windows peut afficher « Windows a protégé votre ordinateur ». Cliquer sur **Informations complémentaires**, puis sur **Exécuter quand même**. Vous pouvez vérifier le fichier téléchargé avec l'empreinte SHA-256 publiée dans la release.

**Configuration requise :** Windows 10 ou 11, 64 bits. Python n'est pas nécessaire.

**Désinstallation :** Paramètres › Applications › ELPRO Config › Désinstaller. Vos projets dans `Documents\ELPRO Config` sont conservés.

## Démarrage rapide

1. Ouvrir un exemple : **Ouvrir** › `examples\demo_site_A.json`.
2. Onglet 1 : vérifier les radios et leurs périphériques.
3. Cliquer sur **Générer la configuration**.
4. Onglet 2 : parcourir le résultat, puis exporter le `.cdb`, les `.sconf`, le PDF et l'Excel.
5. Ouvrir le `.cdb` dans CConfig et programmer les radios.

Les exemples `demo_site_A` et `demo_site_B` sont des sites **fictifs**. `demo_site_B` contient un radar.

## Documentation

| Document | Contenu |
|---|---|
| [Lisez-moi technique](docs/00_LISEZMOI.md) | Organisation du projet et règles de travail |
| [Architecture](docs/01_Architecture.md) | Moteur, interface, exports |
| [Page 1 — Configuration](docs/02_Page1_Configuration.md) | Saisie du projet |
| [Modèle de données](docs/03_Modele_de_donnees.md) | Format `.elpro.json` |
| [Page 2 — Visualisation](docs/04_Page2_Visualisation.md) | Résultat et exports |
| [Recette](docs/05_Recette.md) | Tests de validation |
| [Historique des versions](CHANGELOG.md) | Nouveautés de chaque version |

## Développement

Prérequis : Python 3.11, et Inno Setup 6 pour l'installateur.

```bat
py -3.11 -m venv venv
.\venv\Scripts\pip install -r requirements.txt
.\venv\Scripts\python.exe app.py
```

| Commande | Rôle |
|---|---|
| `.\venv\Scripts\python.exe -m unittest discover -s tests -v` | Tests du moteur |
| `.\venv\Scripts\python.exe tests\ui_acceptance.py` | Recette de l'interface |
| `.\build.bat` | Tests, exécutable, puis installateur dans `dist\` |

## Avertissement

Ce projet est un outil indépendant développé par Geoazimut SàRL. Il n'est ni affilié à ELPRO Technologies ni approuvé par ELPRO Technologies. ELPRO, 415U et CConfig sont des marques de leurs propriétaires respectifs.

Les fichiers générés doivent être vérifiés par une personne qualifiée avant leur mise en service. Les logiques IO Plus sont livrées désactivées : il faut les activer volontairement sur chaque radio.

## Licence

**© 2026 [Geoazimut SàRL](https://geoazimut.com). Tous droits réservés.**

L'application compilée peut être téléchargée et utilisée gratuitement. Le code source est publié pour consultation uniquement : toute copie, modification ou redistribution nécessite l'autorisation écrite de Geoazimut SàRL. Voir [LICENSE](LICENSE). Composants tiers : voir [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

---

<p align="center">© 2026 <a href="https://geoazimut.com">Geoazimut SàRL</a> · Tous droits réservés</p>
