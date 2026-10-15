# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""
Vues prêtes à afficher, calculées à partir du plan (elpro_engine.calculer_plan).
- vue_page2(plan)      -> arbre de pages façon CConfig (lecture seule)
- donnees_excel(plan)  -> 3 onglets (colonnes + lignes)
- donnees_pdf(plan)    -> sections du compte rendu
L'interface ne fait QUE afficher ces structures. Aucune règle métier ici côté UI.
"""
from elpro_engine import OP, CRENEAU_S

NOM_OP = {v: k for k, v in OP.items()}
ROLE_FR = {'base': 'Base', 'repeater': 'Repeater', 'remote': 'Remote'}
SERIE_MODE = {0: 'None'}
MASQUE = '255.255.255.0'


def hms(s):
    if not s:
        return 'Disabled'
    return f'{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}'


def hms0(s):
    return f'{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}'


def _nom_reg(S, plan, adr):
    """Nom d'un registre vu depuis la station S (comme CConfig affiche les noms)."""
    for a, n in S['noms_registres']:
        if a == adr:
            return f'{adr} {n}'
    return str(adr)


def _dest(plan, d):
    if d == 'local':
        return 'Cette unité (127.0.0.1)'
    for X in plan['stations']:
        if X['uid'] == d:
            return X['nom']
    return d


def _ack(S):
    return [('Tx Ack Count', S['ack'][0]), ('Tx Ack Timeout (ms)', S['ack'][1]), ('Tx Un Ack Count', 1)]


