# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""Threads de travail : import des logs et calculs longs.
Chaque thread ouvre SA PROPRE instance L.Magasin (une connexion SQLite ne se partage pas entre threads)
et la ferme à la fin."""
import os
import traceback

from PySide6.QtCore import QThread, Signal

import elpro_logs as L

# Threads en cours : une référence est gardée jusqu'à la fin (sinon Qt détruirait un thread actif)
_ACTIFS = set()


def _garder(thread):
    _ACTIFS.add(thread)
    thread.finished.connect(lambda t=thread: _ACTIFS.discard(t))


def attendre_tous(ms=30000):
    """À la fermeture de l'application : laisse finir les threads en cours."""
    for t in list(_ACTIFS):
        t.wait(ms)


class Tache(QThread):
    """Exécute fonction(magasin) hors du thread de l'interface. Résultat par le signal `termine`."""
    termine = Signal(object)
    echec = Signal(str)

    def __init__(self, chemin_base, fonction, parent=None):
        super().__init__(parent)
        self.chemin_base = chemin_base
        self.fonction = fonction
        _garder(self)

    def run(self):
        m = None
        try:
            m = L.Magasin(self.chemin_base, creer=False)
            res = self.fonction(m)
        except Exception as e:          # erreur remontée à l'interface, jamais de plantage silencieux
            traceback.print_exc()
            self.echec.emit(str(e) or e.__class__.__name__)
        else:
            self.termine.emit(res)
        finally:
            if m is not None:
                m.fermer()


class ImportLogs(QThread):
    """Import d'une liste de fichiers dans un système. `fichiers` : [(chemin, forcer_serie)].
    Annuler : l'import s'arrête après le fichier en cours."""
    fichier_commence = Signal(int, str)          # index, nom du fichier
    avancement = Signal(int, int)                # lignes traitées, total du fichier en cours
    fichier_termine = Signal(int, str, object)   # index, chemin, [rapports]

    def __init__(self, chemin_base, sid, fichiers, parent=None):
        super().__init__(parent)
        self.chemin_base = chemin_base
        self.sid = sid
        self.fichiers = list(fichiers)
        self.annule = False
        self.resultats = []                      # [(chemin, rapports)] dans l'ordre
        _garder(self)

    def annuler(self):
        self.annule = True

    def run(self):
        m = None
        try:
            m = L.Magasin(self.chemin_base, creer=False)
        except Exception as e:
            for i, (chemin, _f) in enumerate(self.fichiers):
                r = [{'fichier': os.path.basename(chemin), 'statut': 'erreur', 'message': str(e)}]
                self.resultats.append((chemin, r))
                self.fichier_termine.emit(i, chemin, r)
            return
        try:
            with m.lot():                   # un seul lot : chaque bloc réécrit une fois ; annuler garde ce qui est importé
                for i, (chemin, forcer) in enumerate(self.fichiers):
                    if self.annule:
                        break
                    self.fichier_commence.emit(i, os.path.basename(chemin))
                    try:
                        r = m.importer_fichier(self.sid, chemin, forcer_serie=forcer,
                                               progression=lambda n, total: self.avancement.emit(n, total))
                    except Exception as e:  # fichier illisible… : rapport d'erreur, on continue
                        traceback.print_exc()
                        r = [{'fichier': os.path.basename(chemin), 'statut': 'erreur', 'message': str(e)}]
                    self.resultats.append((chemin, r))
                    self.fichier_termine.emit(i, chemin, r)
        except Exception as e:              # écriture du lot impossible (disque plein…) : le lot entier est annulé
            traceback.print_exc()
            self.resultats = [(c, [{'fichier': os.path.basename(c), 'statut': 'erreur',
                                    'message': f'Import annulé, aucun fichier gardé : {e}'}]) for c, _r in self.resultats]
        finally:
            m.fermer()


class Fonction(QThread):
    """Exécute fonction() hors du thread de l'interface, sans base (ex. test de connexion à la centrale)."""
    termine = Signal(object)
    echec = Signal(object)                       # l'exception levée

    def __init__(self, fonction, parent=None):
        super().__init__(parent)
        self.fonction = fonction
        _garder(self)

    def run(self):
        try:
            res = self.fonction()
        except Exception as e:
            self.echec.emit(e)
        else:
            self.termine.emit(res)


class RecupererLogs(QThread):
    """Récupération des logs depuis la centrale (elpro_remote), avec sa propre instance L.Magasin.
    sid = None : tous les systèmes configurés (recuperer_tout). Annuler : arrêt après le fichier en cours."""
    avancement = Signal(str, int, int, str)      # système, n, total, nom du fichier
    resultat = Signal(object)                    # rapport (un système) ou [(systeme, rapport)] (tous)

    def __init__(self, chemin_base, sid=None, forcer=False, parent=None):
        super().__init__(parent)
        self.chemin_base, self.sid, self.forcer = chemin_base, sid, forcer
        self.annule = False
        self.rapport = None
        _garder(self)

    def annuler(self):
        self.annule = True

    def run(self):
        import elpro_remote as R
        m = None
        try:
            m = L.Magasin(self.chemin_base, creer=False)
            if self.sid is None:
                self.rapport = R.recuperer_tout(
                    m, progression=lambda s, n, t, nom: self.avancement.emit(s, n, t, nom),
                    annuler=lambda: self.annule)
            else:
                self.rapport = R.recuperer(
                    m, self.sid, forcer=self.forcer,
                    progression=lambda n, t, nom: self.avancement.emit('', n, t, nom),
                    annuler=lambda: self.annule)
        except Exception as e:           # erreur inattendue : rapportée comme les erreurs de la centrale
            traceback.print_exc()
            rap = {'statut': 'erreur', 'message': str(e) or e.__class__.__name__, 'centrale': None,
                   'disponibles': 0, 'nouveaux': 0, 'imports': [], 'plus_ancien': None, 'alerte': None}
            self.rapport = rap if self.sid is not None else []
        finally:
            if m is not None:
                m.fermer()
        self.resultat.emit(self.rapport)
