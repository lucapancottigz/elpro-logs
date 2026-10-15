# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""Tests de recette du moteur. Lancer :  python -m unittest discover -s tests -v   (depuis le dossier livrable)
Tous les tests doivent passer avant toute livraison. Ne pas modifier les fichiers expected_*.json."""
import os, sys, json, re, unittest, tempfile, tarfile
from pathlib import Path
ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ICI, '..', 'engine'))
import elpro_engine as M

EX = os.path.join(ICI, '..', 'examples')


def charger(nom):
    return json.loads(Path(EX, f'{nom}.json').read_text(encoding='utf-8'))


def resume(plan):
    """Partie du plan figée dans expected_*.json (indépendante de la date)."""
    st = []
    for S in plan['stations']:
        st.append({k: S[k] for k in ('nom', 'uid', 'xx', 'role', 'ip', 'amont', 'puissance_dbm', 'ack')} | {
            'reads': S['reads'], 'scatters': [dict(m, paires=[list(p) for p in m['paires']]) for m in S['scatters']],
            'writes': S['writes'], 'failsafe': [list(x) for x in S['failsafe']],
            'iop': [list(l) for l in S['iop']] if S['iop'] else None,
            'noms_io': S['noms_io'], 'nb_tags': len(S['tags']), 'groupes': [list(g) for g in S['groupes']]})
    return json.loads(json.dumps({'T': plan['T'], 'registres': plan['registres'], 'stations': st}))


def simuler_iop(lignes, mem, cycles=1):
    """Interpréteur IO Plus (sous-ensemble utilisé). Sauts I=1 relatifs à la ligne du saut (validé sur radio)."""
    inv = {v: k for k, v in M.OP.items()}
    for _ in range(cycles):
        pc, acc = 0, 0
        while pc < len(lignes):
            op, I, N, _b, v, _c = lignes[pc]; o = inv[op]; arg = v if I else mem.get(v, 0); nxt = pc + 1
            if o == 'LOAD': acc = arg
            elif o == 'STOR': mem[v] = acc
            elif o == 'SET':
                if acc: mem[v] = 1
            elif o == 'RES':
                if acc: mem[v] = 0
            elif o == 'ADD': acc = (acc + arg) & 0xFFFF
            elif o == 'SUB': acc = (acc - arg) & 0xFFFF
            elif o == 'OR': acc = acc | arg
            elif o == 'XOR': acc = acc ^ arg
            elif o == 'GE': acc = int(acc >= arg)
            elif o == 'LE': acc = int(acc <= arg)
            elif o == 'LT': acc = int(acc < arg)
            elif o == 'NE': acc = int(acc != arg)
            elif o == 'JMP': nxt = pc + v if I else v - 1
            elif o == 'JMP_C':
                if (acc == 0) if N else (acc != 0): nxt = pc + v if I else v - 1
            else: raise AssertionError(o)
            pc = nxt
    return mem


class TestExemples(unittest.TestCase):
    def test_attendus(self):
        for nom in ('demo_site_A', 'demo_site_B'):
            with self.subTest(nom):
                plan = M.calculer_plan(charger(nom))
                att = json.loads(Path(EX, f'expected_{nom}.json').read_text(encoding='utf-8'))
                self.assertEqual(resume(plan), att)

    def test_fichiers(self):
        for nom in ('demo_site_A', 'demo_site_B'):
            with self.subTest(nom), tempfile.TemporaryDirectory() as d:
                plan, fichiers = M.generer_tout(charger(nom), d)
                cdb = Path(fichiers[0]).read_bytes()
                self.assertEqual(cdb[:2], b'\xff\xfe')                       # UTF-16 LE + BOM
                txt = cdb.decode('utf-16')
                self.assertIn('\r\n', txt)                                   # CRLF
                self.assertEqual(len(re.findall(r'<Unit Type="E2CI"', txt)), len(plan['stations']))
                for f in fichiers[1:]:
                    with tarfile.open(f) as tf:
                        self.assertEqual(sorted(tf.getnames()), ['Logic.conf', 'Logic.version'])
                        conf = tf.extractfile('Logic.conf').read().decode()
                        self.assertIn('<item name="Enabled"><val><![CDATA[0]]></val></item>', conf)   # livré désactivé
                        for c in re.findall(r'<val><!\[CDATA\[([^\]]*)\]\]></val></tr>', conf):
                            self.assertFalse(set(c) & set('<>&"\''), c)

    def test_iop_base_coherent(self):
        """Chaque bloc comflag additionne exactement les FailReg des lectures de la station ; seuil = nb de lectures."""
        for nom in ('demo_site_A', 'demo_site_B'):
            plan = M.calculer_plan(charger(nom)); B = plan['stations'][0]
            blocs, cur = [], []
            for l in B['iop']:
                cur.append(l)
                if l[0] == M.OP['STOR']: blocs.append(cur); cur = []
            for S in plan['stations'][1:]:
                bl = next(b for b in blocs if b[-1][4] == int(f"151{S['xx']}"))
                lus = sorted(m['fail'] for m in B['reads'] if m['dest'] == S['uid'])
                somme = sorted(l[4] for l in bl if l[0] in (M.OP['LOAD'], M.OP['ADD']))
                seuil = next(l[4] for l in bl if l[0] == M.OP['GE'])
                ou = [l[4] for l in bl if l[0] == M.OP['OR']]
                sg = [m['fail'] for m in B['scatters'] if m['dest'] == S['uid']]
                self.assertEqual(somme, lus); self.assertEqual(seuil, len(lus)); self.assertEqual(ou, sg)

    def test_polling(self):
        for nom in ('demo_site_A', 'demo_site_B'):
            plan = M.calculer_plan(charger(nom)); B = plan['stations'][0]
            per = [m for m in B['reads'] + B['scatters'] if m['periode']]
            offs = sorted(m['offset'] for m in per)
            self.assertEqual(offs, list(range(0, plan['T'], M.CRENEAU_S)))
            self.assertTrue(all(m['periode'] == plan['T'] for m in per))
            fs = [(a, a + c - 1) for a, c in B['failsafe']]
            for m in B['reads'] + B['scatters']:
                if m['fail']: self.assertTrue(any(a <= m['fail'] <= b for a, b in fs), m['nom'])

    def test_radar(self):
        """Comportement du bloc radar : envoi au démarrage, variation, tempo, seuils."""
        plan = M.calculer_plan(charger('demo_site_B'))
        S = next(X for X in plan['stations'] if X['radars']); R = S['radars'][0]
        mem, envois, prec = {}, [], 0
        seq = [20000] * 5 + [20500] * 50 + [22100] * 3 + [33000] * 60 + [31500] * 60 + [31000] * 60
        for t, v in enumerate(seq):
            mem[30000 + R['ai']] = v
            simuler_iop(S['iop'], mem)
            if mem.get(R['force'], 0) != prec:
                envois.append((t, v, mem[R['bloc'] + 2])); prec = mem[R['force']]
        self.assertEqual(envois, [(0, 20000, 0), (55, 22100, 0), (96, 33000, 1), (178, 31000, 0)])

    def test_validation(self):
        p = charger('demo_site_A')
        p['radios'][1]['peripheriques'].append({'type': 'CABLE', 'nom': 'X', 'di': [1]})
        self.assertTrue(any('DI1 déjà utilisée' in e for e in M.valider(p)))
        p = charger('demo_site_A'); p['radios'][2]['ip_octet'] = 101
        self.assertTrue(any('même adresse IP' in e for e in M.valider(p)))
        p = charger('demo_site_A'); p['radios'][0]['role'] = 'remote'
        self.assertTrue(M.valider(p))

    def test_nom_fichier(self):
        self.assertEqual(M.nom_fichier('Demo Site - A'), 'Demo_Site_A')
        self.assertEqual(M.nom_fichier('DEMO_B'), 'DEMO_B')
        self.assertEqual(M.nom_fichier(' -- '), 'projet')
        self.assertEqual(M.nom_fichier('Site Évolène - Hérémence'), 'Site_Evolene_Heremence')   # accents retirés

    def test_cle(self):
        for _ in range(50):
            k = M.generer_cle()
            self.assertEqual(len(k), 24); self.assertFalse(set(k) & set('<>&"\' '))

    def test_import(self):
        with tempfile.TemporaryDirectory() as d:
            plan, f = M.generer_tout(charger('demo_site_A'), d)
            proj, av = M.importer_cdb(f[0])
            self.assertEqual([r['nom'] for r in proj['radios']], [S['nom'] for S in plan['stations']])
            self.assertEqual([r['role'] for r in proj['radios']], [S['role'] for S in plan['stations']])
            self.assertEqual(proj['systeme']['cle_chiffrement'], plan['systeme']['cle_chiffrement'])


class TestVersion(unittest.TestCase):
    """Version de configuration : classement des modifications et noms des fichiers."""
    def test_classement(self):
        import copy
        p = charger('demo_site_B')
        def mod(f):
            q = copy.deepcopy(p); f(q); return M.classer_modification(p, q)
        self.assertIsNone(mod(lambda q: None))
        # majeures
        self.assertEqual(mod(lambda q: q['radios'].append(dict(q['radios'][1], nom='NOUVELLE', ip_octet=150))), 'majeure')
        self.assertEqual(mod(lambda q: q['radios'].pop(3)), 'majeure')
        self.assertEqual(mod(lambda q: q['radios'].insert(2, q['radios'].pop(4))), 'majeure')     # déplacement
        self.assertEqual(mod(lambda q: q['radios'][1]['peripheriques'].pop()), 'majeure')
        self.assertEqual(mod(lambda q: q['radios'][4]['peripheriques'].append({'type': 'SIRENE', 'nom': 'S', 'do': 8})), 'majeure')
        self.assertEqual(mod(lambda q: q['radios'][2].update(mainv={'actif': True, 'di': 8})), 'majeure')
        # mineures
        self.assertEqual(mod(lambda q: q['radios'][2].update(ip_octet=180)), 'mineure')
        self.assertEqual(mod(lambda q: q['radios'][2].update(puissance_dbm=30)), 'mineure')
        self.assertEqual(mod(lambda q: q['radios'][2].update(nom='RENOMMEE')), 'mineure')
        self.assertEqual(mod(lambda q: q['systeme'].update(description='autre')), 'mineure')
        def pin(q):
            per = next(x for x in q['radios'][1]['peripheriques'] if x.get('di'))
            per['di'] = [8]
        self.assertEqual(mod(pin), 'mineure')
        self.assertEqual(mod(lambda q: q['radios'][0].update(mainv={'actif': True, 'di': 7})), 'mineure')   # autre entrée MAINV
        # la version et l'historique ne comptent pas comme des modifications
        self.assertIsNone(mod(lambda q: q.update(version_config='9.9', derniere_generation={})))

    def test_increment(self):
        self.assertEqual(M.prochaine_version('2.3', 'majeure'), '3.0')
        self.assertEqual(M.prochaine_version('2.3', 'mineure'), '2.4')
        self.assertEqual(M.prochaine_version('2.9', 'mineure'), '2.10')
        self.assertEqual(M.prochaine_version('2.3', None), '2.3')
        p = charger('demo_site_A')
        p1, n1 = M.preparer_generation(p)                 # 1re génération : 1.0
        self.assertEqual((M.version_config(p1), n1), ('1.0', None))
        p2, n2 = M.preparer_generation(p1)                # sans modification : inchangée
        self.assertEqual((M.version_config(p2), n2), ('1.0', None))
        p2['radios'][2]['ip_octet'] = 190
        p3, n3 = M.preparer_generation(p2)
        self.assertEqual((M.version_config(p3), n3), ('1.1', 'mineure'))
        p3['radios'][1]['peripheriques'].pop()
        p4, n4 = M.preparer_generation(p3)
        self.assertEqual((M.version_config(p4), n4), ('2.0', 'majeure'))
        self.assertNotIn('version_config', p4['derniere_generation'])

    def test_noms_fichiers(self):
        p = charger('demo_site_B'); p['version_config'] = '3.2'
        with tempfile.TemporaryDirectory() as d:
            plan, f = M.generer_tout(p, d)
            self.assertEqual(sorted(os.path.basename(x) for x in f),
                             ['Demo_Site_B_V3.2.cdb', 'IOPlus_B-BASE_V3.2_DESACTIVE.sconf', 'IOPlus_B-SM3_V3.2_DESACTIVE.sconf'])
        self.assertEqual(M.base_nom_fichier(plan), 'Demo_Site_B_V3.2')
        p['version_config'] = '3'
        self.assertTrue(any('Version de configuration' in e for e in M.valider(p)))



class TestRegistres(unittest.TestCase):
    def test_pas_de_registres_echec(self):
        """Les registres d'échec (152xx–157xx, 15501) ne figurent pas dans la liste des registres."""
        for nom in ('demo_site_A', 'demo_site_B'):
            plan = M.calculer_plan(charger(nom))
            adr = [r['adresse'] for r in plan['registres']]
            self.assertFalse([a for a in adr if 15200 <= a <= 15799], nom)
            self.assertTrue(any(15101 <= a <= 15117 for a in adr))            # les comflags restent
            B = plan['stations'][0]
            self.assertTrue(all(m['fail'] for m in B['reads']))                # toujours utilisés par les mappings


