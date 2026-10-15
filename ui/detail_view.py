# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""Détail : à gauche, filtres par type et arbre Station › Famille › Canal ; à droite, graphiques empilés
à axe X commun (couloirs des états binaires, puis un graphique par unité), panneau des valeurs sous
le curseur et statistiques des canaux cochés. Les valeurs viennent de Magasin.courbe / segments_decodes."""
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QCheckBox,
                               QTreeWidget, QTreeWidgetItem, QSplitter, QGroupBox, QTableWidget, QHeaderView,
                               QStackedWidget, QScrollArea)

import elpro_logs as L
from ui.common import (AxeHeureSuisse, COULEURS_COULOIRS, PALETTE, cellule, preparer_tableau, nombre, duree,
                       nom_canal, GRIS)

MAX_CONSEILLE = 30
FAMILLES_PAR_DEFAUT = {f for f, _l, _g in L.FAMILLES} - {'ECHECS', 'AUTRES'}
LIBELLE_FAMILLE = {f: l for f, l, _g in L.FAMILLES}
GENRE_FAMILLE = {g: f for f, _l, gs in L.FAMILLES for g in gs}
NOEUD_AUTRES = 'Autres registres'
ROLE_REGISTRE = Qt.UserRole
ROLE_STATION = Qt.UserRole + 1
ROLE_GENRE = Qt.UserRole + 2
FOND_TROU = (176, 176, 176, 70)
FOND_PERTE = (211, 47, 47, 38)
LARGEUR_AXE = 210


def couleur_couloir(c):
    g = c['genre']
    return COULEURS_COULOIRS.get(g, COULEURS_COULOIRS['COMFLAG'] if g.startswith('FAIL_') else GRIS)


def plein(c, v):
    """Couloir plein quand la valeur vaut 1 ; secteur : plein quand il est absent (valeur 0)."""
    return v == 0 if c['genre'] == 'MAINV' else bool(v)


def texte_valeur(c, v):
    if v is None:
        return 'pas de données'
    if c['binaire']:
        return str(v)
    return f"{nombre(v)} {c['unite']}".strip()


class DetailView(QWidget):
    selection_changee = Signal()

    def __init__(self, onglet):
        super().__init__()
        self.onglet = onglet
        self.a_jour = False
        self.cat = None
        self.coches = set()                 # registres cochés
        self.familles = set(FAMILLES_PAR_DEFAUT)
        self.plots = []
        self.curseurs = []
        self.courbes = []                   # [(canal, PlotDataItem)]
        self._fenetre_courbes = None        # (a, b) des données chargées pour les courbes
        self._x_curseur = None

        sep = QSplitter(Qt.Horizontal)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.addWidget(sep)

        # ============ gauche : sélection
        gauche = QWidget()
        g = QVBoxLayout(gauche)
        g.setContentsMargins(0, 0, 0, 0)
        boite = QGroupBox('Types de données')
        grille = QGridLayout(boite)
        grille.setContentsMargins(6, 4, 6, 4)
        grille.setVerticalSpacing(2)
        self.cases_familles = {}
        for k, (f, lib, _g) in enumerate(L.FAMILLES):
            cb = QCheckBox(lib)
            cb.setChecked(f in self.familles)
            cb.toggled.connect(lambda on, f=f: self._filtre(f, on))
            grille.addWidget(cb, k // 2, k % 2)
            self.cases_familles[f] = cb
        g.addWidget(boite)
        self.arbre = QTreeWidget()
        self.arbre.setHeaderLabels(['Canal', 'Nom'])
        self.arbre.setColumnWidth(0, 230)
        self.arbre.itemChanged.connect(self._item_change)
        g.addWidget(self.arbre, 1)
        bs = QGridLayout()
        b1 = QPushButton('Toute la station')
        b1.setToolTip('Coche tous les canaux visibles de la station sélectionnée')
        b1.clicked.connect(self.toute_la_station)
        b2 = QPushButton('Même donnée, toutes les stations')
        b2.setToolTip('Coche le même type de donnée pour toutes les stations (ex. toutes les batteries)')
        b2.clicked.connect(self.meme_donnee)
        b3 = QPushButton('Tout décocher')
        b3.clicked.connect(self.tout_decocher)
        bs.addWidget(b1, 0, 0)
        bs.addWidget(b3, 0, 1)
        bs.addWidget(b2, 1, 0, 1, 2)
        g.addLayout(bs)
        self.avertissement = QLabel()
        self.avertissement.setWordWrap(True)
        self.avertissement.setStyleSheet('color: #EF6C00;')
        g.addWidget(self.avertissement)
        sep.addWidget(gauche)

        # ============ droite : graphiques
        droite = QWidget()
        d = QVBoxLayout(droite)
        d.setContentsMargins(0, 0, 0, 0)
        outils = QHBoxLayout()
        self.message = QLabel()
        self.message.setStyleSheet('color: gray;')
        outils.addWidget(self.message)
        outils.addStretch(1)
        aide = QLabel('Molette : zoom · clic-glisser : défilement · clic sur la légende : masquer/afficher')
        aide.setStyleSheet('color: gray;')
        outils.addWidget(aide)
        self.bouton_vue = QPushButton('Utiliser cette vue comme période')
        self.bouton_vue.clicked.connect(self.vue_comme_periode)
        outils.addWidget(self.bouton_vue)
        d.addLayout(outils)

        vert = QSplitter(Qt.Vertical)
        horiz = QSplitter(Qt.Horizontal)
        self.pile = QStackedWidget()
        self.vide = QLabel('Cochez des canaux dans l\'arbre de gauche pour afficher leurs graphiques.')
        self.vide.setAlignment(Qt.AlignCenter)
        self.vide.setStyleSheet('color: gray;')
        self.pile.addWidget(self.vide)
        self.defilement = QScrollArea()
        self.defilement.setWidgetResizable(True)
        self.graphiques = pg.GraphicsLayoutWidget()
        self.graphiques.ci.setSpacing(2)
        self.defilement.setWidget(self.graphiques)
        self.pile.addWidget(self.defilement)
        horiz.addWidget(self.pile)
        panneau = QWidget()
        p = QVBoxLayout(panneau)
        p.setContentsMargins(0, 0, 0, 0)
        self.titre_valeurs = QLabel('Valeurs sous le curseur')
        self.titre_valeurs.setStyleSheet('font-weight: bold;')
        p.addWidget(self.titre_valeurs)
        self.valeurs = QTreeWidget()
        self.valeurs.setHeaderLabels(['Canal', 'Valeur'])
        self.valeurs.setRootIsDecorated(False)
        self.valeurs.setColumnWidth(0, 190)
        p.addWidget(self.valeurs)
        horiz.addWidget(panneau)
        horiz.setStretchFactor(0, 4)
        horiz.setStretchFactor(1, 1)
        horiz.setSizes([900, 280])
        vert.addWidget(horiz)
        self.stats = preparer_tableau(QTableWidget(), ['Canal', 'Station', 'Min', 'Moyenne', 'Max',
                                                       'Activations', 'Durée active'])
        self.stats.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        vert.addWidget(self.stats)
        vert.setSizes([600, 160])
        d.addWidget(vert, 1)
        sep.addWidget(droite)
        sep.setSizes([330, 1000])
        sep.setStretchFactor(1, 1)

        self._tracer_bientot = QTimer(self)
        self._tracer_bientot.setSingleShot(True)
        self._tracer_bientot.setInterval(150)
        self._tracer_bientot.timeout.connect(self.tracer)
        self._valeurs_bientot = QTimer(self)
        self._valeurs_bientot.setSingleShot(True)
        self._valeurs_bientot.setInterval(60)
        self._valeurs_bientot.timeout.connect(self._maj_valeurs)
        self._recharger_bientot = QTimer(self)
        self._recharger_bientot.setSingleShot(True)
        self._recharger_bientot.setInterval(250)
        self._recharger_bientot.timeout.connect(self._recharger_courbes)
        self.graphiques.scene().sigMouseMoved.connect(self._souris)

    # ================================================================ données
    @property
    def m(self):
        return self.onglet.m

    def actualiser(self):
        """Période ou données changées : catalogue de la config en vigueur à la fin, arbre, graphiques."""
        p = self.onglet.periode
        self.cat = self.m.catalogue(self.onglet.sid, p[1] if p else None)
        self.coches &= set(self.cat['par_registre'])
        self._remplir_arbre()
        self.tracer()

    def tous_canaux(self):
        """Canaux du catalogue, dans l'ordre de l'arbre (stations puis autres registres)."""
        if self.cat is None:
            return []
        return [c for S in self.cat['stations'] for c in S['canaux']] + list(self.cat['autres'])

    def canaux_affiches(self):
        """Canaux cochés dont le type de donnée est affiché (ce qui est tracé et exporté)."""
        return [c for c in self.tous_canaux() if c['registre'] in self.coches and c['famille'] in self.familles]

    # ================================================================ arbre
    def _remplir_arbre(self):
        a = self.arbre
        a.blockSignals(True)
        a.clear()
        gris = QBrush(QColor(GRIS))
        if self.cat:
            for S in self.cat['stations']:
                st = QTreeWidgetItem([S['nom'], ''])
                st.setData(0, ROLE_STATION, S['nom'])
                st.setFlags(st.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
                for f, lib, _g in L.FAMILLES:
                    if f not in self.familles:
                        continue
                    cs = [c for c in S['canaux'] if c['famille'] == f]
                    if not cs:
                        continue
                    fi = QTreeWidgetItem([lib, ''])
                    fi.setData(0, ROLE_STATION, S['nom'])
                    fi.setFlags(fi.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
                    for c in cs:
                        fi.addChild(self._item_canal(c, gris))
                    st.addChild(fi)
                if st.childCount():
                    a.addTopLevelItem(st)
                    st.setExpanded(True)
                    for k in range(st.childCount()):
                        st.child(k).setExpanded(True)
            if 'AUTRES' in self.familles and self.cat['autres']:
                au = QTreeWidgetItem([NOEUD_AUTRES, ''])
                au.setToolTip(0, 'Colonnes du log que la configuration n\'utilise pas (gardées pour avoir toutes les valeurs)')
                au.setFlags(au.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
                for c in self.cat['autres']:
                    au.addChild(self._item_canal(c, gris))
                a.addTopLevelItem(au)
        a.blockSignals(False)
        self._maj_avertissement()

    def _item_canal(self, c, gris):
        it = QTreeWidgetItem([c['libelle'], c['nom']])
        it.setData(0, ROLE_REGISTRE, c['registre'])
        it.setData(0, ROLE_STATION, c['station'])
        it.setData(0, ROLE_GENRE, c['genre'])
        it.setForeground(1, gris)
        it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
        it.setCheckState(0, Qt.Checked if c['registre'] in self.coches else Qt.Unchecked)
        return it

    def _items_canaux(self):
        res = []

        def parcourir(it):
            if it.data(0, ROLE_REGISTRE) is not None:
                res.append(it)
            for k in range(it.childCount()):
                parcourir(it.child(k))
        for k in range(self.arbre.topLevelItemCount()):
            parcourir(self.arbre.topLevelItem(k))
        return res

    def _item_change(self, it, col):
        r = it.data(0, ROLE_REGISTRE)
        if col != 0 or r is None:
            return
        if it.checkState(0) == Qt.Checked:
            self.coches.add(r)
        else:
            self.coches.discard(r)
        self._selection_modifiee()

    def _selection_modifiee(self):
        self._maj_avertissement()
        self._tracer_bientot.start()
        self.selection_changee.emit()
        self.onglet.export_change.emit()

    def _maj_avertissement(self):
        n = len(self.canaux_affiches())
        self.avertissement.setText(f'{n} canaux cochés : au-delà de {MAX_CONSEILLE}, l\'affichage devient '
                                   f'chargé et plus lent.' if n > MAX_CONSEILLE else '')

    def _cocher(self, predicat, etat=True):
        """Coche (ou décoche) les canaux visibles qui satisfont predicat(item)."""
        self.arbre.blockSignals(True)
        for it in self._items_canaux():
            if predicat(it):
                it.setCheckState(0, Qt.Checked if etat else Qt.Unchecked)
                (self.coches.add if etat else self.coches.discard)(it.data(0, ROLE_REGISTRE))
        self.arbre.blockSignals(False)
        self.arbre.viewport().update()
        self._selection_modifiee()

    def _filtre(self, f, on):
        (self.familles.add if on else self.familles.discard)(f)
        self._remplir_arbre()
        self._selection_modifiee()

    def toute_la_station(self):
        it = self.arbre.currentItem()
        if it is None:
            return
        while it.parent() is not None:
            it = it.parent()
        st = it.data(0, ROLE_STATION)
        self._cocher(lambda x: x.data(0, ROLE_STATION) == st)

    def meme_donnee(self):
        it = self.arbre.currentItem()
        if it is None or it.data(0, ROLE_GENRE) is None:
            return
        g = it.data(0, ROLE_GENRE)
        self._cocher(lambda x: x.data(0, ROLE_GENRE) == g)

    def tout_decocher(self):
        self.coches.clear()
        self._cocher(lambda x: True, False)

    def cocher_station(self, station):
        """Depuis la Vue globale ou le Journal : cette station seule, toutes familles sauf les registres
        non attribués."""
        tout = {f for f, _l, _g in L.FAMILLES} - {'AUTRES'}
        for f, cb in self.cases_familles.items():
            cb.blockSignals(True)
            cb.setChecked(f in tout)
            cb.blockSignals(False)
        self.familles = tout
        if self.cat is None:
            p = self.onglet.periode
            self.cat = self.m.catalogue(self.onglet.sid, p[1] if p else None)
        self.coches = {c['registre'] for S in self.cat['stations'] if S['nom'] == station for c in S['canaux']}
        self.a_jour = False
        if self.isVisible():
            self.a_jour = True
            self.actualiser()
        self.onglet.export_change.emit()

    # ================================================================ graphiques
    def _nouveau_plot(self, row, titre=None):
        p = self.graphiques.addPlot(row=row, col=0, axisItems={'bottom': AxeHeureSuisse()})
        p.setMenuEnabled(False)
        p.hideButtons()
        p.showGrid(x=True, y=True, alpha=0.15)
        p.getAxis('left').setWidth(LARGEUR_AXE)
        vb = p.getViewBox()
        vb.setMouseEnabled(x=True, y=False)
        if titre:
            p.setTitle(titre, size='9pt', justify='left')
        if self.plots:
            p.setXLink(self.plots[0])
        ligne = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('#455A64', width=1))
        ligne.setZValue(50)
        ligne.hide()
        p.addItem(ligne, ignoreBounds=True)
        self.curseurs.append(ligne)
        self.plots.append(p)
        return p

    def _fonds(self, p, trous, pertes):
        for zones, couleur in ((trous, FOND_TROU), (pertes, FOND_PERTE)):
            for a, b in zones:
                r = pg.LinearRegionItem(values=(a, b), movable=False, brush=pg.mkBrush(*couleur),
                                        pen=pg.mkPen(None))
                r.setZValue(-10)
                for ln in r.lines:
                    ln.setPen(pg.mkPen(None))
                    ln.setHoverPen(pg.mkPen(None))
                p.addItem(r, ignoreBounds=True)

    def _pertes_comm(self, canaux, t0, t1):
        """Pertes de comm des stations affichées (segments à 1 du COMFLAG de chaque station)."""
        stations = {c['station'] for c in canaux if c['station']}
        res = []
        for S in self.cat['stations']:
            if S['nom'] not in stations:
                continue
            for c in S['canaux']:
                if c['genre'] == 'COMFLAG':
                    res += [(a, b) for a, b, v in self.m.segments_decodes(self.onglet.sid, c, t0, t1) if v]
        return res

    def _largeur_px(self):
        return max(300, self.graphiques.width() - LARGEUR_AXE - 20)

    def tracer(self):
        self.graphiques.clear()
        self.plots, self.curseurs, self.courbes = [], [], []
        self._fenetre_courbes = None
        self.valeurs.clear()
        canaux = self.canaux_affiches()
        p = self.onglet.periode
        self.bouton_vue.setEnabled(bool(canaux) and p is not None)
        if not canaux or p is None:
            self.pile.setCurrentWidget(self.vide)
            self.vide.setText('Aucun log importé.' if p is None else
                              'Cochez des canaux dans l\'arbre de gauche pour afficher leurs graphiques.')
            self.stats.setRowCount(0)
            return
        self.pile.setCurrentWidget(self.defilement)
        sid = self.onglet.sid
        t0, t1 = p
        trous = self.m.trous(sid, t0, t1)
        pertes = self._pertes_comm(canaux, t0, t1)
        hauteur = 0

        # --- 1. états binaires : couloirs
        binaires = [c for c in canaux if c['binaire']]
        if binaires:
            pl = self._nouveau_plot(0, 'États')
            pl.getViewBox().invertY(True)
            pl.showGrid(x=True, y=False)
            for k, c in enumerate(binaires):
                segs = self.m.segments_decodes(sid, c, t0, t1)
                actifs = [(a, b) for a, b, v in segs if v is not None and plein(c, v)]
                if actifs:
                    x0 = np.array([a for a, _b in actifs], dtype=float)
                    w = np.array([b - a for a, b in actifs], dtype=float)
                    pl.addItem(pg.BarGraphItem(x0=x0, width=w, y0=np.full(len(actifs), k - 0.35), height=0.7,
                                               brush=pg.mkBrush(couleur_couloir(c)), pen=pg.mkPen(None)))
            pl.getAxis('left').setTicks([[(k, nom_canal(c)) for k, c in enumerate(binaires)]])
            pl.setYRange(-0.5, len(binaires) - 0.5, padding=0)
            h = 40 + 20 * len(binaires)
            pl.setMinimumHeight(h)
            pl.setMaximumHeight(h + 10)
            hauteur += h
            self._fonds(pl, trous, pertes)

        # --- 2. un graphique par (type de donnée, unité)
        groupes = {}
        for c in canaux:
            if not c['binaire']:
                groupes.setdefault((c['famille'], c['unite']), []).append(c)
        n_max = self._largeur_px() * 2
        couleur = 0
        for (f, unite), cs in groupes.items():
            titre = LIBELLE_FAMILLE[f] + (f' ({unite})' if unite else '')
            pl = self._nouveau_plot(len(self.plots), titre)
            pl.addLegend(offset=(8, 4), labelTextSize='8pt', brush=pg.mkBrush(255, 255, 255, 200))
            vb = pl.getViewBox()
            vb.setAutoVisible(y=True)
            vb.enableAutoRange(axis='y')
            if unite:
                pl.getAxis('left').setLabel(unite)
            for c in cs:
                xs, ys = self._donnees_courbe(c, t0, t1, n_max)
                coul = PALETTE[couleur % len(PALETTE)]
                couleur += 1
                it = pl.plot(xs, ys, pen=pg.mkPen(coul, width=1.5), name=nom_canal(c), connect='finite')
                self.courbes.append((c, it))
            seuils = set()
            for c in cs:
                if c['genre'] == 'BATTV':
                    seuils.add(L.BATTV_BAS)
                elif c['genre'] == 'RSSI':
                    seuils.add(L.RSSI_FAIBLE)
                elif c['genre'] == 'RADAR' and c.get('seuil_haut') is not None:
                    seuils.add(c['seuil_haut'])
            for s in sorted(seuils):
                pl.addItem(pg.InfiniteLine(pos=s, angle=0, movable=False,
                                           pen=pg.mkPen('#B71C1C', width=1, style=Qt.DashLine),
                                           label=f'{nombre(s)} {unite}'.strip(),
                                           labelOpts={'position': 0.02, 'color': '#B71C1C', 'anchors': [(0, 1), (0, 1)]}))
            pl.setMinimumHeight(170)
            hauteur += 170
            self._fonds(pl, trous, pertes)

        for pl in self.plots[:-1]:
            pl.getAxis('bottom').setStyle(showValues=False)
        self.graphiques.setMinimumHeight(hauteur + 30)
        self.plots[0].getViewBox().sigXRangeChanged.connect(lambda *_: self._recharger_bientot.start())
        self.plots[0].setXRange(t0, t1, padding=0)
        self._fenetre_courbes = (t0, t1)
        if self._x_curseur is not None and t0 <= self._x_curseur < t1:
            self.placer_curseur(self._x_curseur)          # le curseur reste en place après un retraçage
        else:
            self._x_curseur = None
            self._remplir_valeurs(None)
        self._stats(canaux)

    @staticmethod
    def _tableaux(xs, ys):
        x = np.array(xs, dtype=float)
        y = np.array([np.nan if v is None else v for v in ys], dtype=float)
        return x, y

    def _donnees_courbe(self, c, a, b, n_max):
        r = self.m.courbe(self.onglet.sid, c, a, b, n_max=n_max)
        if not r or not r[0]:
            return np.array([], dtype=float), np.array([], dtype=float)
        return self._tableaux(*r)

    def _recharger_courbes(self):
        """Après un zoom : recharge les courbes plus finement sur la zone visible (avec une marge)."""
        if not self.plots or not self.courbes or self.onglet.periode is None:
            return
        t0, t1 = self.onglet.periode
        xa, xb = self.plots[0].getViewBox().viewRange()[0]
        w = xb - xa
        fa, fb = self._fenetre_courbes or (t0, t1)
        if xa >= fa and xb <= fb and w >= (fb - fa) / 4:
            return                                 # résolution encore suffisante
        a, b = int(max(t0, xa - w)), int(min(t1, xb + w))
        if b <= a:
            return
        n_max = self._largeur_px() * 2 * max(1, int(round((b - a) / max(w, 1))))
        for c, it in self.courbes:
            x, y = self._donnees_courbe(c, a, b, n_max)
            it.setData(x, y, connect='finite')
        self._fenetre_courbes = (a, b)

    def vue_comme_periode(self):
        if self.plots:
            xa, xb = self.plots[0].getViewBox().viewRange()[0]
            self.onglet.definir_periode(int(xa), int(xb))

    # ================================================================ curseur et valeurs
    def _souris(self, pos):
        for p in self.plots:
            if p.getViewBox().sceneBoundingRect().contains(pos):
                x = p.getViewBox().mapSceneToView(pos).x()
                self.placer_curseur(x)
                return

    def placer_curseur(self, x):
        self._x_curseur = int(x)
        for ln in self.curseurs:
            ln.setPos(x)
            ln.show()
        self._valeurs_bientot.start()

    def _maj_valeurs(self):
        self._remplir_valeurs(self._x_curseur)

    def valeurs_au(self, t):
        """[(canal, valeur)] à l'instant t (valeur None = pas de données)."""
        res = []
        for c in self.canaux_affiches():
            s = self.m.segments_decodes(self.onglet.sid, c, t, t + 1)
            res.append((c, s[0][2] if s else None))
        return res

    def _remplir_valeurs(self, t):
        self.valeurs.clear()
        if t is None:
            self.titre_valeurs.setText('Valeurs sous le curseur')
            return
        self.titre_valeurs.setText(f'Valeurs au {L.heure_locale(t)}')
        for c, v in self.valeurs_au(t):
            it = QTreeWidgetItem([nom_canal(c), texte_valeur(c, v)])
            it.setToolTip(0, f"{nom_canal(c)} ({c['nom']})")
            if v is None:
                it.setForeground(1, QBrush(QColor(GRIS)))
            self.valeurs.addTopLevelItem(it)

    # ================================================================ statistiques
    def _stats(self, canaux):
        self.stats.setRowCount(0)
        for c in canaux:
            k = self.stats.rowCount()
            self.stats.insertRow(k)
            self.stats.setItem(k, 0, cellule(c['libelle']))
            self.stats.setItem(k, 1, cellule(c['station'] or ''))
        self.onglet.demander_global(lambda res, t0, t1, cs=canaux: self._remplir_stats(res, t0, t1, cs))

    def _remplir_stats(self, res, t0, t1, canaux):
        if self.onglet.periode != (t0, t1) or canaux != self.canaux_affiches():
            return                      # période ou sélection changée pendant le calcul
        par_reg = {r['canal']['registre']: r for st in res['synthese']['stations'] for r in st['canaux']}
        for k, c in enumerate(canaux):
            r = par_reg.get(c['registre'])
            if r is None:
                continue
            u = f" {c['unite']}" if c['unite'] else ''
            if c['binaire']:
                vals = ['', '', '', str(r.get('nb_activations', '')), duree(r.get('duree_active'))]
            else:
                vals = [nombre(r.get('min')) + u if r.get('min') is not None else '',
                        nombre(r.get('moyenne')) + u if r.get('moyenne') is not None else '',
                        nombre(r.get('max')) + u if r.get('max') is not None else '', '', '']
            for j, v in enumerate(vals):
                self.stats.setItem(k, 2 + j, cellule(v, droite=True))
