# 04 — Page 2 : Visualisation et exports

Onglet « 2. Configuration générée ». **Lecture seule.** Il présente le résultat comme le logiciel ELPRO CConfig (arbre à gauche, détail à droite) et permet d'exporter les fichiers.

Tant qu'aucun plan n'existe (pas encore généré, ou page 1 modifiée depuis) : afficher au centre « Aucune configuration générée. Remplir la page 1 puis cliquer sur Générer la configuration. » et griser les 4 boutons.

## Disposition

```
┌─ Arbre ──────────────┬─ Contenu du nœud sélectionné ───────────────────────┐
│ ▾ Demo Site A        │                                                       │
│    IP Address List   │   formulaire (libellé : valeur)                       │
│   ▾ Units            │   ou un ou plusieurs tableaux                         │
│     ▾ A-BASE         │                                                       │
│        Mappings      │                                                       │
│       ▾ Networking   │                                                       │
│          Time Server │                                                       │
│        RS232 …       │                                                       │
├──────────────────────┴───────────────────────────────────────────────────────┤
│ [Générer le .cdb] [Générer les .sconf] [Compte rendu PDF] [Liste d'adresses Excel] │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Construction de l'arbre

`noeuds = V.vue_page2(plan)` renvoie une liste ordonnée de nœuds :

```python
{'chemin': ['Demo Site A', 'Units', 'A-BASE', 'Mappings'],
 'type': 'formulaire' | 'tables',
 'contenu': ...}
```

- Créer un élément d'arbre (`QTreeWidget`) par nœud, en respectant `chemin` (les parents intermédiaires sans contenu, comme `Units`, sont créés vides). Conserver l'ordre de la liste.
- Si le chemin contient `Units`, n'ouvrir au démarrage que la première radio.
- Sélection d'un nœud :
  - `type == 'formulaire'` : `contenu` = liste de couples `(libellé, valeur)` → `QFormLayout` de `QLabel` non éditables (valeur sélectionnable à la souris pour copier) ;
  - `type == 'tables'` : `contenu` = liste de `{'titre', 'colonnes', 'lignes'}` → pour chacune, un titre en gras puis un `QTableWidget` en lecture seule (`NoEditTriggers`), colonnes redimensionnées au contenu, en-têtes = `colonnes`, une ligne par élément de `lignes`.
- Aucune autre transformation des valeurs : afficher `str(valeur)`.

## Boutons d'export

Tous ouvrent une boîte « Enregistrer sous » / « Choisir un dossier » qui propose par défaut le dernier dossier utilisé et le nom indiqué. Après succès : message « Fichier créé : <chemin> » avec un bouton « Ouvrir le dossier ».

| Bouton | Dialogue | Nom proposé | Appel |
|---|---|---|---|
| Générer le .cdb | Enregistrer sous, filtre `*.cdb` | `M.base_nom_fichier(plan) + '.cdb'` (ex. `Demo_Site_A_V2.1.cdb`) | `M.ecrire_cdb(plan, chemin)` |
| Générer les .sconf | Choisir un dossier | un fichier par radio ayant `S['iop']` non vide : `IOPlus_<nom radio>_V<version>_DESACTIVE.sconf` (ex. `IOPlus_A-BASE_V2.1_DESACTIVE.sconf`) | pour chaque `S` de `plan['stations']` avec `S['iop']` : `M.ecrire_sconf(S['iop'], os.path.join(dossier, nom))`. Afficher ensuite la liste des fichiers créés. La base en a toujours un ; une remote/un repeater seulement s'il a un radar. |
| Compte rendu PDF | Enregistrer sous, `*.pdf` | `M.base_nom_fichier(plan) + '_Compte_rendu.pdf'` | `PDF.ecrire_pdf(V.donnees_pdf(plan), chemin, f"{plan['systeme']['nom_projet']} — V{plan['version_config']}")` |
| Liste d'adresses Excel | Enregistrer sous, `*.xlsx` | `M.base_nom_fichier(plan) + '_Adresses.xlsx'` | `XL.ecrire_excel(V.donnees_excel(plan), chemin, f"{plan['systeme']['nom_projet']} — V{plan['version_config']}")` |

Si l'écriture échoue (fichier ouvert dans Excel, droits…) : afficher le message de l'exception, ne rien faire d'autre.

## Contenu des exports (déjà produit par le moteur — pour information)

- **Excel**, 3 onglets : `Registres base` (adresse, nom, type, station, description), `Radios` (index, nom, rôle, UID, IP, amont, puissance, MAINV, titre), `Câblage` (chaque DI/DO/AI de chaque radio, périphérique, registre de la base, inversion).
- **PDF** (A4 paysage) : page de titre, 1. Synthèse du système (paramètres, topologie, grille de polling), 2. Détail par radio (réglages, câblage, mappings), 3. Plan de registres, 4. Checklist de mise en service (cases à cocher).

Seule la **mise en forme** de `export_excel.py` / `export_pdf.py` peut être retouchée (couleurs, largeurs, logo GeoAzimut en en-tête si fourni). Le contenu vient de `views.py` et ne doit pas changer.
