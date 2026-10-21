# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""Tests de la récupération automatique (v1.1) contre une fausse centrale HTTP locale."""
import os, sys, json, base64, shutil, tempfile, threading, unittest
from http.server import HTTPServer, BaseHTTPRequestHandler

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.join(ICI, '..')
sys.path.insert(0, os.path.join(RACINE, 'engine'))
sys.path.insert(0, os.path.join(RACINE, 'tools'))
import elpro_logs as L
import elpro_remote as R
import make_demo_logs as G

PROJET_B = os.path.join(RACINE, 'examples', 'demo_site_B.json')


def lire(p, mode='rb'):
    with open(p, mode, **({} if 'b' in mode else {'encoding': 'utf-8'})) as f:
        return f.read()
ACCUEIL = ('<table><tr><td>Device Name:</td><td>{nom}</td></tr>'
           '<tr><td>Serial Number:</td><td>{serie}</td></tr></table>')


class FausseCentrale:
    """Imite une 415U-2-C4 : authentification Basic, main.asp, Datalogs/ (liens absolus)."""

    def __init__(self, fichiers, nom='B-BASE', serie='99000000001', mdp='secret'):
        self.fichiers, self.nom, self.serie, self.mdp = dict(fichiers), nom, serie, mdp
        self.coupes = set()            # fichiers dont l'envoi est coupé au milieu (v1.2)
        fc = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                attendu = 'Basic ' + base64.b64encode(f'user:{fc.mdp}'.encode()).decode()
                if self.headers.get('Authorization') != attendu:
                    self.send_response(401)
                    self.send_header('WWW-Authenticate', 'Basic realm="415U"')
                    self.end_headers(); return
                hote = f'http://{self.headers["Host"]}'
                if self.path == '/operator/main.asp':
                    corps = ACCUEIL.format(nom=fc.nom, serie=fc.serie).encode()
                elif self.path.rstrip('/') == '/operator/Datalogs':
                    corps = ('<ul><li><a href="%s/operator/"> Parent Directory</a></li>' % hote + ''.join(
                        f'<li><a href="{hote}/operator/Datalogs/{n}"> {n}</a></li>'
                        for n in sorted(fc.fichiers, reverse=True)) + '</ul>').encode()
                elif self.path.startswith('/operator/Datalogs/') and self.path[19:] in fc.fichiers:
                    corps = fc.fichiers[self.path[19:]]
                else:
                    self.send_response(404); self.end_headers(); return
                self.send_response(200)
                self.send_header('Content-Length', str(len(corps)))
                self.end_headers()
                if self.path[19:] in fc.coupes:
                    self.wfile.write(corps[:len(corps) // 3])       # la centrale coupe en plein fichier
                    self.wfile.flush()
                    self.close_connection = True
                    return
                self.wfile.write(corps)

        self.srv = HTTPServer(('127.0.0.1', 0), H)
        self.adresse = f'127.0.0.1:{self.srv.server_port}'
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def arreter(self):
        self.srv.shutdown(); self.srv.server_close()


class TestRecuperation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.logs = G.generer(PROJET_B, os.path.join(cls.tmp, 'logs'), 3)
        cls.contenus = {os.path.basename(p): lire(p) for p in cls.logs}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.fc = FausseCentrale({n: c for n, c in list(self.contenus.items())[:2]})
        self.addCleanup(self.fc.arreter)
        chemin = os.path.join(self.tmp, f'{self.id()}.db')
        self.m = L.Magasin(chemin)
        self.addCleanup(self.m.fermer)
        self.sid = self.m.ajouter_config(json.loads(lire(PROJET_B, 'r')))['systeme_id']
        self.m.definir_acces(self.sid, self.fc.adresse, 'user', R.proteger_mdp('secret'))

    def test_mot_de_passe(self):
        p = R.proteger_mdp('éàü-123')
        self.assertNotIn(b'123', p.split(b':', 1)[1] if p.startswith(b'DPAPI') else b'')
        self.assertEqual(R.retrouver_mdp(p), 'éàü-123')

    def test_identifier_et_lister(self):
        s = R.Session(self.fc.adresse, 'user', 'secret')
        self.assertEqual(s.identifier(), {'nom': 'B-BASE', 'serie': '99000000001'})
        self.assertEqual(s.lister(), sorted(list(self.contenus)[:2]))
        self.assertEqual(R.heure_fichier('20261019071714-X_CA_F9-DAT.log'),
                         L.utc_depuis_texte('2026-10-19 07:17:14'))

    def test_recuperation_puis_rien_de_nouveau(self):
        vus = []
        r = R.recuperer(self.m, self.sid, progression=lambda n, t, nom: vus.append((n, t)))
        self.assertEqual((r['statut'], r['disponibles'], r['nouveaux']), ('ok', 2, 2))
        self.assertEqual([x['statut'] for x in r['imports']], ['importe', 'importe'])
        self.assertEqual(vus[-1], (2, 2))
        self.assertEqual(self.m.systemes()[0]['nb_fichiers'], 2)
        self.assertEqual(self.m.acces(self.sid)['dernier_resultat'], 'ok')
        r = R.recuperer(self.m, self.sid)
        self.assertEqual((r['statut'], r['nouveaux']), ('rien_de_nouveau', 0))
        # un nouveau fichier apparaît sur la centrale
        n3 = list(self.contenus)[2]
        self.fc.fichiers[n3] = self.contenus[n3]
        r = R.recuperer(self.m, self.sid)
        self.assertEqual((r['statut'], r['nouveaux']), ('ok', 1))
        self.assertEqual(self.m.periode(self.sid)[1] - self.m.periode(self.sid)[0], 3 * 86400)

    def test_import_manuel_puis_auto(self):
        self.m.importer_fichier(self.sid, self.logs[0])
        r = R.recuperer(self.m, self.sid)
        self.assertEqual(r['nouveaux'], 1)                 # le fichier importé à la main est reconnu

    def test_mauvais_mot_de_passe(self):
        self.m.definir_acces(self.sid, self.fc.adresse, 'user', R.proteger_mdp('faux'))
        r = R.recuperer(self.m, self.sid)
        self.assertEqual(r['statut'], 'acces_refuse')
        self.assertEqual(self.m.systemes()[0]['nb_fichiers'], 0)

    def test_injoignable(self):
        self.m.definir_acces(self.sid, '127.0.0.1:1', 'user', R.proteger_mdp('secret'))
        r = R.recuperer(self.m, self.sid)
        self.assertEqual(r['statut'], 'injoignable')
        self.assertIn('WireGuard', r['message'])

    def test_mauvaise_centrale(self):
        self.fc.nom, self.fc.serie = 'X_CA_F9', '12345678901'
        r = R.recuperer(self.m, self.sid)
        self.assertEqual(r['statut'], 'mauvaise_centrale')
        self.assertIn('X_CA_F9', r['message'])
        self.assertEqual(self.m.systemes()[0]['nb_fichiers'], 0)
        # une fois le n° de série connu, c'est lui qui fait foi
        self.fc.nom, self.fc.serie = 'B-BASE', '99000000001'
        R.recuperer(self.m, self.sid)
        self.fc.nom, self.fc.serie = 'B-BASE', '123'
        self.assertEqual(R.recuperer(self.m, self.sid)['statut'], 'mauvaise_centrale')

    def test_non_configure_et_annulation(self):
        sid2 = self.m.ajouter_config(json.loads(lire(os.path.join(RACINE, 'examples', 'demo_site_A.json'), 'r')))['systeme_id']
        self.assertEqual(R.recuperer(self.m, sid2)['statut'], 'non_configure')
        r = R.recuperer(self.m, self.sid, annuler=lambda: True)
        self.assertEqual(r['statut'], 'annule')

    def test_periode_par_defaut(self):
        self.assertIsNone(self.m.periode_par_defaut(self.sid))                 # aucune donnée
        R.recuperer(self.m, self.sid)                                           # 2 jours de données
        self.assertEqual(self.m.periode_par_defaut(self.sid), self.m.periode(self.sid))
        t0, t1 = self.m.periode(self.sid)
        self.assertEqual(self.m.periode_par_defaut(self.sid, jours=1), (t1 - 86400, t1))   # plus que 1 jour de données
        # changement d'heure : lundi 26.10 10:00 -> lundi 19.10 10:00 (heure suisse) = 7 j + 1 h
        t1 = L.utc_depuis_locale(2026, 10, 26, 10)
        self.assertEqual(L.heure_locale(L.reculer_jours(t1, 7)), '19.10.2026 10:00:00')
        self.assertEqual(t1 - L.reculer_jours(t1, 7), 7 * 86400 + 3600)

    def test_coupure_en_plein_fichier(self):
        n1, n2 = sorted(self.fc.fichiers)
        self.fc.coupes.add(n2)
        r = R.recuperer(self.m, self.sid)
        self.assertEqual(r['statut'], 'injoignable')
        self.assertIn('Arrêt après 1 fichier', r['message'])
        self.assertEqual(self.m.noms_fichiers(self.sid), {n1})               # le 1er fichier est gardé
        self.assertEqual(self.m.acces(self.sid)['dernier_resultat'], 'injoignable')
        self.fc.coupes.clear()
        self.assertEqual(R.recuperer(self.m, self.sid)['nouveaux'], 1)       # la suite à la récupération suivante

    def test_tout_recuperer_continue_apres_coupure(self):
        sid2 = self.m.ajouter_config(json.loads(lire(os.path.join(RACINE, 'examples', 'demo_site_A.json'), 'r')))['systeme_id']
        self.m.definir_acces(sid2, '127.0.0.1:1', 'user', R.proteger_mdp('x'))
        self.fc.coupes.add(sorted(self.fc.fichiers)[0])
        res = R.recuperer_tout(self.m)
        self.assertEqual([r['statut'] for _, r in res], ['injoignable', 'injoignable'])
        self.assertIsNotNone(self.m.acces(sid2)['derniere_recuperation'])

    def test_tout_recuperer(self):
        sid2 = self.m.ajouter_config(json.loads(lire(os.path.join(RACINE, 'examples', 'demo_site_A.json'), 'r')))['systeme_id']
        self.m.definir_acces(sid2, '127.0.0.1:1', 'user', R.proteger_mdp('x'))     # injoignable
        vus = []
        res = R.recuperer_tout(self.m, progression=lambda s, n, t, nom: vus.append(s))
        self.assertEqual([(S['cle'], r['statut']) for S, r in res], [('DEMO_B', 'ok'), ('DEMO_A', 'injoignable')])
        self.assertIn('Demo Site B', vus)

    def test_trou_efface_par_la_centrale(self):
        self.m.importer_fichier(self.sid, self.logs[0])
        n3 = list(self.contenus)[2]
        self.fc.fichiers = {n3: self.contenus[n3]}           # le jour 2 a déjà été effacé
        r = R.recuperer(self.m, self.sid)
        self.assertIn('déjà effacé', r['alerte'])
        self.assertIsNone(R.rappel_necessaire(self.m, self.sid, maintenant=self.m.periode(self.sid)[1] + 86400))
        self.assertIn('rapidement', R.rappel_necessaire(self.m, self.sid,
                                                        maintenant=self.m.periode(self.sid)[1] + 6 * 86400))


if __name__ == '__main__':
    unittest.main()