class TestNomsEtRadar(unittest.TestCase):
    def test_noms_16_caracteres(self):
        """Noms de registres et de tags : 16 caractères max (au-delà la radio affiche DIn1, DOut5…), uniques."""
        p = charger('demo_site_B')
        p['radios'][0]['nom'] = 'NOM-TRES-LONG-BASE'                       # 18 caractères
        for r in p['radios'][1:]:
            if r.get('amont') == 'B-BASE': r['amont'] = 'NOM-TRES-LONG-BASE'
        plan = M.calculer_plan(p)
        noms = [r['nom'] for r in plan['registres']]
        self.assertTrue(all(len(n) <= M.NOM_MAX for n in noms), [n for n in noms if len(n) > M.NOM_MAX])
        self.assertEqual(len(noms), len(set(noms)))
        for S in plan['stations']:
            self.assertTrue(all(len(t['nom']) <= M.NOM_MAX for t in S['tags']))
            self.assertTrue(all(len(n) <= M.NOM_MAX for _a, n in S['noms_registres']))
        self.assertEqual(M.nom_court('SB-CA-SM1', 'RADAR_LVL'), 'SB-CA_RADAR_LVL')

    def test_radar_echelle(self):
        """Radar avec échelle : tableau de bord dans l'unité (cm), seuil converti ; sans échelle : mA."""
        p = charger('demo_site_B')
        rad = next(x for r in p['radios'] for x in r['peripheriques'] if x['type'] == 'RADAR')
        plan = M.calculer_plan(p)
        t = next(t for t in plan['stations'][0]['tags'] if t['registre'] == 35201)
        self.assertEqual(t['unites'], 'mA')
        rad.update(mesure_4ma=0, mesure_20ma=1000, unite='cm', seuil_haut_ma=12.0)
        self.assertEqual(M.valider(p), [])
        plan = M.calculer_plan(p)
        t = next(t for t in plan['stations'][0]['tags'] if t['registre'] == 35201)
        self.assertEqual((t['unites'], t['dp1'], t['dp2'], t['haut']), ('cm', '0', '1000', 500.0))
        self.assertIn('= 1000 cm', next(r for r in plan['registres'] if r['adresse'] == 35201)['description'])
        R = plan['stations'][-1]['radars'][0]
        self.assertAlmostEqual(M.unite_vers_ma(M.ma_vers_unite(9.3, R), R), 9.3)
        rad['mesure_20ma'] = 0
        self.assertTrue(any('différentes' in e for e in M.valider(p)))
        rad.pop('mesure_20ma')
        self.assertTrue(any('incomplète' in e for e in M.valider(p)))


