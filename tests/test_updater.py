# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""Tests de engine/updater.py (fichier identique dans elpro-logs et elpro-config).
Aucun accès réseau : un faux GitHub répond aux URL attendues."""
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'engine'))
import updater as U  # noqa: E402

DEPOT = 'exemple/elpro-demo'
PREFIXE = 'ELPRO_Demo_Setup_'
API = U.API.format(depot=DEPOT)
URL_EXE = 'https://github.com/exemple/elpro-demo/releases/download/v1.6.0/ELPRO_Demo_Setup_1.6.0.exe'
URL_SUMS = 'https://github.com/exemple/elpro-demo/releases/download/v1.6.0/SHA256SUMS.txt'
CONTENU = b'MZ' + b'installateur fictif ' * 20000           # ~400 ko : plusieurs blocs de lecture
SHA = hashlib.sha256(CONTENU).hexdigest()


def release(tag='v1.6.0', assets=None, **autres):
    if assets is None:
        assets = [{'name': 'ELPRO_Demo_Setup.exe', 'browser_download_url': URL_EXE.replace('_1.6.0', ''), 'size': 1},
                  {'name': 'ELPRO_Demo_Setup_1.6.0.exe', 'browser_download_url': URL_EXE, 'size': len(CONTENU)},
                  {'name': 'SHA256SUMS.txt', 'browser_download_url': URL_SUMS, 'size': 200}]
    r = {'tag_name': tag, 'draft': False, 'prerelease': False, 'body': '### Nouveautés\n- mise à jour automatique',
         'html_url': 'https://github.com/exemple/elpro-demo/releases/tag/' + tag,
         'published_at': '2026-11-10T08:00:00Z', 'assets': assets}
    r.update(autres)
    return json.dumps(r).encode('utf-8')


class Reponse(io.BytesIO):
    def __init__(self, data, url, coupure_apres=None):
        super().__init__(data)
        self.url, self.coupure_apres = url, coupure_apres

    def geturl(self):
        return self.url

    def read(self, n=-1):
        if self.coupure_apres is not None and self.tell() >= self.coupure_apres:
            raise ConnectionResetError('coupure')
        return super().read(n)


class FauxGithub:
    """ouvrir(url, user_agent) : renvoie la réponse prévue pour `url`, ou lève l'exception prévue."""
    def __init__(self, routes):
        self.routes, self.appels = routes, []

    def __call__(self, url, user_agent):
        self.appels.append((url, user_agent))
        r = self.routes[url]
        if isinstance(r, Exception):
            raise r
        if isinstance(r, tuple):                    # (données, url finale après redirection[, coupure])
            return Reponse(r[0], r[1], *(r[2:]))
        return Reponse(r, url)


def routes_ok(sums=None):
    sums = sums if sums is not None else (f'{"0" * 64}  ELPRO_Demo_Setup.exe\n{SHA}  ELPRO_Demo_Setup_1.6.0.exe\n').encode()
    return {API: release(), URL_SUMS: sums,
            URL_EXE: (CONTENU, 'https://objects.githubusercontent.com/github-production-release-asset/123')}


class TestVersions(unittest.TestCase):
    def test_version_tuple(self):
        self.assertEqual(U.version_tuple('v1.5.0'), (1, 5, 0))
        self.assertEqual(U.version_tuple('1.10.2'), (1, 10, 2))
        for faux in ('', None, '1.5', 'v1.5.0-beta', 'latest'):
            with self.assertRaises(ValueError):
                U.version_tuple(faux)

    def test_comparaison_numerique(self):
        self.assertTrue(U.est_plus_recente('1.10.0', '1.9.9'))       # pas une comparaison de textes
        self.assertTrue(U.est_plus_recente('v2.0.0', '1.99.99'))
        self.assertFalse(U.est_plus_recente('1.5.0', '1.5.0'))
        self.assertFalse(U.est_plus_recente('1.4.1', '1.5.0'))

    def test_verification_due(self):
        m = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
        self.assertTrue(U.verification_due('', m))
        self.assertTrue(U.verification_due(None, m))
        self.assertTrue(U.verification_due('n\'importe quoi', m))
        self.assertFalse(U.verification_due((m - timedelta(hours=3)).isoformat(), m))
        self.assertTrue(U.verification_due((m - timedelta(hours=25)).isoformat(), m))
        self.assertTrue(U.verification_due((m + timedelta(days=3)).isoformat(), m))   # horloge du PC reculée
        self.assertFalse(U.verification_due(U.maintenant_iso()))

    def test_version_simulee(self):
        self.assertEqual(U.version_pour_recherche('1.5.0', {}), '1.5.0')
        self.assertEqual(U.version_pour_recherche('1.5.0', {U.VARIABLE_TEST: 'v1.4.0'}), '1.4.0')
        self.assertEqual(U.version_pour_recherche('1.5.0', {U.VARIABLE_TEST: 'n\'importe quoi'}), '1.5.0')

    def test_a_proposer(self):
        info = {'version': '1.6.0'}
        self.assertTrue(U.a_proposer(info, ''))
        self.assertTrue(U.a_proposer(info, '1.5.9'))
        self.assertFalse(U.a_proposer(info, '1.6.0'))
        self.assertFalse(U.a_proposer(None, ''))


