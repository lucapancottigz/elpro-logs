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


class TestV13(Base):
    """Moteur v1.3 : import atomique par fichier, emplacement de la base."""

    def test_fichier_qui_plante_hors_lot(self):
        m, sid = self.nouveau('v13a.db')
        vrai = m._ecrire_points
        m._ecrire_points = lambda *a: (_ for _ in ()).throw(RuntimeError('plantage'))
        with self.assertRaises(RuntimeError):
            m.importer_fichier(sid, self.logs[0])
        m._ecrire_points = vrai
        m.importer_fichier(sid, self.logs[1])                 # commit suivant : ne doit rien entraîner du 1er
        self.assertEqual([f['nom'] for f in m.fichiers(sid)], [os.path.basename(self.logs[1])])
        self.assertEqual(m.importer_fichier(sid, self.logs[0])[0]['statut'], 'importe')

    def test_fichier_qui_plante_dans_un_lot(self):
        m, sid = self.nouveau('v13b.db')
        vrai = m._ecrire_points

        def parfois(cur, s, lots):
            if m._casse:
                raise RuntimeError('plantage')
            return vrai(cur, s, lots)
        m._ecrire_points = parfois
        with m.lot():
            for k, p in enumerate(self.logs):
                m._casse = (k == 1)
                try:
                    m.importer_fichier(sid, p)
                except RuntimeError:
                    pass                                      # l'interface note l'erreur et continue
        noms = sorted(f['nom'] for f in m.fichiers(sid))
        self.assertEqual(noms, sorted(os.path.basename(p) for p in (self.logs[0], self.logs[2])))
        self.assertEqual(len(m.trous(sid, *m.periode(sid))), 1)  # le jour du fichier raté manque, rien d'autre
        m._casse = False
        self.assertEqual(m.importer_fichier(sid, self.logs[1])[0]['statut'], 'importe')
        self.assertEqual(m.trous(sid, *m.periode(sid)), [])

    def test_copier_et_verifier_base(self):
        m, sid = self.nouveau('v13c.db')
        m.importer_fichier(sid, self.logs[0])
        dest = os.path.join(self.tmp, 'ailleurs', 'elpro_logs.db')
        if os.path.exists(dest):
            os.remove(dest)
        self.assertGreater(L.copier_base(m.chemin, dest), 0)
        self.assertTrue(L.verifier_base(dest)['ok'])
        self.assertEqual(L.verifier_base(dest)['nb_systemes'], 1)
        m2 = L.Magasin(dest, creer=False)
        self.addCleanup(m2.fermer)
        self.assertEqual(m2.periode(sid), m.periode(sid))
        with self.assertRaises(FileExistsError):
            L.copier_base(m.chemin, dest)
        faux = os.path.join(self.tmp, 'pas_une_base.db')
        open(faux, 'w').write('bonjour')
        self.assertFalse(L.verifier_base(faux)['ok'])
        self.assertFalse(L.verifier_base(os.path.join(self.tmp, 'absent.db'))['ok'])
        with self.assertRaises(FileNotFoundError):
            L.Magasin(os.path.join(self.tmp, 'absent.db'), creer=False)

    def test_avertissement_emplacement(self):
        self.assertIsNotNone(L.avertissement_emplacement('//serveur/partage/elpro_logs.db'))
        self.assertIsNone(L.avertissement_emplacement('/home/x/OneDrive - Geo/elpro_logs.db'))   # v1.5 : pris en charge
        self.assertIsNone(L.avertissement_emplacement(os.path.join(self.tmp, 'elpro_logs.db')))

