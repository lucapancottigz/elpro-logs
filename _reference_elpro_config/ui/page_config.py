# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""Page 1 : saisie du projet (format 03_Modele_de_donnees.md).
Les formulaires modifient directement le dict `self.projet`, et seulement les clés touchées par
l'utilisateur : un fichier ouvert puis enregistré sans modification reste identique."""
from PySide6.QtCore import Qt, Signal, QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QGridLayout, QFormLayout, QLabel,
                               QLineEdit, QSpinBox, QPushButton, QTableWidget, QTableWidgetItem, QAbstractItemView,
                               QHeaderView, QComboBox, QCheckBox, QSplitter, QMessageBox, QScrollArea, QToolButton)

import elpro_engine as M
from ui.dialogs import DialoguePeripherique, LIBELLES, texte_cablage, occupations, remplir_combo, choisir

ROLES = {'base': 'Base', 'repeater': 'Repeater', 'remote': 'Remote'}
CHAMPS_TEXTE_SYSTEME = ('nom_projet', 'system_name', 'cle_chiffrement', 'proprietaire', 'contact', 'localisation',
                        'description')


def nouvelle_radio(nom, role, ip_octet, amont=None):
    r = {'nom': nom, 'role': role}
    if role != 'base':
        r['amont'] = amont
    r.update({'ip_octet': ip_octet, 'puissance_dbm': None, 'titre_page': '', 'description': '',
              'inversion_entrees': False, 'inversion_sorties': False, 'mainv': {'actif': True, 'di': 8},
              'peripheriques': []})
    return r


def projet_vide():
    return {'version': 1,
            'systeme': {'nom_projet': '', 'system_name': '', 'cle_chiffrement': M.generer_cle(), 'puissance_dbm': 34,
                        'proprietaire': '', 'contact': '', 'description': '', 'localisation': ''},
            'radios': [nouvelle_radio('CA', 'base', 100)]}


def _item(texte, centre=False):
    it = QTableWidgetItem(str(texte))
    it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
    if centre:
        it.setTextAlignment(Qt.AlignCenter)
    return it


