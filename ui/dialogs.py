# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""Boîtes de dialogue : progression et rapport d'import, date d'une mise à jour de configuration,
aide « liste de log », à propos."""
import os, re

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QGuiApplication
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar,
                               QTableWidget, QHeaderView, QDialogButtonBox, QPlainTextEdit, QMessageBox,
                               QFormLayout)

import elpro_logs as L
from ui.common import cellule, preparer_tableau, editeur_date, utc_depuis_qdatetime, ORANGE
from ui.workers import ImportLogs
from version import APP_VERSION, APP_COPYRIGHT, APP_WEBSITE

# Résultat affiché pour chaque statut d'import (02_Ecrans.md § 7)
RESULTATS = {
    'importe': 'Importé',
    'deja_importe': 'Déjà importé',
    'deja_couvert': 'Déjà présent (mêmes horodatages)',
    'vide': 'Fichier vide',
    'erreur': 'Erreur',
    'serie_differente': 'Non importé — autre radio',
}


def texte_resultat(r):
    """Rapport d'import -> (résultat, détail)."""
    st = r.get('statut')
    if st == 'importe':
        return f"Importé — {r.get('message', '')}", ''
    if st == 'erreur':
        return f"Erreur — {r.get('message', '')}", ''
    if st == 'serie_differente':
        return RESULTATS[st], r.get('message', '')
    return RESULTATS.get(st, st), ''


def site_affiche(url):
    """'https://geoazimut.com' -> 'geoazimut.com'."""
    return re.sub(r'^https?://', '', url).rstrip('/')


# ============================================================================================ import
class ProgressionImport(QDialog):
    """Fenêtre de progression : une barre pour le fichier en cours, une barre globale, bouton Annuler.
    Lance l'import dans un QThread ; `resultats` = [(chemin, rapports)] à la fermeture."""

    def __init__(self, parent, chemin_base, sid, fichiers, titre='Import des logs'):
        super().__init__(parent)
        self.setWindowTitle(titre)
        self.setMinimumWidth(480)
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)
        self.n = len(fichiers)
        lay = QVBoxLayout(self)
        self.lbl_fichier = QLabel('Préparation…')
        lay.addWidget(self.lbl_fichier)
        self.barre_fichier = QProgressBar()
        self.barre_fichier.setRange(0, 100)
        lay.addWidget(self.barre_fichier)
        self.lbl_global = QLabel(f'Fichier 0 sur {self.n}')
        lay.addWidget(self.lbl_global)
        self.barre_globale = QProgressBar()
        self.barre_globale.setRange(0, max(1, self.n))
        lay.addWidget(self.barre_globale)
        b = QHBoxLayout()
        b.addStretch(1)
        self.bouton_annuler = QPushButton('Annuler')
        self.bouton_annuler.setToolTip("Arrête l'import après le fichier en cours")
        self.bouton_annuler.clicked.connect(self.annuler)
        b.addWidget(self.bouton_annuler)
        lay.addLayout(b)

        self.thread = ImportLogs(chemin_base, sid, fichiers)
        self.thread.fichier_commence.connect(self._commence)
        self.thread.avancement.connect(self._avance)
        self.thread.fichier_termine.connect(self._termine)
        self.thread.finished.connect(self.accept)

    @property
    def resultats(self):
        return self.thread.resultats

    def exec(self):
        self.thread.start()
        return super().exec()

    def _commence(self, i, nom):
        self.lbl_fichier.setText(f'Import de {nom}…')
        self.lbl_global.setText(f'Fichier {i + 1} sur {self.n}')
        self.barre_fichier.setValue(0)

    def _avance(self, n, total):
        self.barre_fichier.setValue(int(100 * n / total) if total else 0)

    def _termine(self, i, _chemin, _r):
        self.barre_fichier.setValue(100)
        self.barre_globale.setValue(i + 1)

    def annuler(self):
        self.thread.annuler()
        self.bouton_annuler.setEnabled(False)
        self.bouton_annuler.setText('Arrêt après le fichier en cours…')

    def reject(self):           # Échap : même effet que Annuler (la fenêtre se ferme à la fin du thread)
        self.annuler()

    def closeEvent(self, e):
        if self.thread.isRunning():
            self.annuler()
            e.ignore()
        else:
            e.accept()


