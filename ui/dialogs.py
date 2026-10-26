# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""Boîtes de dialogue : progression et rapport d'import, date d'une mise à jour de configuration,
aide « liste de log », à propos, emplacement des données."""
import os, re, datetime

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QPixmap, QGuiApplication, QDesktopServices
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar,
                               QTableWidget, QHeaderView, QDialogButtonBox, QPlainTextEdit, QMessageBox,
                               QFormLayout, QLineEdit, QFileDialog)

import elpro_logs as L
from ui.common import cellule, preparer_tableau, editeur_date, utc_depuis_qdatetime, nombre, pluriel, ORANGE
from ui.workers import ImportLogs, Fonction, RecupererLogs
import elpro_remote as R
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

    def __init__(self, parent, resultats, annule=False, titre="Rapport d'import", resume=None, alerte=None):
        super().__init__(parent)
        self.setWindowTitle(titre)
        self.resize(820, 380)
        lay = QVBoxLayout(self)
        rapports = [r for _c, rs in resultats for r in rs]
        if alerte:                                  # ex. logs déjà effacés par la centrale
            self.alerte = QLabel(alerte)
            self.alerte.setWordWrap(True)
            self.alerte.setStyleSheet(f'color: {ORANGE}; font-weight: bold;')
            lay.addWidget(self.alerte)
        if resume is None:
            n_ok = sum(1 for r in rapports if r.get('statut') == 'importe')
            resume = f'{n_ok} log(s) importé(s) sur {len(rapports)}.'
            if annule:
                resume += ' Import annulé : les fichiers suivants n\'ont pas été traités.'
        self.resume = QLabel(resume)
        self.resume.setWordWrap(True)
        lay.addWidget(self.resume)
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


# ============================================================================================ centrale
class ConnexionCentrale(QDialog):
    """Système › Connexion à la centrale : adresse, utilisateur, mot de passe (chiffré par le moteur),
    bouton Tester (dans un thread). Le mot de passe n'est jamais écrit en clair."""

    def __init__(self, parent, magasin, sid, nom):
        super().__init__(parent)
        self.m, self.sid = magasin, sid
        self.acces = magasin.acces(sid)
        self.setWindowTitle(f'Connexion à la centrale — {nom}')
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        f = QFormLayout()
        self.adresse = QLineEdit(self.acces['adresse'] if self.acces else R.ADRESSE_DEFAUT)
        self.adresse.setPlaceholderText('adresse de la centrale dans le tunnel WireGuard')
        f.addRow('Adresse :', self.adresse)
        self.utilisateur = QLineEdit((self.acces or {}).get('utilisateur') or R.UTILISATEUR_DEFAUT)
        f.addRow('Utilisateur :', self.utilisateur)
        self.mdp = QLineEdit()
        self.mdp.setEchoMode(QLineEdit.Password)
        if self.acces and self.acces['mdp']:
            self.mdp.setPlaceholderText('(inchangé)')
        f.addRow('Mot de passe :', self.mdp)
        lay.addLayout(f)
        note = QLabel('Activez d\'abord le tunnel WireGuard.')
        note.setStyleSheet('color: gray;')
        lay.addWidget(note)
        t = QHBoxLayout()
        self.bouton_tester = QPushButton('Tester la connexion')
        self.bouton_tester.clicked.connect(self.tester)
        t.addWidget(self.bouton_tester)
        self.resultat = QLabel()
        self.resultat.setWordWrap(True)
        t.addWidget(self.resultat, 1)
        lay.addLayout(t)
        b = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        b.button(QDialogButtonBox.Save).setText('Enregistrer')
        b.button(QDialogButtonBox.Cancel).setText('Annuler')
        b.accepted.connect(self.enregistrer)
        b.rejected.connect(self.reject)
        lay.addWidget(b)
        self.thread = None

    def _mdp(self):
        """Mot de passe saisi, sinon celui déjà enregistré (déchiffré seulement pour s'en servir)."""
        if self.mdp.text():
            return self.mdp.text()
        if self.acces and self.acces['mdp']:
            return R.retrouver_mdp(self.acces['mdp'])
        return ''

    def tester(self):
        try:
            session = R.Session(self.adresse.text().strip(), self.utilisateur.text().strip(), self._mdp())
        except (ValueError, OSError) as e:
            self._afficher(False, str(e))
            return
        self.bouton_tester.setEnabled(False)
        self.resultat.setStyleSheet('color: gray;')
        self.resultat.setText('Connexion…')
        self.thread = Fonction(session.identifier)
        self.thread.termine.connect(lambda c: self._afficher(True, f"Connecté à {c['nom'] or '?'} (n° {c['serie'] or '?'})"))
        self.thread.echec.connect(lambda e: self._afficher(False, getattr(e, 'message', None) or str(e)))
        self.thread.start()

    def _afficher(self, ok, texte):
        self.bouton_tester.setEnabled(True)
        self.resultat.setStyleSheet('color: #2E7D32;' if ok else 'color: #C62828;')
        self.resultat.setText(texte)

    def enregistrer(self):
        if not self.adresse.text().strip():
            QMessageBox.warning(self, 'Connexion à la centrale', 'Saisissez l\'adresse de la centrale.')
            return
        if self.mdp.text():
            protege = R.proteger_mdp(self.mdp.text())
        else:                                       # champ vide : garder le mot de passe enregistré tel quel
            protege = self.acces['mdp'] if self.acces else R.proteger_mdp('')
        self.m.definir_acces(self.sid, self.adresse.text(), self.utilisateur.text() or R.UTILISATEUR_DEFAUT, protege)
        self.accept()