class PageConfig(QWidget):
    modifie = Signal()          # le projet vient d'être modifié par l'utilisateur
    generer = Signal()          # clic sur « Générer la configuration »

    def __init__(self, parent=None):
        super().__init__(parent)
        self.projet = projet_vide()
        self._chargement = False
        self._renommage = False
        self._radio_form = None
        lay = QVBoxLayout(self)
        lay.addWidget(self._bloc_systeme())

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self._bloc_radios())
        split.addWidget(self._bloc_radio())
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 4)
        split.setChildrenCollapsible(False)
        lay.addWidget(split, 1)

        self.bt_generer = QPushButton('  Générer la configuration  ')
        self.bt_generer.setMinimumHeight(34)
        f = self.bt_generer.font(); f.setBold(True); self.bt_generer.setFont(f)
        self.bt_generer.clicked.connect(self.generer.emit)
        bas = QHBoxLayout(); bas.addStretch(1); bas.addWidget(self.bt_generer)
        lay.addLayout(bas)
        self.charger(self.projet)

    # ================================================================ construction
    def _bloc_systeme(self):
        g = QGroupBox('Système')
        grille = QGridLayout(g)
        self.sys = {}
        for cle in CHAMPS_TEXTE_SYSTEME:
            ed = QLineEdit()
            ed.textEdited.connect(lambda txt, c=cle: self._maj_systeme(c, txt))
            self.sys[cle] = ed
        self.sys['system_name'].setMaxLength(32)
        self.sys['system_name'].setValidator(QRegularExpressionValidator(QRegularExpression(r'[A-Za-z0-9_-]{0,32}'), self))
        self.sys['cle_chiffrement'].setMaxLength(63)
        self.sys['cle_chiffrement'].setEchoMode(QLineEdit.Password)
        self.sys['cle_chiffrement'].setFont(self._police_fixe())
        self.sp_puissance = QSpinBox(); self.sp_puissance.setRange(10, 40); self.sp_puissance.setSuffix(' dBm')
        self.sp_puissance.valueChanged.connect(self._maj_puissance_generale)

        bt_cle = QPushButton('Générer'); bt_cle.clicked.connect(self._generer_cle)
        self.bt_oeil = QToolButton(); self.bt_oeil.setText('👁'); self.bt_oeil.setCheckable(True)
        self.bt_oeil.setToolTip('Afficher / masquer la clé')
        self.bt_oeil.toggled.connect(lambda v: self.sys['cle_chiffrement'].setEchoMode(
            QLineEdit.Normal if v else QLineEdit.Password))

        def lab(t):
            l = QLabel(t); l.setAlignment(Qt.AlignRight | Qt.AlignVCenter); return l
        # version de configuration : calculée par le moteur à chaque génération, jamais saisie
        self.ed_version = QLineEdit(); self.ed_version.setReadOnly(True); self.ed_version.setMaximumWidth(80)
        self.lb_version = QLabel()
        f = self.lb_version.font(); f.setPointSize(8); self.lb_version.setFont(f)
        version = QHBoxLayout(); version.addWidget(self.ed_version); version.addWidget(self.lb_version, 1)

        grille.addWidget(lab('Nom du projet'), 0, 0); grille.addWidget(self.sys['nom_projet'], 0, 1, 1, 3)
        grille.addWidget(lab('System Name'), 0, 4); grille.addWidget(self.sys['system_name'], 0, 5, 1, 3)
        grille.addWidget(lab('Version de configuration'), 1, 0); grille.addLayout(version, 1, 1, 1, 3)
        cle = QHBoxLayout(); cle.addWidget(self.sys['cle_chiffrement'], 1); cle.addWidget(bt_cle); cle.addWidget(self.bt_oeil)
        grille.addWidget(lab('Clé de chiffrement'), 2, 0); grille.addLayout(cle, 2, 1, 1, 3)
        grille.addWidget(lab('Puissance générale'), 2, 4); grille.addWidget(self.sp_puissance, 2, 5)
        grille.addWidget(lab('Propriétaire'), 3, 0); grille.addWidget(self.sys['proprietaire'], 3, 1)
        grille.addWidget(lab('Contact'), 3, 2); grille.addWidget(self.sys['contact'], 3, 3)
        grille.addWidget(lab('Localisation'), 3, 4); grille.addWidget(self.sys['localisation'], 3, 5, 1, 3)
        grille.addWidget(lab('Description'), 4, 0); grille.addWidget(self.sys['description'], 4, 1, 1, 7)
        for c in (1, 3, 5):
            grille.setColumnStretch(c, 1)
        return g

    @staticmethod
    def _police_fixe():
        from PySide6.QtGui import QFontDatabase
        return QFontDatabase.systemFont(QFontDatabase.FixedFont)

    def _bloc_radios(self):
        g = QGroupBox('Radios')
        v = QVBoxLayout(g)
        self.tab_radios = QTableWidget(0, 6)
        self.tab_radios.setHorizontalHeaderLabels(['#', 'Nom', 'Rôle', 'IP', 'Amont', 'Nb périphériques'])
        self.tab_radios.verticalHeader().setVisible(False)
        self.tab_radios.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tab_radios.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tab_radios.setEditTriggers(QAbstractItemView.NoEditTriggers)
        h = self.tab_radios.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        self.tab_radios.itemSelectionChanged.connect(self._selection_radio)
        v.addWidget(self.tab_radios)
        b = QHBoxLayout()
        self.bt_ajouter = QPushButton('+ Ajouter'); self.bt_ajouter.clicked.connect(self._ajouter_radio)
        self.bt_supprimer = QPushButton('Supprimer'); self.bt_supprimer.clicked.connect(self._supprimer_radio)
        self.bt_monter = QPushButton('▲'); self.bt_monter.clicked.connect(lambda: self._deplacer(-1))
        self.bt_descendre = QPushButton('▼'); self.bt_descendre.clicked.connect(lambda: self._deplacer(1))
        self.bt_monter.setToolTip('Monter la radio'); self.bt_descendre.setToolTip('Descendre la radio')
        for w in (self.bt_ajouter, self.bt_supprimer, self.bt_monter, self.bt_descendre):
            b.addWidget(w)
        b.addStretch(1)
        v.addLayout(b)
        return g

    def _bloc_radio(self):
        g = QGroupBox('Radio sélectionnée')
        ext = QVBoxLayout(g)
        defil = QScrollArea(); defil.setWidgetResizable(True); defil.setFrameShape(QScrollArea.NoFrame)
        interieur = QWidget(); v = QVBoxLayout(interieur); v.setContentsMargins(0, 0, 0, 0)
        defil.setWidget(interieur)
        ext.addWidget(defil)
        self.f_radio = QFormLayout()
        v.addLayout(self.f_radio)

        self.ed_nom = QLineEdit(); self.ed_nom.setMaxLength(20)
        self.ed_nom.setValidator(QRegularExpressionValidator(QRegularExpression(r'[A-Za-z0-9_-]{0,20}'), self))
        self.ed_nom.editingFinished.connect(self._renommer)     # pas à chaque frappe (recette 1, C2)
        self.cb_role = QComboBox(); self.cb_role.activated.connect(self._changer_role)
        self.cb_amont = QComboBox(); self.cb_amont.activated.connect(self._changer_amont)
        self.sp_ip = QSpinBox(); self.sp_ip.setRange(100, 254); self.sp_ip.setPrefix('192.168.1.')
        self.sp_ip.valueChanged.connect(lambda v: self._maj_radio('ip_octet', v))
        self.ck_puiss = QCheckBox('Utiliser la puissance générale'); self.ck_puiss.clicked.connect(self._changer_puissance)
        self.sp_puiss = QSpinBox(); self.sp_puiss.setRange(10, 40); self.sp_puiss.setSuffix(' dBm')
        self.sp_puiss.valueChanged.connect(self._changer_puissance)
        puiss = QHBoxLayout(); puiss.addWidget(self.ck_puiss); puiss.addWidget(self.sp_puiss); puiss.addStretch(1)
        self.ed_titre = QLineEdit(); self.ed_titre.setPlaceholderText('vide = nom de la radio')
        self.ed_titre.textEdited.connect(lambda t: self._maj_radio('titre_page', t))
        self.ed_desc = QLineEdit(); self.ed_desc.setPlaceholderText('vide = description générale')
        self.ed_desc.textEdited.connect(lambda t: self._maj_radio('description', t))
        self.ck_mainv = QCheckBox('Actif'); self.ck_mainv.clicked.connect(self._changer_mainv)
        self.cb_mainv = QComboBox(); self.cb_mainv.activated.connect(self._changer_mainv)
        mainv = QHBoxLayout(); mainv.addWidget(self.ck_mainv); mainv.addWidget(self.cb_mainv); mainv.addStretch(1)
        self.ck_inv_e = QCheckBox(); self.ck_inv_e.clicked.connect(lambda v: self._maj_radio('inversion_entrees', v))
        self.ck_inv_s = QCheckBox(); self.ck_inv_s.clicked.connect(lambda v: self._maj_radio('inversion_sorties', v))

        self.f_radio.addRow('Nom', self.ed_nom)
        self.f_radio.addRow('Rôle', self.cb_role)
        self.f_radio.addRow('Amont', self.cb_amont)
        self.f_radio.addRow('Adresse IP', self.sp_ip)
        self.f_radio.addRow('Puissance', puiss)
        self.f_radio.addRow('Titre de page web', self.ed_titre)
        self.f_radio.addRow('Description', self.ed_desc)
        self.f_radio.addRow('Présence secteur (MAINV)', mainv)
        self.f_radio.addRow('Inverser toutes les entrées', self.ck_inv_e)
        self.f_radio.addRow('Inverser toutes les sorties', self.ck_inv_s)

        gp = QGroupBox('Périphériques')
        vp = QVBoxLayout(gp)
        self.tab_periph = QTableWidget(0, 5)
        self.tab_periph.setHorizontalHeaderLabels(['Type', 'Nom', 'Câblage', '', ''])
        self.tab_periph.verticalHeader().setVisible(False)
        self.tab_periph.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tab_periph.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tab_periph.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hp = self.tab_periph.horizontalHeader()
        hp.setSectionResizeMode(QHeaderView.ResizeToContents)
        hp.setSectionResizeMode(2, QHeaderView.Stretch)
        self.tab_periph.cellDoubleClicked.connect(lambda r, _c: self._modifier_periph(r))
        self.tab_periph.setMinimumHeight(170)
        vp.addWidget(self.tab_periph)
        bp = QHBoxLayout()
        self.bt_ajout_periph = QPushButton('+ Ajouter un périphérique'); self.bt_ajout_periph.clicked.connect(self._ajouter_periph)
        bp.addWidget(self.bt_ajout_periph); bp.addStretch(1)
        vp.addLayout(bp)
        v.addWidget(gp, 1)
        return g

    # ================================================================ chargement
    def charger(self, projet):
        """Affiche un projet (dict) dans les formulaires, sans le modifier."""
        self.projet = projet
        self._chargement = True
        s = projet.get('systeme', {})
        for cle, ed in self.sys.items():
            ed.setText(str(s.get(cle, '') or ''))
        self.sp_puissance.setValue(int(s.get('puissance_dbm', 34) or 34))
        self.bt_oeil.setChecked(False)
        self._chargement = False
        self._rafraichir_radios(0)
        self.maj_version()

    def maj_version(self):
        """Champ « Version de configuration » et libellé d'état (comparaison avec la dernière génération)."""
        version = M.version_config(self.projet)
        self.ed_version.setText(f'V{version}')
        ref = self.projet.get('derniere_generation')
        if ref is None:
            texte, couleur = f'Jamais générée — prochaine génération : V{version}', 'gray'
        else:
            try:
                niveau = M.classer_modification(ref, self.projet)
            except Exception:       # données inattendues : la validation affiche déjà l'erreur
                niveau = 'majeure'
            if niveau is None:
                texte, couleur = f'À jour (dernière génération : V{version})', 'gray'
            else:
                texte = (f'Modification {niveau} — prochaine génération : '
                         f'V{M.prochaine_version(version, niveau)}')
                couleur = '#E67E00' if niveau == 'majeure' else 'gray'
        self.lb_version.setText(texte)
        self.lb_version.setStyleSheet(f'color: {couleur};')

    def radio_courante(self):
        i = self.index_courant()
        return self.projet['radios'][i] if i is not None else None

    def index_courant(self):
        lignes = self.tab_radios.selectionModel().selectedRows()
        if not lignes:
            return None
        i = lignes[0].row()
        return i if i < len(self.projet['radios']) else None

    def _base(self):
        return next((r for r in self.projet['radios'] if r.get('role') == 'base'), None)

    def _rafraichir_radios(self, selection=None):
        """Remplit le tableau des radios, sélectionne la ligne `selection` (sinon garde la sélection)
        et réaffiche le formulaire de la radio sélectionnée."""
        if selection is None:
            selection = self.index_courant()
        self._maj_ligne()
        n = len(self.projet.get('radios', []))
        if n:
            self.tab_radios.blockSignals(True)
            self.tab_radios.selectRow(min(selection or 0, n - 1))
            self.tab_radios.blockSignals(False)
        self._selection_radio()

    def _maj_ligne(self):
        """Met à jour les textes du tableau sans toucher au formulaire (pendant une saisie)."""
        radios = self.projet.get('radios', [])
        t = self.tab_radios
        t.blockSignals(True)
        t.setRowCount(len(radios))
        for i, r in enumerate(radios):
            ip = r.get('ip_octet')
            vals = [i + 1, r.get('nom', ''), ROLES.get(r.get('role'), r.get('role', '')),
                    f'192.168.1.{ip}' if ip is not None else '', '—' if r.get('role') == 'base' else (r.get('amont') or ''),
                    len(r.get('peripheriques', []))]
            for c, val in enumerate(vals):
                t.setItem(i, c, _item(val, centre=c in (0, 5)))
        t.blockSignals(False)

    def _selection_radio(self):
        i = self.index_courant()
        r = self.radio_courante()
        n = len(self.projet.get('radios', []))
        self.bt_supprimer.setEnabled(r is not None and r.get('role') != 'base')
        self.bt_monter.setEnabled(i is not None and i >= 2)
        self.bt_descendre.setEnabled(i is not None and 1 <= i < n - 1)
        self.bt_ajout_periph.setEnabled(r is not None)
        self._radio_form = r            # radio affichée dans le formulaire (cible du renommage)
        self._chargement = True
        try:
            if r is None:
                self.ed_nom.clear(); self.tab_periph.setRowCount(0)
                return
            self.ed_nom.setText(r.get('nom', ''))
            self.cb_role.clear()
            if i == 0 and r.get('role') == 'base':
                roles = ['base']
            elif i == 0:
                roles = ['base', 'repeater', 'remote']
            else:
                roles = ['repeater', 'remote'] + (['base'] if r.get('role') == 'base' else [])
            for k in roles:
                self.cb_role.addItem(ROLES[k], k)
            choisir(self.cb_role, r.get('role'))
            self.cb_role.setEnabled(not (i == 0 and r.get('role') == 'base'))
            self._remplir_amont(r)
            self.sp_ip.setValue(int(r.get('ip_octet') or 100))
            pw = r.get('puissance_dbm')
            self.ck_puiss.setChecked(pw is None)
            self.sp_puiss.setValue(int(pw if pw is not None else self.projet['systeme'].get('puissance_dbm', 34)))
            self.sp_puiss.setEnabled(pw is not None)
            self.ed_titre.setText(r.get('titre_page', '') or '')
            self.ed_desc.setText(r.get('description', '') or '')
            self._remplir_mainv(r)
            self.ck_inv_e.setChecked(bool(r.get('inversion_entrees')))
            self.ck_inv_s.setChecked(bool(r.get('inversion_sorties')))
            self._remplir_periph(r)
        finally:
            self._chargement = False

    def _remplir_amont(self, r):
        base = r.get('role') == 'base'
        self.cb_amont.setVisible(not base)
        self.f_radio.labelForField(self.cb_amont).setVisible(not base)
        self.cb_amont.clear()
        if base:
            return
        for x in self.projet['radios']:
            if x is not r and x.get('role') in ('base', 'repeater'):
                self.cb_amont.addItem(x.get('nom', ''), x.get('nom', ''))
        am = r.get('amont')
        if am and self.cb_amont.findData(am) < 0:
            self.cb_amont.addItem(f'{am} (invalide)', am)
        if am:
            choisir(self.cb_amont, am)
        else:
            self.cb_amont.setCurrentIndex(-1)

    def _remplir_mainv(self, r):
        mv = r.get('mainv') or {}
        di, _do, _ai = occupations(r, sauf='MAINV')
        remplir_combo(self.cb_mainv, 'DI', list(range(1, 9)), di)
        choisir(self.cb_mainv, mv.get('di', 8))
        self.ck_mainv.setChecked(bool(mv.get('actif')))
        self.cb_mainv.setEnabled(bool(mv.get('actif')))

    def _remplir_periph(self, r):
        t = self.tab_periph
        ps = r.get('peripheriques', [])
        t.setRowCount(len(ps))
        for i, p in enumerate(ps):
            t.setItem(i, 0, _item(LIBELLES.get(p.get('type'), p.get('type', ''))))
            t.setItem(i, 1, _item(p.get('nom', '')))
            t.setItem(i, 2, _item(texte_cablage(p)))
            bm = QToolButton(); bm.setText('✎'); bm.setToolTip('Modifier'); bm.setAutoRaise(True)
            bm.clicked.connect(lambda _=False, k=i: self._modifier_periph(k))
            bs = QToolButton(); bs.setText('✕'); bs.setToolTip('Supprimer'); bs.setAutoRaise(True)
            bs.clicked.connect(lambda _=False, k=i: self._supprimer_periph(k))
            t.setCellWidget(i, 3, bm)
            t.setCellWidget(i, 4, bs)

    # ================================================================ modifications
    def _signaler(self):
        if not self._chargement:
            self.maj_version()
            self.modifie.emit()

    def _maj_systeme(self, cle, valeur):
        self.projet['systeme'][cle] = valeur
        self._signaler()

    def _maj_puissance_generale(self, v):
        if self._chargement:
            return
        self.projet['systeme']['puissance_dbm'] = v
        r = self.radio_courante()
        if r is not None and r.get('puissance_dbm') is None:
            self._chargement = True; self.sp_puiss.setValue(v); self._chargement = False
        self._signaler()

    def _generer_cle(self):
        rep = QMessageBox.question(self, 'Nouvelle clé de chiffrement',
                                   'Toutes les radios devront être reprogrammées. Continuer ?')
        if rep != QMessageBox.Yes:
            return
        cle = M.generer_cle()
        self.sys['cle_chiffrement'].setText(cle)
        self._maj_systeme('cle_chiffrement', cle)

    def _maj_radio(self, cle, valeur):
        if self._chargement:
            return
        r = self.radio_courante()
        if r is None:
            return
        r[cle] = valeur
        self._maj_ligne()
        self._signaler()

    def _renommer(self):
        """Applique le nom saisi à la sortie du champ ou sur Entrée (docs/02, « Renommage »)."""
        r = self._radio_form
        if r is None or self._chargement or self._renommage:
            return
        ancien, nouveau = r.get('nom', ''), self.ed_nom.text()
        if nouveau == ancien:
            return
        self._renommage = True          # la boîte de message fait perdre le focus : editingFinished est réémis
        try:
            if not nouveau or any(x is not r and x.get('nom') == nouveau for x in self.projet['radios']):
                self.ed_nom.setText(ancien)
                QMessageBox.warning(self, 'Renommer la radio', 'Nom vide ou déjà utilisé')
                return
            for x in self.projet['radios']:
                if x is not r and x.get('role') != 'base' and x.get('amont') == ancien:
                    x['amont'] = nouveau
            r['nom'] = nouveau
            self._rafraichir_radios()
            self._signaler()
        finally:
            self._renommage = False

    def _ip_libre(self, r, depuis):
        """Plus petit dernier octet libre ≥ `depuis` (sans compter la radio r elle-même)."""
        pris = {x.get('ip_octet') for x in self.projet['radios'] if x is not r}
        return next((n for n in range(depuis, 255) if n not in pris), r.get('ip_octet'))

    def _changer_role(self, _):
        r = self.radio_courante()
        role = self.cb_role.currentData()
        if r is None or role == r.get('role'):
            return
        ancien_role, r['role'] = r.get('role'), role
        if role != 'base' and not r.get('amont'):
            b = self._base()
            r['amont'] = b.get('nom') if b and b is not r else ''
        # plan d'adressage : repeaters à partir de .120, remotes à partir de .101 (recette 1, C4)
        if role == 'repeater':
            r['ip_octet'] = self._ip_libre(r, 120)
        elif role == 'remote' and ancien_role == 'repeater':
            r['ip_octet'] = self._ip_libre(r, 101)
        self._rafraichir_radios()
        self._signaler()

    def _changer_amont(self, _):
        self._maj_radio('amont', self.cb_amont.currentData())

    def _changer_puissance(self, *_):
        if self._chargement:
            return
        general = self.ck_puiss.isChecked()
        self.sp_puiss.setEnabled(not general)
        if general:
            self._chargement = True
            self.sp_puiss.setValue(int(self.projet['systeme'].get('puissance_dbm', 34)))
            self._chargement = False
        self._maj_radio('puissance_dbm', None if general else self.sp_puiss.value())

    def _changer_mainv(self, *_):
        actif = self.ck_mainv.isChecked()
        self.cb_mainv.setEnabled(actif)
        self._maj_radio('mainv', {'actif': True, 'di': self.cb_mainv.currentData() or 8} if actif else {'actif': False})

    # ---------------------------------------------------------------- liste des radios
    def _ajouter_radio(self):
        radios = self.projet['radios']
        if len(radios) >= M.MAX_RADIOS:
            QMessageBox.warning(self, 'Ajouter une radio', f'Impossible : {M.MAX_RADIOS} radios au maximum.')
            return
        noms = {r.get('nom') for r in radios}
        n = len(radios) + 1
        while f'RADIO{n}' in noms:
            n += 1
        pris = {r.get('ip_octet') for r in radios}
        ip = next((x for x in range(101, 255) if x not in pris), 254)
        b = self._base()
        radios.append(nouvelle_radio(f'RADIO{n}', 'remote', ip, b.get('nom') if b else ''))
        self._rafraichir_radios(len(radios) - 1)
        self._signaler()

    def _supprimer_radio(self):
        i, r = self.index_courant(), self.radio_courante()
        if r is None or r.get('role') == 'base':
            return
        rep = QMessageBox.question(self, 'Supprimer une radio', f'Supprimer la radio « {r.get("nom")} » ?')
        if rep != QMessageBox.Yes:
            return
        b = self._base()
        for x in self.projet['radios']:
            if x is not r and x.get('role') != 'base' and x.get('amont') == r.get('nom'):
                x['amont'] = b.get('nom') if b else ''
        del self.projet['radios'][i]
        self._rafraichir_radios(max(0, i - 1))
        self._signaler()

    def _deplacer(self, sens):
        i = self.index_courant()
        radios = self.projet['radios']
        j = (i or 0) + sens
        if i is None or i == 0 or not (1 <= j < len(radios)):
            return
        radios[i], radios[j] = radios[j], radios[i]
        self._rafraichir_radios(j)
        self._signaler()

    # ---------------------------------------------------------------- périphériques
    def _ajouter_periph(self):
        r = self.radio_courante()
        if r is None:
            return
        d = DialoguePeripherique(self, self.projet, r)
        if d.exec():
            r.setdefault('peripheriques', []).append(d.peripherique())
            self._apres_periph()

    def _modifier_periph(self, k):
        r = self.radio_courante()
        if r is None or k >= len(r.get('peripheriques', [])):
            return
        d = DialoguePeripherique(self, self.projet, r, k)
        if d.exec():
            r['peripheriques'][k] = d.peripherique()
            self._apres_periph(k)

    def _supprimer_periph(self, k):
        r = self.radio_courante()
        if r is None:
            return
        p = r['peripheriques'][k]
        rep = QMessageBox.question(self, 'Supprimer un périphérique', f'Supprimer « {p.get("nom")} » ?')
        if rep == QMessageBox.Yes:
            del r['peripheriques'][k]
            self._apres_periph()

    def _apres_periph(self, ligne=None):
        r = self.radio_courante()
        self._chargement = True
        self._remplir_periph(r)
        self._remplir_mainv(r)
        self._chargement = False
        if ligne is not None:
            self.tab_periph.selectRow(ligne)
        self._maj_ligne()
        self._signaler()
