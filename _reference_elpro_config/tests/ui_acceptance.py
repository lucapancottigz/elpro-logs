# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""Recette automatisée de l'interface (complément de test_engine.py, ne remplace pas la recette manuelle).
Lancer depuis le dossier livrable :  python tests/ui_acceptance.py
Pilote les vrais widgets en mode hors écran ; les boîtes de dialogue sont simulées."""
import os, re, sys, json, tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.join(ICI, '..')
sys.path.insert(0, RACINE)
sys.path.insert(0, os.path.join(RACINE, 'engine'))

from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog, QDialog  # noqa: E402
from PySide6.QtCore import QSettings  # noqa: E402

import elpro_engine as M  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui import dialogs  # noqa: E402
from version import APP_VERSION  # noqa: E402
from PySide6.QtCore import QStandardPaths  # noqa: E402

MESSAGES = []
REPONSES = {'fichier': None, 'dossier': None, 'question': QMessageBox.Yes}


def _msg(kind):
    def f(parent, titre, texte, *a, **k):
        MESSAGES.append((kind, titre, texte))
        return REPONSES['question'] if kind == 'question' else QMessageBox.Ok
    return f


sys.stdout.reconfigure(encoding='utf-8')
QMessageBox.warning = staticmethod(_msg('warning'))
QMessageBox.critical = staticmethod(_msg('critical'))
QMessageBox.information = staticmethod(_msg('information'))
QMessageBox.question = staticmethod(_msg('question'))
QMessageBox.exec = lambda self: MESSAGES.append(('box', self.windowTitle(), self.text())) or 0
PROPOSES = []          # nom de fichier proposé par chaque « Enregistrer sous »
DOSSIERS_PROPOSES = []  # dossier proposé par chaque « Enregistrer sous »


def _enregistrer_sous(parent, titre, propose, *a, **k):
    PROPOSES.append(os.path.basename(propose))
    DOSSIERS_PROPOSES.append(os.path.dirname(propose))
    return REPONSES['fichier'], ''


QFileDialog.getSaveFileName = staticmethod(_enregistrer_sous)
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (REPONSES['fichier'], ''))
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: REPONSES['dossier'])

ECHECS = []


def verifier(cond, libelle):
    print(('  OK   ' if cond else '  ÉCHEC ') + libelle)
    if not cond:
        ECHECS.append(libelle)


def dernier(kind=None):
    return next((m for m in reversed(MESSAGES) if kind is None or m[0] == kind), None)


def main():
    app = QApplication(sys.argv)
    QSettings.setDefaultFormat(QSettings.IniFormat)
    app.setOrganizationName('GeoAzimut-Recette'); app.setApplicationName('ELPRO Config Recette')
    tmp = tempfile.mkdtemp(prefix='elpro_recette_')
    F = MainWindow(RACINE)
    p1, p2 = F.page_config, F.page_result
    ex = os.path.join(RACINE, 'examples')

    print('Page 1')
    F.ouvrir_fichier(os.path.join(ex, 'demo_site_A.json'))
    verifier(p1.tab_radios.rowCount() == 6, 'demo_site_A : 6 radios')
    verifier(p1.sys['nom_projet'].text() == 'Demo Site A', 'demo_site_A : nom du projet affiché')
    verifier(F.windowTitle() == f'ELPRO Config {APP_VERSION} — demo_site_A.json[*]' and not F.isWindowModified(),
             'titre de fenêtre (avec la version)')
    for i in range(6):                      # parcourir toutes les radios ne doit rien modifier
        p1.tab_radios.selectRow(i)
    verifier(not F.isWindowModified(), 'parcourir les radios ne marque pas le projet modifié')
    REPONSES['fichier'] = os.path.join(tmp, 'demo_A_copie.elpro.json')
    F.enregistrer_sous()
    orig = json.load(open(os.path.join(ex, 'demo_site_A.json'), encoding='utf-8'))
    copie = json.load(open(REPONSES['fichier'], encoding='utf-8'))
    verifier(orig == copie, 'Enregistrer sous : JSON identique')
    with open(os.path.join(ex, 'demo_site_B.json'), encoding='utf-8') as f:
        fr_orig = json.load(f)
    F.ouvrir_fichier(os.path.join(ex, 'demo_site_B.json'))
    for i in range(p1.tab_radios.rowCount()):
        p1.tab_radios.selectRow(i)
    REPONSES['fichier'] = os.path.join(tmp, 'demo_B_copie.elpro.json')
    F.enregistrer_sous()
    verifier(json.load(open(REPONSES['fichier'], encoding='utf-8')) == fr_orig, 'demo_site_B : JSON identique')

    F.nouveau()
    verifier(len(p1.projet['radios']) == 1 and p1.projet['radios'][0]['nom'] == 'CA'
             and p1.projet['radios'][0]['role'] == 'base', 'Nouveau : une base CA seule')
    verifier(len(p1.projet['systeme']['cle_chiffrement']) == 24, 'Nouveau : clé de 24 caractères')
    verifier(p1.projet['radios'][0]['ip_octet'] == 100 and p1.projet['radios'][0]['mainv'] == {'actif': True, 'di': 8},
             'Nouveau : IP .100, MAINV DI8')
    for _ in range(16):
        p1.bt_ajouter.click()
    verifier(len(p1.projet['radios']) == 17, '17 radios ajoutées')
    verifier([r['ip_octet'] for r in p1.projet['radios']] == list(range(100, 117)), 'IP par défaut 101, 102…')
    MESSAGES.clear()
    p1.bt_ajouter.click()
    verifier(len(p1.projet['radios']) == 17 and dernier('warning') is not None, '18e radio refusée avec message')

    # DI occupée grisée
    F.ouvrir_fichier(os.path.join(ex, 'demo_site_A.json'))
    p1.tab_radios.selectRow(1)          # A-SM1 : CABLE1 sur DI1
    d = dialogs.DialoguePeripherique(p1, p1.projet, p1.radio_courante())
    dialogs.choisir(d.cb_type, 'CABLE')
    cb = d.champs['di0']
    it = cb.model().item(cb.findData(1))
    verifier(not it.isEnabled() and '(CABLE1)' in it.text(), 'DI1 occupée grisée avec le nom de l\'occupant')
    it8 = cb.model().item(cb.findData(8))
    verifier(not it8.isEnabled() and '(MAINV)' in it8.text(), 'DI8 occupée par MAINV')
    verifier(d.ed_nom.text() == 'CABLE3', 'nom proposé CABLE3')
    verifier(d.cb_type.findData('RADAR') >= 0, 'Radar proposé sur une remote')
    p1.tab_radios.selectRow(0)
    db = dialogs.DialoguePeripherique(p1, p1.projet, p1.radio_courante())
    verifier(db.cb_type.findData('RADAR') >= 0 and db.cb_type.count() == len(dialogs.LIBELLES),
             'base : tous les types proposés, Radar compris')
    dialogs.choisir(db.cb_type, 'FEU')
    verifier(db.ed_nom.text() == 'F4', 'feu : nom F4 (numérotation sur le site)')
    libelles = [db.form.labelForField(db.champs[k]).text() for k in ('do_rouge', 'do_orange_cli', 'do_orange_fixe', 'do_vert')]
    verifier(libelles == ['Sortie rouge', 'Sortie orange clignotant', 'Sortie orange fixe', 'Sortie verte'],
             'feu : 4 listes rouge, orange clignotant, orange fixe, verte')
    verifier([db.champs[k].currentData() for k in ('do_rouge', 'do_orange_cli', 'do_orange_fixe', 'do_vert')]
             == [1, 2, None, None], 'feu : proposé rouge DO1, orange clignotant DO2, orange fixe et vert « aucune »')
    verifier(all(db.champs[k].itemText(0) == 'aucune' for k in ('do_rouge', 'do_orange_cli', 'do_orange_fixe', 'do_vert')),
             'feu : choix « aucune » sur les 4 listes')
    dialogs.choisir(db.champs['do_orange_fixe'], 3); dialogs.choisir(db.champs['do_vert'], 4)
    pf = db.peripherique()
    verifier(pf == {'type': 'FEU', 'nom': 'F4', 'do_rouge': 1, 'do_orange_cli': 2, 'do_orange_fixe': 3, 'do_vert': 4},
             'feu : périphérique à 4 sorties')
    verifier(dialogs.texte_cablage(pf) == 'R DO1 · OC DO2 · OF DO3 · V DO4', 'feu : câblage « R DO1 · OC DO2 · OF DO3 · V DO4 »')
    verifier(dialogs.texte_cablage(dict(pf, do_orange_cli=None, do_vert=None)) == 'R DO1 · OF DO3',
             'feu : câblage limité aux sorties utilisées')
    dialogs.choisir(db.cb_type, 'LIDAR6')
    verifier([db.champs[f'di{k}'].currentData() for k in range(6)] == [1, 2, 3, 4, 5, 6], 'Lidar 6 : DI1–DI6 proposées')
    dialogs.choisir(db.champs['premiere'], 2)
    verifier([db.champs[f'di{k}'].currentData() for k in range(6)] == [2, 3, 4, 5, 6, 7], 'Lidar 6 : suite recalculée')

    # ajout de périphérique via la page, puis JSON forcé en doublon
    p1.tab_radios.selectRow(1)
    orig_exec = dialogs.DialoguePeripherique.exec
    dialogs.DialoguePeripherique.exec = lambda self: QDialog.Accepted
    p1._ajouter_periph()
    dialogs.DialoguePeripherique.exec = orig_exec
    verifier(p1.projet['radios'][1]['peripheriques'][-1] == {'type': 'CABLE', 'nom': 'CABLE3', 'di': [6]},
             'ajout d\'un câble sur la première DI libre (DI6)')
    verifier(F.isWindowModified() and 'erreur' not in F.etat.text(), 'projet modifié, toujours valide')
    p1.projet['radios'][1]['peripheriques'].append({'type': 'CABLE', 'nom': 'X', 'di': [1]})
    MESSAGES.clear()
    F.generer()
    m = dernier('warning')
    verifier(m and m[1] == 'Configuration incomplète' and 'DI1 déjà utilisée' in m[2] and F.onglets.currentIndex() == 0,
             'DI forcée en double : erreur du moteur, reste en page 1')

    # renommer un amont
    F.ouvrir_fichier(os.path.join(ex, 'demo_site_A.json'))
    p1.tab_radios.selectRow(5)          # A-RR
    p1.ed_nom.setText('A-REP'); p1.ed_nom.editingFinished.emit()
    verifier(all(r['amont'] == 'A-REP' for r in p1.projet['radios'][1:5]), 'renommer un repeater : les radios aval suivent')
    verifier(p1.tab_radios.item(1, 4).text() == 'A-REP', 'tableau mis à jour')
    REPONSES['question'] = QMessageBox.Yes
    p1.tab_radios.selectRow(5)
    p1.bt_supprimer.click()
    verifier(len(p1.projet['radios']) == 5 and all(r['amont'] == 'A-BASE' for r in p1.projet['radios'][1:]),
             'supprimer un repeater : radios aval sur la base')
    p1.tab_radios.selectRow(0)
    verifier(not p1.bt_supprimer.isEnabled() and not p1.bt_monter.isEnabled() and not p1.bt_descendre.isEnabled(),
             'base : suppression et déplacement interdits')
    p1.tab_radios.selectRow(1)
    verifier(not p1.bt_monter.isEnabled() and p1.bt_descendre.isEnabled(), 'position 2 : ▲ grisé')
    p1.bt_descendre.click()
    verifier(p1.projet['radios'][2]['nom'] == 'A-SM1' and p1.index_courant() == 2, '▼ déplace la radio')

    # projet invalide
    F.nouveau() if not F.isWindowModified() else None
    REPONSES['question'] = QMessageBox.Discard
    F.nouveau()
    p1.sys['system_name'].setText(''); p1.sys['system_name'].textEdited.emit('')
    MESSAGES.clear(); F.generer()
    verifier(dernier('warning') and dernier('warning')[1] == 'Configuration incomplète' and F.onglets.currentIndex() == 0,
             'projet invalide : erreurs listées, reste en page 1')
    verifier('erreur' in F.etat.text(), 'barre d\'état : nombre d\'erreurs')

    print('Recette 1 — corrections C1 à C4')
    # C1 : le projet est toujours enregistré en .elpro.json
    F.ouvrir_fichier(os.path.join(ex, 'demo_site_A.json'))
    PROPOSES.clear()
    REPONSES['fichier'] = os.path.join(tmp, 'demo_A_test.json')      # ce que Qt renvoie avec le filtre par défaut
    F.enregistrer_sous()
    verifier(PROPOSES == ['Demo_Site_A.elpro.json'], 'C1 : nom proposé Demo_Site_A.elpro.json')
    verifier(os.path.exists(os.path.join(tmp, 'demo_A_test.elpro.json'))
             and not os.path.exists(os.path.join(tmp, 'demo_A_test.json')), 'C1 : « demo_A_test » → demo_A_test.elpro.json')
    REPONSES['fichier'] = os.path.join(tmp, 'demo_A_t2')
    F.enregistrer_sous()
    verifier(os.path.exists(os.path.join(tmp, 'demo_A_t2.elpro.json')), 'C1 : sans extension → .elpro.json ajouté')
    REPONSES['fichier'] = os.path.join(tmp, 'demo_A_t3.elpro.json')
    F.enregistrer_sous()
    verifier(os.path.exists(os.path.join(tmp, 'demo_A_t3.elpro.json')), 'C1 : .elpro.json conservé tel quel')

    def role(i, r):
        p1.tab_radios.selectRow(i)
        dialogs.choisir(p1.cb_role, r)
        p1.cb_role.activated.emit(p1.cb_role.currentIndex())

    def renommer(i, nom):
        p1.tab_radios.selectRow(i)
        p1.ed_nom.setText(nom)
        p1.ed_nom.editingFinished.emit()

    # C2 : renommage appliqué en fin de saisie, amonts et tableau complet mis à jour
    REPONSES['question'] = QMessageBox.Discard
    F.nouveau()
    p1.bt_ajouter.click(); p1.bt_ajouter.click()            # RADIO2, RADIO3
    role(1, 'repeater')
    p1.tab_radios.selectRow(2)
    dialogs.choisir(p1.cb_amont, 'RADIO2'); p1.cb_amont.activated.emit(p1.cb_amont.currentIndex())
    verifier(p1.projet['radios'][2]['amont'] == 'RADIO2', 'C2 : RADIO3 a pour amont RADIO2')
    p1.tab_radios.selectRow(1)
    p1.ed_nom.setText('R')                                  # frappe en cours : rien n'est encore appliqué
    verifier(p1.projet['radios'][1]['nom'] == 'RADIO2', 'C2 : pas de renommage à chaque frappe')
    renommer(1, 'RR')
    verifier(p1.projet['radios'][1]['nom'] == 'RR' and p1.projet['radios'][2]['amont'] == 'RR', 'C2 : RADIO2 → RR, amont suivi')
    verifier(p1.tab_radios.item(2, 4).text() == 'RR', 'C2 : colonne Amont de RADIO3 = RR')
    p1.tab_radios.selectRow(2)
    verifier(p1.cb_amont.currentData() == 'RR' and p1.cb_amont.currentText() == 'RR', 'C2 : liste Amont de RADIO3 = RR')
    MESSAGES.clear()
    renommer(1, 'CA')
    verifier(p1.projet['radios'][1]['nom'] == 'RR' and p1.ed_nom.text() == 'RR'
             and dernier('warning') and dernier('warning')[2] == 'Nom vide ou déjà utilisé', 'C2 : nom déjà pris refusé')
    MESSAGES.clear()
    renommer(1, '')
    verifier(p1.projet['radios'][1]['nom'] == 'RR' and dernier('warning'), 'C2 : nom vide refusé')

    # C4 : IP automatique selon le rôle
    F.nouveau()
    p1.bt_ajouter.click()                                   # RADIO2 .101
    role(1, 'repeater')
    verifier(p1.projet['radios'][1]['ip_octet'] == 120 and p1.sp_ip.value() == 120
             and p1.tab_radios.item(1, 3).text() == '192.168.1.120', 'C4 : RADIO2 en Repeater → .120 (champ et tableau)')
    p1.bt_ajouter.click()                                   # RADIO3 : plus petite IP libre ≥ 101
    ip3 = p1.projet['radios'][2]['ip_octet']
    role(2, 'repeater')
    verifier(p1.projet['radios'][2]['ip_octet'] == 121, 'C4 : RADIO3 en Repeater → .121')
    role(2, 'remote')
    verifier(p1.projet['radios'][2]['ip_octet'] == 101 == ip3, 'C4 : RADIO3 repasse en Remote → plus petite libre ≥ 101 (.101)')
    p1.tab_radios.selectRow(2)
    p1.sp_ip.setValue(150)
    verifier(p1.projet['radios'][2]['ip_octet'] == 150, 'C4 : IP modifiable ensuite à la main')

    print('Installation dans Program Files')
    # F.base (racine du dépôt) joue le rôle du dossier d'installation, non inscriptible une fois installé
    docs = os.path.join(QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation), 'ELPRO Config')
    demo_a = os.path.join(ex, 'demo_site_A.json')
    avant = os.path.getmtime(demo_a)
    F.ouvrir_fichier(demo_a)
    DOSSIERS_PROPOSES.clear()
    REPONSES['fichier'] = ''                                 # l'utilisateur annule la boîte de dialogue
    F.enregistrer()
    verifier(DOSSIERS_PROPOSES and os.path.normcase(DOSSIERS_PROPOSES[-1]) == os.path.normcase(docs),
             'Enregistrer un exemple : dossier proposé Documents\\ELPRO Config')
    verifier(os.path.isdir(docs), 'Documents\\ELPRO Config créé')
    verifier(os.path.getmtime(demo_a) == avant, 'exemple du dossier d\'installation non réécrit')
    DOSSIERS_PROPOSES.clear()
    F.nouveau() if not F.isWindowModified() else None
    REPONSES['question'] = QMessageBox.Discard
    F.nouveau()
    F.enregistrer_sous()
    verifier(DOSSIERS_PROPOSES and os.path.normcase(DOSSIERS_PROPOSES[-1]) == os.path.normcase(docs),
             'Nouveau projet : Enregistrer sous propose Documents\\ELPRO Config')
    hors = os.path.join(tmp, 'demo_A_test.elpro.json')        # fichier hors installation : réécrit sur place
    F.ouvrir_fichier(hors)
    DOSSIERS_PROPOSES.clear()
    verifier(F.enregistrer() and not DOSSIERS_PROPOSES, 'fichier hors installation : Enregistrer sans boîte de dialogue')

    print('Mentions légales')
    from PySide6.QtWidgets import QLabel
    from version import APP_COPYRIGHT, APP_WEBSITE
    ouvertes = []
    exec_dialog = QDialog.exec
    QDialog.exec = lambda self: ouvertes.append(self) or 0    # fenêtres modales simulées
    F.action_a_propos.trigger()
    apropos = next((d for d in ouvertes if isinstance(d, dialogs.AboutDialog)), None)
    verifier(apropos is not None, 'À propos : la fenêtre s\'ouvre (bouton « ? »)')
    textes = [l.text() for l in apropos.findChildren(QLabel)] if apropos else []
    verifier(any(t == APP_COPYRIGHT for t in textes), 'À propos : contient APP_COPYRIGHT')
    verifier(any(f'href="{APP_WEBSITE}"' in t for t in textes) and apropos.lien.openExternalLinks(),
             'À propos : lien cliquable vers https://geoazimut.com')
    verifier(any(APP_VERSION in t for t in textes), 'À propos : contient APP_VERSION')
    for titre in ('Licence', 'Composants tiers'):
        ouvertes.clear(); MESSAGES.clear()
        apropos.afficher_fichier(titre)
        verifier(len(apropos.texte_fichier(titre)) > 100 and ouvertes and not dernier('warning'),
                 f'À propos : bouton « {titre} » trouve son fichier, non vide')
    QDialog.exec = exec_dialog
    verifier('Geoazimut SàRL' in F.mention.text() and 'geoazimut.com' in F.mention.text()
             and F.mention.parent() is not None, 'Barre d\'état : « © 2026 Geoazimut SàRL — geoazimut.com »')

    print('Page 2')

    def tableau_base():
        """Tags du tableau de bord de la base et contrôle « une seule commande par genre »."""
        B = p2.plan['stations'][0]
        genres = {}
        for S in p2.plan['stations']:
            for c in S['commandes']:
                genres.setdefault(c['genre'], c['nom'])      # première commande de chaque genre, ordre du site
        cmd = [t['nom'] for t in B['tags'] if 401 <= t['registre'] <= 450]
        return B['tags'], dict(B['groupes']), cmd == list(genres.values())
    F.ouvrir_fichier(os.path.join(ex, 'demo_site_A.json'))
    MESSAGES.clear()
    F.generer()
    verifier(F.onglets.currentIndex() == 1 and p2.plan is not None, 'demo_site_A généré, page 2 affichée')
    verifier(not any(m[1] == 'Configuration générée avec des remarques' for m in MESSAGES),
             'demo_site_A : pas de boîte de remarques')
    tags, groupes, un_par_genre = tableau_base()
    verifier(len(tags) == 36 and un_par_genre and groupes.get('Status - RSSI') == 5
             and sum(t['unites'] == 'dBm' for t in tags) == 5,
             'demo_site_A : tableau de bord de la base, 36 éléments, une commande par genre, RSSI présents')
    racine = p2.arbre.topLevelItem(0)
    noms = [racine.child(i).text(0) for i in range(racine.childCount())]
    verifier(racine.text(0) == 'Demo Site A' and noms == ['IP Address List', 'Units'], 'arbre racine')
    units = racine.child(1)
    verifier(units.child(0).text(0) == 'A-BASE' and units.child(0).child(0).text(0) == 'Mappings', 'A-BASE / Mappings')
    verifier(units.child(0).isExpanded() and not units.child(1).isExpanded(), 'seule la première radio est ouverte')
    maps = p2.noeuds[('Demo Site A', 'Units', 'A-BASE', 'Mappings')]['contenu'][0]['lignes']
    verifier(sum(l[1] == 'Read' for l in maps) == 16 and sum(l[1] == 'Gather/Scatter' for l in maps) == 5,
             'Mappings A-BASE : 16 lectures + 5 scatters')
    verifier(any('440 s' in str(v) for _l, v in p2.noeuds[('Demo Site A',)]['contenu']), 'cycle de polling 440 s')
    p2.arbre.setCurrentItem(units.child(0).child(0))       # affiche un nœud « tables »
    p2.arbre.setCurrentItem(units.child(0))                # affiche un nœud « formulaire »
    verifier(all(b.isEnabled() for b in p2.boutons), 'boutons d\'export actifs')

    PROPOSES.clear()
    REPONSES['fichier'] = os.path.join(tmp, 'demo_A.cdb'); p2._export_cdb()
    REPONSES['fichier'] = os.path.join(tmp, 'demo_A.pdf'); p2._export_pdf()
    REPONSES['fichier'] = os.path.join(tmp, 'demo_A.xlsx'); p2._export_excel()
    d_gl = os.path.join(tmp, 'sconf_demo_a'); os.makedirs(d_gl); REPONSES['dossier'] = d_gl; p2._export_sconf()
    verifier(all(os.path.getsize(os.path.join(tmp, f)) > 0 for f in ('demo_A.cdb', 'demo_A.pdf', 'demo_A.xlsx')),
             '.cdb, PDF et Excel créés')
    verifier(PROPOSES == ['Demo_Site_A_V1.0.cdb', 'Demo_Site_A_V1.0_Compte_rendu.pdf', 'Demo_Site_A_V1.0_Adresses.xlsx'],
             'noms proposés Demo_Site_A_V1.0.cdb / _Compte_rendu.pdf / _Adresses.xlsx')
    verifier(sorted(os.listdir(d_gl)) == ['IOPlus_A-BASE_V1.0_DESACTIVE.sconf'], 'demo_site_A : 1 .sconf (base)')
    verifier(dernier('box') and 'Fichiers créés' in dernier('box')[2], 'message de succès')

    # Excel verrouillé -> message propre
    import builtins
    MESSAGES.clear()
    import export_excel
    vrai = export_excel.Workbook.save
    export_excel.Workbook.save = lambda self, c: (_ for _ in ()).throw(PermissionError(13, 'Permission denied', c))
    p2._export_excel()
    export_excel.Workbook.save = vrai
    verifier(dernier('critical') and 'Permission denied' in dernier('critical')[2], 'fichier Excel ouvert : message d\'erreur')
    del builtins

    p1.tab_radios.selectRow(2)
    p1.ed_titre.setText('X'); p1.ed_titre.textEdited.emit('X')
    verifier(p2.plan is None and p2.arbre.topLevelItemCount() == 0 and not any(b.isEnabled() for b in p2.boutons)
             and not p2.bandeau.isHidden(), 'modifier la page 1 : page 2 vidée, boutons grisés, bandeau')

    F.ouvrir_fichier(os.path.join(ex, 'demo_site_B.json'))
    MESSAGES.clear()
    F.generer()
    m = dernier('information')
    verifier(m and m[1] == 'Configuration générée avec des remarques' and 'RSSI ont été retirés' in m[2]
             and F.onglets.currentIndex() == 1 and p2.plan is not None,
             'demo_site_B : boîte « Configuration générée avec des remarques » (RSSI retirés), génération valide')
    tags, groupes, un_par_genre = tableau_base()
    verifier(len(tags) == 49 <= 50 and un_par_genre and not any(t['unites'] == 'dBm' for t in tags)
             and list(groupes) == ['Alarmes', 'Radars', 'Signalisations', 'Status - MAINV', 'Status - BATTV', 'Status - FLAGC'],
             'demo_site_B : tableau de bord de la base, 49 éléments, une commande par genre, sans RSSI')
    d_fr = os.path.join(tmp, 'sconf_fr'); os.makedirs(d_fr); REPONSES['dossier'] = d_fr; p2._export_sconf()
    verifier(sorted(os.listdir(d_fr)) == ['IOPlus_B-BASE_V1.0_DESACTIVE.sconf', 'IOPlus_B-SM3_V1.0_DESACTIVE.sconf'],
             'demo_site_B : 2 .sconf (B-BASE et B-SM3)')
    cmd = {c['nom']: c['adresse'] for S in p2.plan['stations'] for c in S['commandes']}
    verifier([cmd.get(f'B-F3_F3_{c}') for c in ('ROUGE', 'OR_CLI', 'OR_FIXE', 'VERT')] == [403, 413, 423, 443],
             'demo_site_B : B-F3 commandes 403, 413, 423, 443')
    autres = sorted(a for n, a in cmd.items() if not n.endswith(('_ROUGE', '_OR_CLI', '_OR_FIXE', '_VERT')))
    verifier(autres == list(range(431, 438)), 'demo_site_B : autres signalisations en 431–437')
    verifier(cmd.get('CAMON_SPOTON') == 433 and cmd.get('SIRENE_FLASH') == 435,
             'demo_site_B : noms raccourcis CAMON_SPOTON (433) et SIRENE_FLASH (435)')
    noms = [n for S in p2.plan['stations'] for _a, n in S['noms_registres']] + \
           [t['nom'] for S in p2.plan['stations'] for t in S['tags']]
    verifier(noms and max(len(n) for n in noms) <= M.NOM_MAX == 16,
             'demo_site_B : noms de registres et de tags de 16 caractères au plus, toutes radios')
    dash = [l for ch, n in p2.noeuds.items() if ch[2:] == ('B-BASE', 'Dashboard') for t in n['contenu'] for l in t['lignes']]
    noms_dash = [str(c) for l in dash for c in l if isinstance(c, str)]
    verifier(dash and not any(re.fullmatch(r'D(In|Out)\d+', c) for c in noms_dash),
             'demo_site_B : tableau de bord de la base sans nom DIn… / DOut…')

    def echec(a):
        return 15200 <= int(a) <= 15799        # registres d'échec 152xx–157xx (15501 compris)
    import views
    noms_io = [l[2] for ch, n in p2.noeuds.items() if ch[-1:] == ('IO',) for t in n['contenu'] for l in t['lignes']]
    xl = next(o for o in views.donnees_excel(p2.plan) if o['onglet'] == 'Registres base')['lignes']
    pdf = [l[0] for sec in views.donnees_pdf(p2.plan) if sec['titre'].startswith('3.') for b in sec['blocs'] for l in b['lignes']]
    verifier(noms_io and xl and pdf and not any(echec(a) for a in [r['adresse'] for r in p2.plan['registres']] + noms_io
                                                 + [l[0] for l in xl] + pdf),
             'liste des registres (page 2 › IO, Excel, PDF) : aucun registre 152xx–157xx ni 15501')
    verifier(any(15101 <= int(a) <= 15199 for a in noms_io), 'liste des registres : comflags 151xx présents')

    print('Version de configuration')
    F.ouvrir_fichier(os.path.join(ex, 'demo_site_A.json'))
    verifier(p1.ed_version.text() == 'V1.0' and p1.ed_version.isReadOnly()
             and p1.lb_version.text() == 'Jamais générée — prochaine génération : V1.0', 'ouverture : V1.0, « Jamais générée »')
    F.generer()
    verifier(p1.projet['version_config'] == '1.0' and p1.lb_version.text() == 'À jour (dernière génération : V1.0)'
             and F.statusBar().currentMessage() == 'Configuration générée — version V1.0 (aucune modification)',
             'première génération : V1.0, « À jour »')
    verifier(F.isWindowModified(), 'après génération : projet à enregistrer (*)')
    F.generer()
    verifier(p1.projet['version_config'] == '1.0', 'générer sans modification : reste V1.0')
    p1.tab_radios.selectRow(2)
    p1.sp_ip.setValue(150)
    verifier(p1.lb_version.text() == 'Modification mineure — prochaine génération : V1.1', 'IP modifiée : libellé mineure V1.1')
    F.generer()
    verifier(p1.projet['version_config'] == '1.1' and p1.ed_version.text() == 'V1.1'
             and F.statusBar().currentMessage() == 'Configuration générée — version V1.1 (modification mineure)',
             'IP modifiée : V1.1')
    REPONSES['question'] = QMessageBox.Yes
    p1.tab_radios.selectRow(2)
    p1._supprimer_periph(1)
    REPONSES['question'] = QMessageBox.Discard
    verifier(p1.lb_version.text() == 'Modification majeure — prochaine génération : V2.0'
             and '#E67E00' in p1.lb_version.styleSheet(), 'périphérique supprimé : libellé majeure V2.0 (orange)')
    F.generer()
    verifier(p1.projet['version_config'] == '2.0'
             and F.statusBar().currentMessage() == 'Configuration générée — version V2.0 (modification majeure)',
             'périphérique supprimé : V2.0')
    p1.bt_ajouter.click()
    F.generer()
    verifier(p1.projet['version_config'] == '3.0', 'radio ajoutée : V3.0')
    nom = p1.projet['radios'][2]['nom']
    p1.projet['radios'][2]['nom'] = p1.projet['radios'][1]['nom']
    MESSAGES.clear()
    F.generer()
    verifier(dernier('warning') and 'même nom' in dernier('warning')[2] and p1.projet['version_config'] == '3.0',
             'projet invalide (deux radios de même nom) : erreur, version inchangée')
    p1.projet['radios'][2]['nom'] = nom
    REPONSES['fichier'] = os.path.join(tmp, 'version.elpro.json')
    F.enregistrer_sous()
    F.ouvrir_fichier(REPONSES['fichier'])
    verifier(p1.ed_version.text() == 'V3.0' and p1.lb_version.text() == 'À jour (dernière génération : V3.0)'
             and not F.isWindowModified(), 'enregistrer puis rouvrir : V3.0, « À jour »')
    F.generer()
    PROPOSES.clear()
    REPONSES['fichier'] = ''
    p2._export_cdb()
    verifier(PROPOSES == ['Demo_Site_A_V3.0.cdb'], 'export : nom du .cdb avec la version (V3.0)')
    p1.sys['nom_projet'].setText('Test é à ç'); p1.sys['nom_projet'].textEdited.emit('Test é à ç')
    F.generer()
    PROPOSES.clear()
    p2._export_cdb()
    verifier(PROPOSES == ['Test_e_a_c_V3.1.cdb'], 'accents retirés : « Test é à ç » → Test_e_a_c_V3.1.cdb')

    print('Feu à 4 sorties')
    with open(os.path.join(ex, 'demo_site_A.json'), encoding='utf-8') as f:
        ancien = json.load(f)
    for r in ancien['radios']:
        for pp in r['peripheriques']:
            if pp['type'] == 'FEU':
                pp['do_orange'] = pp.pop('do_orange_cli'); pp.pop('do_orange_fixe')
    ancien_ch = os.path.join(tmp, 'ancien.elpro.json')
    with open(ancien_ch, 'w', encoding='utf-8') as f:
        json.dump(ancien, f, ensure_ascii=False, indent=2)
    F.ouvrir_fichier(ancien_ch)
    verifier(F.isWindowModified() and p1.ed_version.text() == 'V1.0', 'ancien projet (do_orange) : titre avec *, version V1.0')
    p1.tab_radios.selectRow(2)                       # A-F1 : F1 rouge DO1, orange DO2
    d = dialogs.DialoguePeripherique(p1, p1.projet, p1.radio_courante(), 0)
    verifier(d.champs['do_orange_cli'].currentData() == 2 and d.champs['do_orange_fixe'].currentData() is None,
             'ancien projet : l\'orange s\'affiche en « orange clignotant » (DO2)')
    REPONSES['fichier'] = ancien_ch
    F.enregistrer()
    feux = [pp for r in json.load(open(ancien_ch, encoding='utf-8'))['radios'] for pp in r['peripheriques'] if pp['type'] == 'FEU']
    verifier(feux and all('do_orange' not in pp and pp['do_orange_cli'] == 2 for pp in feux),
             'ancien projet enregistré : do_orange_cli, plus de do_orange')
    p1.projet['radios'][2]['peripheriques'][0].update(do_orange_cli=None, do_orange_fixe=None)
    MESSAGES.clear()
    F.generer()
    verifier(dernier('warning') and 'au moins une sortie orange' in dernier('warning')[2], 'feu rouge seul : refusé par le moteur')
    p1.projet['radios'][2]['peripheriques'][0]['do_orange_fixe'] = 2
    MESSAGES.clear()
    F.generer()
    verifier(not dernier('warning') and p2.plan is not None, 'feu rouge + orange fixe : accepté')

    print('Périphériques sur la base')
    F.ouvrir_fichier(os.path.join(ex, 'demo_site_B.json'))
    p1.tab_radios.selectRow(0)
    dialogs.DialoguePeripherique.exec = lambda self: QDialog.Accepted
    orig_init = dialogs.DialoguePeripherique.__init__

    def init_radar(self, *a, **k):          # l'utilisateur choisit Radar sur AI1, seuil 500 cm
        orig_init(self, *a, **k)
        dialogs.choisir(self.cb_type, 'RADAR'); dialogs.choisir(self.champs['ai'], 1)
        self.champs['seuil_haut_ma'].setValue(500)
    dialogs.DialoguePeripherique.__init__ = init_radar
    p1._ajouter_periph()
    dialogs.DialoguePeripherique.__init__ = orig_init
    dialogs.DialoguePeripherique.exec = orig_exec
    radar = p1.projet['radios'][0]['peripheriques'][-1]
    verifier(radar['type'] == 'RADAR' and radar['ai'] == 1, 'radar ajouté sur la base (AI1)')
    verifier(radar.get('mesure_4ma') == 0 and radar.get('mesure_20ma') == 1000 and radar.get('unite') == 'cm'
             and radar['seuil_haut_ma'] == 12.0, 'radar : échelle 0–1000 cm par défaut, seuil 500 cm → seuil_haut_ma 12.0')
    verifier(p1.tab_periph.item(len(p1.projet['radios'][0]['peripheriques']) - 1, 2).text() == 'AI1 · 0–1000 cm · seuil 500 cm',
             'radar : câblage « AI1 · 0–1000 cm · seuil 500 cm »')
    MESSAGES.clear()
    F.generer()
    reg = {r['adresse']: r for r in p2.plan['registres']}
    verifier(not dernier('warning') and 35201 in reg and reg[35201]['station'] == 'B-BASE',
             'radar sur la base : pas d\'erreur, registre 35201 au nom de la base')
    d_rb = os.path.join(tmp, 'sconf_radar_base'); os.makedirs(d_rb); REPONSES['dossier'] = d_rb; p2._export_sconf()
    verifier(len(os.listdir(d_rb)) == 2, 'radar sur la base : toujours 2 fichiers .sconf')
    tag = next((t for t in p2.plan['stations'][0]['tags'] if t['registre'] == 35201), None)
    verifier(tag and tag['unites'] == 'cm' and tag['haut'] == 500, 'radar : tag 35201 de la base en cm, alarme haute 500')

    print('Échelle du radar')
    sm3 = next(i for i, r in enumerate(p1.projet['radios']) if r['nom'] == 'B-SM3')
    p1.tab_radios.selectRow(sm3)
    k = next(i for i, x in enumerate(p1.radio_courante()['peripheriques']) if x['type'] == 'RADAR')
    avant = dict(p1.radio_courante()['peripheriques'][k])
    d = dialogs.DialoguePeripherique(p1, p1.projet, p1.radio_courante(), k)
    verifier(not d.champs['echelle'].isChecked() and not d.champs['mesure_20ma'].isEnabled()
             and d.champs['seuil_haut_ma'].suffix() == ' mA' and d.peripherique() == avant,
             'ancien radar sans échelle : case décochée, seuils en mA, JSON inchangé')
    d.champs['echelle'].setChecked(True)
    verifier(d.champs['seuil_haut_ma'].value() == 500 and d.champs['seuil_haut_ma'].suffix() == ' cm'
             and d.peripherique()['seuil_haut_ma'] == avant['seuil_haut_ma'],
             'échelle cochée : seuil réaffiché en cm (500 cm), valeur en mA inchangée')
    d.champs['hysteresis_ma'].setValue(100)
    verifier(d.peripherique()['hysteresis_ma'] == 1.6, 'hystérésis saisie 100 cm → 1,6 mA')
    d.champs['echelle'].setChecked(False)
    pr = d.peripherique()
    verifier(not any(c in pr for c in ('mesure_4ma', 'mesure_20ma', 'unite')),
             'case Échelle décochée : mesure_4ma, mesure_20ma et unite absentes du JSON')
    verifier(dialogs.texte_cablage(avant) == 'AI1 · seuil 12.0 mA', 'radar sans échelle : câblage « AI1 · seuil 12.0 mA »')

    print('Import')
    REPONSES['fichier'] = os.path.join(tmp, 'demo_A.cdb')
    MESSAGES.clear()
    F.importer_cdb()
    g = orig
    imp = p1.projet
    verifier([(r['nom'], r['role'], r['ip_octet'], r.get('amont') or '') for r in imp['radios']] ==
             [(r['nom'], r['role'], r['ip_octet'], r.get('amont') or '') for r in g['radios']],
             'import : mêmes radios, rôles, IP, amonts')
    verifier(imp['systeme']['cle_chiffrement'] == g['systeme']['cle_chiffrement'], 'import : même clé')
    verifier(dernier('information') and 'périphériques ne sont pas importés' in dernier('information')[2],
             'import : message sur les périphériques')
    prot = os.path.join(tmp, 'protege.cdb')
    with open(prot, 'w', encoding='utf-16') as f:
        f.write('<?xml version="1.0" encoding="UTF-16"?><CConfig><DBE>xxxx</DBE></CConfig>')
    REPONSES['fichier'] = prot
    REPONSES['question'] = QMessageBox.Discard
    MESSAGES.clear()
    F.importer_cdb()
    verifier(dernier('warning') and 'Projet protégé par mot de passe' in dernier('warning')[2], 'import protégé : message dédié')

    print()
    print(f'{len(ECHECS)} échec(s)' if ECHECS else 'Recette interface : tout est OK')
    QSettings().clear()
    return 1 if ECHECS else 0


if __name__ == '__main__':
    sys.exit(main())