FILTRE_BASE = 'Base ELPRO Logs (*.db)'


class EmplacementDonnees(QDialog):
    """Fichier › Emplacement des données : chemin et taille de la base, déplacer, ouvrir une autre base,
    copie de sauvegarde, retour à l'emplacement par défaut (actions faites par la fenêtre principale)."""

    def __init__(self, fenetre):
        super().__init__(fenetre)
        self.fenetre = fenetre
        self.setWindowTitle('Emplacement des données')
        self.resize(640, 260)
        lay = QVBoxLayout(self)
        f = QFormLayout()
        ligne = QHBoxLayout()
        self.chemin = QLabel()
        self.chemin.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.chemin.setWordWrap(True)
        ligne.addWidget(self.chemin, 1)
        dossier = QPushButton('Ouvrir le dossier')
        dossier.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(os.path.dirname(os.path.abspath(self.fenetre.chemin_base)))))
        ligne.addWidget(dossier)
        f.addRow('Emplacement actuel :', ligne)
        self.taille = QLabel()
        f.addRow('Taille :', self.taille)
        lay.addLayout(f)
        self.boutons = []
        for texte, fonction in (('Déplacer vers un autre dossier…', self.deplacer),
                                ('Ouvrir une base existante…', self.ouvrir),
                                ('Faire une copie de sauvegarde…', self.sauvegarder),
                                ('Revenir à l\'emplacement par défaut', self.defaut)):
            bt = QPushButton(texte)
            bt.clicked.connect(lambda _=False, fn=fonction: (fn(), self.actualiser()))
            lay.addWidget(bt)
            self.boutons.append(bt)
        self.bouton_defaut = self.boutons[-1]
        b = QDialogButtonBox(QDialogButtonBox.Close)
        b.button(QDialogButtonBox.Close).setText('Fermer')
        b.rejected.connect(self.reject)
        lay.addWidget(b)
        self.actualiser()

    def actualiser(self):
        fe = self.fenetre
        self.chemin.setText(os.path.abspath(fe.chemin_base))
        try:
            mo = fe.magasin.taille_fichier() / 1e6
        except OSError:
            mo = 0
        self.taille.setText(f"{nombre(round(mo, 1))} Mo · {pluriel(len(fe.magasin.systemes()), 'système')}")
        for bt in self.boutons:                    # rien pendant un import ou une récupération
            bt.setEnabled(not fe.occupe)
        self.bouton_defaut.setEnabled(not fe.occupe and not fe.est_par_defaut())

    def deplacer(self):
        d = QFileDialog.getExistingDirectory(self, 'Déplacer la base vers…',
                                             os.path.dirname(os.path.abspath(self.fenetre.chemin_base)))
        if d:
            self.fenetre.deplacer_base(d)

    def ouvrir(self):
        c, _ = QFileDialog.getOpenFileName(self, 'Ouvrir une base existante',
                                           os.path.dirname(os.path.abspath(self.fenetre.chemin_base)), FILTRE_BASE)
        if c:
            self.fenetre.ouvrir_base_existante(c)

    def sauvegarder(self):
        nom = f'elpro_logs_sauvegarde_{datetime.date.today():%Y-%m-%d}.db'
        c, _ = QFileDialog.getSaveFileName(self, 'Faire une copie de sauvegarde',
                                           os.path.join(os.path.dirname(os.path.abspath(self.fenetre.chemin_base)), nom),
                                           FILTRE_BASE)
        if c:
            self.fenetre.sauvegarder_base(c)

    def defaut(self):
        self.fenetre.revenir_defaut()


