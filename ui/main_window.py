# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""Fenêtre principale : menus (dont l'entrée « Tout récupérer »), un onglet par système (tous ouverts au démarrage), page d'accueil,
glisser-déposer, récupération des logs depuis les centrales, barre d'état (taille de la base, copyright)."""
import os, sqlite3

from PySide6.QtCore import Qt, QSettings, QStandardPaths, QEventLoop, QTimer, QEvent, QUrl
from PySide6.QtGui import QAction, QKeySequence, QDesktopServices
from PySide6.QtWidgets import (QMainWindow, QTabWidget, QStackedWidget, QWidget, QVBoxLayout, QLabel, QPushButton,
                               QFileDialog, QMessageBox, QInputDialog, QProgressDialog, QApplication)

import elpro_engine as M
import elpro_logs as L
from ui.common import lire_projet, cle_systeme, projet_normalise, pluriel, nombre
from ui.dialogs import (AboutDialog, ProgressionImport, RapportImport, DateMiseEnService, AideListeLog,
                        site_affiche, ConnexionCentrale, ProgressionRecuperation, RapportRecuperationTout,
                        EmplacementDonnees, FILTRE_BASE)
from ui.system_tab import SystemTab
from ui.workers import Tache, Fonction, attendre_tous
from version import APP_COMPANY, APP_COPYRIGHT, APP_WEBSITE

FILTRE_PROJET = 'Projet ELPRO Config (*.elpro.json *.json)'
FILTRE_LOGS = 'Logs ELPRO (*.log *.zip *.csv);;Tous les fichiers (*)'
EXT_LOGS = ('.log', '.zip', '.csv')
CLE_BASE = 'base/chemin'                    # QSettings : emplacement choisi ; absent = emplacement par défaut
SURVEILLANCE_MS = 30000                     # v1.5 : contrôle du fichier partagé (publications des autres PC)
PAS_ENREGISTRE = ('Les dernières modifications ne sont pas encore enregistrées dans le fichier partagé. '
                  'Réessayez dans un instant.')