class TestDashboardBase(unittest.TestCase):
    def test_contenu(self):
        """Base : toutes les alarmes, une commande de chaque genre, tous les BATTV/MAINV/RSSI/comflags."""
        plan = M.calculer_plan(charger('demo_site_A')); B = plan['stations'][0]
        regs = [t['registre'] for t in B['tags']]
        det = [d['adresse'] for X in plan['stations'] for d in X['detections'] if d['label']]
        self.assertTrue(set(det) <= set(regs))
        genres = [c['genre'] for X in plan['stations'] for c in X['commandes']]
        cmd = [r for r in regs if 401 <= r <= 450]
        self.assertEqual(len(cmd), len(set(genres)))                            # une par genre
        self.assertEqual(sorted(r for r in regs if 30500 < r < 30600), [int(f"305{X['xx']}") for X in plan['stations']])
        self.assertEqual(len([r for r in regs if 15100 < r < 15200]), len(plan['stations']) - 1)
        self.assertEqual(len([r for r in regs if 35100 < r < 35200]), len(plan['stations']) - 1)
        self.assertEqual(plan['avertissements'], [])
        self.assertEqual(sum(n for _g, n in B['groupes']), len(B['tags']))

    def test_limite_50(self):
        """Plus de 50 tags : les RSSI sont retirés et un avertissement est émis."""
        p = charger('demo_site_B')
        modele = p['radios'][1]
        for i in range(8):                                                     # 17 radios au total
            p['radios'].append(dict(json.loads(json.dumps(modele)), nom=f'X{i}', ip_octet=130 + i))
        plan = M.calculer_plan(p); B = plan['stations'][0]
        self.assertLessEqual(len(B['tags']), M.MAX_TAGS)
        self.assertFalse(any(t['unites'] == 'dBm' for t in B['tags']))
        self.assertTrue(plan['avertissements'])
        self.assertEqual(sum(n for _g, n in B['groupes']), len(B['tags']))