def vue_page2(plan):
    """Retourne une liste de nœuds : {'chemin': [..], 'type': 'formulaire'|'tables', 'contenu': ...}
    formulaire : contenu = [(libellé, valeur), ...]
    tables     : contenu = [{'titre': str, 'colonnes': [..], 'lignes': [[..], ..]}, ...]"""
    s = plan['systeme']
    st = plan['stations']
    N = []
    N.append({'chemin': [s['nom_projet']], 'type': 'formulaire', 'contenu': [
        ('Nom du projet', s['nom_projet']), ('Version de configuration', plan['version_config']),
        ('System Name', s['system_name']), ('Généré le', plan['genere_le']),
        ('Cycle de polling', f"{plan['T']} s ({len(plan['creneaux'])} créneaux de {CRENEAU_S} s)")]})
    N.append({'chemin': [s['nom_projet'], 'IP Address List'], 'type': 'tables', 'contenu': [{
        'titre': 'IP Address List', 'colonnes': ['Name', 'IP Address', 'Network Address', 'Subnet Mask'],
        'lignes': [[X['nom'], X['ip'], '192.168.1.0', MASQUE] for X in st]}]})
    for S in st:
        racine = [s['nom_projet'], 'Units', S['nom']]
        base = S['role'] == 'base'
        ips = sorted(int(X['ip'].rsplit('.', 1)[1]) for X in st)
        N.append({'chemin': racine, 'type': 'formulaire', 'contenu': [
            ('System Name', s['system_name']), ('Device Name', S['nom']), ('Device Model', '415U-2 C4'),
            ('Networking Mode', 'Fixed Links'), ('Device Mode', ROLE_FR[S['role']]),
            ('Upstream Device Name', S['amont'] or '—'), ('Radio Encryption', 'AES 256 bit'),
            ('Encryption Passphrase', s['cle_chiffrement']), ('Modulation', 'High Speed mode (QAM)'),
            ('Bandwidth (kHz)', 25), ('Transmit Power Level (dBm)', S['puissance_dbm']),
            ('Tx Frequency (MHz)', '433.925'), ('Rx Frequency (MHz)', '433.925'),
            ('IP Address', S['ip']), ('IP Network Mask', MASQUE), ('Default Gateway', '192.168.1.1'),
            ('Easy Filter', 'Activé'), ('First Radio/device IP', f'192.168.1.{ips[0]}'),
            ('Last Radio/device IP', f'192.168.1.{ips[-1]}'), ('Remote Access', 'Activé'),
            ('Index station (xx)', S['xx']), ('Unit ID CConfig', S['uid'])]})
        lignes = []
        for i, m in enumerate(S['reads'], 1):
            lignes.append([i, 'Read', '✔', m['nom'], _dest(plan, m['dest']), _nom_reg(S, plan, m['local']), m['distant'],
                           m['nb'], 'Oui' if m['inv'] else '', hms(m['periode']), hms(m['offset']), 'Disabled', _nom_reg(S, plan, m['fail'])])
        for i, m in enumerate(S['scatters'], 1):
            lignes.append([i, 'Gather/Scatter', '✔', m['nom'], _dest(plan, m['dest']),
                           ' ; '.join(f'{a}→{b}' for a, b in m['paires']), '', len(m['paires']),
                           'Oui' if m['inv'] else '', hms(m['periode']), hms(m['offset']), 'Disabled',
                           _nom_reg(S, plan, m['fail']) if m['fail'] else 'Disabled'])
        for i, m in enumerate(S['writes'], 1):
            lignes.append([i, 'Write', '✔', m['nom'], _dest(plan, m['dest']), m['local'], m['distant'], m['nb'],
                           'Oui' if m['inv'] else '', 'Disabled', 'Disabled', m['force'] or 'Disabled', 'Disabled'])
        N.append({'chemin': racine + ['Mappings'], 'type': 'tables', 'contenu': [
            {'titre': 'Mappings', 'colonnes': ['#', 'Type', 'Ena', 'Name', 'Destination', 'First Local Reg', 'First Remote Reg',
                                              'Reg Count', 'Inv', 'Update Time', 'Update Offset', 'Force Reg', 'Fail Reg'],
             'lignes': lignes},
            {'titre': 'Advanced', 'colonnes': ['Paramètre', 'Valeur'], 'lignes': [list(x) for x in _ack(S)]}]})
        N.append({'chemin': racine + ['Networking'], 'type': 'formulaire', 'contenu': [
            ('Network Mode', 'Bridge'), ('IP Address', S['ip']), ('IP Network Mask', MASQUE),
            ('Default Gateway', '192.168.1.1'), ('Primary DNS', '8.8.8.8'), ('Secondary DNS', '8.8.4.4')]})
        N.append({'chemin': racine + ['Networking', 'Time Server'], 'type': 'formulaire', 'contenu': [
            ('NTP Enabled', 'Oui'), ('NTP Server Address', '195.176.26.204')]})
        N.append({'chemin': racine + ['RS232'], 'type': 'formulaire', 'contenu': [
            ('Operating Mode', 'None (mode 0)'), ('Baud Rate (code)', 11 if base else 6)]})
        N.append({'chemin': racine + ['RS485'], 'type': 'formulaire', 'contenu': [
            ('Operating Mode', 'None (mode 0)'), ('Baud Rate (code)', 9 if base else 6)]})
        N.append({'chemin': racine + ['Modbus'], 'type': 'formulaire', 'contenu': [
            ('Modbus TCP Server Enabled', 'Oui' if base else 'Non'), ('Device ID', 1)]})
        N.append({'chemin': racine + ['IO'], 'type': 'tables', 'contenu': [
            {'titre': 'I/O Register Name Configuration', 'colonnes': ['#', 'Name', 'Address'],
             'lignes': [[i, n, a] for i, (a, n) in enumerate(S['noms_registres'], 1)]}]})
        din = [[i, S['noms_io'].get(f'Din{i}', 'MAINV' if i == 8 and S['mainv'] else f'DI{i}'),
                S['debounce'].get(f'Din{i}', 0.5), 10000 + i] for i in range(1, 9)]
        N.append({'chemin': racine + ['IO', 'Digital Inputs'], 'type': 'tables', 'contenu': [
            {'titre': 'Digital Inputs', 'colonnes': ['#', 'Name', 'Debounce Time (Sec)', 'Address'], 'lignes': din}]})
        dout = [[i, S['noms_io'].get(f'Dot{i}', f'DO{i}'), 'Disabled', 'OFF', i] for i in range(1, 9)]
        N.append({'chemin': racine + ['IO', 'Digital Outputs'], 'type': 'tables', 'contenu': [
            {'titre': 'Digital Outputs', 'colonnes': ['#', 'Name', 'Fail-Safe Time (Sec)', 'Fail-Safe State', 'Address'], 'lignes': dout}]})
        ain = [[i, S['noms_io'].get(f'Ain{i}', f'AI{i} (0-20mA)'), 30000 + i] for i in range(1, 5)]
        N.append({'chemin': racine + ['IO', 'Analogue Inputs'], 'type': 'tables', 'contenu': [
            {'titre': 'Analogue Inputs (4-20 mA)', 'colonnes': ['#', 'Name', 'Address'], 'lignes': ain}]})
        N.append({'chemin': racine + ['Fail Safe Blocks'], 'type': 'tables', 'contenu': [
            {'titre': 'Fail Safe Blocks', 'colonnes': ['#', 'First Register', 'Count', 'Update Time', 'Startup Value', 'Fail Value'],
             'lignes': [[i, _nom_reg(S, plan, a), c, 0, 'OFF', 'OFF'] for i, (a, c) in enumerate(S['failsafe'], 1)]}]})
        sens = S['sensibilite'] or [(30001, 12, 1000), (38001, 24, 0.5)]
        N.append({'chemin': racine + ['Sensitivity Blocks'], 'type': 'tables', 'contenu': [
            {'titre': 'Sensitivity Blocks', 'colonnes': ['#', 'First Register', 'Count', 'Sensitivity'],
             'lignes': [[i, a, c, v] for i, (a, c, v) in enumerate(sens, 1)]}]})
        N.append({'chemin': racine + ['Unit Details'], 'type': 'formulaire', 'contenu': [
            ('Owner', s.get('proprietaire', '')), ('Contact', s.get('contact', '')),
            ('Description', S['description']), ('Location', s.get('localisation', ''))]})
        N.append({'chemin': racine + ['Dashboard'], 'type': 'tables', 'contenu': [
            {'titre': f"Dashboard Tags — Page Title : {S['titre_page']}",
             'colonnes': ['#', 'Name', 'Register', 'Units', 'Over Range', 'Under Range', 'High Alarm', 'Low Alarm',
                          'Invert', 'Register Pt1', 'Register Pt2', 'Display Pt1', 'Display Pt2'],
             'lignes': [[i, t['nom'], t['registre'], t['unites'], t['over'], t['under'], t['haut'], t['bas'],
                         'Oui' if t['invert'] else '', t['rp1'], t['rp2'], t['dp1'], t['dp2']]
                        for i, t in enumerate(S['tags'], 1)]},
            {'titre': 'Dashboard Groups', 'colonnes': ['#', 'Name', 'Count'],
             'lignes': [[i, n, c] for i, (n, c) in enumerate(S['groupes'], 1)]}]})
        if S['iop']:
            N.append({'chemin': racine + ['IO Plus'], 'type': 'tables', 'contenu': [
                {'titre': 'IO Plus (livré désactivé)', 'colonnes': ['Ligne', 'Operation', 'I', 'N', 'Value/Register', 'Notes'],
                 'lignes': [[i, NOM_OP[l[0]], '✔' if l[1] else '', '✔' if l[2] else '', l[4], l[5]]
                            for i, l in enumerate(S['iop'], 1)]}]})
    return N


