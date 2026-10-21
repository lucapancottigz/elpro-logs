# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""Tests du moteur ELPRO Logs. Lancer : python -m unittest discover -s tests -v"""
import os, sys, io, json, gzip, shutil, tarfile, zipfile, tempfile, unittest

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.join(ICI, '..')
sys.path.insert(0, os.path.join(RACINE, 'engine'))
sys.path.insert(0, os.path.join(RACINE, 'tools'))
import elpro_logs as L
import make_demo_logs as G

PROJET_B = os.path.join(RACINE, 'examples', 'demo_site_B.json')
PROJET_A = os.path.join(RACINE, 'examples', 'demo_site_A.json')
JOUR = 86400
T_DEBUT = L.utc_depuis_texte('2026-10-01 00:00:00')


def charger(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.logs = G.generer(PROJET_B, os.path.join(cls.tmp, 'logs'), 3)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def nouveau(self, nom='t.db'):
        chemin = os.path.join(self.tmp, nom)
        for suf in ('', '-wal', '-shm'):
            if os.path.exists(chemin + suf):
                os.remove(chemin + suf)
        m = L.Magasin(chemin)
        self.addCleanup(m.fermer)
        sid = m.ajouter_config(charger(PROJET_B))['systeme_id']
        return m, sid


class TestLecture(Base):
    def test_format_radio(self):
        lg = L.lire_fichier_log(self.logs[0])[0]
        self.assertEqual(lg['serie'], '99000000001')
        self.assertEqual(len(lg['colonnes']), 310)
        self.assertEqual(len(lg['lignes']), 2880)
        self.assertEqual(lg['lignes'][1][0] - lg['lignes'][0][0], 30)
        self.assertEqual(lg['lignes'][0][0], T_DEBUT)

    def test_colonnes_standard(self):
        cols = [c for c, _ in G.colonnes_standard()]
        regs, avert = L.resoudre_colonnes(cols)
        self.assertEqual(avert, [])
        d = dict(zip(cols, regs))
        self.assertEqual(d['CABLE201'], 15021)
        self.assertEqual(d['CABLE220'], 15040)
        self.assertEqual(d['RADAR_FAIL20'], 15720)
        self.assertEqual(d['FEUX310'], 450)
        self.assertEqual(d['COMFLAGS04'], 15104)
        self.assertEqual(len(set(regs)), 310)

    def test_ancienne_liste(self):
        regs, avert = L.resoudre_colonnes(['COMFLAGS01', 'CABLE01', 'MAINV01', 'XYZ01'])
        self.assertEqual(regs, [15101, 15001, None, None])
        self.assertEqual(len(avert), 2)
        regs, avert = L.resoudre_colonnes(['MAINV01'], {'MAINV': (10517, 1)})
        self.assertEqual(regs, [10517])

    def test_zip_et_csv(self):
        z = os.path.join(self.tmp, 'deux.zip')
        with zipfile.ZipFile(z, 'w') as f:
            for p in self.logs[:2]:
                f.write(p, os.path.basename(p))
        self.assertEqual(len(L.lire_fichier_log(z)), 2)
        with tarfile.open(fileobj=io.BytesIO(gzip.decompress(open(self.logs[0], 'rb').read()))) as t:
            csv = t.extractfile('data.csv').read()
        p = os.path.join(self.tmp, 'data.csv')
        open(p, 'wb').write(csv)
        self.assertEqual(len(L.lire_fichier_log(p)[0]['lignes']), 2880)

    def test_fichier_invalide(self):
        p = os.path.join(self.tmp, 'faux.log')
        open(p, 'w').write('bonjour')
        m, sid = self.nouveau('inv.db')
        self.assertEqual(m.importer_fichier(sid, p)[0]['statut'], 'erreur')

    def test_profil_xml(self):
        xml = ('<group name="E2Config"><group name="DataLog"><table name="Records" ncols="4" maxrows="100">'
               '<tr><val><![CDATA[1]]></val><val><![CDATA[MAINV]]></val><val><![CDATA[10517]]></val>'
               '<val><![CDATA[1]]></val></tr></table></group></group>')
        self.assertEqual(L.lire_profil_xml(xml), {'MAINV': (10517, 1)})


class TestCodage(unittest.TestCase):
    def test_aller_retour(self):
        m = L.mois_de(T_DEBUT)
        pts = [(T_DEBUT, 0), (T_DEBUT + 30, 49152), (T_DEBUT + 60, None), (T_DEBUT + 90, 12),
               (T_DEBUT + 20 * JOUR, -5), (T_DEBUT + 20 * JOUR + 30, 65535)]
        self.assertEqual(L.decoder_bloc(L.coder_bloc(pts, m), m), pts)

    def test_mois(self):
        self.assertEqual(L.debut_mois(L.mois_de(T_DEBUT + 5 * JOUR)), T_DEBUT)


class TestImport(Base):
    def test_import_et_doublon(self):
        m, sid = self.nouveau('a.db')
        r = m.importer_fichier(sid, self.logs[0])[0]
        self.assertEqual(r['statut'], 'importe')
        self.assertEqual(m.importer_fichier(sid, self.logs[0])[0]['statut'], 'deja_importe')
        self.assertEqual(m.periode(sid), (T_DEBUT, T_DEBUT + JOUR))
        self.assertEqual(m.systemes()[0]['serie'], '99000000001')

    def test_chevauchement(self):
        m, sid = self.nouveau('b.db')
        m.importer_fichier(sid, self.logs[0])
        lg = L.lire_fichier_log(self.logs[0])[0]
        lg['lignes'] = lg['lignes'][100:200]
        lg['empreinte'] = 'autre'
        self.assertEqual(m.importer_log(sid, lg)['statut'], 'deja_couvert')

    def test_ordre_indifferent(self):
        m1, s1 = self.nouveau('c1.db')
        for p in self.logs:
            m1.importer_fichier(s1, p)
        m2, s2 = self.nouveau('c2.db')
        for p in reversed(self.logs):
            m2.importer_fichier(s2, p)
        t0, t1 = m1.periode(s1)
        self.assertEqual((t0, t1), m2.periode(s2))
        for c in m1.catalogue(s1)['stations'][2]['canaux']:
            self.assertEqual(m1.segments(s1, c['registre'], t0, t1), m2.segments(s2, c['registre'], t0, t1))

    def test_trou(self):
        m, sid = self.nouveau('d.db')
        m.importer_fichier(sid, self.logs[0]); m.importer_fichier(sid, self.logs[2])
        t0, t1 = m.periode(sid)
        self.assertEqual(m.trous(sid, t0, t1), [(T_DEBUT + JOUR, T_DEBUT + 2 * JOUR)])
        st = m.etat_stations(sid, t0, t1)[0]['segments']
        self.assertIn((T_DEBUT + JOUR, T_DEBUT + 2 * JOUR, 'SANS_DONNEES'), st)
        xs, ys = m.courbe(sid, m.catalogue(sid)['stations'][0]['canaux'][0], t0, t1)
        self.assertIn(None, ys)
        msgs = [e['message'] for e in m.evenements(sid, t0, t1, familles=['DONNEES'])]
        self.assertEqual(msgs, ["Début d'absence de données (1 j 0 h 00 min)", 'Reprise des données'])

    def test_serie_differente(self):
        m, sid = self.nouveau('e.db')
        m.importer_fichier(sid, self.logs[0])
        lg = L.lire_fichier_log(self.logs[1])[0]
        lg['serie'] = '123'
        self.assertEqual(m.importer_log(sid, lg)['statut'], 'serie_differente')
        self.assertEqual(m.importer_log(sid, lg, forcer_serie=True)['statut'], 'importe')

    def test_persistance_et_ouverture(self):
        m, sid = self.nouveau('f.db')
        m.importer_fichier(sid, self.logs[0])
        m.ajouter_config(charger(PROJET_A))
        m.fermer()
        m2 = L.Magasin(os.path.join(self.tmp, 'f.db'))
        self.assertEqual([s['cle'] for s in m2.systemes()], ['DEMO_B', 'DEMO_A'])
        self.assertEqual(m2.systemes()[0]['nb_fichiers'], 1)

    def test_versions_config(self):
        m, sid = self.nouveau('g.db')
        self.assertEqual(m.ajouter_config(charger(PROJET_B))['statut'], 'identique')
        p = charger(PROJET_B)
        p['radios'][1]['peripheriques'][0]['nom'] = 'CABLE_X'
        p['version_config'] = '1.1'
        r = m.ajouter_config(p, valable_depuis=T_DEBUT + JOUR)
        self.assertEqual(r, {'systeme_id': sid, 'statut': 'version'})
        self.assertEqual(len(m.configs(sid)), 2)
        self.assertEqual(len(m.versions_dans_periode(sid, T_DEBUT, T_DEBUT + 2 * JOUR)), 2)
        nom = lambda t: m.catalogue(sid, t)['stations'][1]['canaux'][3]['libelle']
        self.assertTrue(nom(T_DEBUT + 10).startswith('CABLE (DI1)'))
        self.assertTrue(nom(T_DEBUT + JOUR + 10).startswith('CABLE_X'))

    def test_taille(self):
        m, sid = self.nouveau('h.db')
        for p in self.logs:
            m.importer_fichier(sid, p)
        m.cx.execute('PRAGMA wal_checkpoint(TRUNCATE)'); m.compacter_base()
        # seuls les changements sont gardés : moins de 2 % des valeurs brutes
        self.assertLess(m.nb_points(sid), 0.02 * 3 * 2880 * 310)
        self.assertLess(m.taille_fichier(), 200 * 1024)


class TestAnalyse(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.m = L.Magasin(os.path.join(cls.tmp, 'analyse.db'))
        cls.sid = cls.m.ajouter_config(charger(PROJET_B))['systeme_id']
        for p in cls.logs:
            cls.m.importer_fichier(cls.sid, p)
        cls.t0, cls.t1 = cls.m.periode(cls.sid)

    def test_catalogue(self):
        cat = self.m.catalogue(self.sid)
        self.assertEqual([s['nom'] for s in cat['stations']][:3], ['B-BASE', 'B-SM1', 'B-SM2'])
        base = {c['genre'] for c in cat['stations'][0]['canaux']}
        self.assertNotIn('COMFLAG', base)
        self.assertIn('FAIL_SGNL', base)          # 15501 : commandes locales de la base
        sm3 = {c['genre']: c for c in cat['stations'][-1]['canaux']}
        self.assertEqual(sm3['RADAR']['unite'], 'cm')
        self.assertEqual(sm3['RADAR']['seuil_haut'], 250.0)
        self.assertTrue(cat['autres'])           # registres non utilisés : gardés et visibles

    def test_etat_comm_perdue(self):
        st = {s['station']: s['segments'] for s in self.m.etat_stations(self.sid, self.t0, self.t1)}
        pertes = [(a, b) for a, b, v in st['B-SM2'] if v == 'COMM_PERDUE']
        self.assertEqual(len(pertes), 1)
        a, b = pertes[0]
        self.assertTrue(T_DEBUT + 10 * 3600 <= a < T_DEBUT + 10 * 3600 + 600)
        self.assertTrue(abs((b - a) - 7200) < 600)
        self.assertIn('ALERTE', [v for _, _, v in st['B-SM3']])        # batterie basse jour 2
        self.assertIn('ALERTE', [v for _, _, v in st['B-BASE']])       # coupure secteur
        sysm = self.m.etat_systeme(self.sid, self.t0, self.t1)
        self.assertIn('COMM_PERDUE', [v for _, _, v in sysm])
        cases = L.Magasin.par_cases(st['B-SM2'], self.t0, self.t1, 72)
        self.assertEqual(sum(1 for c in cases if c[2] == 'COMM_PERDUE'), 3)      # 10:01 -> 12:04 UTC

    def test_synthese(self):
        sy = self.m.synthese(self.sid, self.t0, self.t1)
        self.assertEqual(sy['couverture_pct'], 100.0)
        st = {s['station']: s for s in sy['stations']}
        self.assertEqual(st['B-SM2']['comm']['nb_pertes'], 1)
        self.assertLess(st['B-SM2']['comm']['disponibilite_pct'], 100)
        bv = [c for c in st['B-SM3']['canaux'] if c['canal']['genre'] == 'BATTV'][0]
        self.assertLess(bv['min'], L.BATTV_BAS)
        self.assertGreater(bv['duree_basse'], 3600)
        mainv = [c for c in st['B-BASE']['canaux'] if c['canal']['genre'] == 'MAINV'][0]
        self.assertEqual((mainv['nb_coupures'], mainv['duree_coupures']), (1, 1800))
        # pendant la perte de comm, la batterie de B-SM2 est figée : exclue de la moyenne
        self.assertIsNotNone([c for c in st['B-SM2']['canaux'] if c['canal']['genre'] == 'BATTV'][0]['moyenne'])

    def test_evenements(self):
        ev = self.m.evenements(self.sid, self.t0, self.t1)
        msgs = [(e['station'], e['message']) for e in ev]
        self.assertIn(('B-SM2', 'Perte de communication'), msgs)
        self.assertIn(('B-BASE', 'Coupure secteur'), msgs)
        self.assertIn(('B-SM3', 'RADAR1 (AI1) : seuil atteint (251.9 cm)'), [(e['station'], e['message']) for e in ev
                                                                             if e.get('genre') == 'RADAR'][:1])
        self.assertFalse([e for e in ev if str(e.get('genre', '')).startswith('FAIL_')])   # regroupés avec le comflag
        perte = [e for e in ev if e['message'] == 'Perte de communication'][0]
        self.assertTrue(abs(perte['duree'] - 7200) < 600)
        filtre = self.m.evenements(self.sid, self.t0, self.t1, stations=['B-BASE'], familles=['SECTEUR'])
        self.assertEqual([e['message'] for e in filtre], ['Coupure secteur', 'Secteur rétabli'])

    def test_courbe_reduite(self):
        c = [c for c in self.m.catalogue(self.sid)['stations'][1]['canaux'] if c['genre'] == 'RSSI'][0]
        xs, ys = self.m.courbe(self.sid, c, self.t0, self.t1, n_max=100)
        self.assertLess(len(xs), 400)
        vals = [v for v in ys if v is not None]
        segs = self.m.segments_decodes(self.sid, c, self.t0, self.t1)
        self.assertEqual(min(vals), min(v for _, _, v in segs))
        self.assertEqual(max(vals), max(v for _, _, v in segs))

    def test_export_csv(self):
        p = os.path.join(self.tmp, 'export.csv')
        cs = self.m.catalogue(self.sid)['stations'][0]['canaux'][:2]
        self.m.exporter_csv(self.sid, cs, self.t0, self.t0 + 3600, p)
        lignes = open(p, encoding='utf-8-sig').read().splitlines()
        self.assertEqual(len(lignes), 121)
        self.assertTrue(lignes[1].startswith('01.10.2026 02:00:00;'))      # heure suisse (UTC+2)


class TestHeure(unittest.TestCase):
    def test_heure_suisse(self):
        self.assertEqual(L.heure_locale(L.utc_depuis_texte('2026-10-15 11:44:10')), '15.10.2026 13:44:10')
        self.assertEqual(L.heure_locale(L.utc_depuis_texte('2026-10-26 11:44:10')), '26.10.2026 12:44:10')
        self.assertEqual(L.utc_depuis_locale(2026, 10, 15, 13, 44, 10), L.utc_depuis_texte('2026-10-15 11:44:10'))

    def test_duree(self):
        self.assertEqual(L.duree_texte(7410), '2 h 03 min')
        self.assertEqual(L.duree_texte(90061), '1 j 1 h 01 min')



class TestV12(Base):
    """Moteur v1.2 : corrections de la relecture."""

    def test_batterie_0V_basse_partout(self):
        self.assertTrue(L._batterie_basse(8192))            # 0,00 V
        self.assertTrue(L._batterie_basse(8195))
        self.assertFalse(L._batterie_basse(None))            # jamais lue : pas de valeur, pas d'alerte
        self.assertFalse(L._batterie_basse(8192 + int(12.5 / 40 * 40960)))
        self.assertLess(L.DISPO_ROUGE, L.DISPO_ORANGE)

    def test_etat_systeme_reutilise_les_stations(self):
        m, sid = self.nouveau('v12a.db')
        m.importer_fichier(sid, self.logs[0])
        t0, t1 = m.periode(sid)
        st = m.etat_stations(sid, t0, t1)
        self.assertEqual(m.etat_systeme(sid, t0, t1, stations=st), m.etat_systeme(sid, t0, t1))

    def test_lot_identique_et_tout_ou_rien(self):
        m1, s1 = self.nouveau('v12b.db')
        for p in self.logs:
            m1.importer_fichier(s1, p)
        m2, s2 = self.nouveau('v12c.db')
        with m2.lot():
            for p in reversed(self.logs):
                m2.importer_fichier(s2, p)
        t0, t1 = m1.periode(s1)
        self.assertEqual((t0, t1), m2.periode(s2))
        for c in m1.catalogue(s1)['stations'][2]['canaux']:
            self.assertEqual(m1.segments(s1, c['registre'], t0, t1), m2.segments(s2, c['registre'], t0, t1))
        m3, s3 = self.nouveau('v12d.db')
        with self.assertRaises(RuntimeError):
            with m3.lot():
                m3.importer_fichier(s3, self.logs[0])
                raise RuntimeError('plantage')
        self.assertIsNone(m3.periode(s3))                     # rien n'a été gardé
        self.assertEqual(m3.fichiers(s3), [])

if __name__ == '__main__':
    unittest.main()