class TestFeu(unittest.TestCase):
    """Feu à 4 sorties : rouge, orange clignotant, orange fixe, vert."""
    def test_registres_4_sorties(self):
        plan = M.calculer_plan(charger('demo_site_B'))
        F3 = next(S for S in plan['stations'] if S['nom'] == 'B-F3')
        self.assertEqual([(c['adresse'], c['do']) for c in F3['commandes']],
                         [(403, [1]), (413, [2]), (423, [3]), (443, [4])])
        autres = sorted(r['adresse'] for r in plan['registres'] if r['type'] == 'Commande signalisation')
        self.assertEqual(autres, list(range(431, 438)))                       # autres signalisations : 431-440 (vert : 441-450)
        self.assertEqual(plan['stations'][0]['failsafe'][0], (401, 50))       # fail-safe 401-450

    def test_ancien_format(self):
        """Ancien fichier (do_orange) : lu comme orange clignotant, plan identique."""
        p = charger('demo_site_A'); anc = json.loads(json.dumps(p))
        for r in anc['radios']:
            for x in r['peripheriques']:
                if x['type'] == 'FEU':
                    x['do_orange'] = x.pop('do_orange_cli'); x.pop('do_orange_fixe')
        self.assertEqual(resume(M.calculer_plan(anc)), resume(M.calculer_plan(p)))
        self.assertIsNone(M.classer_modification(anc, p))                     # pas une modification
        q = M.normaliser_projet(anc)
        f = next(x for r in q['radios'] for x in r['peripheriques'] if x['type'] == 'FEU')
        self.assertNotIn('do_orange', f); self.assertEqual(f['do_orange_cli'], 2); self.assertIsNone(f['do_orange_fixe'])

    def test_validation_feu(self):
        def feu(**do):
            p = charger('demo_site_A'); f = next(x for x in p['radios'][4]['peripheriques'] if x['type'] == 'FEU')
            f.update(do_rouge=1, do_orange_cli=None, do_orange_fixe=None, do_vert=None); f.update(do)
            return [e for e in M.valider(p) if 'feu' in e]
        self.assertEqual(feu(do_orange_cli=2), [])
        self.assertEqual(feu(do_orange_fixe=2), [])                            # orange fixe seul : accepté
        self.assertEqual(feu(do_orange_cli=2, do_orange_fixe=4, do_vert=5), [])
        self.assertTrue(feu())                                                 # aucun orange : refusé
        self.assertTrue(feu(do_rouge=None, do_orange_cli=2))                   # pas de rouge : refusé

    def test_base_tous_peripheriques(self):
        """La base accepte tous les périphériques, radar compris (copie locale, sans IO Plus)."""
        p = charger('demo_site_B')
        p['radios'][0]['peripheriques'].append({'type': 'RADAR', 'nom': 'RADAR_B', 'ai': 1, 'seuil_haut_ma': 12.0})
        self.assertEqual(M.valider(p), [])
        plan = M.calculer_plan(p); B = plan['stations'][0]
        dftl = next(m for m in B['scatters'] if m['nom'].endswith('-DFTL'))
        self.assertIn((30001, 35201), dftl['paires'])
        self.assertEqual(B['noms_io']['Ain1'], 'RADAR_B')
        self.assertTrue(all(l[4] not in (501, 502) for l in B['iop']))          # pas de bloc radar IO Plus sur la base

    def test_ajout_sortie_feu_mineure(self):
        p = charger('demo_site_A'); q = json.loads(json.dumps(p))
        next(x for x in q['radios'][4]['peripheriques'] if x['type'] == 'FEU')['do_vert'] = 6
        self.assertEqual(M.classer_modification(p, q), 'mineure')


if __name__ == '__main__':
    unittest.main()
