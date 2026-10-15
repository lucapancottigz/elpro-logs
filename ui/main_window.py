# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""Fenêtre principale : menus, un onglet par système (tous ouverts au démarrage), page d'accueil,
glisser-déposer, barre d'état (taille de la base, copyright)."""
import os, sqlite3

from PySide6.QtCore import Qt, QSettings, QStandardPaths
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QMainWindow, QTabWidget, QStackedWidget, QWidget, QVBoxLayout, QLabel, QPushButton,
                               QFileDialog, QMessageBox, QInputDialog, QProgressDialog)

import elpro_engine as M
import elpro_logs as L
from ui.common import lire_projet, cle_systeme, projet_normalise
from ui.dialogs import (AboutDialog, ProgressionImport, RapportImport, DateMiseEnService, AideListeLog,
                        site_affiche)
from ui.system_tab import SystemTab
from ui.workers import Tache, attendre_tous
from version import APP_COMPANY, APP_COPYRIGHT, APP_WEBSITE

FILTRE_PROJET = 'Projet ELPRO Config (*.elpro.json *.json)'
FILTRE_LOGS = 'Logs ELPRO (*.log *.zip *.csv);;Tous les fichiers (*)'
EXT_LOGS = ('.log', '.zip', '.csv')


class MainWindow(QMainWindow):
    def __init__(self, base, chemin_base, magasin):
        super().__init__()
        self.base = base
        self.chemin_base = chemin_base
        self.magasin = magasin
        self.setWindowTitle('ELPRO Logs')
        self.resize(1400, 900)
        self.setAcceptDrops(True)

        # --- page d'accueil (aucun système) et onglets
        self.pile = QStackedWidget()
        accueil = QWidget()
        v = QVBoxLayout(accueil)
        v.addStretch(1)
        self.bouton_accueil = QPushButton('Ajouter un système (.elpro.json)…')
        f = self.bouton_accueil.font()
        f.setPointSize(f.pointSize() + 4)
        self.bouton_accueil.setFont(f)
        self.bouton_accueil.setMinimumSize(420, 64)
        self.bouton_accueil.clicked.connect(lambda: self.ajouter_systeme())
        v.addWidget(self.bouton_accueil, 0, Qt.AlignHCenter)
        phrase = QLabel('Ajoutez d\'abord un système avec le fichier .elpro.json créé par ELPRO Config, '
                        'puis importez les fichiers .log de sa centrale.')
        phrase.setWordWrap(True)
        phrase.setAlignment(Qt.AlignCenter)
        phrase.setStyleSheet('color: gray;')
        phrase.setMaximumWidth(520)
        v.addWidget(phrase, 0, Qt.AlignHCenter)
        v.addStretch(2)
        self.pile.addWidget(accueil)
        self.onglets = QTabWidget()
        self.onglets.setTabsClosable(False)
        self.onglets.setDocumentMode(True)
        self.onglets.currentChanged.connect(self._onglet_change)
        self.pile.addWidget(self.onglets)
        self.setCentralWidget(self.pile)

        self._menus()

        # --- barre d'état : taille de la base à gauche, copyright à droite
        self.taille = QLabel()
        self.statusBar().addWidget(self.taille)
        court = APP_COPYRIGHT.split(APP_COMPANY)[0] + APP_COMPANY          # « © 2026 Geoazimut SàRL »
        self.mention = QLabel(f'{court} — <a href="{APP_WEBSITE}" style="color:gray;">'
                              f'{site_affiche(APP_WEBSITE)}</a>')
        self.mention.setTextFormat(Qt.RichText)
        self.mention.setOpenExternalLinks(True)
        self.mention.setStyleSheet('color: gray;')
        f = self.mention.font()
        f.setPointSize(8)
        self.mention.setFont(f)
        self.statusBar().addPermanentWidget(self.mention)

        # --- un onglet par système, dans l'ordre de la base ; dernier onglet actif resélectionné
        dernier = QSettings().value('dernier_systeme')
        for s in self.magasin.systemes():
            self._ajouter_onglet(s)
        for k in range(self.onglets.count()):
            if str(self.onglets.widget(k).sid) == str(dernier):
                self.onglets.setCurrentIndex(k)
        self._maj_etat()

    # ================================================================ menus
    def _menus(self):
        def action(menu, texte, fonction, raccourci=None):
            a = QAction(texte, self)
            if raccourci:
                a.setShortcut(raccourci)
            a.triggered.connect(lambda _=False: fonction())
            menu.addAction(a)
            return a

        mf = self.menuBar().addMenu('&Fichier')
        action(mf, 'Ajouter un système (.elpro.json)…', self.ajouter_systeme)
        self.action_importer = action(mf, 'Importer des logs…', self.importer_logs, QKeySequence('Ctrl+I'))
        self.action_exporter = action(mf, 'Exporter en CSV…', self.exporter_csv)
        mf.addSeparator()
        action(mf, 'Quitter', self.close, QKeySequence.Quit)

        ms = self.menuBar().addMenu('&Système')
        self.actions_systeme = [
            action(ms, 'Mettre à jour la configuration (.elpro.json)…', self.mettre_a_jour_config),
            action(ms, 'Liste de log de la centrale (XML)…', self.liste_log_xml),
            action(ms, 'Revenir à la liste standard', self.liste_standard),
        ]
        ms.addSeparator()
        self.actions_systeme += [action(ms, 'Renommer…', self.renommer),
                                 action(ms, 'Supprimer ce système…', self.supprimer)]

        ma = self.menuBar().addMenu('&Aide')
        action(ma, 'Liste de log à configurer sur la centrale', lambda: AideListeLog(self).exec())
        action(ma, 'À propos', self.a_propos)

    def a_propos(self):
        AboutDialog(self, self.base).exec()

    # ================================================================ onglets
    def _ajouter_onglet(self, s):
        tab = SystemTab(self, s)
        tab.export_change.connect(self._maj_export)
        self.onglets.addTab(tab, s['nom'])
        return tab

    def onglet_actif(self):
        return self.onglets.currentWidget() if self.onglets.count() else None

    def onglet_de(self, sid):
        for k in range(self.onglets.count()):
            if self.onglets.widget(k).sid == sid:
                return self.onglets.widget(k)
        return None

    def _onglet_change(self, _i):
        tab = self.onglet_actif()
        if tab is not None:
            QSettings().setValue('dernier_systeme', tab.sid)
        self._maj_etat()

    def _maj_etat(self):
        a = self.onglets.count() > 0
        self.pile.setCurrentIndex(1 if a else 0)
        self.action_importer.setEnabled(a)
        for x in self.actions_systeme:
            x.setEnabled(a)
        self._maj_export()
        self._maj_taille()

    def _maj_export(self):
        tab = self.onglet_actif()
        self.action_exporter.setEnabled(bool(tab and tab.export_possible()))

    def _maj_taille(self):
        try:
            mo = self.magasin.taille_fichier() / 1e6
        except OSError:
            mo = 0
        self.taille.setText(f'Base : {mo:.1f} Mo'.replace('.', ','))
        self.taille.setToolTip(self.chemin_base)

    def reouvrir_base(self):
        """Après un import fait par un autre thread : nouvelle connexion (caches de lecture à jour)."""
        self.magasin.fermer()
        self.magasin = L.Magasin(self.chemin_base)

    # ================================================================ dossiers mémorisés
    @staticmethod
    def _documents():
        return QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)

    def _dossier(self, cle):
        d = QSettings().value(cle, '')
        return d if d and os.path.isdir(d) else self._documents()

    # ================================================================ systèmes
    def ajouter_systeme(self, chemin=None):
        if chemin is None:
            chemin, _ = QFileDialog.getOpenFileName(self, 'Ajouter un système', self._dossier('dossier_config'),
                                                    FILTRE_PROJET)
            if not chemin:
                return
        QSettings().setValue('dossier_config', os.path.dirname(chemin))
        try:
            projet = lire_projet(chemin)
            cle = cle_systeme(projet)
        except Exception as e:
            QMessageBox.critical(self, 'Ajouter un système', f'Impossible de lire {os.path.basename(chemin)} :\n{e}')
            return
        existant = next((s for s in self.magasin.systemes() if s['cle'] == cle), None)
        if existant is not None:
            tab = self.onglet_de(existant['id'])
            self.onglets.setCurrentWidget(tab)
            if projet_normalise(projet) == self.magasin.projet(existant['id']):
                QMessageBox.information(self, 'Ajouter un système', 'Ce système est déjà dans l\'application.')
                return
            self._mise_a_jour(tab, projet)          # nouvelle version de la config d'un système existant
            return
        try:
            r = self.magasin.ajouter_config(projet)
        except Exception as e:
            QMessageBox.warning(self, 'Ajouter un système', str(e))
            return
        if r['statut'] == 'nouveau':
            s = next(s for s in self.magasin.systemes() if s['id'] == r['systeme_id'])
            tab = self._ajouter_onglet(s)
            self.onglets.setCurrentWidget(tab)
            self._maj_etat()
            self.statusBar().showMessage(f"Système « {s['nom']} » ajouté. Importez maintenant ses logs.", 8000)
        else:
            tab = self.onglet_de(r['systeme_id'])
            self.onglets.setCurrentWidget(tab)
            if r['statut'] == 'identique':
                QMessageBox.information(self, 'Ajouter un système', 'Ce système est déjà dans l\'application.')
            else:
                tab.vider_cache()
                tab.rafraichir()

    def mettre_a_jour_config(self, chemin=None):
        tab = self.onglet_actif()
        if tab is None:
            return
        if chemin is None:
            chemin, _ = QFileDialog.getOpenFileName(self, f'Mettre à jour la configuration — {tab.nom}',
                                                    self._dossier('dossier_config'), FILTRE_PROJET)
            if not chemin:
                return
        QSettings().setValue('dossier_config', os.path.dirname(chemin))
        try:
            projet = lire_projet(chemin)
            cle = cle_systeme(projet)
        except Exception as e:
            QMessageBox.critical(self, 'Mettre à jour la configuration',
                                 f'Impossible de lire {os.path.basename(chemin)} :\n{e}')
            return
        sy = next(s for s in self.magasin.systemes() if s['id'] == tab.sid)
        if cle != sy['cle']:
            QMessageBox.warning(self, 'Mettre à jour la configuration',
                                f'Ce fichier décrit un autre système ({cle}), pas « {sy["nom"]} » ({sy["cle"]}).')
            return
        self._mise_a_jour(tab, projet)

    def _mise_a_jour(self, tab, projet):
        titre = 'Mettre à jour la configuration'
        if projet_normalise(projet) == self.magasin.projet(tab.sid):
            QMessageBox.information(self, titre, 'Cette configuration est déjà celle du système.')
            return
        d = DateMiseEnService(self, M.version_config(projet))
        if not d.exec():
            return
        try:
            r = self.magasin.ajouter_config(projet, valable_depuis=d.valable_depuis())
        except Exception as e:
            QMessageBox.warning(self, titre, str(e))
            return
        tab.vider_cache()
        tab.rafraichir()
        self.onglets.setTabText(self.onglets.indexOf(tab), tab.nom)
        if r['statut'] == 'version':
            self.statusBar().showMessage(f'Configuration V{M.version_config(projet)} enregistrée.', 8000)
        else:
            QMessageBox.information(self, titre, 'Cette configuration est déjà celle du système.')

    def liste_log_xml(self):
        tab = self.onglet_actif()
        if tab is None:
            return
        chemin, _ = QFileDialog.getOpenFileName(self, 'Liste de log de la centrale (export XML de la radio)',
                                                self._dossier('dossier_config'), 'Export XML (*.xml);;Tous (*)')
        if not chemin:
            return
        try:
            profil = L.lire_profil_xml(chemin)
        except Exception as e:
            QMessageBox.warning(self, 'Liste de log', f'Impossible de lire la liste de log :\n{e}')
            return
        self.magasin.definir_profil(tab.sid, profil)
        tab.fichiers.a_jour = False
        tab._actualiser_visible()
        QMessageBox.information(self, 'Liste de log',
                                f'Liste de log propre à cette centrale enregistrée ({len(profil)} entrées).\n'
                                'Elle s\'applique aux prochains imports.')

    def liste_standard(self):
        tab = self.onglet_actif()
        if tab is None:
            return
        if self.magasin.profil(tab.sid) is None:
            QMessageBox.information(self, 'Liste de log', 'Ce système utilise déjà la liste standard.')
            return
        if QMessageBox.question(self, 'Liste de log', 'Revenir à la liste de log standard GeoAzimut ?\n'
                                'Elle s\'appliquera aux prochains imports.') != QMessageBox.Yes:
            return
        self.magasin.definir_profil(tab.sid, None)
        tab.fichiers.a_jour = False
        tab._actualiser_visible()

    def renommer(self):
        tab = self.onglet_actif()
        if tab is None:
            return
        nom, ok = QInputDialog.getText(self, 'Renommer', 'Nouveau nom du système :', text=tab.nom)
        nom = (nom or '').strip()
        if ok and nom:
            self.magasin.renommer(tab.sid, nom)
            tab.nom = nom
            self.onglets.setTabText(self.onglets.indexOf(tab), nom)

    def supprimer(self):
        tab = self.onglet_actif()
        if tab is None:
            return
        titre = 'Supprimer ce système'
        if QMessageBox.question(self, titre, f'Supprimer le système « {tab.nom} » ?\n\n'
                                'Toutes les valeurs importées de ce système seront effacées.',
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        if QMessageBox.question(self, titre, f'Confirmer la suppression définitive de « {tab.nom} » et de '
                                'toutes ses valeurs ? Cette opération est irréversible.',
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        attendre_tous()
        self.magasin.supprimer_systeme(tab.sid)
        try:
            self.magasin.compacter_base()
        except sqlite3.Error:
            pass                                  # base occupée : l'espace sera récupéré plus tard
        self.onglets.removeTab(self.onglets.indexOf(tab))
        tab.deleteLater()
        self._maj_etat()

    # ================================================================ import des logs
    def importer_logs(self, chemins=None):
        tab = self.onglet_actif()
        if tab is None:
            QMessageBox.information(self, 'Importer des logs', 'Ajoutez d\'abord un système (.elpro.json).')
            return
        if chemins is None:
            chemins, _ = QFileDialog.getOpenFileNames(self, f'Importer des logs — {tab.nom}',
                                                      self._dossier('dossier_logs'), FILTRE_LOGS)
            if not chemins:
                return
        QSettings().setValue('dossier_logs', os.path.dirname(chemins[0]))
        resultats, annule = self._importer(tab, [(c, False) for c in chemins])
        # logs d'une autre radio : rien n'est importé sans confirmation
        a_forcer = []
        for chemin, rs in resultats:
            for r in rs:
                if r.get('statut') == 'serie_differente' and chemin not in a_forcer:
                    rep = QMessageBox.question(self, 'Autre radio', f"{r['fichier']} : {r['message']}\n\n"
                                               'Importer quand même dans ce système ?',
                                               QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                    if rep == QMessageBox.Yes:
                        a_forcer.append(chemin)
        if a_forcer:
            res2, _a = self._importer(tab, [(c, True) for c in a_forcer])
            nouveaux = {(c, r.get('fichier')): r for c, rs in res2 for r in rs}
            resultats = [(c, [nouveaux.get((c, r.get('fichier')), r) if r.get('statut') == 'serie_differente'
                              else r for r in rs]) for c, rs in resultats]
        self.reouvrir_base()
        tab.rafraichir(apres_import=True)
        self._maj_taille()
        self.rapport = RapportImport(self, resultats, annule)
        self.rapport.exec()

    def _importer(self, tab, fichiers):
        d = ProgressionImport(self, self.chemin_base, tab.sid, fichiers)
        d.exec()
        d.thread.wait()
        return d.resultats, d.thread.annule and len(d.resultats) < len(fichiers)

    # ================================================================ export CSV
    def exporter_csv(self):
        tab = self.onglet_actif()
        if not tab or not tab.export_possible():
            return
        canaux = tab.detail.canaux_affiches()
        t0, t1 = tab.periode
        nom = f"{tab.nom}_{L.heure_locale(t0, '%Y%m%d_%H%M')}.csv".replace(' ', '_')
        chemin, _ = QFileDialog.getSaveFileName(self, 'Exporter en CSV',
                                                os.path.join(self._dossier('dossier_export'), nom),
                                                'Fichier CSV (*.csv)')
        if not chemin:
            return
        if not chemin.lower().endswith('.csv'):
            chemin += '.csv'
        QSettings().setValue('dossier_export', os.path.dirname(chemin))
        attente = QProgressDialog('Export en cours…', None, 0, 0, self)
        attente.setWindowTitle('Exporter en CSV')
        attente.setWindowModality(Qt.WindowModal)
        attente.setMinimumDuration(300)
        sid = tab.sid
        tache = Tache(self.chemin_base, lambda m: m.exporter_csv(sid, canaux, t0, t1, chemin))

        def fini(_r):
            attente.close()
            self.statusBar().showMessage(f'Export terminé : {chemin}', 8000)

        def echec(msg):
            attente.close()
            QMessageBox.critical(self, 'Exporter en CSV', f'Export impossible :\n{msg}')
        tache.termine.connect(fini)
        tache.echec.connect(echec)
        self.tache_export = tache
        tache.start()

    # ================================================================ glisser-déposer
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        chemins = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        self.deposer(chemins)
        e.acceptProposedAction()

    def deposer(self, chemins):
        """.elpro.json : ajoute un système ; .log/.zip/.csv : import dans le système de l'onglet actif."""
        for c in chemins:
            if c.lower().endswith('.json'):
                self.ajouter_systeme(c)
        logs = [c for c in chemins if c.lower().endswith(EXT_LOGS)]
        if logs:
            self.importer_logs(logs)

    # ================================================================ fermeture
    def closeEvent(self, e):
        tab = self.onglet_actif()
        if tab is not None:
            QSettings().setValue('dernier_systeme', tab.sid)
        attendre_tous()
        self.magasin.fermer()
        e.accept()