def _cablage(S, plan):
    """20 lignes : DI1-8, DO1-8, AI1-4 avec le périphérique branché."""
    di, do, ai = {}, {}, {}
    if S['mainv']:
        di[S['mainv'].get('di', 8)] = ('MAINV', 'Secteur', int(f"105{S['xx']}"))
    for d in S['detections']:
        if d['label']:
            di[d['di']] = (d['label'], d['type'], d['adresse'])
    for c in S['commandes']:
        for o in c['do']:
            do[o] = (c['label'], 'Commande', c['adresse'])
    for R in S['radars']:
        ai[R['ai']] = (R['label'], 'RADAR', R['adresse'])
    L = []
    for i in range(1, 9):
        p = di.get(i); L.append([S['nom'], f'DI{i}', *(p if p else ('libre', '', '')), 'Oui' if p and S['inv_entrees'] and p[1] != 'Secteur' else ''])
    for i in range(1, 9):
        p = do.get(i); L.append([S['nom'], f'DO{i}', *(p if p else ('libre', '', '')), 'Oui' if p and S['inv_sorties'] else ''])
    for i in range(1, 5):
        p = ai.get(i); L.append([S['nom'], f'AI{i}', *(p if p else ('libre', '', '')), ''])
    return L


def donnees_excel(plan):
    st = plan['stations']
    return [
        {'onglet': 'Registres base', 'colonnes': ['Adresse', 'Nom', 'Type', 'Station', 'Description'],
         'largeurs': [10, 34, 28, 16, 40],
         'lignes': [[r['adresse'], r['nom'], r['type'], r['station'], r['description']] for r in plan['registres']]},
        {'onglet': 'Radios', 'colonnes': ['Index', 'Nom', 'Rôle', 'Adresse IP', 'Amont', 'Puissance (dBm)', 'MAINV', 'Titre de page'],
         'largeurs': [7, 18, 11, 15, 18, 15, 10, 30],
         'lignes': [[S['xx'], S['nom'], ROLE_FR[S['role']], S['ip'], S['amont'], S['puissance_dbm'],
                     f"DI{S['mainv'].get('di', 8)}" if S['mainv'] else 'non', S['titre_page']] for S in st]},
        {'onglet': 'Câblage', 'colonnes': ['Radio', 'E/S', 'Périphérique', 'Type', 'Registre base', 'Inversé'],
         'largeurs': [16, 7, 22, 14, 14, 9],
         'lignes': [l for S in st for l in _cablage(S, plan)]},
    ]


