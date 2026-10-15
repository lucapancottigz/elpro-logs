# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""Vue globale : chiffres clés, frise des états (une ligne par station + Système), tableau de synthèse.
Tous les chiffres viennent de Magasin.synthese / etat_stations / etat_systeme (calculés dans un thread)."""
import bisect

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSplitter, QTableWidget,
                               QHeaderView, QToolTip, QSizePolicy)

import elpro_logs as L
from ui.common import AxeHeureSuisse, cellule, preparer_tableau, nombre, duree, pluriel, ROUGE, ORANGE, JAUNE

LIGNE_SYSTEME = 'Système'


class VueFrise(pg.ViewBox):
    """ViewBox de la frise : clic-glisser horizontal = sélection d'une nouvelle période ; pas de molette."""
    zoom = Signal(float, float)

    def __init__(self):
        super().__init__(enableMouse=False, enableMenu=False)
        self.selection = pg.LinearRegionItem(movable=False, brush=pg.mkBrush(25, 118, 210, 50),
                                             pen=pg.mkPen('#1976D2'))
        self.selection.setZValue(100)
        self.selection.hide()
        self.addItem(self.selection, ignoreBounds=True)
        self._debut = None

    def mouseDragEvent(self, ev, axis=None):
        if ev.button() != Qt.LeftButton:
            ev.ignore()
            return
        ev.accept()
        x = self.mapSceneToView(ev.scenePos()).x()
        if ev.isStart():
            self._debut = self.mapSceneToView(ev.buttonDownScenePos()).x()
            self.selection.show()
        if self._debut is None:
            return
        self.selection.setRegion((min(self._debut, x), max(self._debut, x)))
        if ev.isFinish():
            self.selection.hide()
            a, b = sorted((self._debut, x))
            self._debut = None
            if b - a >= 60:                   # au moins une minute : évite les clics involontaires
                self.zoom.emit(a, b)

    def wheelEvent(self, ev, axis=None):
        ev.ignore()


