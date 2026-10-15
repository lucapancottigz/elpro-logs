# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""Page 2 : configuration générée, affichée façon CConfig (lecture seule) + exports."""
import os

from PySide6.QtCore import Qt, QSettings, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeWidget, QTreeWidgetItem, QLabel,
                               QScrollArea, QFormLayout, QTableWidget, QTableWidgetItem, QAbstractItemView, QPushButton,
                               QStackedWidget, QFileDialog, QMessageBox, QFrame)

import elpro_engine as M
import views as V
import export_excel as XL
import export_pdf as PDF

MSG_VIDE = 'Aucune configuration générée. Remplir la page 1 puis cliquer sur Générer la configuration.'


class PageResult(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.plan = None
        self.noeuds = {}
        lay = QVBoxLayout(self)

        self.bandeau = QLabel('Configuration modifiée : cliquer sur Générer')
        self.bandeau.setAlignment(Qt.AlignCenter)
        self.bandeau.setStyleSheet('background:#FFF4CE; color:#7A5800; border:1px solid #E6C35C; padding:6px; font-weight:bold;')
        self.bandeau.hide()
        lay.addWidget(self.bandeau)

        self.pile = QStackedWidget()
        vide = QLabel(MSG_VIDE); vide.setAlignment(Qt.AlignCenter); vide.setWordWrap(True)
        f = vide.font(); f.setPointSize(f.pointSize() + 2); vide.setFont(f)
        vide.setStyleSheet('color:#666;')
        self.pile.addWidget(vide)

        split = QSplitter(Qt.Horizontal)
        self.arbre = QTreeWidget()
        self.arbre.setHeaderHidden(True)
        self.arbre.currentItemChanged.connect(self._afficher_noeud)
        self.defil = QScrollArea(); self.defil.setWidgetResizable(True)
        split.addWidget(self.arbre)
        split.addWidget(self.defil)
        split.setStretchFactor(1, 1)
        split.setSizes([260, 900])
        split.setChildrenCollapsible(False)
        self.pile.addWidget(split)
        lay.addWidget(self.pile, 1)

        b = QHBoxLayout()
        self.boutons = []
        for texte, action in (('Générer le .cdb', self._export_cdb), ('Générer les .sconf', self._export_sconf),
                              ('Compte rendu PDF', self._export_pdf), ("Liste d'adresses Excel", self._export_excel)):
            bt = QPushButton(texte); bt.setMinimumHeight(30); bt.clicked.connect(action)
            b.addWidget(bt); self.boutons.append(bt)
        b.addStretch(1)
        lay.addLayout(b)
        self.vider()

    # ================================================================ état
    def vider(self, modifiee=False):
        """Plus de plan : page vide, boutons grisés (bandeau si la page 1 a été modifiée après génération)."""
        self.plan = None
        self.arbre.clear()
        self.noeuds = {}
        self.pile.setCurrentIndex(0)
        self.bandeau.setVisible(modifiee)
        for bt in self.boutons:
            bt.setEnabled(False)

    def afficher(self, plan):
        self.plan = plan
        self.bandeau.hide()
        self.arbre.blockSignals(True)
        self.arbre.clear()
        self.noeuds = {}
        items = {}
        premiere_radio = None
        for n in V.vue_page2(plan):
            ch = tuple(n['chemin'])
            for k in range(1, len(ch) + 1):
                cle = ch[:k]
                if cle not in items:
                    parent = items.get(cle[:-1])
                    it = QTreeWidgetItem([cle[-1]])
                    (parent.addChild(it) if parent else self.arbre.addTopLevelItem(it))
                    items[cle] = it
            it = items[ch]
            it.setData(0, Qt.UserRole, ch)
            self.noeuds[ch] = n
            if 'Units' in ch:
                u = ch.index('Units')
                if len(ch) > u + 1 and premiere_radio is None:
                    premiere_radio = ch[:u + 2]
        # ouverture : racine, « Units », et la première radio seulement
        for cle, it in items.items():
            ouvrir = 'Units' not in cle or len(cle) <= cle.index('Units') + 1 or cle[:len(premiere_radio)] == premiere_radio
            it.setExpanded(ouvrir)
        self.arbre.blockSignals(False)
        self.pile.setCurrentIndex(1)
        for bt in self.boutons:
            bt.setEnabled(True)
        if self.arbre.topLevelItemCount():
            self.arbre.setCurrentItem(self.arbre.topLevelItem(0))
            self._afficher_noeud(self.arbre.topLevelItem(0))

    # ================================================================ contenu d'un nœud
    def _afficher_noeud(self, it, _precedent=None):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setAlignment(Qt.AlignTop)
        if it is None:
            self.defil.setWidget(page); return
        ch = it.data(0, Qt.UserRole)
        titre = QLabel(' / '.join(ch) if ch else it.text(0))
        f = titre.font(); f.setPointSize(f.pointSize() + 3); f.setBold(True); titre.setFont(f)
        v.addWidget(titre)
        trait = QFrame(); trait.setFrameShape(QFrame.HLine); trait.setFrameShadow(QFrame.Sunken)
        v.addWidget(trait)
        n = self.noeuds.get(ch) if ch else None
        if n is None:
            v.addWidget(QLabel('Sélectionner un élément dans l\'arbre.'))
        elif n['type'] == 'formulaire':
            form = QFormLayout()
            form.setLabelAlignment(Qt.AlignRight)
            form.setHorizontalSpacing(16)
            for lib, val in n['contenu']:
                lv = QLabel(str(val))
                lv.setTextInteractionFlags(Qt.TextSelectableByMouse)
                lv.setStyleSheet('background:palette(base); border:1px solid palette(mid); padding:2px 4px;')
                lv.setMinimumWidth(260)
                form.addRow(QLabel(str(lib)), lv)
            h = QHBoxLayout(); h.addLayout(form); h.addStretch(1)
            v.addLayout(h)
        else:
            for tb in n['contenu']:
                lt = QLabel(str(tb['titre']))
                fb = lt.font(); fb.setBold(True); lt.setFont(fb)
                v.addSpacing(6)
                v.addWidget(lt)
                v.addWidget(self._tableau(tb['colonnes'], tb['lignes']), 0, Qt.AlignLeft)
        v.addStretch(1)
        self.defil.setWidget(page)

    @staticmethod
    def _tableau(colonnes, lignes):
        t = QTableWidget(len(lignes), len(colonnes))
        t.setHorizontalHeaderLabels([str(c) for c in colonnes])
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.verticalHeader().setVisible(False)
        t.setAlternatingRowColors(True)
        for i, l in enumerate(lignes):
            for j, val in enumerate(l):
                t.setItem(i, j, QTableWidgetItem(str(val)))
        t.resizeColumnsToContents()
        t.resizeRowsToContents()
        # le tableau prend toute sa taille : c'est la zone de défilement de la page qui défile
        t.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        t.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        cadre = 2 * t.frameWidth()
        t.setFixedSize(t.horizontalHeader().length() + cadre + 2,
                       t.horizontalHeader().height() + t.verticalHeader().length() + cadre + 2)
        return t

    # ================================================================ exports
    def _dossier(self):
        return QSettings().value('dossier_export', os.path.expanduser('~/Documents'))

    def _memoriser(self, chemin_ou_dossier):
        d = chemin_ou_dossier if os.path.isdir(chemin_ou_dossier) else os.path.dirname(chemin_ou_dossier)
        QSettings().setValue('dossier_export', d)

    def _succes(self, message, dossier):
        box = QMessageBox(QMessageBox.Information, 'Export', message, parent=self)
        ouvrir = box.addButton('Ouvrir le dossier', QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec()
        if box.clickedButton() is ouvrir:
            QDesktopServices.openUrl(QUrl.fromLocalFile(dossier))

    def _echec(self, e):
        QMessageBox.critical(self, 'Export impossible', f"L'écriture a échoué :\n{e}")

    def _enregistrer(self, suffixe, filtre, ecrire):
        if self.plan is None:
            return
        nom = M.base_nom_fichier(self.plan) + suffixe      # ex. Demo_Site_A_V2.1.cdb
        chemin, _ = QFileDialog.getSaveFileName(self, 'Enregistrer sous', os.path.join(self._dossier(), nom), filtre)
        if not chemin:
            return
        try:
            ecrire(chemin)
        except Exception as e:  # fichier ouvert dans Excel, droits, disque...
            self._echec(e)
            return
        self._memoriser(chemin)
        self._succes(f'Fichier créé : {os.path.normpath(chemin)}', os.path.dirname(chemin))

    def _titre(self):
        """Titre du PDF et en-tête de l'Excel : « Demo Site A — V2.1 »."""
        return f"{self.plan['systeme']['nom_projet']} — V{self.plan['version_config']}"

    def _export_cdb(self):
        self._enregistrer('.cdb', 'CConfig (*.cdb)', lambda c: M.ecrire_cdb(self.plan, c))

    def _export_pdf(self):
        self._enregistrer('_Compte_rendu.pdf', 'PDF (*.pdf)',
                          lambda c: PDF.ecrire_pdf(V.donnees_pdf(self.plan), c, self._titre()))

    def _export_excel(self):
        self._enregistrer('_Adresses.xlsx', 'Excel (*.xlsx)',
                          lambda c: XL.ecrire_excel(V.donnees_excel(self.plan), c, self._titre()))

    def _export_sconf(self):
        if self.plan is None:
            return
        dossier = QFileDialog.getExistingDirectory(self, 'Choisir un dossier', self._dossier())
        if not dossier:
            return
        crees = []
        v = self.plan['version_config']
        try:
            for S in self.plan['stations']:
                if S['iop']:
                    crees.append(M.ecrire_sconf(S['iop'], os.path.join(dossier, f"IOPlus_{S['nom']}_V{v}_DESACTIVE.sconf")))
        except Exception as e:
            self._echec(e)
            return
        self._memoriser(dossier)
        liste = '\n'.join(f'  • {os.path.basename(c)}' for c in crees)
        self._succes(f'Fichiers créés dans {os.path.normpath(dossier)} :\n{liste}', dossier)
