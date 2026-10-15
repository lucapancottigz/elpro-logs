# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""Journal des événements de la période : Magasin.evenements (calculé dans un thread), filtres par
station, type de donnée et gravité, export CSV."""
import os, csv

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSettings
from PySide6.QtGui import QColor, QAction
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableView, QToolButton,
                               QMenu, QHeaderView, QFileDialog, QMessageBox)

import elpro_logs as L
from ui.common import COULEURS_GRAVITE, LIBELLES_GRAVITE, duree

COLONNES = ['Date et heure', 'Station', 'Événement', 'Durée']
FAMILLE_DONNEES = ('DONNEES', 'Données (trous)')


def textes_evenement(e):
    return [L.heure_locale(e['t']), e['station'] or '', e['message'], duree(e.get('duree'))]


class ModeleJournal(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self.ev = []

    def definir(self, ev):
        self.beginResetModel()
        self.ev = ev
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.ev)

    def columnCount(self, parent=QModelIndex()):
        return len(COLONNES)

    def headerData(self, s, o, role=Qt.DisplayRole):
        if o == Qt.Horizontal and role == Qt.DisplayRole:
            return COLONNES[s]
        return None

    def data(self, i, role=Qt.DisplayRole):
        e = self.ev[i.row()]
        if role == Qt.DisplayRole:
            return textes_evenement(e)[i.column()]
        if role == Qt.BackgroundRole:
            c = COULEURS_GRAVITE.get(e.get('gravite'))
            return QColor(c) if c else None
        if role == Qt.TextAlignmentRole and i.column() == 3:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None


class Filtre(QToolButton):
    """Bouton à menu de cases à cocher (« Stations ▾ »)."""

    def __init__(self, titre, rappel):
        super().__init__()
        self.titre = titre
        self.setPopupMode(QToolButton.InstantPopup)
        self.menu_ = QMenu(self)
        self.setMenu(self.menu_)
        self.rappel = rappel
        self.actions_ = {}

    def definir(self, elements, coches=None):
        """elements : [(code, libellé)] ; coches : codes cochés (None = tous)."""
        self.menu_.clear()
        self.actions_ = {}
        tout = QAction('Tout cocher', self)
        tout.triggered.connect(lambda: self._tous(True))
        rien = QAction('Tout décocher', self)
        rien.triggered.connect(lambda: self._tous(False))
        self.menu_.addAction(tout)
        self.menu_.addAction(rien)
        self.menu_.addSeparator()
        for code, lib in elements:
            a = QAction(lib, self)
            a.setCheckable(True)
            a.setChecked(coches is None or code in coches)
            a.toggled.connect(lambda _on: self._change())
            self.menu_.addAction(a)
            self.actions_[code] = a
        self._texte()

    def _tous(self, on):
        for a in self.actions_.values():
            a.blockSignals(True)
            a.setChecked(on)
            a.blockSignals(False)
        self._change()

    def _change(self):
        self._texte()
        self.rappel()

    def _texte(self):
        n, tot = len(self.coches()), len(self.actions_)
        self.setText(f'{self.titre} ({"toutes" if n == tot else f"{n}/{tot}"}) ▾')

    def coches(self):
        return [c for c, a in self.actions_.items() if a.isChecked()]

    def tous(self):
        return len(self.coches()) == len(self.actions_)

    def cocher(self, codes):
        for c, a in self.actions_.items():
            a.blockSignals(True)
            a.setChecked(c in codes)
            a.blockSignals(False)
        self._change()


class JournalView(QWidget):
    def __init__(self, onglet):
        super().__init__()
        self.onglet = onglet
        self.a_jour = False
        self._stations = None
        self._demande = None
        self.evenements = []                  # liste affichée (après filtre de gravité)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 0)
        haut = QHBoxLayout()
        haut.addWidget(QLabel('Filtres :'))
        self.f_stations = Filtre('Stations', self.actualiser)
        self.f_familles = Filtre('Types', self.actualiser)
        self.f_familles.definir([(f, l) for f, l, _g in L.FAMILLES] + [FAMILLE_DONNEES])
        self.f_gravite = Filtre('Gravité', self._filtrer_gravite)
        self.f_gravite.definir(list(LIBELLES_GRAVITE.items()))
        for f in (self.f_stations, self.f_familles, self.f_gravite):
            haut.addWidget(f)
        self.message = QLabel()
        self.message.setStyleSheet('color: gray;')
        haut.addSpacing(12)
        haut.addWidget(self.message)
        haut.addStretch(1)
        self.bouton_export = QPushButton('Exporter le journal (CSV)…')
        self.bouton_export.clicked.connect(self.exporter)
        haut.addWidget(self.bouton_export)
        lay.addLayout(haut)
        self.modele = ModeleJournal()
        self.table = QTableView()
        self.table.setModel(self.modele)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(22)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.doubleClicked.connect(self._double_clic)
        lay.addWidget(self.table)
        note = QLabel('Double-clic : graphiques de la station, une heure avant et après l\'événement.')
        note.setStyleSheet('color: gray;')
        lay.addWidget(note)
        self._brut = []

    def _maj_stations(self):
        cat = self.onglet.m.catalogue(self.onglet.sid, self.onglet.t1)
        noms = [S['nom'] for S in cat['stations']]
        if noms != self._stations:
            self._stations = noms
            self.f_stations.definir([(n, n) for n in noms])

    def actualiser(self):
        p = self.onglet.periode
        if p is None:
            self.message.setText('Aucun log importé.')
            self.modele.definir([])
            return
        self._maj_stations()
        stations = None if self.f_stations.tous() else tuple(self.f_stations.coches())
        familles = None if self.f_familles.tous() else tuple(self.f_familles.coches())
        self.message.setText('Calcul en cours…')
        sid = self.onglet.sid

        def calcul(m, t0, t1, s=stations, f=familles):
            if (s is not None and not s) or (f is not None and not f):
                return []
            return m.evenements(sid, t0, t1, stations=list(s) if s else None, familles=list(f) if f else None)
        self._demande = (stations, familles)
        self.onglet.demander('evenements', calcul,
                             lambda ev, t0, t1, d=self._demande: self._afficher(ev, t0, t1, d),
                             extra=(stations, familles), echec=lambda _m: self.message.setText('Calcul impossible.'))

    def _afficher(self, ev, t0, t1, demande=None):
        if self.onglet.periode != (t0, t1) or (demande is not None and demande != self._demande):
            return                      # résultat d'une période ou de filtres qui ont changé depuis
        self._brut = ev
        self._filtrer_gravite()

    def _filtrer_gravite(self):
        g = set(self.f_gravite.coches())
        self.evenements = [e for e in self._brut if e.get('gravite') in g]
        self.modele.definir(self.evenements)
        n = len(self.evenements)
        self.message.setText(f'{n} événement{"s" if n > 1 else ""}')

    def _double_clic(self, i):
        e = self.evenements[i.row()]
        self.onglet.ouvrir_detail(e['station'], e['t'] - 3600, e['t'] + 3600)

    def lignes(self):
        """Textes affichés (recette automatique)."""
        return [textes_evenement(e) for e in self.evenements]

    def exporter(self):
        if not self.evenements:
            QMessageBox.information(self, 'Exporter le journal', 'Aucun événement à exporter.')
            return
        s = QSettings()
        nom = f"Journal_{self.onglet.nom}_{L.heure_locale(self.onglet.t0, '%Y%m%d')}.csv".replace(' ', '_')
        chemin, _ = QFileDialog.getSaveFileName(self, 'Exporter le journal',
                                                os.path.join(s.value('dossier_export', '') or '', nom),
                                                'Fichier CSV (*.csv)')
        if not chemin:
            return
        if not chemin.lower().endswith('.csv'):
            chemin += '.csv'
        try:
            self.ecrire_csv(chemin)
        except OSError as e:
            QMessageBox.critical(self, 'Exporter le journal', f'Impossible d\'écrire le fichier :\n{e}')
            return
        s.setValue('dossier_export', os.path.dirname(chemin))
        self.window().statusBar().showMessage(f'Journal exporté : {chemin}', 6000)

    def ecrire_csv(self, chemin):
        """Séparateur « ; », UTF-8 avec BOM (lisible directement par Excel), mêmes colonnes que le tableau."""
        with open(chemin, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.writer(f, delimiter=';', lineterminator='\r\n')
            w.writerow(COLONNES)
            for e in self.evenements:
                w.writerow(textes_evenement(e))
