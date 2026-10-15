# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""Fichiers : logs importés, versions de configuration, liste de log utilisée pour les imports."""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QHeaderView,
                               QSplitter)
from PySide6.QtCore import Qt

import elpro_logs as L
from ui.common import cellule, preparer_tableau, FOND_GRISE


def _titre(texte):
    l = QLabel(texte)
    l.setStyleSheet('font-weight: bold; margin-top: 4px;')
    return l


class FilesView(QWidget):
    def __init__(self, onglet):
        super().__init__()
        self.onglet = onglet
        self.a_jour = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 0)
        b = QHBoxLayout()
        f = onglet.fenetre
        for texte, action in (('Importer des logs…', f.importer_logs),
                              ('Mettre à jour la configuration…', f.mettre_a_jour_config),
                              ('Liste de log (XML)…', f.liste_log_xml)):
            bt = QPushButton(texte)
            bt.clicked.connect(lambda _=False, a=action: a())
            b.addWidget(bt)
        b.addStretch(1)
        lay.addLayout(b)

        sep = QSplitter(Qt.Vertical)
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(_titre('Logs importés'))
        self.logs = preparer_tableau(QTableWidget(), ['Fichier', 'N° de série', 'Du', 'Au', 'Lignes',
                                                      'Lignes gardées', 'Importé le'])
        self.logs.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        v.addWidget(self.logs)
        sep.addWidget(w)

        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(_titre('Versions de configuration'))
        self.configs = preparer_tableau(QTableWidget(), ['Version', 'En service depuis', 'Importée le'])
        self.configs.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        v.addWidget(self.configs)
        sep.addWidget(w)

        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(_titre('Liste de log'))
        self.type_liste = QLabel()
        v.addWidget(self.type_liste)
        self.liste = preparer_tableau(QTableWidget(), ['Nom', '1er registre', 'Nombre'])
        self.liste.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        v.addWidget(self.liste)
        sep.addWidget(w)
        sep.setSizes([300, 120, 220])
        lay.addWidget(sep, 1)

    def actualiser(self):
        m, sid = self.onglet.m, self.onglet.sid
        self.logs.setRowCount(0)
        for fi in m.fichiers(sid):
            k = self.logs.rowCount()
            self.logs.insertRow(k)
            partiel = fi['nb_lignes_gardees'] < fi['nb_lignes']        # lignes déjà présentes
            style = {'fond': FOND_GRISE, 'italique': True} if partiel else {}
            for j, (v, droite) in enumerate(((fi['nom'], False), (fi['serie'] or '', False),
                                             (L.heure_locale(fi['t_debut']), False),
                                             (L.heure_locale(fi['t_fin']), False), (fi['nb_lignes'], True),
                                             (fi['nb_lignes_gardees'], True),
                                             (L.heure_locale(fi['importe_le']), False))):
                self.logs.setItem(k, j, cellule(v, droite=droite, **style))
        self.configs.setRowCount(0)
        for c in m.configs(sid):
            k = self.configs.rowCount()
            self.configs.insertRow(k)
            self.configs.setItem(k, 0, cellule(f"V{c['version']}"))
            self.configs.setItem(k, 1, cellule('origine' if c['valable_depuis'] == 0
                                               else L.heure_locale(c['valable_depuis'])))
            self.configs.setItem(k, 2, cellule(L.heure_locale(c['importe_le'])))
        p = m.profil(sid)
        if p is None:
            self.type_liste.setText('Standard GeoAzimut')
            entrees = L.LISTE_STANDARD
        else:
            self.type_liste.setText('Propre à cette centrale (XML importé)')
            entrees = [(nom, v[0], v[1]) if isinstance(v, (list, tuple)) else (nom, v, '') for nom, v in p.items()]
        self.liste.setRowCount(0)
        for nom, reg, n in entrees:
            k = self.liste.rowCount()
            self.liste.insertRow(k)
            self.liste.setItem(k, 0, cellule(nom))
            self.liste.setItem(k, 1, cellule(reg, droite=True))
            self.liste.setItem(k, 2, cellule(n, droite=True))
