# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""Aides d'affichage communes à tous les écrans : heure suisse, axe des temps, nombres, tableaux.
Aucune règle métier ici : les heures sont converties par elpro_logs, les couleurs et libellés en viennent."""
import json, calendar

import pyqtgraph as pg
from PySide6.QtCore import Qt, QDate, QTime, QDateTime, QTimeZone
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QTableWidgetItem, QDateTimeEdit

import elpro_engine as M
import elpro_logs as L

FORMAT_QT = 'dd.MM.yyyy HH:mm:ss'
FORMAT_COURT = '%d.%m.%Y %H:%M'

pg.setConfigOptions(antialias=False, background='w', foreground='#303030')

# Couleurs des couloirs binaires du Détail (02_Ecrans.md § 4.2), reprises des couleurs d'état du moteur
COULEUR_COMMANDE = '#1976D2'
COULEURS_COULOIRS = {'COMFLAG': L.COULEURS_ETATS['COMM_PERDUE'], 'MAINV': L.COULEURS_ETATS['ALERTE'],
                     'DETECTION': L.COULEURS_ETATS['DEGRADE'], 'COMMANDE': COULEUR_COMMANDE}
# Couleurs de fond des lignes du journal selon la gravité de l'événement
COULEURS_GRAVITE = {'defaut': '#FADBD8', 'alarme': '#FDE3C8', 'alerte': '#FFF5C2', 'commande': '#DCEBFA',
                    'info': None}
LIBELLES_GRAVITE = {'defaut': 'Défaut', 'alarme': 'Alarme', 'alerte': 'Alerte', 'commande': 'Commande',
                    'info': 'Information'}
ROUGE, ORANGE, JAUNE = '#C62828', '#EF6C00', '#FFF59D'
GRIS = '#707070'
# Palette des courbes (distinctes, lisibles sur fond blanc)
PALETTE = ['#1f77b4', '#d62728', '#2ca02c', '#9467bd', '#ff7f0e', '#17becf', '#8c564b', '#e377c2',
           '#7f7f7f', '#bcbd22', '#393b79', '#637939', '#8c6d31', '#843c39', '#7b4173']


# ------------------------------------------------------------------------------------------- heures
def composantes(t):
    """Seconde UTC -> (année, mois, jour, h, min, s) en heure suisse."""
    return tuple(int(x) for x in L.heure_locale(int(t), '%Y %m %d %H %M %S').split())


def decalage_suisse(t):
    """Avance de l'heure suisse sur l'UTC à l'instant t, en secondes (3600 ou 7200).
    Calcul arithmétique (calendar.timegm) : surtout pas de strptime, appelé pendant le dessin des axes
    alors qu'un thread d'import l'utilise (verrou interne de Python -> plantage de PySide6 >= 6.10)."""
    return calendar.timegm(composantes(t)) - int(t)


def qdatetime(t):
    """Seconde UTC -> QDateTime portant l'heure suisse en composantes (fuseau UTC : pas de saut d'heure)."""
    a, mo, j, h, mi, s = composantes(t)
    return QDateTime(QDate(a, mo, j), QTime(h, mi, s), QTimeZone.utc())


def utc_depuis_qdatetime(q):
    """QDateTime (composantes en heure suisse) -> seconde UTC."""
    d, h = q.date(), q.time()
    return L.utc_depuis_locale(d.year(), d.month(), d.day(), h.hour(), h.minute(), h.second())


def editeur_date(t=None):
    """QDateTimeEdit au format suisse JJ.MM.AAAA HH:MM:SS, avec calendrier."""
    e = QDateTimeEdit()
    e.setTimeZone(QTimeZone.utc())         # les composantes affichées sont l'heure suisse, sans conversion
    e.setDisplayFormat(FORMAT_QT)
    e.setCalendarPopup(True)
    if t is not None:
        e.setDateTime(qdatetime(t))
    return e