def donnees_pdf(plan):
    s = plan['systeme']; st = plan['stations']
    sections = []
    sections.append({'titre': '1. Synthèse du système', 'blocs': [
        {'type': 'formulaire', 'contenu': [
            ('Projet', s['nom_projet']), ('Version de configuration', plan['version_config']), ('System Name', s['system_name']), ('Propriétaire', s.get('proprietaire', '')),
            ('Contact', s.get('contact', '')), ('Localisation', s.get('localisation', '')),
            ('Description', s.get('description', '')), ('Nombre de radios', len(st)),
            ('Fréquence', '433,925 MHz'), ('Largeur de canal', '25 kHz (Bandwidth 2)'),
            ('Puissance générale', f"{s.get('puissance_dbm', 34)} dBm"), ('Chiffrement', 'AES 256 bit'),
            ('NTP', '195.176.26.204'), ('Cycle de polling', f"{plan['T']} s ({len(plan['creneaux'])} créneaux de {CRENEAU_S} s)"),
            ('Généré le', plan['genere_le'])]},
        {'type': 'table', 'titre': 'Topologie', 'colonnes': ['Index', 'Radio', 'Rôle', 'IP', 'Amont', 'Puissance', 'IO Plus'],
         'lignes': [[S['xx'], S['nom'], ROLE_FR[S['role']], S['ip'], S['amont'] or '—', f"{S['puissance_dbm']} dBm",
                     f"{len(S['iop'])} lignes" if S['iop'] else '—'] for S in st]},
        {'type': 'table', 'titre': 'Grille de polling', 'colonnes': ['Créneau', 'Offset', 'Type', 'Mapping', 'Station', 'IP', 'FailReg'],
         'lignes': [[c['k'], hms0(c['offset']), c['type'], c['mapping'], c['station'], c['ip'], c['failreg']] for c in plan['creneaux']]},
    ]})
    blocs = []
    for S in st:
        blocs.append({'type': 'sous_titre', 'texte': f"{S['nom']} — {ROLE_FR[S['role']]} — {S['ip']}"})
        blocs.append({'type': 'formulaire', 'contenu': [
            ('Index station', S['xx']), ('Amont', S['amont'] or '—'), ('Puissance', f"{S['puissance_dbm']} dBm"),
            ('Accusés radio', f"{S['ack'][0]} × {S['ack'][1]} ms"), ('Inversion entrées / sorties',
            f"{'oui' if S['inv_entrees'] else 'non'} / {'oui' if S['inv_sorties'] else 'non'}"),
            ('MAINV', f"DI{S['mainv'].get('di', 8)}" if S['mainv'] else 'non'),
            ('IO Plus', f"{len(S['iop'])} lignes, livré désactivé" if S['iop'] else 'aucun')]})
        blocs.append({'type': 'table', 'titre': 'Câblage', 'colonnes': ['E/S', 'Périphérique', 'Type', 'Registre base', 'Inversé'],
                      'lignes': [l[1:] for l in _cablage(S, plan) if l[2] != 'libre']})
        maps = ([['Read', m['nom'], _dest(plan, m['dest']), m['local'], m['distant'], m['nb'], hms0(m['offset']), m['fail']] for m in S['reads']] +
                [['Scatter', m['nom'], _dest(plan, m['dest']), ' ; '.join(f'{a} -> {b}' for a, b in m['paires']), '', len(m['paires']),
                  hms0(m['offset']) if m['periode'] else 'COS', m['fail'] or '—'] for m in S['scatters']] +
                [['Write', m['nom'], _dest(plan, m['dest']), m['local'], m['distant'], m['nb'],
                  'COS' if m['cos'] else f"Force {m['force']}", '—'] for m in S['writes']])
        if maps:
            blocs.append({'type': 'table', 'titre': 'Mappings', 'colonnes': ['Type', 'Nom', 'Destination', 'Local', 'Distant', 'Nb', 'Offset/Mode', 'FailReg'],
                          'lignes': maps})
    sections.append({'titre': '2. Détail par radio', 'blocs': blocs})
    sections.append({'titre': '3. Plan de registres de la base', 'blocs': [
        {'type': 'table', 'titre': '', 'colonnes': ['Adresse', 'Nom', 'Type', 'Station', 'Description'],
         'lignes': [[r['adresse'], r['nom'], r['type'], r['station'], r['description']] for r in plan['registres']]}]})
    ck = [f"Programmer les {len(st)} radios avec le .cdb (toutes dans la même intervention).",
          'Contrôler la CfgVersion de chaque radio après programmation.',
          f"Importer IO Plus sur {st[0]['nom']} (System Tools → Write Configuration File), puis l'activer.",
          f"Vérifier le registre 30491 = 256 sur {st[0]['nom']}."]
    for S in st[1:]:
        if S['iop']:
            ck += [f"Importer et activer IO Plus sur {S['nom']} (radar), vérifier 30491 = 256."]
    for S in st[1:]:
        ck.append(f"{S['nom']} : couper la radio → comflag 151{S['xx']} = 1 en moins de {plan['T'] + 30} s, puis retour à 0 après rétablissement.")
        for d in S['detections']:
            if d['label']: ck.append(f"{S['nom']} : déclencher {d['label']} (DI{d['di']}) → {d['adresse']} change (vérifier le sens).")
        for c in S['commandes']: ck.append(f"{S['nom']} : écrire 1 puis 0 dans {c['adresse']} → {c['label']} (DO{'+DO'.join(map(str, c['do']))}).")
        for R in S['radars']:
            ck.append(f"{S['nom']} : faire varier AI{R['ai']} (générateur 4-20 mA) → {R['adresse']} suit, 1 envoi max toutes les {R['tmin_s']} s.")
            ck.append(f"{S['nom']} : franchir {R['seuil_haut_ma']} mA puis {R['seuil_haut_ma'] - R['hysteresis_ma']:.1f} mA → envoi immédiat à chaque franchissement.")
        if S['mainv']: ck.append(f"{S['nom']} : couper le secteur → 105{S['xx']} change.")
    B = st[0]
    for d in B['detections']:
        if d['label']: ck.append(f"{B['nom']} : déclencher {d['label']} (DI{d['di']}) → {d['adresse']} change.")
    for c in B['commandes']: ck.append(f"{B['nom']} : écrire 1 puis 0 dans {c['adresse']} → {c['label']}.")
    ck.append(f"Redémarrer {B['nom']} : tous les comflags et registres d'échec repartent à 0, 10501/30501/35101 se remplissent.")
    sections.append({'titre': '4. Checklist de mise en service', 'blocs': [{'type': 'checklist', 'items': ck}]})
    return sections