class TestChercher(unittest.TestCase):
    def test_nouvelle_version(self):
        gh = FauxGithub(routes_ok())
        info = U.chercher(DEPOT, '1.5.0', PREFIXE, ouvrir=gh)
        self.assertEqual(info['version'], '1.6.0')
        self.assertEqual(info['installateur'], {'nom': 'ELPRO_Demo_Setup_1.6.0.exe', 'url': URL_EXE,
                                                'taille': len(CONTENU)})
        self.assertEqual(info['empreintes'], URL_SUMS)
        self.assertIn('mise à jour automatique', info['notes'])
        self.assertTrue(info['page'].endswith('/v1.6.0'))
        self.assertEqual(gh.appels[0][1], 'GeoAzimut-ELPRO-Demo')

    def test_a_jour_ou_plus_ancienne(self):
        for actuelle in ('1.6.0', '1.7.0'):
            self.assertIsNone(U.chercher(DEPOT, actuelle, PREFIXE, ouvrir=FauxGithub(routes_ok())))

    def test_brouillon_et_preversion_ignores(self):
        for champ in ('draft', 'prerelease'):
            gh = FauxGithub({API: release(**{champ: True})})
            self.assertIsNone(U.chercher(DEPOT, '1.5.0', PREFIXE, ouvrir=gh))

    def test_release_incomplete(self):
        for manque in ('ELPRO_Demo_Setup_1.6.0.exe', 'SHA256SUMS.txt'):
            assets = [a for a in json.loads(release())['assets'] if a['name'] != manque]
            gh = FauxGithub({API: release(assets=assets)})
            with self.assertRaises(U.ErreurMiseAJour) as c:
                U.chercher(DEPOT, '1.5.0', PREFIXE, ouvrir=gh)
            self.assertIn('incomplète', str(c.exception))

    def test_erreurs_reseau(self):
        cas = [(urllib.error.URLError('pas de réseau'), 'Pas de connexion'),
               (urllib.error.HTTPError(API, 403, 'rate limit', {}, None), 'Trop de vérifications'),
               (urllib.error.HTTPError(API, 404, 'Not Found', {}, None), 'Aucune version publiée'),
               (urllib.error.HTTPError(API, 500, 'Server Error', {}, None), '500'),
               (TimeoutError('délai'), 'Pas de connexion')]
        for exc, attendu in cas:
            with self.assertRaises(U.ErreurMiseAJour) as c:
                U.chercher(DEPOT, '1.5.0', PREFIXE, ouvrir=FauxGithub({API: exc}))
            self.assertIn(attendu, str(c.exception))

    def test_reponses_illisibles(self):
        for data in (b'<html>', release(tag='latest')):
            with self.assertRaises(U.ErreurMiseAJour):
                U.chercher(DEPOT, '1.5.0', PREFIXE, ouvrir=FauxGithub({API: data}))

    def test_hotes(self):
        self.assertTrue(U.url_autorisee(URL_EXE))
        self.assertTrue(U.url_autorisee('https://objects.githubusercontent.com/x'))
        self.assertFalse(U.url_autorisee(URL_EXE.replace('https', 'http')))
        self.assertFalse(U.url_autorisee('https://github.com.exemple.net/x'))
        self.assertFalse(U.url_autorisee(''))
        gh = FauxGithub({API: (release(), 'https://ailleurs.example/api')})     # redirection vers un autre hôte
        with self.assertRaises(U.ErreurMiseAJour) as c:
            U.chercher(DEPOT, '1.5.0', PREFIXE, ouvrir=gh)
        self.assertIn('refusée', str(c.exception))


