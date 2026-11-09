# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""Mise à jour automatique (v1.5) : recherche et téléchargement dans des threads, fenêtre « Mise à jour disponible ».
Le travail réseau est fait par engine/updater.py (fichier de l'ingénieur, identique dans ELPRO Config)."""
from PySide6.QtCore import Qt, QThread, Signal, QSettings, QEventLoop
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextBrowser, QPushButton,
                               QProgressDialog, QMessageBox)

import updater as U
from ui.workers import _garder
from version import APP_VERSION

APP = 'ELPRO Logs'
DEPOT = U.DEPOT_LOGS
PREFIXE = U.PREFIXE_LOGS
ANNULE = 'Téléchargement annulé.'


class RechercheMaj(QThread):
    """U.chercher() hors du thread de l'interface. fini(info ou None, message d'erreur ou '')."""
    fini = Signal(object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        _garder(self)                           # attendu par attendre_tous() à la fermeture

    def run(self):
        try:
            info = U.chercher(DEPOT, U.version_pour_recherche(APP_VERSION), PREFIXE)
        except U.ErreurMiseAJour as e:
            self.fini.emit(None, str(e))
        except Exception as e:                  # imprévu : traité comme une erreur réseau, jamais de plantage
            self.fini.emit(None, f'Recherche de mise à jour impossible : {e}')
        else:
            self.fini.emit(info, '')


class TelechargementMaj(QThread):
    """U.telecharger() hors du thread de l'interface. progression(reçus, total) ; fini(chemin ou '', erreur ou '')."""
    progression = Signal(int, int)
    fini = Signal(str, str)

    def __init__(self, info, parent=None):
        super().__init__(parent)
        self.info = info
        self._annule = False
        _garder(self)

    def annuler(self):
        self._annule = True

    def run(self):
        try:
            chemin = U.telecharger(self.info, progression=lambda r, t: self.progression.emit(r, t),
                                   annule=lambda: self._annule)
        except U.ErreurMiseAJour as e:
            self.fini.emit('', str(e))
        except Exception as e:
            self.fini.emit('', f'Téléchargement impossible : {e}')
        else:
            self.fini.emit(chemin, '')


class FenetreMaj(QDialog):
    """« Mise à jour disponible » : notes de la version, Installer et redémarrer / Plus tard / Ignorer cette version."""

    def __init__(self, parent, info):
        super().__init__(parent)
        self.info = info
        self.setWindowTitle('Mise à jour disponible')
        self.resize(560, 420)
        lay = QVBoxLayout(self)
        self.entete = QLabel(f"{APP} {info['version']} est disponible. Version installée : {APP_VERSION}.")
        self.entete.setWordWrap(True)
        lay.addWidget(self.entete)
        self.notes = QTextBrowser()
        self.notes.setOpenExternalLinks(True)
        self.notes.setMarkdown(info['notes'] or 'Pas de notes pour cette version.')
        self.notes.setMinimumHeight(220)
        lay.addWidget(self.notes, 1)
        lien = QLabel(f'<a href="{info["page"]}">Voir la page de la version</a>')
        lien.setTextFormat(Qt.RichText)
        lien.setOpenExternalLinks(True)
        lay.addWidget(lien)
        h = QHBoxLayout()
        h.addStretch(1)
        self.bouton_installer = QPushButton('Installer et redémarrer')
        self.bouton_installer.setDefault(True)
        self.bouton_installer.clicked.connect(self.installer)
        self.bouton_plus_tard = QPushButton('Plus tard')
        self.bouton_plus_tard.clicked.connect(self.reject)
        self.bouton_ignorer = QPushButton('Ignorer cette version')
        self.bouton_ignorer.clicked.connect(self.ignorer)
        for b in (self.bouton_installer, self.bouton_plus_tard, self.bouton_ignorer):
            h.addWidget(b)
        lay.addLayout(h)

    def ignorer(self):
        QSettings().setValue('maj/version_ignoree', self.info['version'])
        self.reject()

    def installer(self):
        """Téléchargement (barre annulable, en Mo), puis parent.installer_maj(chemin) si l'empreinte est bonne."""
        parent = self.parentWidget()
        self.accept()
        t = TelechargementMaj(self.info)
        d = QProgressDialog('Téléchargement de la mise à jour…', 'Annuler', 0, 0, parent)
        d.setWindowTitle('Mise à jour')
        d.setWindowModality(Qt.WindowModal)
        d.setMinimumDuration(0)
        d.setAutoClose(False)
        d.setAutoReset(False)
        d.canceled.connect(t.annuler)

        def avance(recus, total):
            if total:
                d.setMaximum(total)
                d.setValue(min(recus, total))
            d.setLabelText(f'Téléchargement de la mise à jour…\n'
                           f'{recus / 1e6:.1f} Mo sur {total / 1e6:.1f} Mo'.replace('.', ','))
        resultat = {}
        t.progression.connect(avance)
        t.fini.connect(lambda chemin, erreur: resultat.update(chemin=chemin, erreur=erreur))
        boucle = QEventLoop()
        t.finished.connect(boucle.quit)
        t.start()
        boucle.exec()
        t.wait()
        d.canceled.disconnect(t.annuler)
        d.close()
        erreur = resultat.get('erreur', '')
        if erreur:
            if erreur != ANNULE:
                QMessageBox.warning(parent, 'Mise à jour', erreur)
        elif resultat.get('chemin'):
            parent.installer_maj(resultat['chemin'])