class TestV14Analogique(unittest.TestCase):
    """Entrées / sorties analogiques (ELPRO Config 1.5+) et étalonnage (1.6)."""

    def projet(self):
        p = charger(PROJET_A)
        R = {r['nom']: r for r in p['radios']}
        R['A-SM1']['peripheriques'].append({'type': 'ENTREE_ANA', 'nom': 'NIVEAU', 'ai': 2, 'mode': 'courant',
                                            'mesure_bas': 0, 'mesure_haut': 10, 'unite': 'bar'})
        # ELPRO Config v2.4 : AI2 en tension = 0-20 V, Span 2048 (8192 = 0 V, 49152 = 20 V)
        R['A-BASE']['peripheriques'].append({'type': 'ENTREE_ANA', 'nom': 'CAM1_BATTV', 'ai': 2, 'mode': 'tension',
                                             'unite': 'V'})
        R['A-F1']['peripheriques'].append({'type': 'SORTIE_ANA', 'nom': 'VANNE', 'ao': 1})
        return p

    def test_catalogue_et_decodage(self):
        cat = L.catalogue(self.projet())
        pr = cat['par_registre']
        batt, niv, ao = pr[35301], pr[35302], pr[45001]
        self.assertEqual((batt['genre'], batt['famille'], batt['unite'], batt['station']), ('ANA', 'ANALOGIQUES', 'V', 'A-BASE'))
        self.assertEqual(batt['libelle'], 'CAM1_BATTV (AI2)')
        self.assertEqual((niv['genre'], niv['unite'], niv['libelle']), ('ANA', 'bar', 'NIVEAU (AI2)'))
        self.assertEqual((ao['genre'], ao['unite'], ao['libelle']), ('CONSIGNE', 'mA', 'VANNE (AO1)'))
        self.assertEqual(L.decoder(batt, 8192 + 12 * 2048), 12.0)
        self.assertEqual(L.decoder(niv, 32768), 5.0)
        self.assertEqual(L.decoder(ao, 49152), 20.0)
        self.assertIsNone(L.decoder(niv, 0))
        self.assertEqual(pr[15802]['genre'], 'FAIL_ANA')                        # A-SM1 lit une entrée analogique
        self.assertEqual(pr[15503]['genre'], 'FAIL_SGNL')                       # A-F1 reçoit des commandes / consignes
        self.assertNotIn(15801, pr)                                              # la base n'a pas de lecture distante

    def test_colonnes(self):
        regs, avert = L.resoudre_colonnes(['ANA01', 'ANA02', 'ANA_FAIL02', 'AO01', 'BATTTV01', 'BATTV02'])
        self.assertEqual((regs, avert), ([35301, 35302, 15802, 45001, 30501, 30502], []))
        self.assertEqual([n for n, _, _ in L.LISTE_ANALOGIQUE], ['ANA', 'ANA_FAIL', 'AO'])

    def test_import_et_courbe(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        m = L.Magasin(os.path.join(d, 'a.db')); self.addCleanup(m.fermer)
        sid = m.ajouter_config(self.projet())['systeme_id']
        lignes = ['TimeStamp: 2026-10-01 00:00:00', 'Unit Serial Number: 99000000002', '',
                  'Timestamp,ANA01,ANA02,AO01,']
        for i in range(10):
            lignes.append(f'2026-10-01 00:{i:02d}:00,{8192 + int(12.5 * 2048)},{16384 + 2048 * i},49152,')
        r = m.importer_octets(sid, ('\n'.join(lignes) + '\n').encode(), 'data.csv')
        self.assertEqual(r[0]['statut'], 'importe', r)
        cat = m.catalogue(sid)
        t0, t1 = T_DEBUT, T_DEBUT + 600
        segs = m.segments_decodes(sid, cat['par_registre'][35302], t0, t1)
        self.assertEqual([round(v, 2) for _, _, v in segs if v is not None][:3], [0.0, 0.62, 1.25])
        self.assertEqual({round(v, 1) for _, _, v in m.segments_decodes(sid, cat['par_registre'][35301], t0, t1)
                          if v is not None}, {12.5})



class TestV141ColonneSansNumero(unittest.TestCase):
    """Entrée de log d'un seul registre : la radio écrit « ANA » et non « ANA01 » (constaté sur radio)."""

    def test_resolution(self):
        regs, avert = L.resoudre_colonnes(['BATTV01', 'ANA', 'ANA_FAIL01', 'RADAR', ''])
        self.assertEqual((regs, avert), ([30501, 35301, 15801, 35201, None], []))

    def test_relire_complete_sans_rien_changer(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        m = L.Magasin(os.path.join(d, 'a.db')); self.addCleanup(m.fermer)
        sid = m.ajouter_config(TestV14Analogique().projet())['systeme_id']
        lignes = ['TimeStamp: 2026-10-01 00:00:00', 'Unit Serial Number: 99000000004', '',
                  'Timestamp,COMFLAGS02,BATTV01,ANA,']
        for i in range(20):
            lignes.append(f'2026-10-01 00:{i:02d}:00,0,{8192 + 13 * 1024 + i},{8192 + int((12 + i / 10) * 2048)},')
        octets = ('\n'.join(lignes) + '\n').encode()
        # 1er import comme la v1.4.0 : la colonne « ANA » n'est pas reconnue
        m.definir_profil(sid, {k: v for k, v in L.PROFIL_STANDARD.items() if k != 'ANA'})
        r = m.importer_octets(sid, octets, 'x.csv')[0]
        self.assertEqual(r['statut'], 'importe')
        m.definir_profil(sid, None)
        cat = m.catalogue(sid)
        t0, t1 = T_DEBUT, T_DEBUT + 1200
        self.assertEqual([v for _, _, v in m.segments(sid, 35301, t0, t1)], [])
        batt_avant = m.segments(sid, 30501, t0, t1)
        n_avant = m.nb_points(sid)
        # même fichier sans « completer » : déjà importé
        self.assertEqual(m.importer_octets(sid, octets, 'x.csv')[0]['statut'], 'deja_importe')
        # relecture : seule la colonne manquante est ajoutée
        r = m.importer_octets(sid, octets, 'x.csv', completer=True)[0]
        self.assertEqual(r['statut'], 'complete', r)
        self.assertIn('ANA', r['message'])
        vals = [v for _, _, v in m.segments_decodes(sid, cat['par_registre'][35301], t0, t1)]
        self.assertEqual((vals[0], round(vals[-1], 1)), (12.0, 13.9))
        self.assertEqual(m.segments(sid, 30501, t0, t1), batt_avant)        # rien d'existant n'a bougé
        self.assertEqual(len(m.fichiers(sid)), 1)
        self.assertGreater(m.nb_points(sid), n_avant)
        # 2e relecture : plus rien à compléter
        r = m.importer_octets(sid, octets, 'x.csv', completer=True)[0]
        self.assertEqual(r['statut'], 'deja_importe')

class TestV141AncienFormat(unittest.TestCase):
    """Une config au format 1 (ELPRO Config < 1.6.1) garde l'échelle réellement programmée dans la radio."""

    def projet(self, version, **per):
        p = charger(PROJET_A); p['version'] = version
        p['radios'][0]['peripheriques'].append(dict({'type': 'ENTREE_ANA', 'nom': 'CAM1_BATTV', 'mode': 'tension',
                                                     'unite': 'V'}, **per))
        return p

    def test_echelles(self):
        et = {'reg_bas': 8192, 'reg_haut': 30720, 'eng_bas': 0, 'eng_haut': 25}
        c1 = L.catalogue(self.projet(1, ai=4, etalonnage=et))['par_registre'][35301]
        self.assertEqual(c1['libelle'], 'CAM1_BATTV (AI2)')
        self.assertEqual(L.decoder(c1, 8192 + 12 * 901.12), 12.0)
        c0 = L.catalogue(self.projet(1, ai=4))['par_registre'][35301]          # sans étalonnage : 0-5 V
        self.assertEqual(L.decoder(c0, 8192 + 4 * 8192), 4.0)
        c2 = L.catalogue(self.projet(2, ai=2))['par_registre'][35301]          # format 2 : Span 2048
        self.assertEqual(L.decoder(c2, 8192 + 12 * 2048), 12.0)

    def test_stockage_et_nouvelle_version(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, True)
        m = L.Magasin(os.path.join(d, 'a.db')); self.addCleanup(m.fermer)
        et = {'reg_bas': 8192, 'reg_haut': 28672, 'eng_bas': 0, 'eng_haut': 20}
        sid = m.ajouter_config(self.projet(1, ai=4, etalonnage=et))['systeme_id']
        self.assertEqual(L.decoder(m.catalogue(sid)['par_registre'][35301], 8192 + 12 * 1024), 12.0)
        t = L.utc_depuis_texte('2026-11-10 08:00:00')
        r = m.ajouter_config(dict(self.projet(2, ai=2), version_config='1.1'), valable_depuis=t)
        self.assertEqual(r['statut'], 'version')
        self.assertEqual(L.decoder(m.catalogue(sid, t - 60)['par_registre'][35301], 8192 + 12 * 1024), 12.0)
        self.assertEqual(L.decoder(m.catalogue(sid, t + 60)['par_registre'][35301], 8192 + 12 * 2048), 12.0)


if __name__ == '__main__':
    unittest.main()


class TestV15FichierPartage(unittest.TestCase):
    """v1.5 — Fichier partagé (OneDrive, kDrive…) jamais ouvert par SQLite ; copie de travail par PC."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.sync = os.path.join(self.tmp, 'OneDrive', 'ELPRO')
        self.partage = os.path.join(self.sync, 'elpro_logs.db')
        self.projet = charger(PROJET_B)

    def espace(self, pc):
        return L.Espace(self.partage, dossier_travail=os.path.join(self.tmp, 'local_' + pc), poste=pc + '\\luca')

    def modifier(self, e, nom=None):
        m = L.Magasin(e.travail, creer=False, poste=e.poste)
        try:
            if nom is None:
                m.ajouter_config(self.projet)
            else:
                sid = m.systemes()[0]['id']
                m.renommer(sid, nom)
        finally:
            m.fermer()

    def noms(self, chemin):
        cx = __import__('sqlite3').connect(chemin)
        try:
            return [r[0] for r in cx.execute('SELECT nom FROM systemes')]
        finally:
            cx.close()

    def fichiers_sync(self):
        return sorted(os.listdir(self.sync))

    def test_creation_et_aucun_fichier_sqlite_dans_le_dossier_synchronise(self):
        a = self.espace('PC-FIXE')
        self.assertTrue(a.ouvrir(creer=True)['cree'])
        self.modifier(a)
        a.publier()
        self.assertEqual(self.fichiers_sync(), ['elpro_logs.db'])          # ni -wal, ni -shm, ni .tmp
        self.assertTrue(L.verifier_base(self.partage)['ok'])
        self.assertEqual(self.noms(self.partage), ['Demo Site B'])

    def test_verifier_partage(self):
        a = self.espace('PC-FIXE'); a.ouvrir(creer=True)
        os.environ['LOCALAPPDATA'] = os.path.join(self.tmp, 'appdata')
        try:
            self.assertTrue(L.verifier_partage(self.partage)['ok'])
            with open(os.path.join(self.sync, 'autre.db'), 'wb') as f:
                f.write(b'pas une base')
            self.assertFalse(L.verifier_partage(os.path.join(self.sync, 'autre.db'))['ok'])
        finally:
            del os.environ['LOCALAPPDATA']
        self.assertEqual(sorted(os.listdir(self.sync)), ['autre.db', 'elpro_logs.db'])

    def test_absent_sans_creer(self):
        with self.assertRaises(FileNotFoundError):
            self.espace('PC-FIXE').ouvrir()

    def test_aller_retour_entre_deux_pc(self):
        a = self.espace('PC-FIXE'); a.ouvrir(creer=True); self.modifier(a); a.publier(); a.fermer()
        self.assertFalse(os.path.exists(a.travail))                     # copie locale effacée à la fermeture
        b = self.espace('PC-PORTABLE')
        self.assertIsNone(b.ouvrir()['ouvert_ailleurs'])                # PC-FIXE a bien refermé
        self.modifier(b, 'Renommé sur le portable'); b.publier(); b.fermer()
        a2 = self.espace('PC-FIXE'); a2.ouvrir()
        self.assertEqual(self.noms(a2.travail), ['Renommé sur le portable'])
        a2.fermer()
        self.assertEqual(self.fichiers_sync(), ['elpro_logs.db'])

    def test_ouvert_ailleurs_puis_rechargement(self):
        a = self.espace('PC-FIXE'); a.ouvrir(creer=True); self.modifier(a); a.publier(); a.annoncer()
        b = self.espace('PC-PORTABLE')
        info = b.ouvrir()
        self.assertEqual(info['ouvert_ailleurs']['poste'], 'PC-FIXE')
        self.assertEqual(a.verifier(), 'a_jour')
        self.modifier(b, 'Nouveau nom'); b.publier()
        self.assertEqual(a.verifier(), 'modifie')
        self.assertEqual(a.info_partage()['poste'], 'PC-PORTABLE')
        a.recharger()
        self.assertEqual(self.noms(a.travail), ['Nouveau nom'])
        self.assertEqual(a.verifier(), 'a_jour')

    def test_recharger_refuse_si_modifications_non_publiees(self):
        a = self.espace('PC-FIXE'); a.ouvrir(creer=True)
        a.en_attente = True
        with self.assertRaises(RuntimeError):
            a.recharger()

    def test_conflit_rien_n_est_ecrase(self):
        a = self.espace('PC-FIXE'); a.ouvrir(creer=True); self.modifier(a); a.publier()
        b = self.espace('PC-PORTABLE'); b.ouvrir()
        self.modifier(a, 'Version fixe'); a.publier()
        self.modifier(b, 'Version portable')
        with self.assertRaises(L.ConflitPublication) as c:
            b.publier()
        self.assertIn('PC-FIXE', str(c.exception))
        self.assertTrue(b.en_attente)
        self.assertEqual(self.noms(self.partage), ['Version fixe'])     # rien d'écrasé

    def test_conflit_les_deux(self):
        a = self.espace('PC-FIXE'); a.ouvrir(creer=True); self.modifier(a); a.publier()
        b = self.espace('PC-PORTABLE'); b.ouvrir()
        self.modifier(a, 'Version fixe'); a.publier()
        self.modifier(b, 'Version portable')
        self.assertRaises(L.ConflitPublication, b.publier)
        copie = b.resoudre('les_deux')
        self.assertIn('copie PC-PORTABLE', os.path.basename(copie))
        self.assertEqual(self.noms(copie), ['Version portable'])
        self.assertEqual(self.noms(b.travail), ['Version fixe'])
        self.assertFalse(b.en_attente)
        self.assertEqual(self.noms(self.partage), ['Version fixe'])

    def test_conflit_mienne_et_autre(self):
        a = self.espace('PC-FIXE'); a.ouvrir(creer=True); self.modifier(a); a.publier()
        b = self.espace('PC-PORTABLE'); b.ouvrir()
        self.modifier(a, 'Version fixe'); a.publier()
        self.modifier(b, 'Version portable')
        self.assertRaises(L.ConflitPublication, b.publier)
        b.resoudre('mienne')
        self.assertEqual(self.noms(self.partage), ['Version portable'])
        self.assertEqual(a.verifier(), 'modifie')
        self.modifier(a, 'Encore le fixe')
        a.en_attente = True
        self.assertRaises(L.ConflitPublication, a.publier)
        a.resoudre('autre')
        self.assertEqual(self.noms(a.travail), ['Version portable'])

    def test_publication_impossible_puis_reprise_au_demarrage(self):
        a = self.espace('PC-FIXE'); a.ouvrir(creer=True); self.modifier(a); a.publier()
        self.modifier(a, 'Pas encore publié')
        cache = self.sync + '_absent'
        os.rename(self.sync, cache)                                     # kDrive pas monté, clé retirée…
        with self.assertRaises(L.PublicationImpossible):
            a.publier()
        with self.assertRaises(L.PublicationImpossible):
            a.fermer()
        self.assertTrue(os.path.exists(a.travail))                      # copie locale gardée
        os.rename(cache, self.sync)
        a2 = self.espace('PC-FIXE')                                     # démarrage suivant
        self.assertTrue(a2.a_reprendre())
        self.assertTrue(a2.ouvrir()['repris'])
        self.assertEqual(self.noms(self.partage), ['Pas encore publié'])

    def test_reprise_en_conflit(self):
        a = self.espace('PC-FIXE'); a.ouvrir(creer=True); self.modifier(a); a.publier()
        b = self.espace('PC-PORTABLE'); b.ouvrir()
        self.modifier(a, 'Fixe non publié'); a.en_attente = True; a._sauver_etat()   # plantage avant publication
        self.modifier(b, 'Portable'); b.publier(); b.fermer()
        a2 = self.espace('PC-FIXE')
        with self.assertRaises(L.ConflitPublication):
            a2.ouvrir()
        self.assertTrue(os.path.exists(a2.travail))
        a2.resoudre('les_deux')
        self.assertEqual(self.noms(a2.travail), ['Portable'])

    def test_fermeture_retire_ouvert(self):
        a = self.espace('PC-FIXE'); a.ouvrir(creer=True); a.annoncer(); a.fermer()
        b = self.espace('PC-PORTABLE')
        self.assertIsNone(b.ouvrir()['ouvert_ailleurs'])

    def test_copies_en_conflit_du_synchroniseur(self):
        a = self.espace('PC-FIXE'); a.ouvrir(creer=True)
        self.assertEqual(a.copies_en_conflit(), [])
        for nom in ('elpro_logs-PC-FIXE.db', 'elpro_logs (conflit 2026-11-09).db',      # OneDrive, autres
                    'elpro_logs (copie PC-FIXE 2026-11-09 08h12).db',                   # la nôtre : exclue
                    'elpro_logs_sauvegarde_2026-11-09.db', 'autre.db', 'elpro_logs-PC-FIXE.txt'):
            shutil.copyfile(self.partage, os.path.join(self.sync, nom))
        self.assertEqual(sorted(os.path.basename(c) for c in a.copies_en_conflit()),
                         ['elpro_logs (conflit 2026-11-09).db', 'elpro_logs-PC-FIXE.db'])

    def test_date_touchee_sans_changement(self):
        a = self.espace('PC-FIXE'); a.ouvrir(creer=True)
        os.utime(self.partage, (1, 1))                                 # le synchroniseur retouche la date
        self.assertEqual(a.verifier(), 'a_jour')
        os.remove(self.partage)
        self.assertEqual(a.verifier(), 'absent')

    def test_migration_base_avec_wal(self):
        """Base des versions précédentes ouverte directement dans OneDrive : -wal/-shm à côté du fichier."""
        os.makedirs(self.sync)
        m = L.Magasin(self.partage)
        m.cx.execute('PRAGMA wal_autocheckpoint=0')
        m.ajouter_config(self.projet)
        copie = os.path.join(self.tmp, 'ancien'); os.makedirs(copie)
        for suf in ('', '-wal', '-shm'):
            shutil.copyfile(self.partage + suf, os.path.join(copie, 'elpro_logs.db' + suf))
        m.fermer()
        shutil.rmtree(self.sync); shutil.copytree(copie, self.sync)
        self.assertIn('elpro_logs.db-wal', self.fichiers_sync())
        a = self.espace('PC-FIXE'); a.ouvrir()
        self.assertEqual(self.noms(a.travail), ['Demo Site B'])
        self.assertEqual(self.fichiers_sync(), ['elpro_logs.db'])


class TestV15MotDePasseParPoste(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.chemin = os.path.join(self.tmp, 't.db')
        m = L.Magasin(self.chemin)
        self.sid = m.ajouter_config(charger(PROJET_B))['systeme_id']
        m.fermer()

    def magasin(self, poste):
        m = L.Magasin(self.chemin, creer=False, poste=poste)
        self.addCleanup(m.fermer)
        return m

    def test_chaque_pc_garde_son_mot_de_passe(self):
        fixe, port = self.magasin('PC-FIXE\\luca'), self.magasin('PC-PORTABLE\\luca')
        fixe.definir_acces(self.sid, '10.0.0.1', 'user', b'B64:FIXE')
        acc = port.acces(self.sid)
        self.assertEqual(acc['adresse'], '10.0.0.1')                    # adresse et utilisateur communs
        self.assertFalse(acc['mdp_ce_poste'])
        port.definir_acces(self.sid, '10.0.0.1', 'user', b'B64:PORT')
        self.assertEqual(fixe.acces(self.sid)['mdp'], b'B64:FIXE')       # le portable n'a rien écrasé
        self.assertEqual(port.acces(self.sid)['mdp'], b'B64:PORT')
        fixe.definir_acces(self.sid, '10.0.0.2', 'user')                 # None : mot de passe inchangé
        self.assertEqual(fixe.acces(self.sid)['mdp'], b'B64:FIXE')
        self.assertEqual(port.acces(self.sid)['adresse'], '10.0.0.2')

    def test_ancien_mot_de_passe_commun(self):
        m = self.magasin('PC-FIXE\\luca')
        m.cx.execute("INSERT INTO acces VALUES (?, '10.0.0.1', 'user', ?, NULL, NULL)", (self.sid, b'DPAPI:ancien'))
        m.cx.commit()
        acc = m.acces(self.sid)
        self.assertEqual(acc['mdp'], b'DPAPI:ancien')                    # essayé tel quel (lisible sur le PC d'origine)
        self.assertFalse(acc['mdp_ce_poste'])

    def test_suppression_systeme(self):
        m = self.magasin('PC-FIXE\\luca')
        m.definir_acces(self.sid, '10.0.0.1', 'user', b'B64:x')
        m.supprimer_systeme(self.sid)
        self.assertEqual(m.cx.execute('SELECT COUNT(*) FROM mdp_postes').fetchone()[0], 0)