class TestTelecharger(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dossier, ignore_errors=True)

    def info(self, routes):
        return U.chercher(DEPOT, '1.5.0', PREFIXE, ouvrir=FauxGithub(routes))

    def test_empreinte_attendue(self):
        texte = f'{SHA.upper()} *ELPRO_Demo_Setup_1.6.0.exe\r\n{"a" * 64}  autre.exe\n'
        self.assertEqual(U.empreinte_attendue(texte, 'ELPRO_Demo_Setup_1.6.0.exe'), SHA)
        self.assertIsNone(U.empreinte_attendue(texte, 'ELPRO_Demo_Setup.exe'))
        self.assertIsNone(U.empreinte_attendue('rien', 'x.exe'))

    def test_telechargement_verifie(self):
        routes = routes_ok()
        etapes = []
        chemin = U.telecharger(self.info(routes), self.dossier, progression=lambda r, t: etapes.append((r, t)),
                               ouvrir=FauxGithub(routes))
        self.assertEqual(chemin, os.path.join(self.dossier, 'ELPRO_Demo_Setup_1.6.0.exe'))
        with open(chemin, 'rb') as f:
            self.assertEqual(f.read(), CONTENU)
        self.assertGreater(len(etapes), 1)
        self.assertEqual(etapes[-1], (len(CONTENU), len(CONTENU)))
        self.assertEqual(os.listdir(self.dossier), ['ELPRO_Demo_Setup_1.6.0.exe'])

    def test_empreinte_fausse(self):
        routes = routes_ok(sums=f'{"b" * 64}  ELPRO_Demo_Setup_1.6.0.exe\n'.encode())
        with self.assertRaises(U.ErreurMiseAJour) as c:
            U.telecharger(self.info(routes), self.dossier, ouvrir=FauxGithub(routes))
        self.assertIn('empreinte', str(c.exception))
        self.assertEqual(os.listdir(self.dossier), [])          # rien ne reste

    def test_installateur_absent_des_empreintes(self):
        routes = routes_ok(sums=f'{SHA}  ELPRO_Demo_Setup.exe\n'.encode())
        with self.assertRaises(U.ErreurMiseAJour) as c:
            U.telecharger(self.info(routes), self.dossier, ouvrir=FauxGithub(routes))
        self.assertIn('absent', str(c.exception))
        self.assertFalse(os.listdir(self.dossier))

    def test_annulation(self):
        routes = routes_ok()
        n = []
        with self.assertRaises(U.ErreurMiseAJour) as c:
            U.telecharger(self.info(routes), self.dossier, annule=lambda: n.append(1) or len(n) > 2,
                          ouvrir=FauxGithub(routes))
        self.assertIn('annulé', str(c.exception))
        self.assertEqual(os.listdir(self.dossier), [])

    def test_coupure_et_fichier_incomplet(self):
        routes = routes_ok()
        info = self.info(routes)
        coupe = dict(routes)
        coupe[URL_EXE] = (CONTENU, URL_EXE, 100000)
        with self.assertRaises(U.ErreurMiseAJour) as c:
            U.telecharger(info, self.dossier, ouvrir=FauxGithub(coupe))
        self.assertIn('interrompue', str(c.exception))
        court = dict(routes)
        court[URL_EXE] = CONTENU[:-10]
        with self.assertRaises(U.ErreurMiseAJour) as c:
            U.telecharger(info, self.dossier, ouvrir=FauxGithub(court))
        self.assertIn('incomplet', str(c.exception))
        self.assertEqual(os.listdir(self.dossier), [])


class TestInstallation(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.mkdtemp()
        self.exe = os.path.join(self.dossier, 'ELPRO_Demo_Setup_1.6.0.exe')
        with open(self.exe, 'wb') as f:
            f.write(CONTENU)

    def tearDown(self):
        shutil.rmtree(self.dossier, ignore_errors=True)

    def test_arguments(self):
        appels = []
        U.lancer_installation(self.exe, demarrer=lambda *a: appels.append(a))
        self.assertEqual(appels, [(self.exe, 'open', '/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /RELANCER')])

    def test_uac_refusee_et_fichier_absent(self):
        def refus(*a):
            e = OSError('annulé')
            e.winerror = 1223
            raise e
        with self.assertRaises(U.ErreurMiseAJour) as c:
            U.lancer_installation(self.exe, demarrer=refus)
        self.assertIn('refusée', str(c.exception))
        with self.assertRaises(U.ErreurMiseAJour):
            U.lancer_installation(os.path.join(self.dossier, 'absent.exe'), demarrer=lambda *a: None)

    def test_nettoyer(self):
        for n in ('ancien.exe', 'x.exe.part', 'note.txt'):
            open(os.path.join(self.dossier, n), 'w').close()
        U.nettoyer(self.dossier, garder='ELPRO_Demo_Setup_1.6.0.exe')
        self.assertEqual(sorted(os.listdir(self.dossier)), ['ELPRO_Demo_Setup_1.6.0.exe', 'note.txt'])
        U.nettoyer(os.path.join(self.dossier, 'inexistant'))     # sans erreur


if __name__ == '__main__':
    unittest.main()
