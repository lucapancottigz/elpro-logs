# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""Fenêtre principale : barre d'outils, onglets (Page 1 / Page 2), barre d'état."""
import os, sys, json

from PySide6.QtCore import Qt, QSettings, QTimer, QStandardPaths
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QMainWindow, QTabWidget, QToolBar, QFileDialog, QMessageBox, QLabel, QWidget,
                               QSizePolicy)

import elpro_engine as M
from ui.dialogs import AboutDialog, site_affiche
from ui.page_config import PageConfig, projet_vide
from ui.page_result import PageResult
from version import APP_VERSION, APP_COMPANY, APP_COPYRIGHT, APP_WEBSITE

FILTRE_PROJET = 'Projet ELPRO (*.elpro.json);;Fichiers JSON (*.json)'


class MainWindow(QMainWindow):
    def __init__(self, base):
        super().__init__()
        self.base = base
        self.chemin = None
        self.resize(1280, 820)

        self.page_config = PageConfig()
        self.page_result = PageResult()
        self.onglets = QTabWidget()
        self.onglets.addTab(self.page_config, '1. Configuration')
        self.onglets.addTab(self.page_result, '2. Configuration générée')
        self.setCentralWidget(self.onglets)

        bo = QToolBar('Fichier'); bo.setMovable(False)
        bo.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.addToolBar(bo)
        for texte, raccourci, action in (('Nouveau', QKeySequence.New, self.nouveau),
                                         ('Ouvrir…', QKeySequence.Open, self.ouvrir),
                                         ('Enregistrer', QKeySequence.Save, self.enregistrer),
                                         ('Enregistrer sous…', QKeySequence.SaveAs, self.enregistrer_sous),
                                         (None, None, None),
                                         ('Importer un .cdb…', None, self.importer_cdb)):
            if texte is None:
                bo.addSeparator(); continue
            a = QAction(texte, self)
            a.setIconText(texte)        # sinon Qt retire les « … » dans la barre d'outils
            if raccourci is not None:
                a.setShortcut(raccourci)
            a.triggered.connect(action)
            bo.addAction(a)
        # bouton « ? » calé à droite de la barre d'outils (pas de barre de menus)
        ressort = QWidget(); ressort.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bo.addWidget(ressort)
        self.action_a_propos = QAction('?', self)
        self.action_a_propos.setToolTip("À propos d'ELPRO Config")
        self.action_a_propos.triggered.connect(self.a_propos)
        bo.addAction(self.action_a_propos)

        self.etat = QLabel()
        self.etat.setTextFormat(Qt.RichText)
        self.etat.linkActivated.connect(lambda _: self._montrer_erreurs('Erreurs de configuration'))
        self.statusBar().addWidget(self.etat)
        # mention de copyright permanente, à droite de la barre d'état
        court = APP_COPYRIGHT.split(APP_COMPANY)[0] + APP_COMPANY          # « © 2026 Geoazimut SàRL »
        self.mention = QLabel(f'{court} — <a href="{APP_WEBSITE}" style="color:gray;">'
                              f'{site_affiche(APP_WEBSITE)}</a>')
        self.mention.setTextFormat(Qt.RichText)
        self.mention.setOpenExternalLinks(True)
        self.mention.setStyleSheet('color: gray;')
        f = self.mention.font(); f.setPointSize(8); self.mention.setFont(f)
        self.statusBar().addPermanentWidget(self.mention)
        self._minuterie = QTimer(self); self._minuterie.setSingleShot(True); self._minuterie.setInterval(150)
        self._minuterie.timeout.connect(self._valider_en_direct)

        self.page_config.modifie.connect(self._sur_modification)
        self.page_config.generer.connect(self.generer)
        self._charger(projet_vide(), None)

    def a_propos(self):
        AboutDialog(self, self.base).exec()

    # ================================================================ état du document
    def _charger(self, projet, chemin, modifie=False):
        self.chemin = chemin
        self.page_config.charger(projet)
        self.page_result.vider()
        self.onglets.setCurrentIndex(0)
        self.setWindowModified(modifie)
        self._titre()
        self._valider_en_direct()

    def _titre(self):
        nom = os.path.basename(self.chemin) if self.chemin else 'Sans titre'
        self.setWindowTitle(f'ELPRO Config {APP_VERSION} — {nom}[*]')

    def _sur_modification(self):
        self.setWindowModified(True)
        if self.page_result.plan is not None or not self.page_result.bandeau.isHidden():
            self.page_result.vider(modifiee=True)
        self._minuterie.start()

    def _erreurs(self):
        try:
            return M.valider(self.page_config.projet)
        except Exception as e:      # données inattendues (fichier édité à la main…)
            return [f'Projet illisible : {e}']

    def _valider_en_direct(self):
        n = len(self._erreurs())
        if n:
            self.etat.setText(f'<a href="#" style="color:#B00020;">{n} erreur{"s" if n > 1 else ""} — cliquer pour voir</a>')
        else:
            self.etat.setText('<span style="color:#2E7D32;">Configuration valide</span>')

    def _montrer_erreurs(self, titre):
        erreurs = self._erreurs()
        if erreurs:
            QMessageBox.warning(self, titre, '\n'.join(erreurs))
        return erreurs

    def _confirmer_abandon(self):
        """True si on peut abandonner le projet courant (enregistré, ou l'utilisateur accepte)."""
        if not self.isWindowModified():
            return True
        rep = QMessageBox.question(self, 'Modifications non enregistrées',
                                   'Le projet a été modifié. Enregistrer les modifications ?',
                                   QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if rep == QMessageBox.Save:
            return self.enregistrer()
        return rep == QMessageBox.Discard

    def closeEvent(self, e):
        if self._confirmer_abandon():
            e.accept()
        else:
            e.ignore()

    # ================================================================ barre d'outils
    def _dossier(self):
        d = QSettings().value('dossier_projet', '')
        # dossier mémorisé disparu (dossier renommé ou supprimé) : revenir aux projets d'exemple
        return d if d and os.path.isdir(d) else os.path.join(self.base, 'examples')

    def nouveau(self):
        if self._confirmer_abandon():
            self._charger(projet_vide(), None)

    def ouvrir(self):
        if not self._confirmer_abandon():
            return
        chemin, _ = QFileDialog.getOpenFileName(self, 'Ouvrir un projet', self._dossier(), FILTRE_PROJET)
        if chemin:
            self.ouvrir_fichier(chemin)

    def ouvrir_fichier(self, chemin):
        try:
            with open(chemin, encoding='utf-8') as f:
                projet = json.load(f)
            if not isinstance(projet, dict) or not isinstance(projet.get('systeme'), dict) \
                    or not isinstance(projet.get('radios'), list):
                raise ValueError('ce fichier n\'est pas un projet ELPRO Config (clés « systeme » et « radios » attendues).')
        except Exception as e:
            QMessageBox.critical(self, 'Ouvrir un projet', f'Impossible d\'ouvrir {os.path.basename(chemin)} :\n{e}')
            return
        QSettings().setValue('dossier_projet', os.path.dirname(chemin))
        self._charger(projet, chemin, modifie=self._normaliser(projet))

    @staticmethod
    def _normaliser(projet):
        """Mise à jour des projets d'un ancien format (ex. feu à 3 sorties -> orange clignotant).
        True si le projet a changé : il doit être réenregistré au nouveau format (la version ne change pas)."""
        avant = json.dumps(projet, sort_keys=True)
        M.normaliser_projet(projet)
        return json.dumps(projet, sort_keys=True) != avant

    def _dans_installation(self, chemin):
        """True si `chemin` est dans le dossier d'installation (Program Files : non inscriptible).
        Exécutable : dossier de l'.exe (self.base n'en est que le sous-dossier _internal)."""
        racine = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else self.base
        try:
            base = os.path.normcase(os.path.abspath(racine))
            return os.path.commonpath([base, os.path.normcase(os.path.abspath(chemin))]) == base
        except ValueError:          # lecteurs différents
            return False

    @staticmethod
    def _dossier_documents():
        """Documents\\ELPRO Config, créé au besoin."""
        d = os.path.join(QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation), 'ELPRO Config')
        os.makedirs(d, exist_ok=True)
        return d

    def enregistrer(self):
        # un fichier du dossier d'installation (ex. un exemple) ne peut pas être réécrit sur place
        if not self.chemin or self._dans_installation(self.chemin):
            return self.enregistrer_sous()
        return self._ecrire(self.chemin)

    def enregistrer_sous(self):
        dossier = os.path.dirname(self.chemin) if self.chemin else self._dossier()
        if self._dans_installation(dossier):
            dossier = self._dossier_documents()
        nom = os.path.join(dossier, M.nom_fichier(self.page_config.projet['systeme'].get('nom_projet')) + '.elpro.json')
        chemin, _ = QFileDialog.getSaveFileName(self, 'Enregistrer le projet', nom, FILTRE_PROJET)
        if not chemin:
            return False
        # le fichier se termine toujours par .elpro.json (Qt n'ajoute que « .json » avec ce filtre)
        bas = chemin.lower()
        if bas.endswith('.elpro.json'):
            pass
        elif bas.endswith('.json'):
            chemin = chemin[:-5] + '.elpro.json'
        else:
            chemin += '.elpro.json'
        return self._ecrire(chemin)

    def _ecrire(self, chemin):
        try:
            texte = json.dumps(self.page_config.projet, ensure_ascii=False, indent=2)
            with open(chemin, 'w', encoding='utf-8') as f:
                f.write(texte)
        except Exception as e:
            QMessageBox.critical(self, 'Enregistrer', f'Impossible d\'enregistrer :\n{e}')
            return False
        self.chemin = chemin
        QSettings().setValue('dossier_projet', os.path.dirname(chemin))
        self.setWindowModified(False)
        self._titre()
        self.statusBar().showMessage(f'Projet enregistré : {chemin}', 4000)
        return True

    def importer_cdb(self):
        if not self._confirmer_abandon():
            return
        chemin, _ = QFileDialog.getOpenFileName(self, 'Importer un .cdb', self._dossier(), 'CConfig (*.cdb)')
        if not chemin:
            return
        try:
            projet, avertissements = M.importer_cdb(chemin)
        except M.ProjetProtege:
            QMessageBox.warning(self, 'Importer un .cdb',
                                'Projet protégé par mot de passe : dans CConfig, enregistrer une copie sans protection')
            return
        except Exception as e:
            QMessageBox.critical(self, 'Importer un .cdb', f'Impossible de lire {os.path.basename(chemin)} :\n{e}')
            return
        QSettings().setValue('dossier_projet', os.path.dirname(chemin))
        self._normaliser(projet)
        self._charger(projet, None, modifie=True)
        if avertissements:
            QMessageBox.information(self, 'Import terminé', '\n'.join(avertissements))

    # ================================================================ génération
    def generer(self):
        # validation avant tout : la version ne doit pas augmenter sur un échec
        if self._montrer_erreurs('Configuration incomplète'):
            return
        projet = self.page_config.projet
        try:
            # version de configuration : comparaison avec la dernière génération et incrément automatique
            nouveau, niveau = M.preparer_generation(projet)
            plan = M.calculer_plan(nouveau)
        except Exception as e:
            QMessageBox.critical(self, 'Configuration incomplète', str(e))
            return
        # mise à jour sur place : les formulaires de la page 1 gardent leurs références vers le projet
        avant = json.dumps(projet, sort_keys=True)
        projet['version_config'] = nouveau['version_config']
        projet['derniere_generation'] = nouveau['derniere_generation']
        if json.dumps(projet, sort_keys=True) != avant:
            self.setWindowModified(True)        # le fichier .elpro.json doit être enregistré
        self.page_config.maj_version()
        self.page_result.afficher(plan)
        self.onglets.setCurrentIndex(1)
        detail = {None: 'aucune modification', 'mineure': 'modification mineure', 'majeure': 'modification majeure'}[niveau]
        self.statusBar().showMessage(f"Configuration générée — version V{plan['version_config']} ({detail})", 8000)
        # remarques du moteur (ex. RSSI retirés du tableau de bord de la base) : la génération reste valide
        if plan.get('avertissements'):
            QMessageBox.information(self, 'Configuration générée avec des remarques', '\n'.join(plan['avertissements']))