class RapportImport(QDialog):
    """Rapport final : Fichier, Résultat, Détail ; avertissements en orange sous la ligne du fichier."""

    def __init__(self, parent, resultats, annule=False):
        super().__init__(parent)
        self.setWindowTitle("Rapport d'import")
        self.resize(820, 380)
        lay = QVBoxLayout(self)
        rapports = [r for _c, rs in resultats for r in rs]
        n_ok = sum(1 for r in rapports if r.get('statut') == 'importe')
        resume = f'{n_ok} log(s) importé(s) sur {len(rapports)}.'
        if annule:
            resume += ' Import annulé : les fichiers suivants n\'ont pas été traités.'
        lay.addWidget(QLabel(resume))
        self.table = preparer_tableau(QTableWidget(), ['Fichier', 'Résultat', 'Détail'])
        for r in rapports:
            res, det = texte_resultat(r)
            k = self.table.rowCount()
            self.table.insertRow(k)
            couleur = '#2E7D32' if r.get('statut') == 'importe' else ('#C62828' if r.get('statut') in
                                                                        ('erreur', 'serie_differente') else None)
            self.table.setItem(k, 0, cellule(r.get('fichier', '')))
            self.table.setItem(k, 1, cellule(res, couleur=couleur))
            self.table.setItem(k, 2, cellule(det))
            for a in r.get('avertissements') or []:
                k = self.table.rowCount()
                self.table.insertRow(k)
                self.table.setItem(k, 0, cellule(''))
                self.table.setItem(k, 1, cellule(a, couleur=ORANGE))
                self.table.setSpan(k, 1, 1, 2)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setStretchLastSection(True)
        lay.addWidget(self.table)
        b = QDialogButtonBox(QDialogButtonBox.Close)
        b.button(QDialogButtonBox.Close).setText('Fermer')
        b.rejected.connect(self.reject)
        lay.addWidget(b)

    def lignes(self):
        """Contenu du tableau (pour la recette automatique)."""
        return [tuple(self.table.item(k, c).text() if self.table.item(k, c) else '' for c in range(3))
                for k in range(self.table.rowCount())]


# ============================================================================================ configuration
class DateMiseEnService(QDialog):
    """« À partir de quand cette configuration est-elle en service ? » (heure suisse, défaut : maintenant)."""

    def __init__(self, parent, version):
        super().__init__(parent)
        self.setWindowTitle('Mettre à jour la configuration')
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f'Nouvelle configuration V{version}.\n'
                             'À partir de quand cette configuration est-elle en service ?'))
        f = QFormLayout()
        self.date = editeur_date(L.maintenant())
        f.addRow('En service depuis (heure suisse) :', self.date)
        lay.addLayout(f)
        note = QLabel('Les valeurs enregistrées avant cette date gardent les libellés de la configuration précédente.')
        note.setWordWrap(True)
        note.setStyleSheet('color: gray;')
        lay.addWidget(note)
        b = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        b.button(QDialogButtonBox.Ok).setText('Mettre à jour')
        b.button(QDialogButtonBox.Cancel).setText('Annuler')
        b.accepted.connect(self.accept)
        b.rejected.connect(self.reject)
        lay.addWidget(b)

    def valable_depuis(self):
        return utc_depuis_qdatetime(self.date.dateTime())