class Frise(pg.PlotWidget):
    """Frise des états : rectangles colorés par L.COULEURS_ETATS. Survol : bulle ; double-clic : station."""
    station_double_clic = Signal(str)

    def __init__(self):
        self.vue = VueFrise()
        super().__init__(viewBox=self.vue, axisItems={'bottom': AxeHeureSuisse()})
        self.setMenuEnabled(False)
        self.hideButtons()
        self.vue.invertY(True)
        self.getAxis('left').setStyle(tickLength=0)
        self.setMouseTracking(True)
        self.lignes = []              # [(nom, segments d'origine, segments affichés)]
        self.t0 = self.t1 = None
        self._items = []
        self.scene().sigMouseMoved.connect(self._survol)
        self.scene().sigMouseClicked.connect(self._clic)
        self._minuterie = QTimer(self)
        self._minuterie.setSingleShot(True)
        self._minuterie.setInterval(120)
        self._minuterie.timeout.connect(self._dessiner)

    def afficher(self, lignes, t0, t1):
        """lignes : [(nom, segments)] ; la première est la ligne Système."""
        self.t0, self.t1 = t0, t1
        self.lignes = [(n, s, s) for n, s in lignes]
        self._dessiner()

    def vider(self):
        self.lignes = []
        for it in self._items:
            self.removeItem(it)
        self._items = []

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if getattr(self, 'lignes', None):
            self._minuterie.start()

    def _largeur(self):
        return max(100, int(self.vue.width()) or self.width())

    def _dessiner(self):
        for it in self._items:
            self.removeItem(it)
        self._items = []
        if not self.lignes:
            return
        n = self._largeur()
        par_etat = {e: ([], [], []) for e in L.ETATS}
        res = []
        for k, (nom, segs, _aff) in enumerate(self.lignes):
            # plus de segments que de pixels : une case par pixel, chacune à l'état le plus grave
            aff = L.Magasin.par_cases(segs, self.t0, self.t1, n) if len(segs) > n else segs
            res.append((nom, segs, aff))
            for a, b, e in aff:
                x0, w, y = par_etat[e]
                x0.append(a)
                w.append(b - a)
                y.append(k - 0.38)
        self.lignes = res
        for e, (x0, w, y) in par_etat.items():
            if x0:
                it = pg.BarGraphItem(x0=np.array(x0, dtype=float), width=np.array(w, dtype=float),
                                     y0=np.array(y), height=0.76, brush=pg.mkBrush(L.COULEURS_ETATS[e]),
                                     pen=pg.mkPen(None))
                self.addItem(it)
                self._items.append(it)
        self.getAxis('left').setTicks([[(k, nom) for k, (nom, _s, _a) in enumerate(self.lignes)]])
        self.setXRange(self.t0, self.t1, padding=0)
        self.setYRange(-0.5, len(self.lignes) - 0.5, padding=0)

    def _position(self, pos):
        if not self.lignes or not self.vue.sceneBoundingRect().contains(pos):
            return None
        p = self.vue.mapSceneToView(pos)
        k = int(round(p.y()))
        if 0 <= k < len(self.lignes) and abs(p.y() - k) <= 0.4:
            return k, p.x()
        return None

    def segment_a(self, k, x):
        """Segment affiché sous la souris (état le plus grave de la case), avec ses vraies bornes."""
        nom, segs, aff = self.lignes[k]
        i = bisect.bisect_right([a for a, _b, _e in aff], x) - 1
        if i < 0 or x >= aff[i][1]:
            return None
        a, b, e = aff[i]
        if aff is not segs:              # case réduite : chercher le segment d'origine le plus grave
            j = bisect.bisect_right([s[0] for s in segs], a) - 1
            j = max(j, 0)
            while j < len(segs) and segs[j][0] < b:
                if segs[j][2] == e and segs[j][1] > a:
                    return segs[j]
                j += 1
        return a, b, e

    def _survol(self, pos):
        r = self._position(pos)
        if r is None:
            QToolTip.hideText()
            return
        k, x = r
        s = self.segment_a(k, x)
        if s is None:
            QToolTip.hideText()
            return
        a, b, e = s
        QToolTip.showText(QCursor.pos(), f'{self.lignes[k][0]} · {L.LIBELLES_ETATS[e]}\n'
                                         f'du {L.heure_locale(int(a))} au {L.heure_locale(int(b))} '
                                         f'({L.duree_texte(b - a)})', self)

    def _clic(self, ev):
        if not ev.double():
            return
        r = self._position(ev.scenePos())
        if r and r[0] > 0:
            ev.accept()
            self.station_double_clic.emit(self.lignes[r[0]][0])


class Carte(QFrame):
    """Une carte de chiffre clé : titre, valeur, complément."""

    def __init__(self, titre):
        super().__init__()
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet('Carte { background: #F7F9FB; border: 1px solid #D6DCE2; border-radius: 4px; }')
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 6, 10, 6)
        v.setSpacing(0)
        t = QLabel(titre)
        t.setStyleSheet('color: #546E7A;')
        v.addWidget(t)
        self.valeur = QLabel('—')
        f = self.valeur.font()
        f.setPointSize(f.pointSize() + 6)
        f.setBold(True)
        self.valeur.setFont(f)
        v.addWidget(self.valeur)
        self.complement = QLabel('')
        self.complement.setStyleSheet('color: gray;')
        v.addWidget(self.complement)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def definir(self, valeur, complement=''):
        self.valeur.setText(valeur)
        self.complement.setText(complement)


COLONNES = ['Station', 'Rôle', 'Dispo comm', 'Pertes comm', 'Durée pertes', 'Plus longue', 'Batterie min',
            'Batterie moy', 'Batterie max', 'Batterie basse', 'RSSI min', 'RSSI moy', 'Coupures secteur',
            'Détections', 'Commandes', 'Radar max']
ROLES = {'base': 'Base', 'remote': 'Remote', 'repeater': 'Repeater'}


def _canaux(st, genre):
    return [c for c in st['canaux'] if c['canal']['genre'] == genre]


def _somme_activations(st, genre):
    return sum(c.get('nb_activations', 0) for c in _canaux(st, genre))