class AxeHeureSuisse(pg.AxisItem):
    """Axe des temps en heure suisse, quel que soit le fuseau du PC (été/hiver gérés par le moteur).
    Graduations calculées ici, en Python pur : DateAxisItem, avec un décalage UTC imposé, crée des QDateTime
    pendant le dessin, ce qui fait planter PySide6 >= 6.10 quand un thread de calcul tourne en même temps."""
    PAS = (1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 3 * 3600, 6 * 3600, 12 * 3600,
           86400, 2 * 86400, 7 * 86400)
    MOIS = (1, 3, 6, 12, 24, 60, 120)
    ECART_PX = 85                         # écart minimal entre deux étiquettes, en pixels
    JOUR = 86400

    def __init__(self):
        super().__init__('bottom')

    def tickValues(self, minVal, maxVal, size):
        if not size or size <= 0 or not (0 < minVal < maxVal < 4e9):
            return []
        mini = (maxVal - minVal) * self.ECART_PX / size
        pas = next((p for p in self.PAS if p >= mini), None)
        if pas is not None:
            return [(pas, self._reguliers(minVal, maxVal, pas))]
        mois = next((m for m in self.MOIS if m * 30 * self.JOUR >= mini), self.MOIS[-1])
        return [(mois * 30 * self.JOUR, self._mensuels(minVal, maxVal, mois))]

    @staticmethod
    def _reguliers(a, b, pas):
        """Graduations où l'heure suisse est un multiple du pas (minuit, heures rondes…)."""
        res = []
        off = decalage_suisse(a)
        w = (int(a) + off) // pas * pas                 # heure « murale » suisse, en secondes
        while len(res) < 400:
            u = w - decalage_suisse(w - off)            # retour en UTC (été/hiver)
            if u > b:
                break
            if u >= a and (not res or u > res[-1]):
                res.append(u)
            w += pas
        return res

    @staticmethod
    def _mensuels(a, b, n):
        """Graduations au 1er du mois (tous les n mois), minuit heure suisse."""
        an, mo = composantes(a)[:2]
        k = (an * 12 + mo - 1) // n * n
        res = []
        while len(res) < 400:
            y, m = divmod(k, 12)
            u = L.utc_depuis_locale(y, m + 1, 1)
            if u > b:
                break
            if u >= a:
                res.append(u)
            k += n
        return res

    def tickStrings(self, values, scale, spacing):
        res = []
        for v in values:
            t = int(round(v))
            try:
                if spacing >= 300 * self.JOUR:
                    fmt = '%Y'
                elif spacing >= 28 * self.JOUR:
                    fmt = '%m.%Y'
                elif spacing >= self.JOUR or (spacing >= 60 and L.heure_locale(t, '%H:%M') == '00:00'):
                    fmt = '%d.%m'                   # à minuit, la date plutôt que « 00:00 »
                elif spacing >= 60:
                    fmt = '%H:%M'
                else:
                    fmt = '%H:%M:%S'
                res.append(L.heure_locale(t, fmt))
            except (OverflowError, OSError, ValueError):
                res.append('')
        return res


# ------------------------------------------------------------------------------------------- textes
def nombre(v, decimales=None):
    """12.5 -> '12,5' ; decimales=2 -> '12,50' ; None -> ''."""
    if v is None:
        return ''
    if decimales is None:
        return f'{v:g}'.replace('.', ',')
    return f'{v:.{decimales}f}'.replace('.', ',')


def duree(s):
    return L.duree_texte(s) if s else ''


def pluriel(n, mot, mots=None):
    return f'{n} {mot if n <= 1 else (mots or mot + "s")}'


def nom_canal(c):
    """« station · libellé » (registres non attribués : libellé seul)."""
    return f"{c['station']} · {c['libelle']}" if c.get('station') else c['libelle']


def cle_systeme(projet):
    """Clé qui identifie un système dans la base (comme Magasin.ajouter_config) : system_name, sinon nom du projet."""
    p = M.normaliser_projet(json.loads(json.dumps(projet)))
    s = p.get('systeme') or {}
    return str(s.get('system_name') or s.get('nom_projet') or '').strip()


def projet_normalise(projet):
    """Projet tel que la base le conserve (pour comparer avec la configuration en vigueur)."""
    return json.loads(json.dumps(M.normaliser_projet(json.loads(json.dumps(projet))), sort_keys=True))


def lire_projet(chemin):
    """Lit un .elpro.json ; ValueError avec un message clair si ce n'est pas un projet ELPRO Config."""
    with open(chemin, encoding='utf-8') as f:
        projet = json.load(f)
    if not isinstance(projet, dict) or not isinstance(projet.get('systeme'), dict) \
            or not isinstance(projet.get('radios'), list):
        raise ValueError('ce fichier n\'est pas un projet ELPRO Config (clés « systeme » et « radios » attendues).')
    return projet


# ------------------------------------------------------------------------------------------- tableaux
def cellule(texte, droite=False, fond=None, couleur=None, gras=False, italique=False, info=None):
    it = QTableWidgetItem('' if texte is None else str(texte))
    it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
    if droite:
        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    if fond:
        it.setBackground(QColor(fond))
    if couleur:
        it.setForeground(QColor(couleur))
    if gras or italique:
        f = QFont()
        f.setBold(gras)
        f.setItalic(italique)
        it.setFont(f)
    if info is not None:
        it.setData(Qt.UserRole, info)
    return it


def preparer_tableau(t, entetes):
    t.setColumnCount(len(entetes))
    t.setHorizontalHeaderLabels(entetes)
    t.setEditTriggers(t.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(t.SelectionBehavior.SelectRows)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(22)
    t.setAlternatingRowColors(False)
    t.setWordWrap(False)
    return t