class ProgressionRecuperation(QDialog):
    """Progression d'une récupération : « Fichier n / total : nom » (ou « <système> — fichier n / total »),
    bouton Annuler (arrêt après le fichier en cours). `rapport` à la fermeture."""

    def __init__(self, parent, chemin_base, sid=None, forcer=False):
        super().__init__(parent)
        self.setWindowTitle('Récupération des logs' if sid is not None else 'Tout récupérer')
        self.setMinimumWidth(480)
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)
        lay = QVBoxLayout(self)
        self.texte = QLabel('Connexion à la centrale…')
        lay.addWidget(self.texte)
        self.barre = QProgressBar()
        self.barre.setRange(0, 0)                   # indéterminée tant que la liste n'est pas connue
        lay.addWidget(self.barre)
        b = QHBoxLayout()
        b.addStretch(1)
        self.bouton_annuler = QPushButton('Annuler')
        self.bouton_annuler.setToolTip('Arrête la récupération après le fichier en cours')
        self.bouton_annuler.clicked.connect(self.annuler)
        b.addWidget(self.bouton_annuler)
        lay.addLayout(b)
        self.thread = RecupererLogs(chemin_base, sid, forcer)
        self.thread.avancement.connect(self._avance)
        self.thread.finished.connect(self.accept)

    @property
    def rapport(self):
        return self.thread.rapport

    def exec(self):
        self.thread.start()
        return super().exec()

    def _avance(self, systeme, n, total, nom):
        self.barre.setRange(0, max(1, total))
        self.barre.setValue(n)
        if systeme:
            self.texte.setText(f'{systeme} — fichier {min(n + 1, total)} / {total}' if total else
                               f'{systeme} — aucun nouveau fichier')
        elif nom:
            self.texte.setText(f'Fichier {n + 1} / {total} : {nom}')
        else:
            self.texte.setText(f'{total} fichier(s) traité(s).')

    def annuler(self):
        self.thread.annuler()
        self.bouton_annuler.setEnabled(False)
        self.bouton_annuler.setText('Arrêt après le fichier en cours…')

    def reject(self):
        self.annuler()

    def closeEvent(self, e):
        if self.thread.isRunning():
            self.annuler()
            e.ignore()
        else:
            e.accept()


# Résultat affiché pour chaque statut de récupération (COMPLEMENT_V1.1, tableau des statuts)
STATUTS_RECUPERATION = {
    'ok': 'Logs importés', 'rien_de_nouveau': 'Aucun nouveau fichier', 'injoignable': 'Centrale injoignable',
    'introuvable': 'Erreur', 'erreur': 'Erreur', 'acces_refuse': 'Accès refusé',
    'non_configure': 'Connexion non configurée', 'mauvaise_centrale': 'Autre centrale (non importé)',
    'annule': 'Annulé'}


class RapportRecuperationTout(QDialog):
    """Rapport de « Tout récupérer » : une ligne par système ; alerte en orange sous la ligne."""

    def __init__(self, parent, resultats):
        super().__init__(parent)
        self.setWindowTitle('Tout récupérer')
        self.resize(900, 360)
        lay = QVBoxLayout(self)
        if not resultats:
            lay.addWidget(QLabel('Aucun système n\'a de connexion à la centrale configurée.'))
        self.table = preparer_tableau(QTableWidget(), ['Système', 'Résultat', 'Nouveaux fichiers', 'Message'])
        for S, rap in resultats:
            k = self.table.rowCount()
            self.table.insertRow(k)
            st = rap.get('statut')
            couleur = '#2E7D32' if st == 'ok' else (None if st in ('rien_de_nouveau', 'annule') else '#C62828')
            self.table.setItem(k, 0, cellule(S['nom']))
            self.table.setItem(k, 1, cellule(STATUTS_RECUPERATION.get(st, st), couleur=couleur))
            self.table.setItem(k, 2, cellule(rap.get('nouveaux', 0), droite=True))
            self.table.setItem(k, 3, cellule(rap.get('message', '')))
            if rap.get('alerte'):
                k = self.table.rowCount()
                self.table.insertRow(k)
                self.table.setItem(k, 0, cellule(''))
                self.table.setItem(k, 1, cellule(rap['alerte'], couleur=ORANGE))
                self.table.setSpan(k, 1, 1, 3)
        h = self.table.horizontalHeader()
        for c in range(3):
            h.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        h.setStretchLastSection(True)
        lay.addWidget(self.table)
        b = QDialogButtonBox(QDialogButtonBox.Close)
        b.button(QDialogButtonBox.Close).setText('Fermer')
        b.rejected.connect(self.reject)
        lay.addWidget(b)

    def lignes(self):
        return [tuple(self.table.item(k, c).text() if self.table.item(k, c) else '' for c in range(4))
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
