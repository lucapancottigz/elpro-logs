# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""Recette automatisée de l'interface (complément de tests/test_logs.py, ne remplace pas la recette manuelle
de docs/04_Recette.md). Lancer depuis le dossier du dépôt :  python tests_ui/ui_acceptance.py
Pilote les vrais widgets en mode hors écran, sur une base temporaire ; les boîtes de dialogue sont simulées."""
import os, sys, json, glob, time, shutil, tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.abspath(os.path.join(ICI, '..'))
sys.path.insert(0, RACINE)
sys.path.insert(0, os.path.join(RACINE, 'engine'))
sys.path.insert(0, os.path.join(RACINE, 'tools'))

from PySide6.QtCore import QSettings, QCoreApplication, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog, QInputDialog  # noqa: E402

import elpro_logs as L  # noqa: E402
import make_demo_logs as G  # noqa: E402
from ui import dialogs  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.workers import attendre_tous  # noqa: E402
from version import APP_VERSION  # noqa: E402

sys.stdout.reconfigure(encoding='utf-8')
MESSAGES = []
REPONSES = {'question': QMessageBox.Yes, 'fichier': None, 'date': None}
RAPPORTS = []


def _msg(kind):
    def f(parent, titre, texte, *a, **k):
        MESSAGES.append((kind, titre, texte))
        return REPONSES['question'] if kind == 'question' else QMessageBox.Ok
    return f


QMessageBox.warning = staticmethod(_msg('warning'))
QMessageBox.critical = staticmethod(_msg('critical'))
QMessageBox.information = staticmethod(_msg('information'))
QMessageBox.question = staticmethod(_msg('question'))
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (REPONSES['fichier'], ''))
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (REPONSES['fichier'], ''))
QInputDialog.getText = staticmethod(lambda *a, **k: ('Site B renommé', True))
dialogs.RapportImport.exec = lambda self: RAPPORTS.append(self.lignes()) or 0
dialogs.DateMiseEnService.exec = lambda self: 1
dialogs.DateMiseEnService.valable_depuis = lambda self: REPONSES['date']

ECHECS = []


def verifier(cond, libelle):
    print(('  OK   ' if cond else '  ÉCHEC ') + libelle)
    if not cond:
        ECHECS.append(libelle)


def attendre(cond, delai=20):
    fin = time.time() + delai
    while time.time() < fin:
        QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


def locale(texte):
    """'JJ.MM.AAAA HH:MM:SS' (heure suisse) -> seconde UTC."""
    d, h = texte.split()
    j, mo, a = (int(x) for x in d.split('.'))
    hh, mi, s = (int(x) for x in h.split(':'))
    return L.utc_depuis_locale(a, mo, j, hh, mi, s)


def segments_non_ok(frise, nom):
    for n, segs, _a in frise.lignes:
        if n == nom:
            return [(L.heure_locale(int(a)), L.heure_locale(int(b)), e) for a, b, e in segs if e != 'OK']
    return None


TMP = tempfile.mkdtemp()
EX = os.path.join(RACINE, 'examples')
LOGS = sorted(glob.glob(os.path.join(EX, 'logs', '*.log')))


def fenetre(nom_base):
    chemin = os.path.join(TMP, nom_base)
    f = MainWindow(RACINE, chemin, L.Magasin(chemin))
    f.show()
    QApplication.processEvents()
    return f


def global_pret(tab):
    return attendre(lambda: tab.vue_globale.message.text() == '' and tab.vue_globale.frise.lignes)


def main():
    app = QApplication(sys.argv)
    QCoreApplication.setOrganizationName('GeoAzimutRecette')
    QCoreApplication.setApplicationName('ELPRO Logs recette')
    QSettings().clear()

    print('== Démarrage et ajout de systèmes')
    f = fenetre('r.db')
    verifier(f.windowTitle() == 'ELPRO Logs', 'titre de la fenêtre')
    verifier(f.pile.currentIndex() == 0, "page d'accueil sans système")
    verifier('Geoazimut SàRL' in f.mention.text() and 'geoazimut.com' in f.mention.text(), 'copyright en barre d\'état')
    verifier(f.taille.text().startswith('Base : '), 'taille de la base en barre d\'état')
    verifier(not f.action_importer.isEnabled() and not f.action_exporter.isEnabled(), 'actions grisées sans système')
    f.ajouter_systeme(os.path.join(EX, 'demo_site_B.json'))
    verifier(f.onglets.count() == 1 and f.onglets.tabText(0) == 'Demo Site B', 'onglet Demo Site B créé')
    tab = f.onglet_actif()
    verifier('Aucun log importé' in tab.bandeau.text() and tab.bouton_importer.isVisible(),
             'bandeau « Aucun log importé » + bouton Importer')
    MESSAGES.clear()
    f.ajouter_systeme(os.path.join(EX, 'demo_site_B.json'))
    verifier(f.onglets.count() == 1 and any('déjà dans l\'application' in m[2] for m in MESSAGES),
             'ajout du même système : « déjà dans l\'application »')

    print('== Import (R1–R3)')
    f.importer_logs(LOGS)
    r = RAPPORTS[-1]
    verifier([x[1] for x in r] == ['Importé — 2880 lignes importées.'] * 3, 'R1 3 × « Importé — 2880 lignes importées. »')
    attendu = ('Radio n° 99000000001 · Config V1.0 · Données du 01.10.2026 02:00:00 au 04.10.2026 02:00:00 · '
               '3 fichiers')
    verifier(tab.bandeau.text() == attendu, f'R2 bandeau : {tab.bandeau.text()}')
    verifier(not tab.bouton_importer.isVisible(), 'bouton Importer masqué quand il y a des données')
    f.importer_logs(LOGS)
    verifier([x[1] for x in RAPPORTS[-1]] == ['Déjà importé'] * 3, 'R3 3 × « Déjà importé »')

    print('== Vue globale (G1–G9)')
    verifier(global_pret(tab), 'calcul de la vue globale terminé')
    vg = tab.vue_globale
    verifier(vg.cartes['donnees'].valeur.text() == '100 %' and vg.cartes['donnees'].complement.text() == 'aucun trou',
             'G1 données disponibles 100 %, aucun trou')
    verifier(vg.cartes['pertes'].valeur.text() == '1' and vg.cartes['stations_perte'].valeur.text() == '1 / 8',
             'cartes pertes de comm (1, 1 / 8)')
    verifier(vg.cartes['batteries'].valeur.text() == '1' and vg.cartes['secteur'].valeur.text() == '1'
             and vg.cartes['detections'].valeur.text() == '1', 'cartes batteries, secteur, détections')
    verifier(segments_non_ok(vg.frise, 'B-SM2') == [('01.10.2026 12:01:00', '01.10.2026 14:04:30', 'COMM_PERDUE')],
             'G2 frise B-SM2 rouge 12:01–14:04')
    verifier(segments_non_ok(vg.frise, 'B-SM3') == [('02.10.2026 16:05:30', '02.10.2026 22:06:30', 'ALERTE')],
             'G3 frise B-SM3 jaune 16:05–22:06')
    verifier(segments_non_ok(vg.frise, 'B-BASE') == [('01.10.2026 05:00:00', '01.10.2026 05:30:00', 'ALERTE')],
             'G4 frise B-BASE jaune 05:00–05:30')
    verifier([e for _a, _b, e in segments_non_ok(vg.frise, 'Système')] == ['ALERTE', 'COMM_PERDUE', 'ALERTE'],
             'G5 ligne Système')
    k = [n for n, _s, _a in vg.frise.lignes].index('B-SM2')
    s = vg.frise.segment_a(k, locale('01.10.2026 13:00:00'))
    verifier(s and s[2] == 'COMM_PERDUE', 'survol de la frise : segment de perte de comm')
    sm2, sm3, base = vg.ligne_tableau('B-SM2'), vg.ligne_tableau('B-SM3'), vg.ligne_tableau('B-BASE')
    verifier((sm2['Dispo comm'], sm2['Pertes comm'], sm2['Durée pertes']) == ('97,14 %', '1', '2 h 03 min'),
             f"G7 B-SM2 {sm2['Dispo comm']} · {sm2['Pertes comm']} · {sm2['Durée pertes']}")
    verifier((sm3['Batterie min'], sm3['Batterie basse'], sm3['Radar max']) == ('11,15 V', '6 h 01 min', '281,2 cm'),
             f"G8 B-SM3 {sm3['Batterie min']} · {sm3['Batterie basse']} · {sm3['Radar max']}")
    verifier(base['Coupures secteur'] == '1 (30 min 00 s)' and base['Dispo comm'] == '',
             f"G9 B-BASE coupures {base['Coupures secteur']}, dispo comm vide")
    tout = tab.periode
    tab.periode_derniere(7 * 86400)
    verifier(tab.periode == (tout[1] - 7 * 86400, tout[1]), 'période « 7 jours » depuis la fin des données')
    vg.frise.vue.zoom.emit(locale('01.10.2026 11:00:00'), locale('01.10.2026 15:00:00'))
    verifier(tab.periode == (locale('01.10.2026 11:00:00'), locale('01.10.2026 15:00:00')), 'G6 zoom par clic-glisser')
    verifier(tab.du.dateTime().toString('dd.MM.yyyy HH:mm:ss') == '01.10.2026 11:00:00', 'champ Du en heure suisse')
    tab.retour()
    verifier(tab.periode == (tout[1] - 7 * 86400, tout[1]), 'G6 ↶ revient à la période précédente')
    tab.decaler(-1)
    verifier(tab.periode == (tout[1] - 14 * 86400, tout[1] - 7 * 86400), '◀ décale de la durée de la période')
    tab.periode_tout()
    verifier(tab.periode == tout and tab.tout, 'bouton Tout')

    print('== Détail (D1–D8)')
    verifier(global_pret(tab), 'vue globale recalculée')
    vg.frise.station_double_clic.emit('B-SM3')
    dt = tab.detail
    verifier(tab.sous_onglets.currentWidget() is dt, 'D1 double-clic : onglet Détail ouvert')
    noms = {c['station'] for c in dt.canaux_affiches()}
    verifier(noms == {'B-SM3'} and len(dt.canaux_affiches()) == 14, 'D1 canaux de B-SM3 cochés')
    titres = [p.titleLabel.text for p in dt.plots]
    verifier(any('Batteries' in t for t in titres) and any('Radars (cm)' in t for t in titres),
             f'D2/D3 graphiques Batteries et Radars (cm) : {titres}')
    radar = next(p for p in dt.plots if 'Radars' in p.titleLabel.text)
    seuils = [it.value() for it in radar.items if type(it).__name__ == 'InfiniteLine' and it.angle == 0]
    verifier(250.0 in seuils, 'D3 ligne de seuil radar à 250 cm')
    verifier(f.action_exporter.isEnabled(), 'Exporter en CSV actif dans le Détail avec des canaux cochés')
    item_batt = next(it for it in dt._items_canaux() if it.data(0, Qt.UserRole + 2) == 'BATTV')
    dt.arbre.setCurrentItem(item_batt)
    dt.tout_decocher()
    verifier(not dt.canaux_affiches() and not f.action_exporter.isEnabled(), 'Tout décocher')
    dt.arbre.setCurrentItem(next(it for it in dt._items_canaux() if it.data(0, Qt.UserRole + 2) == 'BATTV'))
    dt.meme_donnee()
    dt.tracer()
    verifier(len(dt.courbes) == 9 and all(c['genre'] == 'BATTV' for c, _i in dt.courbes), 'D4 9 courbes de batterie')
    dt.tout_decocher()
    for it in dt._items_canaux():
        if it.data(0, Qt.UserRole + 1) == 'B-SM2' and it.data(0, Qt.UserRole + 2) in ('COMFLAG', 'RSSI'):
            it.setCheckState(0, Qt.Checked)
    tab.definir_periode(locale('01.10.2026 11:00:00'), locale('01.10.2026 15:00:00'))
    dt.tracer()
    couloir = dt.plots[0]
    barres = [it for it in couloir.items if type(it).__name__ == 'BarGraphItem']
    x0 = barres[0].opts['x0'][0] if barres else None
    verifier(x0 == locale('01.10.2026 12:01:00'), 'D5 couloir COMFLAG rouge à partir de 12:01')
    fonds = [it for it in dt.plots[1].items if type(it).__name__ == 'LinearRegionItem']
    verifier(any(tuple(int(v) for v in r.getRegion()) == (locale('01.10.2026 12:01:00'), locale('01.10.2026 14:04:30'))
                 for r in fonds), 'D5 fond rouge pâle sur le graphique RSSI pendant la perte')
    vals = {c['genre']: v for c, v in dt.valeurs_au(locale('01.10.2026 13:00:00'))}
    verifier(vals.get('COMFLAG') == 1, 'D6 curseur à 13:00 : COMFLAG B-SM2 = 1')
    dt.placer_curseur(locale('01.10.2026 13:00:00'))
    attendre(lambda: dt.valeurs.topLevelItemCount() == 2)
    verifier(dt.titre_valeurs.text() == 'Valeurs au 01.10.2026 13:00:00', 'D6 panneau « Valeurs au … »')
    dt.cases_familles['AUTRES'].setChecked(True)
    racines = [dt.arbre.topLevelItem(k).text(0) for k in range(dt.arbre.topLevelItemCount())]
    verifier('Autres registres' in racines, 'D7 nœud « Autres registres » visible')
    tab.definir_periode(locale('01.10.2026 11:00:00'), locale('01.10.2026 12:00:00'))
    csv_ = os.path.join(TMP, 'export.csv')
    REPONSES['fichier'] = csv_
    f.exporter_csv()
    attendre(lambda: not f.tache_export.isRunning() and os.path.exists(csv_))
    f.tache_export.wait()
    lignes = open(csv_, encoding='utf-8-sig').read().splitlines()
    verifier(len(lignes) == 121 and lignes[1].startswith('01.10.2026 11:00:00;') and ';' in lignes[0],
             f'D8 export CSV de 2 canaux sur 1 h : {len(lignes)} lignes, heure suisse')

    print('== Journal (J1–J4)')
    tab.periode_tout()
    tab.sous_onglets.setCurrentWidget(tab.journal)
    jr = tab.journal
    attendre(lambda: jr.message.text().endswith('événements'))
    lj = jr.lignes()
    verifier(len(lj) == 12, f'J1 {len(lj)} événements')
    verifier(lj and lj[0] == ['01.10.2026 05:00:00', 'B-BASE', 'Coupure secteur', '30 min 00 s'], f'J1 premier : {lj[:1]}')
    verifier(['01.10.2026 12:01:00', 'B-SM2', 'Perte de communication', '2 h 03 min'] in lj
             and ['01.10.2026 14:04:30', 'B-SM2', 'Communication rétablie', ''] in lj, 'J2 perte de comm puis rétablie')
    jr.f_stations.cocher(['B-BASE'])
    jr.f_familles.cocher(['SECTEUR'])
    attendre(lambda: len(jr.lignes()) == 2)
    verifier([x[2] for x in jr.lignes()] == ['Coupure secteur', 'Secteur rétabli'], 'J3 filtre B-BASE + Secteur')
    jr.f_stations.cocher([n for n in jr.f_stations.actions_])
    jr.f_familles.cocher([n for n in jr.f_familles.actions_])
    attendre(lambda: len(jr.lignes()) == 12)
    jcsv = os.path.join(TMP, 'journal.csv')
    jr.ecrire_csv(jcsv)
    jl = open(jcsv, encoding='utf-8-sig').read().splitlines()
    verifier(len(jl) == 13 and jl[0] == 'Date et heure;Station;Événement;Durée', 'export du journal (CSV ;)')
    k = next(i for i, e in enumerate(jr.evenements) if e['message'].startswith('Batterie basse'))
    jr._double_clic(jr.modele.index(k, 0))
    verifier(tab.sous_onglets.currentWidget() is dt and {c['station'] for c in dt.canaux_affiches()} == {'B-SM3'},
             'J4 double-clic : Détail de B-SM3')
    verifier((L.heure_locale(tab.t0, '%d.%m %H:%M'), L.heure_locale(tab.t1, '%d.%m %H:%M')) == ('02.10 15:05', '02.10 17:05'),
             'J4 période du 02.10 15:05 au 17:05')

    print('== Fichiers')
    tab.sous_onglets.setCurrentWidget(tab.fichiers)
    fv = tab.fichiers
    verifier(fv.logs.rowCount() == 3 and fv.configs.rowCount() == 1 and fv.configs.item(0, 1).text() == 'origine',
             'logs importés et version de configuration « origine »')
    verifier(fv.type_liste.text() == 'Standard GeoAzimut' and fv.liste.rowCount() == len(L.LISTE_STANDARD),
             'liste de log standard')

    print('== Redémarrage (R4, R5)')
    f.ajouter_systeme(os.path.join(EX, 'demo_site_A.json'))
    verifier(f.onglets.count() == 2 and f.onglets.currentIndex() == 1, 'R5 2ᵉ onglet Demo Site A sélectionné')
    f.close()
    f = fenetre('r.db')
    verifier([f.onglets.tabText(k) for k in range(f.onglets.count())] == ['Demo Site B', 'Demo Site A'],
             'R4/R5 les 2 onglets se rouvrent dans le même ordre')
    verifier(f.onglets.currentIndex() == 1, 'dernier onglet actif resélectionné')
    tab_b = f.onglet_de(1)
    verifier(tab_b.periode == tout and '3 fichiers' in tab_b.bandeau.text(), 'R4 données présentes après redémarrage')

    print('== Autre radio (T4)')
    f.onglets.setCurrentIndex(1)
    tab_a = f.onglet_actif()
    logs_a = G.generer(os.path.join(EX, 'demo_site_A.json'), os.path.join(TMP, 'logs_A'), 1, serie='99000000002')
    f.importer_logs(logs_a)                   # Demo Site A reçoit d'abord les logs de sa propre radio
    verifier(RAPPORTS[-1][0][1].startswith('Importé'), 'logs de Demo Site A importés')
    REPONSES['question'] = QMessageBox.No
    MESSAGES.clear()
    n_avant = len(f.magasin.fichiers(tab_a.sid))
    f.importer_logs(LOGS[1:2])
    verifier(any(m[0] == 'question' and 'Importer quand même' in m[2] for m in MESSAGES), 'T4 question « autre radio »')
    verifier(RAPPORTS[-1][0][1] == 'Non importé — autre radio' and len(f.magasin.fichiers(tab_a.sid)) == n_avant,
             'T4 Non → rien importé')
    REPONSES['question'] = QMessageBox.Yes
    tab_b2 = f.onglet_de(1)

    print('== Mise à jour de configuration (T3)')
    projet = json.load(open(os.path.join(EX, 'demo_site_B.json'), encoding='utf-8'))
    projet['radios'][1]['peripheriques'][0]['nom'] = 'CABLE_NORD'
    projet['version_config'] = '1.1'
    modifie = os.path.join(TMP, 'demo_site_B_v11.elpro.json')
    json.dump(projet, open(modifie, 'w', encoding='utf-8'))
    f.onglets.setCurrentWidget(tab_b2)
    MESSAGES.clear()
    f.mettre_a_jour_config(os.path.join(EX, 'demo_site_A.json'))
    verifier(any('autre système' in m[2] for m in MESSAGES), 'fichier d\'un autre système refusé')
    REPONSES['date'] = locale('02.10.2026 12:00:00')
    f.mettre_a_jour_config(modifie)
    verifier(len(f.magasin.configs(tab_b2.sid)) == 2, 'T3 deux versions de configuration')
    tab_b2.periode_tout()
    verifier(tab_b2.bandeau_config.isVisibleTo(tab_b2) and 'V1.0 → V1.1' in tab_b2.bandeau_config.text(),
             'T3 bandeau jaune « La configuration a changé… »')
    tab_b2.sous_onglets.setCurrentWidget(tab_b2.fichiers)
    verifier(tab_b2.fichiers.configs.rowCount() == 2, 'T3 onglet Fichiers : 2 versions')

    print('== Renommer, supprimer')
    f.renommer()
    verifier(f.onglets.tabText(f.onglets.indexOf(tab_b2)) == 'Site B renommé', 'Renommer')
    f.onglets.setCurrentWidget(tab_a)
    f.supprimer()
    verifier(f.onglets.count() == 1 and all(s['id'] != tab_a.sid for s in f.magasin.systemes()),
             'Supprimer (double confirmation)')
    f.close()

    print('== Trous de données (T1, T2)')
    f = fenetre('t.db')
    f.ajouter_systeme(os.path.join(EX, 'demo_site_B.json'))
    tab = f.onglet_actif()
    f.importer_logs([LOGS[0], LOGS[2]])
    verifier(global_pret(tab), 'vue globale calculée')
    gris = [s for s in segments_non_ok(tab.vue_globale.frise, 'Système') if s[2] == 'SANS_DONNEES']
    verifier(gris == [('02.10.2026 02:00:00', '03.10.2026 02:00:00', 'SANS_DONNEES')], 'T1 frise grise le 02.10')
    tab.sous_onglets.setCurrentWidget(tab.journal)
    attendre(lambda: tab.journal.message.text().endswith('événements') or tab.journal.message.text().endswith('événement'))
    msgs = [x[2] for x in tab.journal.lignes()]
    verifier('Début d\'absence de données (1 j 0 h 00 min)' in msgs and 'Reprise des données' in msgs,
             'T1 journal : absence puis reprise des données')
    f.importer_logs([LOGS[1]])
    tab.sous_onglets.setCurrentWidget(tab.vue_globale)
    verifier(global_pret(tab), 'vue globale recalculée')
    verifier(not [s for s in segments_non_ok(tab.vue_globale.frise, 'Système') if s[2] == 'SANS_DONNEES']
             and tab.periode == tout, 'T2 plus de gris, période « Tout » étendue')
    tab.sous_onglets.setCurrentWidget(tab.journal)
    attendre(lambda: len(tab.journal.lignes()) == 12)
    verifier(len(tab.journal.lignes()) == 12, 'T2 journal identique (12 événements)')

    print('== Changement d\'heure (T5)')
    from ui.common import AxeHeureSuisse
    logs30 = G.generer(os.path.join(EX, 'demo_site_B.json'), os.path.join(TMP, 'logs30'), 30)
    f.importer_logs(logs30)
    a, b = locale('24.10.2026 00:00:00'), locale('27.10.2026 00:00:00')
    tab.definir_periode(a, b)
    verifier(b - a == 3 * 86400 + 3600, 'T5 période du 24.10 au 27.10 : 73 h (heure d\'hiver le 25.10)')
    axe = AxeHeureSuisse()
    (pas, ticks), = axe.tickValues(a, b, 8000)
    textes = axe.tickStrings(ticks, 1, pas)
    verifier(pas == 3600 and len(ticks) == 73 and all(x < y for x, y in zip(ticks, ticks[1:]))
             and (textes[0], textes[24], textes[25], textes[-1]) == ('24.10', '25.10', '01:00', '27.10')
             and textes.count('02:00') == 3, 'T5 axe horaire en heure suisse : ni décalage ni doublon')
    tab.ouvrir_detail('B-SM3')
    dt = tab.detail
    xs = [c for c, _i in dt.courbes]
    ok = True
    for _c, it in dt.courbes:
        x = it.getData()[0]
        ok = ok and len(x) > 0 and all(x[k] <= x[k + 1] for k in range(len(x) - 1)) and x[0] >= a and x[-1] <= b
    verifier(ok and xs, 'T5 courbes continues et ordonnées sur le changement d\'heure')

    print('== Aide et À propos')
    a = dialogs.AideListeLog(f)
    verifier(a.table.rowCount() == len(L.LISTE_STANDARD) and 'Scan Rate\t30' in a.texte(), 'aide « liste de log »')
    ap = dialogs.AboutDialog(f, RACINE)
    verifier(ap.texte_fichier('Licence').startswith('ELPRO Logs') and ap.texte_fichier('Composants tiers'),
             f'À propos {APP_VERSION} : licence et composants tiers')
    f.close()
    attendre_tous()
    QSettings().clear()
    shutil.rmtree(TMP, ignore_errors=True)

    print()
    if ECHECS:
        print(f'ÉCHEC : {len(ECHECS)} contrôle(s) en échec')
        return 1
    print('Recette interface : OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
