# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""
Génère des fichiers .log FICTIFS, au format exact des centrales ELPRO (gzip -> tar -> data.csv),
pour les projets de démonstration. Sert aux tests et à la recette : aucune donnée réelle.

Usage : python tools/make_demo_logs.py examples/demo_site_B.json examples/logs 3
        (3 = nombre de jours ; un fichier de 2880 lignes par jour, une ligne toutes les 30 s)
"""
import os, sys, io, gzip, json, math, random, tarfile, hashlib, datetime

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ICI, '..', 'engine'))
import elpro_engine as M
import elpro_logs as L

PAS = 30
LIGNES = 2880


def colonnes_standard():
    cols = []
    for nom, premier, n in L.LISTE_STANDARD:
        cols += [(f'{nom}{i:02d}', premier + i - 1) for i in range(1, n + 1)]
    return cols


def simuler(projet, debut_utc, jours, graine=1):
    """Renvoie une liste de (t, {registre: valeur}) — valeurs telles que la centrale les aurait."""
    rnd = random.Random(graine)
    plan = M.calculer_plan(projet)
    T = plan['T']
    st = plan['stations']
    regs = {}
    # valeurs initiales
    for S in st:
        xx = S['xx']
        regs[int(f'305{xx}')] = 8192 + int(12.8 / 40 * 40960)
        if S['role'] != 'base':
            regs[int(f'351{xx}')] = rnd.randint(55, 85)
            regs[int(f'151{xx}')] = 0
        if S['mainv']:
            regs[int(f'105{xx}')] = 1
        for d in S['detections']:
            regs[d['adresse']] = 0
        for c in S['commandes']:
            regs[c['adresse']] = 0
        for R in S['radars']:
            regs[R['adresse']] = L.M.ma_vers_brut(6.0)
    # scénarios
    rem = [S for S in st if S['role'] != 'base']
    perte = rem[1 % len(rem)] if rem else None            # une station perd la comm 2 h le jour 1
    batt_faible = rem[-1] if rem else None                # batterie qui baisse le jour 2
    det = next((S for S in st if S['detections']), None)
    cmd = next((S for S in st if S['commandes']), None)
    radar = next((S for S in st if S['radars']), None)
    res = []
    t_fin = debut_utc + jours * 86400
    t = debut_utc
    while t < t_fin:
        h = (t - debut_utc) / 3600.0
        jour = int(h // 24)
        for k, S in enumerate(st):
            xx = S['xx']
            # mise à jour seulement au passage de la lecture de cette station (cycle T)
            if S['role'] != 'base' and (t // PAS) % max(1, T // PAS) != k % max(1, T // PAS):
                continue
            hors = perte is S and jour == 0 and 10 <= h % 24 < 12
            if S['role'] != 'base':
                for fam in ('151', '152', '153') + (('154',) if S['detections'] else ()) + \
                        (('155',) if S['commandes'] else ()) + (('156',) if S['mainv'] else ()) + \
                        (('157',) if S['radars'] else ()):
                    regs[int(f'{fam}{xx}')] = 1 if hors else 0
                if hors:
                    continue
            # batterie : cycle solaire, + baisse le jour 2 pour une station
            v = 12.6 + 0.8 * max(0.0, math.sin((h % 24 - 6) / 12 * math.pi)) + rnd.uniform(-0.03, 0.03)
            if batt_faible is S and jour == 1 and 14 <= h % 24 < 20:
                v = 11.2 + rnd.uniform(-0.05, 0.05)
            regs[int(f'305{xx}')] = 8192 + int(v / 40 * 40960)
            if S['role'] != 'base':
                regs[int(f'351{xx}')] = max(40, min(110, regs[int(f'351{xx}')] + rnd.choice((-2, -1, 0, 0, 1, 2))))
            if S['mainv']:
                regs[int(f'105{xx}')] = 0 if (jour == 0 and 3 <= h % 24 < 3.5) else 1
            if det is S:
                d0 = det['detections'][0]['adresse']
                regs[d0] = 1 if (jour == 0 and 15 <= h % 24 < 15.25) else 0
            if radar is S:
                R = radar['radars'][0]
                ma = 6.0 + 7.0 * max(0.0, math.sin((h - 30) / 10 * math.pi)) if 30 <= h < 40 else 6.0
                regs[R['adresse']] = M.ma_vers_brut(ma + rnd.uniform(-0.05, 0.05))
        if cmd:
            c0 = cmd['commandes'][0]['adresse']
            regs[c0] = 1 if (15.1 <= h < 15.6) else 0
        res.append((t, dict(regs)))
        t += PAS
    return res


def ecrire_log(lignes, serie, appareil, dossier):
    """Écrit un fichier .log au format radio. Renvoie le chemin."""
    cols = colonnes_standard()
    t0 = lignes[0][0]
    out = io.StringIO()
    out.write(f"TimeStamp: {datetime.datetime.utcfromtimestamp(t0):%Y-%m-%d %H:%M:%S}\n")
    out.write(f"Unit Serial Number: {serie}\n\n")
    out.write('Timestamp,' + ','.join(c for c, _ in cols) + ',\n')
    for t, regs in lignes:
        out.write(f"{datetime.datetime.utcfromtimestamp(t):%Y-%m-%d %H:%M:%S},"
                  + ','.join(str(regs.get(r, 0)) for _, r in cols) + ',\n')
    data = out.getvalue().encode('utf-8')
    tbuf = io.BytesIO()
    with tarfile.open(fileobj=tbuf, mode='w', format=tarfile.USTAR_FORMAT) as tar:
        for nom, contenu in (('data.csv', data), ('logfile.chk', hashlib.md5(data).hexdigest().encode() + b'\n')):
            ti = tarfile.TarInfo(nom); ti.size = len(contenu); ti.mtime = lignes[-1][0]; ti.mode = 0o666
            tar.addfile(ti, io.BytesIO(contenu))
    nom = f"{datetime.datetime.utcfromtimestamp(lignes[-1][0] + PAS):%Y%m%d%H%M%S}-{appareil}-DAT.log"
    chemin = os.path.join(dossier, nom)
    with open(chemin, 'wb') as f:
        f.write(gzip.compress(tbuf.getvalue(), 9))
    return chemin


def generer(chemin_projet, dossier, jours=3, debut='2026-10-01 00:00:00', serie='99000000001'):
    projet = json.load(open(chemin_projet, encoding='utf-8'))
    debut_utc = L.utc_depuis_texte(debut)
    lignes = simuler(projet, debut_utc, jours)
    appareil = M.calculer_plan(projet)['stations'][0]['nom']
    os.makedirs(dossier, exist_ok=True)
    return [ecrire_log(lignes[i:i + LIGNES], serie, appareil, dossier) for i in range(0, len(lignes), LIGNES)]


if __name__ == '__main__':
    p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ICI, '..', 'examples', 'demo_site_B.json')
    d = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ICI, '..', 'examples', 'logs')
    j = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    for c in generer(p, d, j):
        print(c)