def chiffres_cles(sy):
    """Valeurs des 6 cartes (02_Ecrans.md § 3.1) à partir de la synthèse."""
    sts = sy['stations']
    comm = [s['comm'] for s in sts if 'comm' in s]
    nb_pertes = sum(c['nb_pertes'] for c in comm)
    d_pertes = sum(c['duree_pertes'] for c in comm)
    trous = sy['trous']
    return {
        'donnees': (f"{nombre(sy['couverture_pct'])} %", pluriel(len(trous), 'trou') if trous else 'aucun trou'),
        'pertes': (str(nb_pertes), duree(d_pertes) if d_pertes else ''),
        'stations_perte': (f"{sum(1 for c in comm if c['nb_pertes'] > 0)} / {len(comm)}", 'remotes et repeaters'),
        'batteries': (str(sum(1 for s in sts if any((c.get('duree_basse') or 0) > 0 for c in _canaux(s, 'BATTV')))),
                      f'sous {nombre(L.BATTV_BAS)} V'),
        'secteur': (str(sum(c.get('nb_coupures', 0) for s in sts for c in _canaux(s, 'MAINV'))), ''),
        'detections': (str(sum(_somme_activations(s, 'DETECTION') for s in sts)), ''),
    }


def ligne_station(st):
    """Cellules du tableau de synthèse pour une station : [(texte, style)] dans l'ordre de COLONNES."""
    cel = [(st['station'], {}), (ROLES.get(st['role'], st['role']), {})]
    c = st.get('comm')
    if c:
        dispo = c['disponibilite_pct']
        fond = ROUGE if dispo is not None and dispo < 95 else (ORANGE if dispo is not None and dispo < 99 else None)
        cel += [(f'{nombre(dispo)} %' if dispo is not None else '', {'couleur': fond, 'gras': bool(fond)}),
                (str(c['nb_pertes']), {'gras': c['nb_pertes'] > 0}),
                (duree(c['duree_pertes']), {}), (duree(c['plus_longue']), {})]
    else:
        cel += [('', {})] * 4
    bv = _canaux(st, 'BATTV')
    if bv and bv[0].get('min') is not None:
        b = bv[0]
        bas = b['min'] < L.BATTV_BAS
        cel += [(f"{nombre(b['min'], 2)} V", {'couleur': ROUGE if bas else None, 'gras': bas}),
                (f"{nombre(b['moyenne'], 2)} V", {}), (f"{nombre(b['max'], 2)} V", {}),
                (duree(b.get('duree_basse')), {'couleur': ROUGE if b.get('duree_basse') else None,
                                                'gras': bool(b.get('duree_basse'))})]
    else:
        cel += [('', {})] * 4
    rs = _canaux(st, 'RSSI')
    if rs and rs[0].get('min') is not None:
        r = rs[0]
        faible = r['min'] < L.RSSI_FAIBLE
        cel += [(f"{r['min']} dBm", {'couleur': ORANGE if faible else None, 'gras': faible}),
                (f"{nombre(r['moyenne'], 1)} dBm", {})]
    else:
        cel += [('', {})] * 2
    mv = _canaux(st, 'MAINV')
    if mv:
        n = sum(c.get('nb_coupures', 0) for c in mv)
        d = sum(c.get('duree_coupures', 0) for c in mv)
        cel.append((f'{n} ({duree(d)})' if n else '0', {'fond': JAUNE if n else None}))
    else:
        cel.append(('', {}))
    cel.append((str(_somme_activations(st, 'DETECTION')) if _canaux(st, 'DETECTION') else '', {}))
    cel.append((str(_somme_activations(st, 'COMMANDE')) if _canaux(st, 'COMMANDE') else '', {}))
    radars = [r for r in _canaux(st, 'RADAR') if r.get('max') is not None]
    if radars:
        textes = [f"{nombre(r['max'])} {r['canal']['unite']}" for r in radars]
        haut = any(r['max'] >= r['canal']['seuil_haut'] for r in radars)
        cel.append((' · '.join(textes), {'couleur': ORANGE if haut else None, 'gras': haut}))
    else:
        cel.append(('', {}))
    return cel