# ============================================================================================ aide
class AideListeLog(QDialog):
    """Liste de log à configurer sur la centrale : réglages et entrées standard GeoAzimut."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle('Liste de log à configurer sur la centrale')
        self.resize(520, 600)
        lay = QVBoxLayout(self)
        intro = QLabel('Sur la centrale (base), dans la configuration DataLog, régler :')
        intro.setWordWrap(True)
        lay.addWidget(intro)
        lay.addWidget(QLabel('\n'.join(f'• {k} : {v}' for k, v in L.REGLAGES_STANDARD.items())))
        lay.addWidget(QLabel('puis saisir les entrées suivantes, dans cet ordre :'))
        self.table = preparer_tableau(QTableWidget(), ['Nom', '1er registre', 'Nombre'])
        for nom, reg, n in L.LISTE_STANDARD:
            k = self.table.rowCount()
            self.table.insertRow(k)
            self.table.setItem(k, 0, cellule(nom))
            self.table.setItem(k, 1, cellule(reg, droite=True))
            self.table.setItem(k, 2, cellule(n, droite=True))
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        lay.addWidget(self.table)
        b = QHBoxLayout()
        copier = QPushButton('Copier')
        copier.setToolTip('Copie la liste dans le presse-papiers (colonnes séparées par des tabulations)')
        copier.clicked.connect(self.copier)
        b.addWidget(copier)
        b.addStretch(1)
        fermer = QPushButton('Fermer')
        fermer.setDefault(True)
        fermer.clicked.connect(self.accept)
        b.addWidget(fermer)
        lay.addLayout(b)

    @staticmethod
    def texte():
        lignes = [f'{k}\t{v}' for k, v in L.REGLAGES_STANDARD.items()] + ['', 'Nom\t1er registre\tNombre']
        lignes += [f'{nom}\t{reg}\t{n}' for nom, reg, n in L.LISTE_STANDARD]
        return '\n'.join(lignes) + '\n'

    def copier(self):
        QGuiApplication.clipboard().setText(self.texte())


class AboutDialog(QDialog):
    """Fenêtre « À propos » : version, copyright, site web, licence et composants tiers.
    Toutes les mentions viennent de version.py ; LICENSE et THIRD_PARTY_NOTICES.md sont lus dans `base`."""
    FICHIERS = {'Licence': 'LICENSE', 'Composants tiers': 'THIRD_PARTY_NOTICES.md'}

    def __init__(self, parent, base):
        super().__init__(parent)
        self.base = base
        self.setWindowTitle("À propos d'ELPRO Logs")
        self.setFixedSize(420, 360)
        lay = QVBoxLayout(self)
        lay.setSpacing(6)

        def ligne(texte, taille=None, gras=False, lien=False):
            l = QLabel(texte)
            l.setAlignment(Qt.AlignCenter)
            l.setWordWrap(True)
            if taille or gras:
                f = l.font()
                if taille:
                    f.setPointSize(taille)
                f.setBold(gras)
                l.setFont(f)
            if lien:
                l.setTextFormat(Qt.RichText)
                l.setOpenExternalLinks(True)
            lay.addWidget(l)
            return l

        logo = QLabel()
        logo.setAlignment(Qt.AlignCenter)
        logo.setPixmap(QPixmap(os.path.join(base, 'resources', 'app_icon.png'))
                       .scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        lay.addWidget(logo)
        ligne('ELPRO Logs', taille=16, gras=True)
        ligne(f'Version {APP_VERSION}')
        ligne('Historique des logs des centrales d\'alarme ELPRO 415U-2-C4.')
        ligne(APP_COPYRIGHT)
        self.lien = ligne(f'<a href="{APP_WEBSITE}">{site_affiche(APP_WEBSITE)}</a>', lien=True)
        ligne('Utilisation gratuite. Reproduction, modification et redistribution interdites sans '
              'autorisation écrite de Geoazimut SàRL.', taille=8)
        ligne('Outil indépendant, non affilié à ELPRO Technologies.', taille=8)
        lay.addStretch(1)

        boutons = QHBoxLayout()
        for texte in self.FICHIERS:
            b = QPushButton(texte)
            b.clicked.connect(lambda _=False, t=texte: self.afficher_fichier(t))
            boutons.addWidget(b)
        boutons.addStretch(1)
        fermer = QPushButton('Fermer')
        fermer.setDefault(True)
        fermer.clicked.connect(self.accept)
        boutons.addWidget(fermer)
        lay.addLayout(boutons)

    def texte_fichier(self, titre):
        """Contenu de LICENSE / THIRD_PARTY_NOTICES.md embarqué avec l'application ('' si absent)."""
        chemin = os.path.join(self.base, self.FICHIERS[titre])
        try:
            with open(chemin, encoding='utf-8') as f:
                return f.read()
        except OSError:
            return ''

    def afficher_fichier(self, titre):
        texte = self.texte_fichier(titre)
        if not texte:
            QMessageBox.warning(self, titre, f'Fichier introuvable : {self.FICHIERS[titre]}')
            return
        d = QDialog(self)
        d.setWindowTitle(titre)
        d.resize(640, 480)
        v = QVBoxLayout(d)
        zone = QPlainTextEdit(texte)
        zone.setReadOnly(True)
        v.addWidget(zone)
        b = QDialogButtonBox(QDialogButtonBox.Close)
        b.button(QDialogButtonBox.Close).setText('Fermer')
        b.rejected.connect(d.reject)
        v.addWidget(b)
        d.exec()
