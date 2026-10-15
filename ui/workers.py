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
            m = L.Magasin(self.chemin_base)
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
            m = L.Magasin(self.chemin_base)
        except Exception as e:
            for i, (chemin, _f) in enumerate(self.fichiers):
                r = [{'fichier': os.path.basename(chemin), 'statut': 'erreur', 'message': str(e)}]
                self.resultats.append((chemin, r))
                self.fichier_termine.emit(i, chemin, r)
            return
        try:
            for i, (chemin, forcer) in enumerate(self.fichiers):
                if self.annule:
                    break
                self.fichier_commence.emit(i, os.path.basename(chemin))
                try:
                    r = m.importer_fichier(self.sid, chemin, forcer_serie=forcer,
                                           progression=lambda n, total: self.avancement.emit(n, total))
                except Exception as e:      # fichier illisible, disque plein… : rapport d'erreur, on continue
                    traceback.print_exc()
                    r = [{'fichier': os.path.basename(chemin), 'statut': 'erreur', 'message': str(e)}]
                self.resultats.append((chemin, r))
                self.fichier_termine.emit(i, chemin, r)
        finally:
            m.fermer()