class OverviewView(QWidget):
    def __init__(self, onglet):
        super().__init__()
        self.onglet = onglet
        self.a_jour = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 0)

        # --- chiffres clés
        cartes = QHBoxLayout()
        self.cartes = {}
        for cle, titre in (('donnees', 'Données disponibles'), ('pertes', 'Pertes de communication'),
                           ('stations_perte', 'Stations avec perte de comm'), ('batteries', 'Batteries basses'),
                           ('secteur', 'Coupures secteur'), ('detections', 'Détections')):
            self.cartes[cle] = Carte(titre)
            cartes.addWidget(self.cartes[cle])
        lay.addLayout(cartes)
        self.message = QLabel()
        self.message.setStyleSheet('color: gray;')
        lay.addWidget(self.message)

        # --- frise + légende, puis tableau
        sep = QSplitter(Qt.Vertical)
        haut = QWidget()
        h = QVBoxLayout(haut)
        h.setContentsMargins(0, 0, 0, 0)
        self.frise = Frise()
        self.frise.vue.zoom.connect(lambda a, b: self.onglet.definir_periode(a, b))
        self.frise.station_double_clic.connect(lambda s: self.onglet.ouvrir_detail(s))
        h.addWidget(self.frise, 1)
        legende = QHBoxLayout()
        for e in reversed(L.ETATS):
            carre = QLabel()
            carre.setFixedSize(14, 14)
            carre.setStyleSheet(f'background: {L.COULEURS_ETATS[e]}; border: 1px solid #888;')
            legende.addWidget(carre)
            legende.addWidget(QLabel(L.LIBELLES_ETATS[e]))
            legende.addSpacing(10)
        legende.addStretch(1)
        aide = QLabel('Clic-glisser : zoom sur une période · Double-clic sur une station : Détail')
        aide.setStyleSheet('color: gray;')
        legende.addWidget(aide)
        h.addLayout(legende)
        sep.addWidget(haut)

        bas = QWidget()
        b = QVBoxLayout(bas)
        b.setContentsMargins(0, 0, 0, 0)
        self.table = preparer_tableau(QTableWidget(), COLONNES)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.cellDoubleClicked.connect(self._double_clic_table)
        b.addWidget(self.table)
        note = QLabel('Valeurs mesurées hors pertes de communication.')
        note.setStyleSheet('color: gray;')
        b.addWidget(note)
        sep.addWidget(bas)
        sep.setSizes([380, 300])
        lay.addWidget(sep, 1)

    def actualiser(self):
        p = self.onglet.periode
        if p is None:
            self.message.setText('Aucun log importé : importez les fichiers .log de la centrale.')
            self.frise.vider()
            self.table.setRowCount(0)
            for c in self.cartes.values():
                c.definir('—')
            return
        self.message.setText('Calcul en cours…')
        self.onglet.demander_global(self._afficher, echec=lambda _m: self.message.setText('Calcul impossible.'))

    def _afficher(self, res, t0, t1):
        if self.onglet.periode != (t0, t1):
            return                              # période changée pendant le calcul
        self.message.setText('')
        sy = res['synthese']
        for cle, (v, c) in chiffres_cles(sy).items():
            self.cartes[cle].definir(v, c)
        lignes = [(LIGNE_SYSTEME, res['systeme'])] + [(s['station'], s['segments']) for s in res['stations']]
        self.frise.setMinimumHeight(60 + 22 * len(lignes))
        self.frise.afficher(lignes, t0, t1)
        self.table.setRowCount(0)
        for st in sy['stations']:
            k = self.table.rowCount()
            self.table.insertRow(k)
            for j, (texte, style) in enumerate(ligne_station(st)):
                self.table.setItem(k, j, cellule(texte, droite=j >= 2, info=st['station'], **style))

    def _double_clic_table(self, k, _c):
        it = self.table.item(k, 0)
        if it:
            self.onglet.ouvrir_detail(it.data(Qt.UserRole))

    def ligne_tableau(self, station):
        """Textes d'une ligne du tableau (recette automatique)."""
        for k in range(self.table.rowCount()):
            if self.table.item(k, 0).text() == station:
                return {COLONNES[j]: self.table.item(k, j).text() for j in range(len(COLONNES))}
        return None
