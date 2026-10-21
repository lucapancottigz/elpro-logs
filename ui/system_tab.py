# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""Onglet d'un système : bandeau d'informations, barre de période, 4 sous-onglets
(Vue globale · Détail · Journal · Fichiers). Garde la période affichée, son historique
et le cache des calculs longs (faits dans un thread)."""
from collections import OrderedDict

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTabWidget, QFrame,
                               QMessageBox)

import elpro_logs as L
import elpro_remote as R
from ui.common import editeur_date, qdatetime, utc_depuis_qdatetime, pluriel
from ui.workers import Tache
from ui.overview_view import OverviewView
from ui.detail_view import DetailView
from ui.journal_view import JournalView
from ui.files_view import FilesView

HISTORIQUE_MAX = 20
CACHE_MAX = 12
PRESETS = (('24 h', 86400), ('30 jours', 30 * 86400))
# Résultat de la dernière récupération (statut du moteur -> texte court de la ligne grise)
RESULTATS_RECUPERATION = {
    'ok': 'logs importés', 'rien_de_nouveau': 'aucun nouveau fichier', 'injoignable': 'centrale injoignable',
    'acces_refuse': 'accès refusé', 'introuvable': 'page introuvable sur la centrale',
    'mauvaise_centrale': 'autre centrale connectée', 'non_configure': 'connexion non configurée',
    'annule': 'annulée', 'erreur': 'erreur'}


class SystemTab(QWidget):
    export_change = Signal()          # l'action « Exporter en CSV » doit être réévaluée

    def __init__(self, fenetre, systeme):
        super().__init__()
        self.fenetre = fenetre
        self.sid = systeme['id']
        self.nom = systeme['nom']
        self.t0 = self.t1 = None
        # période automatique qui suit les nouvelles données : 'defaut' (dernière semaine de données),
        # 'tout' (toute la période) ; None = période choisie à la main (gardée jusqu'à la fermeture)
        self.mode = 'defaut'
        self.historique = []
        self._cache = OrderedDict()
        self._en_cours = {}
        self._generation = 0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        # --- bandeau d'informations
        ligne = QHBoxLayout()
        self.bandeau = QLabel()
        self.bandeau.setStyleSheet('color: gray;')
        self.bandeau.setTextInteractionFlags(Qt.TextSelectableByMouse)
        ligne.addWidget(self.bandeau)
        self.bouton_importer = QPushButton('Importer des logs…')
        self.bouton_importer.clicked.connect(lambda: self.fenetre.importer_logs())
        ligne.addWidget(self.bouton_importer)
        self.bouton_recuperer = QPushButton('Récupérer les logs')
        self.bouton_recuperer.setToolTip('Télécharge depuis la centrale les logs qui ne sont pas encore dans la base '
                                         '(tunnel WireGuard activé)')
        self.bouton_recuperer.clicked.connect(lambda: self.fenetre.recuperer_logs(self))
        ligne.addWidget(self.bouton_recuperer)
        ligne.addStretch(1)
        lay.addLayout(ligne)
        self.ligne_recuperation = QLabel()
        self.ligne_recuperation.setStyleSheet('color: gray;')
        lay.addWidget(self.ligne_recuperation)

        # --- rappel : la centrale ne garde qu'environ une semaine de logs
        self.rappel = QFrame()
        self.rappel.setStyleSheet('QFrame { background: #FFF59D; border-radius: 3px; } '
                                  'QLabel { color: #202020; background: transparent; }')
        r = QHBoxLayout(self.rappel)
        r.setContentsMargins(6, 3, 6, 3)
        self.texte_rappel = QLabel()
        self.texte_rappel.setWordWrap(True)
        r.addWidget(self.texte_rappel, 1)
        bt = QPushButton('Récupérer les logs')
        bt.clicked.connect(lambda: self.fenetre.recuperer_logs(self))
        r.addWidget(bt)
        self.rappel.hide()
        lay.addWidget(self.rappel)

        # --- barre de période
        self.barre = QFrame()
        b = QHBoxLayout(self.barre)
        b.setContentsMargins(0, 0, 0, 0)
        self.boutons_presets = []
        bt = QPushButton('Tout')
        bt.setToolTip('Toute la période des données')
        bt.clicked.connect(self.periode_tout)
        b.addWidget(bt)
        self.boutons_presets.append(bt)
        bt = QPushButton('7 jours')
        bt.setToolTip('La dernière semaine de données, du même jour à la même heure (période par défaut)')
        bt.clicked.connect(self.periode_defaut)
        b.addWidget(bt)
        self.boutons_presets.append(bt)
        for texte, d in PRESETS:
            bt = QPushButton(texte)
            bt.setToolTip(f'Les derniers {texte} de données (depuis la fin des données)')
            bt.clicked.connect(lambda _=False, d=d: self.periode_derniere(d))
            b.addWidget(bt)
            self.boutons_presets.append(bt)
        b.addSpacing(12)
        b.addWidget(QLabel('Du'))
        self.du = editeur_date()
        b.addWidget(self.du)
        b.addWidget(QLabel('Au'))
        self.au = editeur_date()
        b.addWidget(self.au)
        self.bouton_afficher = QPushButton('Afficher')
        self.bouton_afficher.clicked.connect(self.periode_saisie)
        b.addWidget(self.bouton_afficher)
        b.addSpacing(12)
        self.bouton_avant = QPushButton('◀')
        self.bouton_avant.setToolTip('Période précédente de même durée')
        self.bouton_avant.clicked.connect(lambda: self.decaler(-1))
        self.bouton_apres = QPushButton('▶')
        self.bouton_apres.setToolTip('Période suivante de même durée')
        self.bouton_apres.clicked.connect(lambda: self.decaler(1))
        for bt in (self.bouton_avant, self.bouton_apres):
            bt.setFixedWidth(34)
            b.addWidget(bt)
        self.bouton_retour = QPushButton('↶ Période précédente')
        self.bouton_retour.setToolTip('Revenir à la période affichée avant (20 niveaux)')
        self.bouton_retour.clicked.connect(self.retour)
        b.addWidget(self.bouton_retour)
        b.addStretch(1)
        lay.addWidget(self.barre)

        # --- bandeau jaune : changement de configuration dans la période
        self.bandeau_config = QLabel()
        self.bandeau_config.setWordWrap(True)
        self.bandeau_config.setStyleSheet('background: #FFF59D; color: #5D4037; padding: 4px; border-radius: 3px;')
        self.bandeau_config.hide()
        lay.addWidget(self.bandeau_config)

        # --- sous-onglets
        self.sous_onglets = QTabWidget()
        self.vue_globale = OverviewView(self)
        self.detail = DetailView(self)
        self.journal = JournalView(self)
        self.fichiers = FilesView(self)
        for v, t in ((self.vue_globale, 'Vue globale'), (self.detail, 'Détail'), (self.journal, 'Journal'),
                     (self.fichiers, 'Fichiers')):
            self.sous_onglets.addTab(v, t)
        self.sous_onglets.currentChanged.connect(self._sous_onglet_change)
        lay.addWidget(self.sous_onglets, 1)

        self.rafraichir()

    # ================================================================ accès
    @property
    def m(self):
        """Magasin du thread de l'interface (rouvert par la fenêtre après chaque import)."""
        return self.fenetre.magasin

    @property
    def chemin_base(self):
        return self.fenetre.chemin_base

    @property
    def periode(self):
        return (self.t0, self.t1) if self.t0 is not None else None

    def vues(self):
        return (self.vue_globale, self.detail, self.journal, self.fichiers)

    # ================================================================ rafraîchissement
    def rafraichir(self, apres_import=False):
        """Relit le système dans la base (après ajout, import, mise à jour de config…)."""
        if apres_import:
            self.vider_cache()
        sy = next((s for s in self.m.systemes() if s['id'] == self.sid), None)
        if sy is None:
            return
        self.nom = sy['nom']
        p = sy['periode']
        cs = self.m.configs(self.sid)
        version = cs[-1]['version'] if cs else '?'
        if p is None:
            self.bandeau.setText(f"Radio n° {sy['serie'] or '—'} · Config V{version} · Aucun log importé")
        else:
            self.bandeau.setText(f"Radio n° {sy['serie'] or '—'} · Config V{version} · Données du "
                                 f"{L.heure_locale(p[0])} au {L.heure_locale(p[1])} · "
                                 f"{pluriel(sy['nb_fichiers'], 'fichier')}")
        self.bouton_importer.setVisible(p is None)
        self.barre.setEnabled(p is not None)
        if p is None:
            self.t0 = self.t1 = None
        elif self.t0 is None or self.mode == 'tout':
            if self.t0 is None:
                self.mode = 'defaut'
            self.t0, self.t1 = p if self.mode == 'tout' else self.m.periode_par_defaut(self.sid)
        elif self.mode == 'defaut':
            self.t0, self.t1 = self.m.periode_par_defaut(self.sid)
        self.maj_recuperation()
        self._periode_changee()

    def vider_cache(self):
        self._generation += 1
        self._cache.clear()
        self._en_cours.clear()

    def _periode_changee(self):
        if self.t0 is not None:
            for e, t in ((self.du, self.t0), (self.au, self.t1)):
                e.blockSignals(True)
                e.setDateTime(qdatetime(t))
                e.blockSignals(False)
            vs = self.m.versions_dans_periode(self.sid, self.t0, self.t1)
            if len(vs) > 1:
                self.bandeau_config.setText(
                    'La configuration a changé pendant cette période ('
                    + ' → '.join(f"V{v['version']}" for v in vs)
                    + '). Les libellés sont ceux de la version en vigueur à la fin de la période.')
            self.bandeau_config.setVisible(len(vs) > 1)
        else:
            self.bandeau_config.hide()
        self.bouton_retour.setEnabled(bool(self.historique))
        for v in self.vues():
            v.a_jour = False
        self._actualiser_visible()
        self.export_change.emit()

    def _actualiser_visible(self):
        v = self.sous_onglets.currentWidget()
        if v is not None and not v.a_jour and self.isVisible():
            v.a_jour = True
            v.actualiser()

    def _sous_onglet_change(self, _i):
        self._actualiser_visible()
        self.export_change.emit()

    def showEvent(self, e):
        super().showEvent(e)
        self.maj_recuperation()
        self._actualiser_visible()

    def maj_recuperation(self):
        """Ligne « Dernière récupération » et bandeau de rappel (d'après le moteur)."""
        acc = self.m.acces(self.sid)
        if acc and acc['derniere_recuperation']:
            res = RESULTATS_RECUPERATION.get(acc['dernier_resultat'], acc['dernier_resultat'] or '')
            self.ligne_recuperation.setText(f"Dernière récupération : {L.heure_locale(acc['derniere_recuperation'])}"
                                            f" — {res}")
        else:
            self.ligne_recuperation.setText('Jamais récupéré')
        texte = R.rappel_necessaire(self.m, self.sid)
        self.texte_rappel.setText(texte or '')
        self.rappel.setVisible(bool(texte))

    # ================================================================ période
    def definir_periode(self, t0, t1, historique=True, mode=None):
        """mode : 'defaut', 'tout' (périodes qui suivent les nouvelles données) ou None (choisie à la main)."""
        t0, t1 = int(t0), int(t1)
        if t1 <= t0:
            return
        if (t0, t1) == (self.t0, self.t1) and mode == self.mode:
            return
        if historique and self.t0 is not None:
            self.historique.append((self.t0, self.t1, self.mode))
            del self.historique[:-HISTORIQUE_MAX]
        self.t0, self.t1, self.mode = t0, t1, mode
        self._periode_changee()

    def periode_tout(self):
        p = self.m.periode(self.sid)
        if p:
            self.definir_periode(p[0], p[1], mode='tout')

    def periode_defaut(self):
        p = self.m.periode_par_defaut(self.sid)
        if p:
            self.definir_periode(p[0], p[1], mode='defaut')

    def periode_derniere(self, d):
        p = self.m.periode(self.sid)
        if p:
            self.definir_periode(p[1] - d, p[1])

    def periode_saisie(self):
        t0, t1 = utc_depuis_qdatetime(self.du.dateTime()), utc_depuis_qdatetime(self.au.dateTime())
        if t1 <= t0:
            QMessageBox.warning(self, 'Période', 'La fin de la période doit être après son début.')
            return
        self.definir_periode(t0, t1)

    def decaler(self, sens):
        if self.t0 is not None:
            d = self.t1 - self.t0
            self.definir_periode(self.t0 + sens * d, self.t1 + sens * d)

    def retour(self):
        if self.historique:
            self.t0, self.t1, self.mode = self.historique.pop()
            self._periode_changee()

    # ================================================================ calculs longs (thread + cache)
    def demander(self, nom, fonction, rappel, extra=None, echec=None):
        """Calcul fonction(magasin, t0, t1) pour la période affichée, dans un thread, avec cache par
        (système, nom, t0, t1, extra). rappel(resultat, t0, t1) est appelé dans le thread de l'interface."""
        if self.t0 is None:
            return
        t0, t1 = self.t0, self.t1
        k = (nom, t0, t1, extra)
        if k in self._cache:
            self._cache.move_to_end(k)
            rappel(self._cache[k], t0, t1)
            return
        if k in self._en_cours:
            self._en_cours[k].append((rappel, echec))
            return
        self._en_cours[k] = [(rappel, echec)]
        tache = Tache(self.chemin_base, lambda m: fonction(m, t0, t1))
        g = self._generation
        tache.termine.connect(lambda res, k=k, g=g: self._calcule(k, g, res))
        tache.echec.connect(lambda msg, k=k, g=g: self._echoue(k, g, msg))
        tache.start()

    def _calcule(self, k, g, res):
        if g != self._generation:
            return                         # données importées entre-temps : résultat périmé
        self._cache[k] = res
        while len(self._cache) > CACHE_MAX:
            self._cache.popitem(last=False)
        for rappel, _e in self._en_cours.pop(k, []):
            rappel(res, k[1], k[2])

    def _echoue(self, k, g, msg):
        if g != self._generation:
            return
        attentes = self._en_cours.pop(k, [])
        for _r, echec in attentes:
            if echec:
                echec(msg)
        QMessageBox.warning(self, 'Calcul', f'Le calcul a échoué :\n{msg}')

    def demander_global(self, rappel, echec=None):
        """États des stations, état du système et synthèse de la période (Vue globale et Détail)."""
        def calcul(m, t0, t1):
            st = m.etat_stations(self.sid, t0, t1)
            return {'stations': st, 'systeme': m.etat_systeme(self.sid, t0, t1, stations=st),
                    'synthese': m.synthese(self.sid, t0, t1)}
        self.demander('global', calcul, rappel, echec=echec)

    # ================================================================ navigation entre sous-onglets
    def ouvrir_detail(self, station=None, t0=None, t1=None):
        """Ouvre le Détail avec les canaux de la station cochés (période facultative)."""
        if t0 is not None:
            self.definir_periode(t0, t1)
        if station:
            self.detail.cocher_station(station)
        self.sous_onglets.setCurrentWidget(self.detail)

    def export_possible(self):
        return self.sous_onglets.currentWidget() is self.detail and self.t0 is not None \
            and bool(self.detail.canaux_affiches())