def meme_fichier(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def memoriser_base(chemin):
    """Enregistre l'emplacement de la base (l'emplacement par défaut efface la clé)."""
    if meme_fichier(chemin, L.chemin_base_defaut()):
        QSettings().remove(CLE_BASE)
    else:
        QSettings().setValue(CLE_BASE, os.path.abspath(chemin))


def choisir_base(message, reessayer):
    """Fenêtre « base introuvable / inutilisable » -> 'reessayer' | 'ouvrir' | 'defaut' | 'quitter'."""
    b = QMessageBox(QMessageBox.Critical, 'ELPRO Logs', message)
    choix = {}
    if reessayer:
        choix[b.addButton('Réessayer', QMessageBox.AcceptRole)] = 'reessayer'
    choix[b.addButton('Ouvrir une autre base…', QMessageBox.ActionRole)] = 'ouvrir'
    choix[b.addButton('Utiliser l\'emplacement par défaut', QMessageBox.ActionRole)] = 'defaut'
    quitter = b.addButton('Quitter', QMessageBox.RejectRole)
    b.setEscapeButton(quitter)
    b.exec()
    return choix.get(b.clickedButton(), 'quitter')


def choisir_reessayer(parent, titre, texte, abandon):
    """Fenêtre « Réessayer » / `abandon` (« Quitter », « Fermer quand même ») -> True = réessayer."""
    b = QMessageBox(QMessageBox.Warning, titre, texte, parent=parent)
    reessayer = b.addButton('Réessayer', QMessageBox.AcceptRole)
    b.setEscapeButton(b.addButton(abandon, QMessageBox.RejectRole))
    b.exec()
    return b.clickedButton() is reessayer


def avertir_ouvert_ailleurs(parent, ailleurs, abandon):
    """Avertissement « Base ouverte sur un autre PC » -> True = continuer, False = `abandon` (Quitter, Annuler)."""
    poste = ailleurs['poste']
    depuis = L.heure_locale(ailleurs['depuis'], '%d.%m.%Y %H:%M') if ailleurs['depuis'] else '?'
    b = QMessageBox(QMessageBox.Warning, 'Base ouverte sur un autre PC',
                    f'D\'après le fichier, la base est ouverte sur {poste} depuis le {depuis}.\n\n'
                    'Vous pouvez l\'utiliser sur les deux PC : chaque PC reprend automatiquement ce que l\'autre '
                    'enregistre. Seules deux modifications faites presque en même temps vous demanderont un choix.\n\n'
                    f'Si {poste} est éteint, ou si ELPRO Logs s\'y est mal fermé, ce message n\'a pas d\'importance.',
                    parent=parent)
    continuer = b.addButton('Continuer', QMessageBox.AcceptRole)
    b.setEscapeButton(b.addButton(abandon, QMessageBox.RejectRole))
    b.exec()
    return b.clickedButton() is continuer


def choisir_conflit(parent, exc):
    """Fenêtre « Base modifiée sur un autre PC » -> 'les_deux' | 'mienne' | 'autre'."""
    poste = L.nom_poste(exc.autre.get('publie_par'))
    b = QMessageBox(QMessageBox.Warning, 'Base modifiée sur un autre PC',
                    f'{exc}\n\nQue faire des modifications faites sur ce PC ?', parent=parent)
    b.setInformativeText('Les logs récupérés sur ce PC peuvent aussi être récupérés à nouveau depuis la centrale '
                         '(environ 7 jours).')
    deux = b.addButton('Garder les deux (recommandé)', QMessageBox.AcceptRole)
    choix = {deux: 'les_deux', b.addButton('Garder celle de ce PC', QMessageBox.ActionRole): 'mienne',
             b.addButton(f'Garder celle de {poste}', QMessageBox.ActionRole): 'autre'}
    b.setDefaultButton(deux)
    b.setEscapeButton(deux)
    b.exec()
    return choix.get(b.clickedButton(), 'les_deux')


def resoudre_conflit(parent, espace, exc):
    """Fenêtre de conflit, puis espace.resoudre(choix). Les Magasin doivent être fermés. Lève comme resoudre."""
    titre, poste = 'Base modifiée sur un autre PC', L.nom_poste(exc.autre.get('publie_par'))
    while True:
        choix = choisir_conflit(parent, exc)
        if choix != 'mienne' or QMessageBox.question(
                parent, titre, f'La version enregistrée par {poste} sera remplacée par celle de ce PC. Continuer ?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            break
    copie = espace.resoudre(choix)
    if copie:
        QMessageBox.information(parent, titre, f'Les modifications de ce PC ont été enregistrées à part :\n{copie}\n\n'
                                f'La base affichée est celle de {poste}. Pour reprendre une donnée de la copie, '
                                'ouvrez-la avec Fichier › Emplacement des données › Ouvrir une base existante.')
    return choix


def ouvrir_base_demarrage():
    """Ouvre la base au démarrage (emplacement mémorisé, sinon par défaut) -> (espace, magasin), ou None si
    l'utilisateur quitte. Le fichier choisi n'est jamais ouvert par SQLite : copie de travail locale (L.Espace).
    Ne crée JAMAIS de base vide à un emplacement choisi qui a disparu (clé USB retirée, lecteur réseau absent…)."""
    while True:
        chemin = QSettings().value(CLE_BASE) or None
        c = chemin or L.chemin_base_defaut()
        e = L.Espace(c)
        try:
            info = e.ouvrir(creer=not chemin)
        except FileNotFoundError:
            message, reessayer = (f'La base de données est introuvable :\n{c}\n\nLe dossier est peut-être sur un '
                                  'disque ou un lecteur réseau non connecté.'), True
        except L.ConflitPublication as x:       # session précédente non publiée, et l'autre PC a publié depuis
            try:
                resoudre_conflit(None, e, x)
            except L.PublicationImpossible:
                pass                            # la boucle repasse par la reprise, puis « Réessayer / Quitter »
            continue
        except L.PublicationImpossible as x:
            if choisir_reessayer(None, 'ELPRO Logs', 'Les modifications de la dernière session sur ce PC n\'ont pas '
                                 f'encore pu être enregistrées dans le fichier partagé :\n{x}\n\n'
                                 'Elles sont gardées sur ce PC.', 'Quitter'):
                continue
            return None                         # copie locale gardée, rien de publié
        except RuntimeError as x:               # pas une base ELPRO Logs, version plus récente…
            message, reessayer = f'Impossible d\'ouvrir la base de données :\n{c}\n\n{x}', False
        except Exception as x:                  # fichier verrouillé, souci passager
            message, reessayer = f'Impossible d\'ouvrir la base de données :\n{c}\n\n{x}', True
        else:
            if info['ouvert_ailleurs'] and not avertir_ouvert_ailleurs(None, info['ouvert_ailleurs'], 'Quitter'):
                e.liberer_local()
                return None
            try:
                e.annoncer()
            except (L.PublicationImpossible, L.ConflitPublication):
                pass                            # repris par la surveillance (indicateur orange)
            e.repris = info['repris']
            return e, L.Magasin(e.travail, creer=False)
        choix = choisir_base(message, reessayer)
        if choix == 'reessayer':
            continue
        if choix == 'ouvrir':
            f, _ = QFileDialog.getOpenFileName(None, 'Ouvrir une base existante', os.path.dirname(c), FILTRE_BASE)
            if f:
                v = L.verifier_partage(f)
                if v['ok']:
                    memoriser_base(f)
                else:
                    QMessageBox.warning(None, 'Ouvrir une base existante', v['message'])
            continue
        if choix == 'defaut':
            if QMessageBox.question(None, 'Utiliser l\'emplacement par défaut',
                                    f'Ouvrir ou créer la base à l\'emplacement par défaut ?\n{L.chemin_base_defaut()}'
                                    '\n\nVos systèmes et données enregistrés à l\'ancien emplacement n\'y seront pas.'
                                    ) == QMessageBox.Yes:
                QSettings().remove(CLE_BASE)
            continue
        return None


class MainWindow(QMainWindow):
    def __init__(self, base, espace, magasin):
        super().__init__()
        self.base = base
        self.espace = espace                # v1.5 : fichier partagé et copie de travail (magasin ouvert sur la copie)
        self.magasin = magasin
        self.occupe = False                 # import ou récupération en cours
        self.ferme = False
        self.copies_signalees = set()       # copies en conflit du synchroniseur déjà signalées dans cette session
        self.setWindowTitle('ELPRO Logs')
        self.resize(1400, 900)
        self.setAcceptDrops(True)

        # --- page d'accueil (aucun système) et onglets
        self.pile = QStackedWidget()
        accueil = QWidget()
        v = QVBoxLayout(accueil)
        v.addStretch(1)
        self.bouton_accueil = QPushButton('Ajouter un système (.elpro.json)…')
        f = self.bouton_accueil.font()
        f.setPointSize(f.pointSize() + 4)
        self.bouton_accueil.setFont(f)
        self.bouton_accueil.setMinimumSize(420, 64)
        self.bouton_accueil.clicked.connect(lambda: self.ajouter_systeme())
        v.addWidget(self.bouton_accueil, 0, Qt.AlignHCenter)
        phrase = QLabel('Ajoutez d\'abord un système avec le fichier .elpro.json créé par ELPRO Config, '
                        'puis importez les fichiers .log de sa centrale.')
        phrase.setWordWrap(True)
        phrase.setAlignment(Qt.AlignCenter)
        phrase.setStyleSheet('color: gray;')
        phrase.setMaximumWidth(520)
        v.addWidget(phrase, 0, Qt.AlignHCenter)
        v.addStretch(2)
        self.pile.addWidget(accueil)
        self.onglets = QTabWidget()
        self.onglets.setTabsClosable(False)
        self.onglets.setDocumentMode(True)
        self.onglets.currentChanged.connect(self._onglet_change)
        self.pile.addWidget(self.onglets)
        self.setCentralWidget(self.pile)

        self._menus()

        # --- barre d'état : enregistrement et taille de la base à gauche, copyright à droite
        self.enregistre = QLabel()
        self.statusBar().addWidget(self.enregistre)
        self.taille = QLabel()
        self.statusBar().addWidget(self.taille)
        court = APP_COPYRIGHT.split(APP_COMPANY)[0] + APP_COMPANY          # « © 2026 Geoazimut SàRL »
        self.mention = QLabel(f'{court} — <a href="{APP_WEBSITE}" style="color:gray;">'
                              f'{site_affiche(APP_WEBSITE)}</a>')
        self.mention.setTextFormat(Qt.RichText)
        self.mention.setOpenExternalLinks(True)
        self.mention.setStyleSheet('color: gray;')
        f = self.mention.font()
        f.setPointSize(8)
        self.mention.setFont(f)
        self.statusBar().addPermanentWidget(self.mention)

        # --- un onglet par système, dans l'ordre de la base ; dernier onglet actif resélectionné
        dernier = QSettings().value('dernier_systeme')
        for s in self.magasin.systemes():
            self._ajouter_onglet(s)
        for k in range(self.onglets.count()):
            if str(self.onglets.widget(k).sid) == str(dernier):
                self.onglets.setCurrentIndex(k)
        self._maj_etat()
        self._indicateur()
        self.minuteur = QTimer(self)
        self.minuteur.timeout.connect(self._surveiller)
        self.minuteur.start(SURVEILLANCE_MS)
        QTimer.singleShot(0, self._apres_ouverture)

    def _apres_ouverture(self):
        if getattr(self.espace, 'repris', False):
            self.statusBar().showMessage('Modifications de la dernière session enregistrées dans le fichier partagé.',
                                         10000)
        self._surveiller()

    # ================================================================ menus
    def _menus(self):
        def action(menu, texte, fonction, raccourci=None):
            a = QAction(texte, self)
            if raccourci:
                a.setShortcut(raccourci)
            a.triggered.connect(lambda _=False: fonction())
            menu.addAction(a)
            return a

        mf = self.menuBar().addMenu('&Fichier')
        action(mf, 'Ajouter un système (.elpro.json)…', self.ajouter_systeme)
        self.action_importer = action(mf, 'Importer des logs…', self.importer_logs, QKeySequence('Ctrl+I'))
        self.action_exporter = action(mf, 'Exporter en CSV…', self.exporter_csv)
        self.action_tout_recuperer = action(mf, 'Tout récupérer', self.tout_recuperer, QKeySequence('Ctrl+Shift+R'))
        self.action_tout_recuperer.setToolTip('Récupérer les logs de toutes les centrales configurées (Ctrl+Maj+R)')
        mf.addSeparator()
        action(mf, 'Emplacement des données…', self.emplacement_donnees)
        mf.addSeparator()
        action(mf, 'Quitter', self.close, QKeySequence.Quit)

        ms = self.menuBar().addMenu('&Système')
        self.actions_systeme = [
            action(ms, 'Récupérer les logs', lambda: self.recuperer_logs(), QKeySequence('Ctrl+R')),
        ]
        self.action_relire = action(ms, 'Relire tous les logs de la centrale…', self.relire_logs)
        self.actions_systeme += [
            action(ms, 'Connexion à la centrale…', lambda: self.connexion_centrale()),
            action(ms, 'Mettre à jour la configuration (.elpro.json)…', self.mettre_a_jour_config),
            action(ms, 'Liste de log de la centrale (XML)…', self.liste_log_xml),
            action(ms, 'Revenir à la liste standard', self.liste_standard),
        ]
        ms.addSeparator()
        self.actions_systeme += [action(ms, 'Renommer…', self.renommer),
                                 action(ms, 'Supprimer ce système…', self.supprimer)]

        ma = self.menuBar().addMenu('&Aide')
        action(ma, 'Liste de log à configurer sur la centrale', lambda: AideListeLog(self).exec())
        action(ma, 'À propos', self.a_propos)
        # entrée cliquable de la barre de menus, entre Système et Aide (même action que dans Fichier)
        self.menuBar().insertAction(ma.menuAction(), self.action_tout_recuperer)

    def a_propos(self):
        AboutDialog(self, self.base).exec()

    # ================================================================ onglets
    def _ajouter_onglet(self, s):
        tab = SystemTab(self, s)
        tab.export_change.connect(self._maj_export)
        self.onglets.addTab(tab, s['nom'])
        return tab

    def onglet_actif(self):
        return self.onglets.currentWidget() if self.onglets.count() else None

    def onglet_de(self, sid):
        for k in range(self.onglets.count()):
            if self.onglets.widget(k).sid == sid:
                return self.onglets.widget(k)
        return None

    def _onglet_change(self, _i):
        tab = self.onglet_actif()
        if tab is not None:
            QSettings().setValue('dernier_systeme', tab.sid)
        self._maj_etat()

    def _maj_etat(self):
        a = self.onglets.count() > 0
        self.pile.setCurrentIndex(1 if a else 0)
        self.action_importer.setEnabled(a)
        for x in self.actions_systeme:
            x.setEnabled(a)
        tab = self.onglet_actif()
        self.action_relire.setEnabled(not self.occupe and tab is not None
                                      and bool((self.magasin.acces(tab.sid) or {}).get('adresse')))
        self.action_tout_recuperer.setEnabled(not self.occupe and any((self.magasin.acces(s['id']) or {}).get('adresse')
                                                                      for s in self.magasin.systemes()))
        self._maj_export()
        self._maj_taille()

    def _maj_export(self):
        tab = self.onglet_actif()
        self.action_exporter.setEnabled(bool(tab and tab.export_possible()))

    def _maj_taille(self):
        try:
            mo = self.magasin.taille_fichier() / 1e6
        except OSError:
            mo = 0
        self.taille.setText(f'Base : {mo:.1f} Mo'.replace('.', ','))
        self.taille.setToolTip(self.chemin_partage)

    @property
    def chemin_base(self):
        """Copie de travail de la base : tous les threads ouvrent leur propre instance sur ce chemin."""
        return self.magasin.chemin

    @property
    def chemin_partage(self):
        """Fichier choisi par l'utilisateur (peut être dans OneDrive, kDrive…) : l'emplacement affiché."""
        return self.espace.partage

    def reouvrir_base(self):
        """Après un import fait par un autre thread : nouvelle connexion (caches de lecture à jour)."""
        self.magasin.fermer()
        self.magasin = L.Magasin(self.chemin_base, creer=False)

    def _sid_actif(self):
        tab = self.onglet_actif()
        return tab.sid if tab is not None else None

    def _recharger_onglets(self, actif):
        """Recrée un onglet par système de la base (après un changement ou un rechargement de la base)."""
        while self.onglets.count():
            tab = self.onglets.widget(0)
            self.onglets.removeTab(0)
            tab.deleteLater()
        for s in self.magasin.systemes():
            tab = self._ajouter_onglet(s)
            if s['id'] == actif:
                self.onglets.setCurrentWidget(tab)
        self._maj_etat()

    # ================================================================ fichier partagé (v1.5)
    def _indicateur(self, erreur=None, infobulle=None):
        """« Enregistré à hh:mm » (gris), ou orange si le fichier partagé n'a pas pu être réécrit."""
        if erreur is None:
            t = self.espace.derniere_publication
            self.enregistre.setText(f"Enregistré à {L.heure_locale(t, '%H:%M')}" if t else '')
            self.enregistre.setStyleSheet('color: gray;')
            self.enregistre.setToolTip(self.chemin_partage)
        else:
            self.enregistre.setText('Pas encore enregistré dans le fichier partagé')
            self.enregistre.setStyleSheet('color: #EF6C00;')
            self.enregistre.setToolTip(infobulle or f'{self.chemin_partage}\n{erreur}')

    def publier(self):
        """Enregistre la copie de travail dans le fichier partagé (après chaque modification)."""
        try:
            self.espace.publier()
        except L.ConflitPublication as e:
            self.conflit(e)
        except L.PublicationImpossible as e:
            self._indicateur(str(e))
        else:
            self._indicateur()

    def synchroniser(self):
        """Au début de chaque action qui modifie la base : reprend d'abord ce qu'un autre PC a enregistré.
        False = ne rien faire (import ou récupération en cours)."""
        if self.occupe:
            return False
        if self.espace.verifier() == 'modifie':
            if self.espace.en_attente:
                self.publier()                      # mène à la fenêtre de conflit
            else:
                self.recharger_depuis_partage()
        return True

    def _onglet_synchronise(self, tab):
        """synchroniser(), puis l'onglet du même système (recréé si la base a été rechargée). None = rien à faire."""
        sid = tab.sid if tab is not None else None
        if not self.synchroniser():
            return None
        return self.onglet_de(sid) if sid is not None else self.onglet_actif()

    def recharger_depuis_partage(self):
        """Un autre PC a enregistré la base et rien n'est en attente ici : on reprend sa version."""
        attendre_tous()
        actif = self._sid_actif()
        self.magasin.fermer()
        try:
            meta = self.espace.recharger()
        except Exception as e:                      # fichier en cours d'écriture par le synchroniseur…
            meta = None
            self.statusBar().showMessage(f'Mise à jour de la base impossible pour l\'instant : {e}', 10000)
        finally:
            self.magasin = L.Magasin(self.chemin_base, creer=False)
            self._recharger_onglets(actif)
        if meta:
            quand = L.heure_locale(int(meta['publie_le']), '%H:%M') if meta.get('publie_le') else '?'
            self.statusBar().showMessage(f"Base mise à jour : modifications de {L.nom_poste(meta['publie_par'])} "
                                         f'({quand}).', 10000)

    def conflit(self, exc):
        """Un autre PC a enregistré pendant que ce PC avait des modifications : choix, puis base rechargée."""
        attendre_tous()
        actif = self._sid_actif()
        self.magasin.fermer()
        try:
            resoudre_conflit(self, self.espace, exc)
            self._indicateur()
        except L.PublicationImpossible as e:
            self._indicateur(str(e))
        except Exception as e:
            QMessageBox.critical(self, 'Base modifiée sur un autre PC', str(e))
        finally:
            self.magasin = L.Magasin(self.chemin_base, creer=False)
            self._recharger_onglets(actif)

    def _surveiller(self):
        """Toutes les 30 s et à l'activation de la fenêtre : publie ce qui attend, reprend les modifications
        des autres PC, signale les copies en conflit créées par le synchroniseur."""
        if self.occupe or self.ferme or QApplication.activeModalWidget() is not None:
            return
        if self.espace.en_attente:
            self.publier()
        else:
            st = self.espace.verifier()
            if st == 'modifie':
                self.recharger_depuis_partage()
            elif st == 'absent':
                self._indicateur('', f'Fichier partagé introuvable : {self.chemin_partage}. '
                                     'Les modifications restent sur ce PC.')
            else:
                self._indicateur()
        for c in self.espace.copies_en_conflit():
            if c in self.copies_signalees:
                continue
            self.copies_signalees.add(c)
            b = QMessageBox(QMessageBox.Warning, 'Copie en conflit',
                            'Le synchroniseur (OneDrive, kDrive…) a créé une copie en conflit de la base :\n'
                            f'{os.path.basename(c)}\n\nElle contient probablement des modifications faites sur deux '
                            'PC pendant que la synchronisation était impossible. Vérifiez-la (Fichier › Emplacement '
                            'des données › Ouvrir une base existante), puis supprimez-la.', QMessageBox.Ok, self)
            dossier = b.addButton('Ouvrir le dossier', QMessageBox.ActionRole)
            b.exec()
            if b.clickedButton() is dossier:
                QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.chemin_partage)))

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == QEvent.ActivationChange and self.isActiveWindow():
            self._surveiller()

    def _occuper(self, occupe):
        self.occupe = occupe
        self._maj_etat()

    # ================================================================ dossiers mémorisés
    @staticmethod
    def _documents():
        return QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)

    def _dossier(self, cle):
        d = QSettings().value(cle, '')
        return d if d and os.path.isdir(d) else self._documents()

    # ================================================================ systèmes
    def ajouter_systeme(self, chemin=None):
        if not self.synchroniser():
            return
        if chemin is None:
            chemin, _ = QFileDialog.getOpenFileName(self, 'Ajouter un système', self._dossier('dossier_config'),
                                                    FILTRE_PROJET)
            if not chemin:
                return
        QSettings().setValue('dossier_config', os.path.dirname(chemin))
        try:
            projet = lire_projet(chemin)
            cle = cle_systeme(projet)
        except Exception as e:
            QMessageBox.critical(self, 'Ajouter un système', f'Impossible de lire {os.path.basename(chemin)} :\n{e}')
            return
        existant = next((s for s in self.magasin.systemes() if s['cle'] == cle), None)
        if existant is not None:
            tab = self.onglet_de(existant['id'])
            self.onglets.setCurrentWidget(tab)
            if projet_normalise(projet) == self.magasin.projet(existant['id']):
                QMessageBox.information(self, 'Ajouter un système', 'Ce système est déjà dans l\'application.')
                return
            self._mise_a_jour(tab, projet)          # nouvelle version de la config d'un système existant
            return
        try:
            r = self.magasin.ajouter_config(projet)
        except Exception as e:
            QMessageBox.warning(self, 'Ajouter un système', str(e))
            return
        if r['statut'] == 'nouveau':
            s = next(s for s in self.magasin.systemes() if s['id'] == r['systeme_id'])
            tab = self._ajouter_onglet(s)
            self.onglets.setCurrentWidget(tab)
            self._maj_etat()
            self.publier()
            self.statusBar().showMessage(f"Système « {s['nom']} » ajouté. Importez maintenant ses logs.", 8000)
        else:
            tab = self.onglet_de(r['systeme_id'])
            self.onglets.setCurrentWidget(tab)
            if r['statut'] == 'identique':
                QMessageBox.information(self, 'Ajouter un système', 'Ce système est déjà dans l\'application.')
            else:
                tab.vider_cache()
                tab.rafraichir()
                self.publier()

    def mettre_a_jour_config(self, chemin=None):
        if not self.synchroniser():
            return
        tab = self.onglet_actif()
        if tab is None:
            return
        if chemin is None:
            chemin, _ = QFileDialog.getOpenFileName(self, f'Mettre à jour la configuration — {tab.nom}',
                                                    self._dossier('dossier_config'), FILTRE_PROJET)
            if not chemin:
                return
        QSettings().setValue('dossier_config', os.path.dirname(chemin))
        try:
            projet = lire_projet(chemin)
            cle = cle_systeme(projet)
        except Exception as e:
            QMessageBox.critical(self, 'Mettre à jour la configuration',
                                 f'Impossible de lire {os.path.basename(chemin)} :\n{e}')
            return
        sy = next(s for s in self.magasin.systemes() if s['id'] == tab.sid)
        if cle != sy['cle']:
            QMessageBox.warning(self, 'Mettre à jour la configuration',
                                f'Ce fichier décrit un autre système ({cle}), pas « {sy["nom"]} » ({sy["cle"]}).')
            return
        self._mise_a_jour(tab, projet)

    def _mise_a_jour(self, tab, projet):
        titre = 'Mettre à jour la configuration'
        if projet_normalise(projet) == self.magasin.projet(tab.sid):
            QMessageBox.information(self, titre, 'Cette configuration est déjà celle du système.')
            return
        d = DateMiseEnService(self, M.version_config(projet))
        if not d.exec():
            return
        try:
            r = self.magasin.ajouter_config(projet, valable_depuis=d.valable_depuis())
        except Exception as e:
            QMessageBox.warning(self, titre, str(e))
            return
        tab.vider_cache()
        tab.rafraichir()
        self.onglets.setTabText(self.onglets.indexOf(tab), tab.nom)
        self.publier()
        if r['statut'] == 'version':
            self.statusBar().showMessage(f'Configuration V{M.version_config(projet)} enregistrée.', 8000)
        else:
            QMessageBox.information(self, titre, 'Cette configuration est déjà celle du système.')

    def liste_log_xml(self):
        if not self.synchroniser():
            return
        tab = self.onglet_actif()
        if tab is None:
            return
        chemin, _ = QFileDialog.getOpenFileName(self, 'Liste de log de la centrale (export XML de la radio)',
                                                self._dossier('dossier_config'), 'Export XML (*.xml);;Tous (*)')
        if not chemin:
            return
        try:
            profil = L.lire_profil_xml(chemin)
        except Exception as e:
            QMessageBox.warning(self, 'Liste de log', f'Impossible de lire la liste de log :\n{e}')
            return
        self.magasin.definir_profil(tab.sid, profil)
        tab.fichiers.a_jour = False
        tab._actualiser_visible()
        self.publier()
        QMessageBox.information(self, 'Liste de log',
                                f'Liste de log propre à cette centrale enregistrée ({len(profil)} entrées).\n'
                                'Elle s\'applique aux prochains imports.')

    def liste_standard(self):
        if not self.synchroniser():
            return
        tab = self.onglet_actif()
        if tab is None:
            return
        if self.magasin.profil(tab.sid) is None:
            QMessageBox.information(self, 'Liste de log', 'Ce système utilise déjà la liste standard.')
            return
        if QMessageBox.question(self, 'Liste de log', 'Revenir à la liste de log standard GeoAzimut ?\n'
                                'Elle s\'appliquera aux prochains imports.') != QMessageBox.Yes:
            return
        self.magasin.definir_profil(tab.sid, None)
        tab.fichiers.a_jour = False
        tab._actualiser_visible()
        self.publier()

    def renommer(self):
        if not self.synchroniser():
            return
        tab = self.onglet_actif()
        if tab is None:
            return
        nom, ok = QInputDialog.getText(self, 'Renommer', 'Nouveau nom du système :', text=tab.nom)
        nom = (nom or '').strip()
        if ok and nom:
            self.magasin.renommer(tab.sid, nom)
            tab.nom = nom
            self.onglets.setTabText(self.onglets.indexOf(tab), nom)
            self.publier()

    def supprimer(self):
        if not self.synchroniser():
            return
        tab = self.onglet_actif()
        if tab is None:
            return
        titre = 'Supprimer ce système'
        if QMessageBox.question(self, titre, f'Supprimer le système « {tab.nom} » ?\n\n'
                                'Toutes les valeurs importées de ce système seront effacées.',
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        if QMessageBox.question(self, titre, f'Confirmer la suppression définitive de « {tab.nom} » et de '
                                'toutes ses valeurs ? Cette opération est irréversible.',
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        attendre_tous()
        self.magasin.supprimer_systeme(tab.sid)
        try:
            self.magasin.compacter_base()
        except sqlite3.Error:
            pass                                  # base occupée : l'espace sera récupéré plus tard
        self.onglets.removeTab(self.onglets.indexOf(tab))
        tab.deleteLater()
        self._maj_etat()
        self.publier()

    # ================================================================ récupération depuis la centrale
    def connexion_centrale(self, tab=None):
        """Système › Connexion à la centrale. True si la connexion a été enregistrée."""
        tab = self._onglet_synchronise(tab or self.onglet_actif())
        if tab is None:
            return False
        ok = bool(ConnexionCentrale(self, self.magasin, tab.sid, tab.nom).exec())
        if ok:
            tab.maj_recuperation()
            self._maj_etat()
            self.publier()
        return ok

    def relire_logs(self, tab=None):
        """Système › Relire tous les logs de la centrale (v1.4.1) : complète les colonnes jamais lues."""
        tab = self._onglet_synchronise(tab or self.onglet_actif())
        if tab is None or not (self.magasin.acces(tab.sid) or {}).get('adresse'):
            return
        if QMessageBox.question(self, f'Relire tous les logs — {tab.nom}',
                                'Tous les fichiers encore présents sur la centrale (environ 7 jours) vont être '
                                'téléchargés à nouveau. Les données déjà importées ne changent pas ; seules les '
                                'colonnes qui n\'avaient pas été lues sont ajoutées. Continuer ?',
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.recuperer_logs(tab, relire=True)

    def recuperer_logs(self, tab=None, forcer=False, relire=False):
        tab = self._onglet_synchronise(tab or self.onglet_actif())
        if tab is None:
            return
        if not self.magasin.acces(tab.sid) and not self.connexion_centrale(tab):
            return
        self._occuper(True)
        try:
            d = ProgressionRecuperation(self, self.chemin_base, tab.sid, forcer, relire=relire)
            d.exec()
            d.thread.wait()
        finally:
            self._occuper(False)
        rap = d.rapport
        self.reouvrir_base()
        tab.rafraichir(apres_import=True)
        self._maj_taille()
        self.publier()                              # aussi pour « rien de nouveau » (date de récupération notée)
        self.afficher_recuperation(self.onglet_de(tab.sid) or tab, rap, relire)

    def afficher_recuperation(self, tab, rap, relire=False):
        """Affichage selon le statut du rapport (textes du moteur)."""
        titre = f'{"Relire tous les logs" if relire else "Récupérer les logs"} — {tab.nom}'
        st, msg = rap['statut'], rap['message']
        if st == 'ok':
            # relecture : le message du moteur, puis seulement les fichiers complétés, nouveaux ou en erreur
            imports = [r for r in rap['imports'] if not relire or r['statut'] != 'deja_importe']
            self.rapport = RapportImport(self, [(None, imports)], titre=titre, resume=msg,
                                         alerte=rap.get('alerte'))
            self.rapport.exec()
        elif st in ('rien_de_nouveau', 'annule'):
            QMessageBox.information(self, titre, msg)
        elif st in ('acces_refuse', 'non_configure'):
            b = QMessageBox(QMessageBox.Critical, titre, msg, QMessageBox.Close, self)
            connexion = b.addButton('Connexion à la centrale…', QMessageBox.ActionRole)
            b.exec()
            if b.clickedButton() is connexion:
                self.connexion_centrale(tab)
        elif st == 'mauvaise_centrale':
            rep = QMessageBox.question(self, titre, f'{msg}\n\nImporter quand même dans ce système ?',
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if rep == QMessageBox.Yes:
                self.recuperer_logs(tab, forcer=True, relire=relire)
        else:                                       # injoignable, introuvable, erreur
            QMessageBox.critical(self, titre, msg)

    def tout_recuperer(self):
        if not self.action_tout_recuperer.isEnabled() or not self.synchroniser():
            return
        self._occuper(True)
        try:
            d = ProgressionRecuperation(self, self.chemin_base)
            d.exec()
            d.thread.wait()
        finally:
            self._occuper(False)
        self.reouvrir_base()
        for k in range(self.onglets.count()):
            self.onglets.widget(k).rafraichir(apres_import=True)
        self._maj_taille()
        self.publier()
        self.rapport = RapportRecuperationTout(self, d.rapport or [])
        self.rapport.exec()

    # ================================================================ import des logs
    def importer_logs(self, chemins=None):
        if not self.synchroniser():
            return
        tab = self.onglet_actif()
        if tab is None:
            QMessageBox.information(self, 'Importer des logs', 'Ajoutez d\'abord un système (.elpro.json).')
            return
        if chemins is None:
            chemins, _ = QFileDialog.getOpenFileNames(self, f'Importer des logs — {tab.nom}',
                                                      self._dossier('dossier_logs'), FILTRE_LOGS)
            if not chemins:
                return
        QSettings().setValue('dossier_logs', os.path.dirname(chemins[0]))
        resultats, annule = self._importer(tab, [(c, False) for c in chemins])
        # logs d'une autre radio : rien n'est importé sans confirmation
        a_forcer = []
        for chemin, rs in resultats:
            for r in rs:
                if r.get('statut') == 'serie_differente' and chemin not in a_forcer:
                    rep = QMessageBox.question(self, 'Autre radio', f"{r['fichier']} : {r['message']}\n\n"
                                               'Importer quand même dans ce système ?',
                                               QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                    if rep == QMessageBox.Yes:
                        a_forcer.append(chemin)
        if a_forcer:
            res2, _a = self._importer(tab, [(c, True) for c in a_forcer])
            nouveaux = {(c, r.get('fichier')): r for c, rs in res2 for r in rs}
            resultats = [(c, [nouveaux.get((c, r.get('fichier')), r) if r.get('statut') == 'serie_differente'
                              else r for r in rs]) for c, rs in resultats]
        self.reouvrir_base()
        tab.rafraichir(apres_import=True)
        self._maj_taille()
        self.publier()                              # une seule publication, imports forcés compris
        self.rapport = RapportImport(self, resultats, annule)
        self.rapport.exec()

    def _importer(self, tab, fichiers):
        self._occuper(True)
        try:
            d = ProgressionImport(self, self.chemin_base, tab.sid, fichiers)
            d.exec()
            d.thread.wait()
        finally:
            self._occuper(False)
        return d.resultats, d.thread.annule and len(d.resultats) < len(fichiers)

    # ================================================================ export CSV
    def exporter_csv(self):
        tab = self.onglet_actif()
        if not tab or not tab.export_possible():
            return
        canaux = tab.detail.canaux_affiches()
        t0, t1 = tab.periode
        nom = f"{tab.nom}_{L.heure_locale(t0, '%Y%m%d_%H%M')}.csv".replace(' ', '_')
        chemin, _ = QFileDialog.getSaveFileName(self, 'Exporter en CSV',
                                                os.path.join(self._dossier('dossier_export'), nom),
                                                'Fichier CSV (*.csv)')
        if not chemin:
            return
        if not chemin.lower().endswith('.csv'):
            chemin += '.csv'
        QSettings().setValue('dossier_export', os.path.dirname(chemin))
        attente = QProgressDialog('Export en cours…', None, 0, 0, self)
        attente.setWindowTitle('Exporter en CSV')
        attente.setWindowModality(Qt.WindowModal)
        attente.setMinimumDuration(300)
        sid = tab.sid
        tache = Tache(self.chemin_base, lambda m: m.exporter_csv(sid, canaux, t0, t1, chemin))

        def fini(_r):
            attente.close()
            self.statusBar().showMessage(f'Export terminé : {chemin}', 8000)

        def echec(msg):
            attente.close()
            QMessageBox.critical(self, 'Exporter en CSV', f'Export impossible :\n{msg}')
        tache.termine.connect(fini)
        tache.echec.connect(echec)
        self.tache_export = tache
        tache.start()

    # ================================================================ emplacement des données (v1.3)
    def emplacement_donnees(self):
        EmplacementDonnees(self).exec()

    def est_par_defaut(self):
        return meme_fichier(self.chemin_partage, L.chemin_base_defaut())

    def _en_attente(self, texte, fonction):
        """fonction() dans un thread, avec une barre d'attente ; renvoie son résultat ou relève son exception."""
        res = {}
        t = Fonction(fonction)
        t.termine.connect(lambda r: res.update(ok=r))
        t.echec.connect(lambda e: res.update(erreur=e))
        attente = QProgressDialog(texte, None, 0, 0, self)
        attente.setWindowModality(Qt.WindowModal)
        attente.setMinimumDuration(300)
        boucle = QEventLoop()
        t.finished.connect(boucle.quit)
        t.start()
        boucle.exec()
        attente.close()
        if 'erreur' in res:
            raise res['erreur']
        return res.get('ok')

    def changer_base(self, chemin):
        """Ouvre la base `chemin` (elle doit exister) à la place de l'actuelle et recharge les onglets.
        True si ouverte, False si l'utilisateur annule. En cas d'échec, l'exception remonte et la base actuelle
        reste active."""
        self.publier()
        if self.espace.en_attente:
            raise RuntimeError(PAS_ENREGISTRE)
        attendre_tous()
        e = L.Espace(chemin)
        info = e.ouvrir()
        if info['ouvert_ailleurs'] and not avertir_ouvert_ailleurs(self, info['ouvert_ailleurs'], 'Annuler'):
            e.liberer_local()
            return False
        try:
            e.annoncer()
        except (L.PublicationImpossible, L.ConflitPublication):
            pass                                    # repris par la surveillance
        nouveau = L.Magasin(e.travail, creer=False)
        actif = self._sid_actif()
        self.magasin.fermer()
        try:
            self.espace.fermer()
        except (L.ConflitPublication, L.PublicationImpossible) as x:
            QMessageBox.warning(self, 'Emplacement des données',
                                f'L\'ancienne base n\'a pas pu être enregistrée :\n{x}\n\n'
                                'Sa copie locale est gardée sur ce PC ; elle sera enregistrée à sa prochaine ouverture.')
        self.espace, self.magasin = e, nouveau
        memoriser_base(chemin)
        self._recharger_onglets(actif)
        self._indicateur()
        return True

    def deplacer_base(self, dossier):
        """Copie la base dans `dossier`, l'ouvre à la place de l'actuelle, puis propose de supprimer l'ancienne."""
        titre = 'Déplacer la base'
        dest = os.path.join(dossier, L.NOM_BASE)
        avert = L.avertissement_emplacement(dest)
        if avert and QMessageBox.question(self, titre, f'{avert}\n\nContinuer quand même ?',
                                          QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return False
        if os.path.exists(dest):                  # jamais d'écrasement
            if QMessageBox.question(self, titre, f'Une base existe déjà dans ce dossier :\n{dest}\n\n'
                                    'L\'ouvrir à la place ?') == QMessageBox.Yes:
                return self.ouvrir_base_existante(dest)
            return False
        self.publier()
        if self.espace.en_attente:
            QMessageBox.warning(self, titre, PAS_ENREGISTRE)
            return False
        ancien, travail = self.chemin_partage, self.chemin_base
        attendre_tous()
        try:
            self._en_attente('Copie de la base…', lambda: L.copier_base(travail, dest))
            if not self.changer_base(dest):
                return False
        except Exception as e:
            QMessageBox.critical(self, titre, f'La base n\'a pas été déplacée (l\'ancienne reste utilisée) :\n{e}')
            return False
        if QMessageBox.question(self, titre, f'La base a été déplacée.\n\nSupprimer l\'ancien fichier {ancien} ?',
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            try:
                for suf in ('', '-wal', '-shm'):
                    if os.path.exists(ancien + suf):
                        os.remove(ancien + suf)
            except OSError as e:
                QMessageBox.warning(self, titre, f'Impossible de supprimer l\'ancien fichier :\n{e}')
        self._maj_taille()
        return True

    def ouvrir_base_existante(self, chemin):
        titre = 'Ouvrir une base existante'
        if meme_fichier(chemin, self.chemin_partage):
            QMessageBox.information(self, titre, 'Cette base est déjà ouverte.')
            return False
        v = L.verifier_partage(chemin)
        if not v['ok']:
            QMessageBox.warning(self, titre, v['message'])
            return False
        if QMessageBox.question(self, titre, f"Ouvrir cette base ({pluriel(v['nb_systemes'], 'système')}) ?\n\n"
                                'Les systèmes de la base actuelle ne seront plus affichés (ils restent dans son fichier).'
                                ) != QMessageBox.Yes:
            return False
        try:
            if not self.changer_base(chemin):
                return False
        except Exception as e:
            QMessageBox.critical(self, titre, f'Impossible d\'ouvrir cette base :\n{e}')
            return False
        self._maj_taille()
        return True

    def sauvegarder_base(self, chemin):
        titre = 'Copie de sauvegarde'
        try:
            taille = self._en_attente('Copie de sauvegarde…', lambda: L.copier_base(self.chemin_base, chemin))
        except FileExistsError:
            QMessageBox.warning(self, titre, f'Ce fichier existe déjà, il n\'a pas été remplacé :\n{chemin}')
            return False
        except Exception as e:
            QMessageBox.critical(self, titre, f'La copie a échoué :\n{e}')
            return False
        QMessageBox.information(self, titre, f'Copie enregistrée ({nombre(round(taille / 1e6, 1))} Mo).')
        return True

    def revenir_defaut(self):
        """Ouvre la base de l'emplacement par défaut si elle existe, sinon propose d'y déplacer la base actuelle."""
        defaut = L.chemin_base_defaut()
        if os.path.isfile(defaut):
            return self.ouvrir_base_existante(defaut)
        if QMessageBox.question(self, 'Revenir à l\'emplacement par défaut',
                                f'Il n\'y a pas de base à l\'emplacement par défaut :\n{defaut}\n\n'
                                'Y déplacer la base actuelle ?') == QMessageBox.Yes:
            return self.deplacer_base(os.path.dirname(defaut))
        return False

    # ================================================================ glisser-déposer
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        chemins = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        self.deposer(chemins)
        e.acceptProposedAction()

    def deposer(self, chemins):
        """.elpro.json : ajoute un système ; .log/.zip/.csv : import dans le système de l'onglet actif."""
        for c in chemins:
            if c.lower().endswith('.json'):
                self.ajouter_systeme(c)
        logs = [c for c in chemins if c.lower().endswith(EXT_LOGS)]
        if logs:
            self.importer_logs(logs)

    # ================================================================ fermeture
    def closeEvent(self, e):
        tab = self.onglet_actif()
        if tab is not None:
            QSettings().setValue('dernier_systeme', tab.sid)
        self.ferme = True
        self.minuteur.stop()
        attendre_tous()
        self.magasin.fermer()
        while True:                                 # tout publier, puis effacer la copie locale
            try:
                self.espace.fermer()
                break
            except L.ConflitPublication as x:
                try:
                    resoudre_conflit(self, self.espace, x)
                except L.PublicationImpossible:
                    pass                            # le tour suivant propose Réessayer / Fermer quand même
                except Exception as y:
                    QMessageBox.critical(self, 'Fermeture', str(y))
                    break
            except L.PublicationImpossible as x:
                if not choisir_reessayer(self, 'Fermeture', 'Les dernières modifications n\'ont pas pu être '
                                         f'enregistrées dans le fichier partagé :\n{x}\n\nElles restent sur ce PC '
                                         'et seront enregistrées au prochain démarrage d\'ELPRO Logs sur ce PC.',
                                         'Fermer quand même'):
                    break
        e.accept()
