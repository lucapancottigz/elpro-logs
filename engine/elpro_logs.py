# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""
Moteur ELPRO Logs (v1.1) — IMPLÉMENTATION DE RÉFÉRENCE.

Rôle :
  1. lire les fichiers de log (DataLog) des centrales ELPRO 415U-2-C4 ;
  2. les rattacher au système décrit par son .elpro.json (produit par ELPRO Config) ;
  3. stocker toutes les valeurs dans une base unique, compacte, persistante ;
  4. fournir à l'interface les données prêtes à afficher : catalogue des stations,
     segments de valeurs, état global, synthèse, journal d'événements.

Format du fichier .log (constaté sur radio, firmware 2.59) :
  gzip -> tar -> data.csv + logfile.chk
  data.csv : « TimeStamp: AAAA-MM-JJ hh:mm:ss », « Unit Serial Number: n », ligne vide,
             en-tête « Timestamp,<NOM><nn>,…, » puis une ligne par enregistrement.
  Horodatages en UTC. Colonne <NOM><nn> = registre (premier registre de l'entrée NOM) + nn - 1.

Stockage : SQLite (un seul fichier pour tous les systèmes).
  Seuls les CHANGEMENTS de valeur sont stockés, plus la valeur de chaque registre au début
  de chaque plage continue de données. Les points sont regroupés par registre et par mois
  (table « blocs »), codés en varint différentiel puis compressés (zlib). La table « couverture » indique les plages où des
  données existent (hors couverture = « pas de données », jamais « valeur inchangée »).

Python 3.10+, bibliothèque standard uniquement (+ elpro_engine.py, copie de ELPRO Config).
Toutes les heures manipulées par le moteur sont des secondes UTC (epoch, entiers).
"""
import os, io, re, gzip, json, zlib, sqlite3, tarfile, zipfile, hashlib, datetime, threading

import elpro_engine as M

FORMAT_BASE = 1
COPYRIGHT = M.COPYRIGHT

# --------------------------------------------------------------------------------------------
# Profil de log : nom d'entrée DataLog -> premier registre.
# Liste standard GeoAzimut (identique sur toutes les centrales) + alias usuels.
# --------------------------------------------------------------------------------------------
PROFIL_STANDARD = {
    'COMFLAGS': 15101, 'COMFLAG': 15101,
    'BATTV_FAIL': 15201, 'RSSI_FAIL': 15301,
    'DET_FAIL': 15401, 'CABLE_FAIL': 15401,
    'FEUX_FAIL': 15501, 'SGNL_FAIL': 15501,
    'MAINV_FAIL': 15601, 'RADAR_FAIL': 15701,
    'BATTV': 30501, 'RSSI': 35101,
    'DET': 15001, 'CABLE': 15001, 'DETECTION': 15001,
    'DET2': 15021, 'CABLE2': 15021, 'DETECTION2': 15021,
    'FEUX': 401, 'CMD_401': 401, 'FEUX2': 421, 'CMD_421': 421, 'FEUX3': 441, 'CMD_441': 441,
    'MAINV': 10501, 'RADAR': 35201,
}
# Entrées standard (pour l'aide affichée dans l'app) : nom, premier registre, nombre
LISTE_STANDARD = [('COMFLAGS', 15101, 20), ('BATTV_FAIL', 15201, 20), ('RSSI_FAIL', 15301, 20),
                  ('DET_FAIL', 15401, 20), ('FEUX_FAIL', 15501, 20), ('MAINV_FAIL', 15601, 20),
                  ('BATTV', 30501, 20), ('RSSI', 35101, 20), ('DET', 15001, 20), ('FEUX', 401, 20),
                  ('MAINV', 10501, 20), ('CABLE2', 15021, 20), ('RADAR', 35201, 20), ('FEUX2', 421, 20),
                  ('FEUX3', 441, 10), ('RADAR_FAIL', 15701, 20)]
REGLAGES_STANDARD = {'Scan Rate': 30, 'Records per File': 2880}

RE_COLONNE = re.compile(r'^(.*)(\d{2})$')    # CABLE201 -> CABLE2 + 01

# --------------------------------------------------------------------------------------------
# Genres de canaux, décodage et seuils
# --------------------------------------------------------------------------------------------
GENRES = {
    # genre: (libellé, unité, binaire)
    'COMFLAG':    ('Perte de communication', '', True),
    'BATTV':      ('Tension batterie', 'V', False),
    'RSSI':       ('RSSI', 'dBm', False),
    'MAINV':      ('Secteur présent', '', True),
    'DETECTION':  ('Détection', '', True),
    'COMMANDE':   ('Commande', '', True),
    'RADAR':      ('Radar', '', False),       # unité selon l'échelle du radar
    'FAIL_BATTV': ('Échec lecture batterie', '', True),
    'FAIL_RSSI':  ('Échec lecture RSSI', '', True),
    'FAIL_DET':   ('Échec lecture détections', '', True),
    'FAIL_SGNL':  ('Échec envoi commandes', '', True),
    'FAIL_MAINV': ('Échec lecture secteur', '', True),
    'FAIL_RADAR': ('Échec lecture radar', '', True),
    'AUTRE':      ('Registre non attribué', '', False),
}
# Familles affichées dans l'interface (filtre « type de donnée »)
FAMILLES = [
    ('COMM', 'Communication', ('COMFLAG',)),
    ('ECHECS', 'Échecs de lecture/envoi', ('FAIL_BATTV', 'FAIL_RSSI', 'FAIL_DET', 'FAIL_SGNL', 'FAIL_MAINV', 'FAIL_RADAR')),
    ('BATTERIE', 'Batteries', ('BATTV',)),
    ('RSSI', 'RSSI', ('RSSI',)),
    ('SECTEUR', 'Secteur (MAINV)', ('MAINV',)),
    ('DETECTIONS', 'Détections', ('DETECTION',)),
    ('COMMANDES', 'Commandes', ('COMMANDE',)),
    ('RADARS', 'Radars', ('RADAR',)),
    ('AUTRES', 'Registres non attribués', ('AUTRE',)),
]
FAIL_FAMILLES = (('152', 'FAIL_BATTV'), ('153', 'FAIL_RSSI'), ('154', 'FAIL_DET'),
                 ('155', 'FAIL_SGNL'), ('156', 'FAIL_MAINV'), ('157', 'FAIL_RADAR'))

BATTV_BAS = 11.5        # V, même seuil que le tableau de bord radio
BATTV_HAUT = 14.5
RSSI_FAIBLE = -95       # dBm

# États de la vue globale, du plus grave au moins grave (l'ordre sert de priorité)
ETATS = ['SANS_DONNEES', 'COMM_PERDUE', 'DEGRADE', 'ALERTE', 'OK']
LIBELLES_ETATS = {
    'SANS_DONNEES': 'Pas de données',
    'COMM_PERDUE': 'Communication perdue (comflag)',
    'DEGRADE': 'Lecture ou envoi en échec',
    'ALERTE': 'Batterie basse ou secteur absent',
    'OK': 'OK',
}
COULEURS_ETATS = {'SANS_DONNEES': '#B0B0B0', 'COMM_PERDUE': '#D32F2F', 'DEGRADE': '#F57C00',
                  'ALERTE': '#FBC02D', 'OK': '#388E3C'}


def battv_volts(brut):
    """8192 = 0 V, 49152 = 40 V. Valeur < 8192 (jamais lue) -> None."""
    if brut is None or brut < 8192:
        return None
    return round((brut - 8192) * 40.0 / 40960.0, 2)


def rssi_dbm(brut):
    """Registre 0..150 = 0..-150 dBm. 0 = jamais lu -> None."""
    if not brut:
        return None
    return -int(brut)


def radar_ma(brut):
    """16384 = 4 mA, 49152 = 20 mA. 0 = jamais lu -> None."""
    if not brut:
        return None
    return round(4.0 + (brut - 16384) / 2048.0, 3)


def decoder(canal, brut):
    """Valeur brute du registre -> valeur affichée (float, int ou None)."""
    g = canal['genre']
    if brut is None:
        return None
    if g == 'BATTV':
        return battv_volts(brut)
    if g == 'RSSI':
        return rssi_dbm(brut)
    if g == 'RADAR':
        ma = radar_ma(brut)
        if ma is None:
            return None
        R = canal.get('radar')
        if R and R.get('mesure_20ma') is not None:
            return round(M.ma_vers_unite(ma, R), 1)
        return ma
    if GENRES[g][2]:
        return 1 if brut else 0
    return brut


# --------------------------------------------------------------------------------------------
# Heure
# --------------------------------------------------------------------------------------------
def utc_depuis_texte(txt):
    d = datetime.datetime.strptime(txt.strip(), '%Y-%m-%d %H:%M:%S')
    return int(d.replace(tzinfo=datetime.timezone.utc).timestamp())


def _zone():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo('Europe/Zurich')   # sous Windows : paquet « tzdata » requis
    except Exception:
        return None


ZONE = _zone()


def heure_locale(t, fmt='%d.%m.%Y %H:%M:%S'):
    """Seconde UTC -> texte en heure suisse (été/hiver gérés)."""
    d = datetime.datetime.fromtimestamp(t, datetime.timezone.utc)
    if ZONE:
        d = d.astimezone(ZONE)
    return d.strftime(fmt)


def utc_depuis_locale(annee, mois, jour, h=0, mi=0, s=0):
    """Date/heure suisse -> seconde UTC (pour les sélecteurs de période)."""
    d = datetime.datetime(annee, mois, jour, h, mi, s, tzinfo=ZONE or datetime.timezone.utc)
    return int(d.timestamp())


JOURS_DEFAUT = 6           # période affichée par défaut : 6 jours en arrière + le jour actuel


def periode_defaut(maintenant_utc=None, jours=JOURS_DEFAUT):
    """(t0, t1) : de 00:00 (heure suisse) il y a `jours` jours jusqu'à maintenant."""
    t1 = maintenant_utc if maintenant_utc is not None else int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    d = datetime.datetime.fromtimestamp(t1, datetime.timezone.utc)
    if ZONE:
        d = d.astimezone(ZONE)
    j = d.date() - datetime.timedelta(days=jours)
    return utc_depuis_locale(j.year, j.month, j.day), t1


JOURS_DEFAUT = 6           # période par défaut : le jour actuel + 6 jours en arrière


def debut_jour_local(t, decalage_jours=0):
    """Minuit (heure suisse) du jour de t, décalé de `decalage_jours` jours -> seconde UTC."""
    d = datetime.datetime.fromtimestamp(t, datetime.timezone.utc)
    if ZONE:
        d = d.astimezone(ZONE)
    j = d.date() + datetime.timedelta(days=decalage_jours)
    return utc_depuis_locale(j.year, j.month, j.day)


def reculer_jours(t, jours):
    """Recule de n jours calendaires en heure suisse (même heure affichée, changement d'heure compris)."""
    d = datetime.datetime.fromtimestamp(t, datetime.timezone.utc)
    if ZONE:
        loc = d.astimezone(ZONE).replace(tzinfo=None) - datetime.timedelta(days=jours)
        return int(loc.replace(tzinfo=ZONE).timestamp())
    return int((d - datetime.timedelta(days=jours)).timestamp())


def duree_texte(s):
    s = int(round(s))
    j, s = divmod(s, 86400); h, s = divmod(s, 3600); m, s = divmod(s, 60)
    if j:
        return f'{j} j {h} h {m:02d} min'
    if h:
        return f'{h} h {m:02d} min'
    if m:
        return f'{m} min {s:02d} s'
    return f'{s} s'


# --------------------------------------------------------------------------------------------
# Lecture des fichiers .log
# --------------------------------------------------------------------------------------------
class ErreurLog(Exception):
    pass


def _csv_depuis_octets(octets, nom):
    """Renvoie [(nom, texte_csv)] à partir du contenu d'un fichier (gzip/tar/zip/csv)."""
    if octets[:2] == b'\x1f\x8b':
        try:
            octets = gzip.decompress(octets)
        except Exception as e:
            raise ErreurLog(f'{nom} : archive compressée illisible ({e}).')
    if len(octets) > 262 and octets[257:262] == b'ustar':
        with tarfile.open(fileobj=io.BytesIO(octets)) as tar:
            for m in tar.getmembers():
                if m.isfile() and m.name.lower().endswith('.csv'):
                    return [(nom, tar.extractfile(m).read().decode('utf-8', 'replace'))]
        raise ErreurLog(f'{nom} : aucun data.csv dans le fichier.')
    if octets[:2] == b'PK':
        res = []
        with zipfile.ZipFile(io.BytesIO(octets)) as z:
            for n in z.namelist():
                if n.endswith('/'):
                    continue
                if n.lower().endswith(('.log', '.csv', '.gz', '.tar')):
                    res += _csv_depuis_octets(z.read(n), os.path.basename(n))
        if not res:
            raise ErreurLog(f'{nom} : aucun fichier de log dans le zip.')
        return res
    txt = octets.decode('utf-8', 'replace')
    if 'Timestamp,' not in txt:
        raise ErreurLog(f'{nom} : ce n\'est pas un fichier de log ELPRO.')
    return [(nom, txt)]


def analyser_csv(texte, nom='data.csv'):
    """data.csv -> dict(nom, serie, colonnes, lignes=[(t, [valeurs])], empreinte)."""
    lignes = texte.splitlines()
    serie, i_ent = None, None
    for i, l in enumerate(lignes):
        if l.startswith('Unit Serial Number:'):
            serie = l.split(':', 1)[1].strip()
        if l.startswith('Timestamp,'):
            i_ent = i
            break
    if i_ent is None:
        raise ErreurLog(f'{nom} : en-tête « Timestamp » introuvable.')
    entete = lignes[i_ent].rstrip().rstrip(',').split(',')
    colonnes = [c.strip() for c in entete[1:]]
    data = []
    for l in lignes[i_ent + 1:]:
        l = l.strip()
        if not l:
            continue
        champs = l.rstrip(',').split(',')
        try:
            t = utc_depuis_texte(champs[0])
        except ValueError:
            continue                       # ligne tronquée (coupure pendant l'écriture)
        vals = []
        for c in champs[1:len(colonnes) + 1]:
            c = c.strip()
            try:
                vals.append(int(c))
            except ValueError:
                try:
                    vals.append(int(float(c)))
                except ValueError:
                    vals.append(None)
        vals += [None] * (len(colonnes) - len(vals))
        data.append((t, vals))
    data.sort(key=lambda x: x[0])
    empreinte = hashlib.sha256(texte.encode('utf-8')).hexdigest()
    return {'nom': nom, 'serie': serie, 'colonnes': colonnes, 'lignes': data, 'empreinte': empreinte}


def lire_fichier_log(chemin):
    """Un fichier (.log, .zip, .csv) -> liste de logs analysés."""
    with open(chemin, 'rb') as f:
        octets = f.read()
    return [analyser_csv(txt, n) for n, txt in _csv_depuis_octets(octets, os.path.basename(chemin))]


def lire_profil_xml(chemin_ou_texte):
    """Export XML de configuration de la radio -> {nom d'entrée: (premier registre, nombre)}.
    Sert uniquement pour des logs dont la liste n'est pas la liste standard."""
    import xml.etree.ElementTree as ET
    txt = chemin_ou_texte
    if os.path.exists(chemin_ou_texte):
        with open(chemin_ou_texte, 'rb') as f:
            txt = f.read().decode('utf-8', 'replace')
    racine = ET.fromstring(txt)
    profil = {}
    for g in racine.iter('group'):
        if g.get('name') == 'DataLog':
            for tab in g.iter('table'):
                if tab.get('name') == 'Records':
                    for tr in tab.findall('tr'):
                        v = [x.text or '' for x in tr.findall('val')]
                        if len(v) >= 4 and v[1].strip():
                            profil[v[1].strip()] = (int(v[2]), int(v[3]))
    if not profil:
        raise ErreurLog('Aucune liste de log (DataLog) dans ce fichier XML.')
    return profil


def resoudre_colonnes(colonnes, profil=None):
    """Colonnes du CSV -> (liste registre|None, avertissements).
    profil : {nom: premier registre} ou {nom: (premier, nombre)} ; défaut = PROFIL_STANDARD."""
    p = {}
    for k, v in (profil or PROFIL_STANDARD).items():
        p[k.upper()] = v[0] if isinstance(v, (tuple, list)) else v
    regs, inconnus, comptes = [], set(), {}
    for c in colonnes:
        m = RE_COLONNE.match(c)
        if not m or m.group(1).upper() not in p:
            regs.append(None)
            inconnus.add(m.group(1) if m else c)
            continue
        pref, n = m.group(1).upper(), int(m.group(2))
        comptes[pref] = comptes.get(pref, 0) + 1
        regs.append(p[pref] + n - 1)
    avert = []
    if inconnus:
        avert.append('Colonnes ignorées (nom inconnu) : ' + ', '.join(sorted(inconnus))
                     + '. Importez l\'export XML de la radio pour les rattacher.')
    if profil is None and comptes.get('MAINV') == 1:
        # ancienne liste de log : « MAINV <registre> × 1 », registre inconnu
        i = [k for k, c in enumerate(colonnes) if c.upper().startswith('MAINV') and RE_COLONNE.match(c)
             and RE_COLONNE.match(c).group(1).upper() == 'MAINV'][0]
        regs[i] = None
        avert.append('Une seule colonne MAINV : ancienne liste de log, registre incertain. Colonne ignorée '
                     '(importez l\'export XML de la radio pour la rattacher).')
    vus = {}
    for k, r in enumerate(regs):
        if r is not None:
            if r in vus:
                avert.append(f'Registre {r} présent deux fois ({colonnes[vus[r]]} et {colonnes[k]}) : '
                             f'seule la première colonne est gardée.')
                regs[k] = None
            else:
                vus[r] = k
    return regs, avert


# --------------------------------------------------------------------------------------------
# Catalogue : ce que signifie chaque registre pour un système donné
# --------------------------------------------------------------------------------------------
def catalogue(projet):
    """Projet .elpro.json -> dict(systeme, T, stations=[...], par_registre={reg: canal}).
    Chaque canal : registre, nom, libelle, genre, famille, station, unite, binaire, (radar)."""
    plan = M.calculer_plan(projet)
    fam_de = {g: f for f, _, gs in FAMILLES for g in gs}
    stations, par_reg = [], {}

    def canal(S, reg, genre, nom, libelle, unite=None, **extra):
        c = {'registre': reg, 'genre': genre, 'famille': fam_de[genre], 'nom': nom, 'libelle': libelle,
             'station': S['nom'], 'unite': GENRES[genre][1] if unite is None else unite,
             'binaire': GENRES[genre][2]}
        c.update(extra)
        par_reg[reg] = c
        return c

    for S in plan['stations']:
        xx = S['xx']
        cs = []
        if S['role'] != 'base':
            cs.append(canal(S, int(f'151{xx}'), 'COMFLAG', f"{S['nom']}_COMFLAG", 'Perte de communication'))
        cs.append(canal(S, int(f'305{xx}'), 'BATTV', f"{S['nom']}_BATTV", 'Tension batterie'))
        if S['role'] != 'base':
            cs.append(canal(S, int(f'351{xx}'), 'RSSI', f"{S['nom']}_RSSI", 'RSSI'))
        if S['mainv']:
            cs.append(canal(S, int(f'105{xx}'), 'MAINV', f"{S['nom']}_MAINV", 'Secteur présent'))
        for d in S['detections']:
            lib = (d['label'] or f"DI{d['di']} non câblée") + f" (DI{d['di']})"
            cs.append(canal(S, d['adresse'], 'DETECTION', d['nom'], lib, cablee=d['label'] is not None))
        for c in S['commandes']:
            cs.append(canal(S, c['adresse'], 'COMMANDE', c['nom'], c['label'] + ' (' + '+'.join(f'DO{x}' for x in c['do']) + ')',
                            sorte=c['genre']))
        for R in S['radars']:
            unite = R['unite'] if R.get('mesure_20ma') is not None else 'mA'
            seuil = R['seuil_haut_ma']
            if R.get('mesure_20ma') is not None:
                seuil = round(M.ma_vers_unite(seuil, R), 1)
            cs.append(canal(S, R['adresse'], 'RADAR', R['nom'], f"{R['label']} (AI{R['ai']})", unite=unite,
                            radar={'mesure_4ma': R.get('mesure_4ma'), 'mesure_20ma': R.get('mesure_20ma'),
                                   'unite': R.get('unite')},
                            seuil_haut=seuil))
        # registres d'échec (alimentés par les mappings de la base)
        if S['role'] != 'base':
            presents = {'FAIL_BATTV': True, 'FAIL_RSSI': True, 'FAIL_DET': bool(S['detections']),
                        'FAIL_SGNL': bool(S['commandes']), 'FAIL_MAINV': bool(S['mainv']),
                        'FAIL_RADAR': bool(S['radars'])}
            for fam, g in FAIL_FAMILLES:
                if presents[g]:
                    cs.append(canal(S, int(f'{fam}{xx}'), g, f"{S['nom']}_{g[5:]}_FAIL", GENRES[g][0]))
        elif S['commandes']:
            cs.append(canal(S, 15501, 'FAIL_SGNL', f"{S['nom']}_SGNL_FAIL", GENRES['FAIL_SGNL'][0]))
        stations.append({'nom': S['nom'], 'role': S['role'], 'xx': xx, 'ip': S['ip'], 'canaux': cs})
    return {'systeme': plan['systeme'], 'version_config': plan.get('version_config'), 'T': plan['T'],
            'stations': stations, 'par_registre': par_reg}


def canal_autre(reg):
    return {'registre': reg, 'genre': 'AUTRE', 'famille': 'AUTRES', 'nom': f'REG_{reg}',
            'libelle': f'Registre {reg} (non utilisé par la configuration)', 'station': None,
            'unite': '', 'binaire': False}


# --------------------------------------------------------------------------------------------
# Segments : outils de calcul
# Un segment = (debut, fin, valeur) ; fin exclue ; valeur brute (int) ou état (str).
# --------------------------------------------------------------------------------------------
def fusionner_intervalles(iv, tolerance=0):
    iv = sorted(iv)
    res = []
    for a, b in iv:
        if res and a <= res[-1][1] + tolerance:
            res[-1][1] = max(res[-1][1], b)
        else:
            res.append([a, b])
    return [tuple(x) for x in res]


def intersecter(segments, couverture):
    """Coupe des segments (triés) par les plages de couverture (triées, disjointes)."""
    res, j = [], 0
    for a, b, v in segments:
        while j < len(couverture) and couverture[j][1] <= a:
            j += 1
        k = j
        while k < len(couverture) and couverture[k][0] < b:
            ca, cb = couverture[k]
            res.append((max(a, ca), min(b, cb), v))
            k += 1
    return compacter(res)


def compacter(segments):
    res = []
    for a, b, v in segments:
        if b <= a:
            continue
        if res and res[-1][2] == v and res[-1][1] == a:
            res[-1] = (res[-1][0], b, v)
        else:
            res.append((a, b, v))
    return res


def combiner(listes, fonction, t0, t1):
    """Balayage de plusieurs listes de segments -> segments de fonction(valeurs).
    Une liste sans segment à un instant donne None pour cette liste."""
    bornes = {t0, t1}
    for L in listes:
        for a, b, _ in L:
            if t0 < a < t1: bornes.add(a)
            if t0 < b < t1: bornes.add(b)
    bornes = sorted(bornes)
    idx = [0] * len(listes)
    res = []
    for a, b in zip(bornes, bornes[1:]):
        vals = []
        for k, L in enumerate(listes):
            while idx[k] < len(L) and L[idx[k]][1] <= a:
                idx[k] += 1
            vals.append(L[idx[k]][2] if idx[k] < len(L) and L[idx[k]][0] <= a else None)
        res.append((a, b, fonction(vals)))
    return compacter(res)


def duree(segments, predicat=lambda v: True):
    return sum(b - a for a, b, v in segments if predicat(v))


# --------------------------------------------------------------------------------------------
# Magasin : la base de données (un fichier SQLite pour tous les systèmes)
# --------------------------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (cle TEXT PRIMARY KEY, valeur TEXT);
CREATE TABLE IF NOT EXISTS systemes (
    id INTEGER PRIMARY KEY, cle TEXT UNIQUE NOT NULL, nom TEXT NOT NULL, serie TEXT,
    ordre INTEGER DEFAULT 0, cree_le INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS configs (
    id INTEGER PRIMARY KEY, systeme_id INTEGER NOT NULL, version TEXT, valable_depuis INTEGER NOT NULL,
    importe_le INTEGER NOT NULL, json BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS acces (
    systeme_id INTEGER PRIMARY KEY, adresse TEXT, utilisateur TEXT, mdp BLOB,
    derniere_recuperation INTEGER, dernier_resultat TEXT);
CREATE TABLE IF NOT EXISTS profils (
    systeme_id INTEGER PRIMARY KEY, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS fichiers (
    id INTEGER PRIMARY KEY, systeme_id INTEGER NOT NULL, nom TEXT, empreinte TEXT NOT NULL, serie TEXT,
    t_debut INTEGER, t_fin INTEGER, pas INTEGER, nb_lignes INTEGER, nb_lignes_gardees INTEGER,
    importe_le INTEGER NOT NULL, UNIQUE (systeme_id, empreinte));
CREATE TABLE IF NOT EXISTS couverture (
    systeme_id INTEGER NOT NULL, debut INTEGER NOT NULL, fin INTEGER NOT NULL, fichier_id INTEGER NOT NULL,
    PRIMARY KEY (systeme_id, debut)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS blocs (
    systeme_id INTEGER NOT NULL, registre INTEGER NOT NULL, mois INTEGER NOT NULL, n INTEGER NOT NULL,
    donnees BLOB NOT NULL, PRIMARY KEY (systeme_id, registre, mois)) WITHOUT ROWID;
"""


# --------------------------------------------------------------------------------------------
# Codage compact des points d'un registre pour un mois (bloc)
#   points (t, v) triés ; t codé en écart avec le point précédent (le 1er : écart avec le début du mois) ;
#   v codé 0 = vide, sinon zigzag(v - dernière valeur non vide) + 1 ; entiers en varint ; puis zlib.
#   Ordre de grandeur : 1 à 3 octets par changement de valeur.
# --------------------------------------------------------------------------------------------
def mois_de(t):
    d = datetime.datetime.fromtimestamp(t, datetime.timezone.utc)
    return d.year * 12 + d.month - 1


def debut_mois(m):
    return int(datetime.datetime(m // 12, m % 12 + 1, 1, tzinfo=datetime.timezone.utc).timestamp())


def _varint(n, out):
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return


def coder_bloc(points, mois):
    out = bytearray()
    tp, vp = debut_mois(mois), 0
    for t, v in points:
        _varint(t - tp, out)
        tp = t
        if v is None:
            out.append(0)
        else:
            d = v - vp
            _varint(((d << 1) if d >= 0 else ((-d << 1) - 1)) + 1, out)
            vp = v
    return zlib.compress(bytes(out), 9)


def decoder_bloc(blob, mois):
    data = zlib.decompress(blob)
    pts, i, n = [], 0, len(data)
    tp, vp = debut_mois(mois), 0
    while i < n:
        x = s = 0
        while True:
            b = data[i]; i += 1
            x |= (b & 0x7F) << s; s += 7
            if not b & 0x80:
                break
        tp += x
        x = s = 0
        while True:
            b = data[i]; i += 1
            x |= (b & 0x7F) << s; s += 7
            if not b & 0x80:
                break
        if x == 0:
            pts.append((tp, None))
        else:
            x -= 1
            vp += (x >> 1) if not x & 1 else -((x + 1) >> 1)
            pts.append((tp, vp))
    return pts


def maintenant():
    return int(datetime.datetime.now(datetime.timezone.utc).timestamp())


def chemin_base_defaut():
    """Documents\\ELPRO Logs\\elpro_logs.db (sauvegarde = copier ce fichier)."""
    return os.path.join(os.path.expanduser('~'), 'Documents', 'ELPRO Logs', 'elpro_logs.db')


class Magasin:
    """Accès à la base. Une instance par thread (l'import tourne dans un thread à part)."""

    def __init__(self, chemin):
        d = os.path.dirname(os.path.abspath(chemin))
        os.makedirs(d, exist_ok=True)
        self.chemin = chemin
        self.cx = sqlite3.connect(chemin, timeout=30)
        self.cx.execute('PRAGMA journal_mode=WAL')
        self.cx.execute('PRAGMA synchronous=NORMAL')
        self.cx.executescript(SCHEMA)
        f = self.cx.execute("SELECT valeur FROM meta WHERE cle='format'").fetchone()
        if f is None:
            self.cx.execute("INSERT INTO meta VALUES ('format', ?)", (str(FORMAT_BASE),))
            self.cx.commit()
        elif int(f[0]) > FORMAT_BASE:
            raise RuntimeError('Cette base a été créée par une version plus récente d\'ELPRO Logs.')
        self._cache_cat = {}
        self._cache_blocs = {}

    def fermer(self):
        self.cx.close()

    # ---------------------------------------------------------------- systèmes et configurations
    def systemes(self):
        """Tous les systèmes, dans l'ordre d'affichage (ouverts automatiquement au démarrage)."""
        res = []
        for sid, cle, nom, serie in self.cx.execute(
                'SELECT id, cle, nom, serie FROM systemes ORDER BY ordre, nom'):
            p = self.periode(sid)
            n = self.cx.execute('SELECT COUNT(*) FROM fichiers WHERE systeme_id=?', (sid,)).fetchone()[0]
            res.append({'id': sid, 'cle': cle, 'nom': nom, 'serie': serie, 'periode': p, 'nb_fichiers': n})
        return res

    def ajouter_config(self, projet, valable_depuis=None):
        """Importe un .elpro.json (dict). Nouveau système, ou nouvelle version de config d'un système
        existant (même system_name). Renvoie dict(systeme_id, statut: 'nouveau'|'version'|'identique')."""
        projet = M.normaliser_projet(json.loads(json.dumps(projet)))
        catalogue(projet)                         # valide le projet (lève ValueError sinon)
        s = projet['systeme']
        cle = (s.get('system_name') or s.get('nom_projet')).strip()
        nom = s.get('nom_projet') or cle
        brut = zlib.compress(json.dumps(projet, ensure_ascii=False, sort_keys=True).encode('utf-8'), 9)
        version = M.version_config(projet)
        r = self.cx.execute('SELECT id FROM systemes WHERE cle=?', (cle,)).fetchone()
        t = maintenant()
        if r is None:
            n = self.cx.execute('SELECT COUNT(*) FROM systemes').fetchone()[0]
            sid = self.cx.execute('INSERT INTO systemes (cle, nom, ordre, cree_le) VALUES (?,?,?,?)',
                                  (cle, nom, n, t)).lastrowid
            self.cx.execute('INSERT INTO configs (systeme_id, version, valable_depuis, importe_le, json) VALUES (?,?,?,?,?)',
                            (sid, version, 0, t, brut))
            self.cx.commit()
            return {'systeme_id': sid, 'statut': 'nouveau'}
        sid = r[0]
        der = self.cx.execute('SELECT json FROM configs WHERE systeme_id=? ORDER BY valable_depuis DESC, id DESC LIMIT 1',
                              (sid,)).fetchone()
        if der and der[0] == brut:
            return {'systeme_id': sid, 'statut': 'identique'}
        self.cx.execute('INSERT INTO configs (systeme_id, version, valable_depuis, importe_le, json) VALUES (?,?,?,?,?)',
                        (sid, version, t if valable_depuis is None else int(valable_depuis), t, brut))
        self.cx.execute('UPDATE systemes SET nom=? WHERE id=?', (nom, sid))
        self.cx.commit()
        self._cache_cat.clear()
        return {'systeme_id': sid, 'statut': 'version'}

    def configs(self, sid):
        return [{'id': i, 'version': v, 'valable_depuis': d, 'importe_le': im}
                for i, v, d, im in self.cx.execute(
                    'SELECT id, version, valable_depuis, importe_le FROM configs WHERE systeme_id=? '
                    'ORDER BY valable_depuis, id', (sid,))]

    def projet(self, sid, t=None):
        """Projet en vigueur à l'instant t (défaut : la dernière version)."""
        if t is None:
            r = self.cx.execute('SELECT json FROM configs WHERE systeme_id=? ORDER BY valable_depuis DESC, id DESC LIMIT 1',
                                (sid,)).fetchone()
        else:
            r = self.cx.execute('SELECT json FROM configs WHERE systeme_id=? AND valable_depuis<=? '
                                'ORDER BY valable_depuis DESC, id DESC LIMIT 1', (sid, t)).fetchone()
            if r is None:
                r = self.cx.execute('SELECT json FROM configs WHERE systeme_id=? ORDER BY valable_depuis, id LIMIT 1',
                                    (sid,)).fetchone()
        return json.loads(zlib.decompress(r[0]).decode('utf-8'))

    def catalogue(self, sid, t=None):
        """Catalogue de la config en vigueur à t, complété par les registres présents dans les logs
        mais non utilisés par la configuration (famille AUTRES)."""
        cid = self._config_id(sid, t)
        if cid in self._cache_cat:
            return self._cache_cat[cid]
        cat = catalogue(self.projet(sid, t))
        connus = set(cat['par_registre'])
        autres = [canal_autre(r) for (r,) in self.cx.execute(
            'SELECT DISTINCT registre FROM blocs WHERE systeme_id=? ORDER BY registre', (sid,)) if r not in connus]
        cat['autres'] = autres
        for c in autres:
            cat['par_registre'][c['registre']] = c
        self._cache_cat[cid] = cat
        return cat

    def _config_id(self, sid, t):
        if t is None:
            r = self.cx.execute('SELECT id FROM configs WHERE systeme_id=? ORDER BY valable_depuis DESC, id DESC LIMIT 1',
                                (sid,)).fetchone()
        else:
            r = self.cx.execute('SELECT id FROM configs WHERE systeme_id=? AND valable_depuis<=? '
                                'ORDER BY valable_depuis DESC, id DESC LIMIT 1', (sid, t)).fetchone() or \
                self.cx.execute('SELECT id FROM configs WHERE systeme_id=? ORDER BY valable_depuis, id LIMIT 1',
                                (sid,)).fetchone()
        return (sid, r[0], self.cx.execute('SELECT COUNT(*) FROM fichiers WHERE systeme_id=?', (sid,)).fetchone()[0])

    def versions_dans_periode(self, sid, t0, t1):
        cs = self.configs(sid)
        return [c for k, c in enumerate(cs)
                if c['valable_depuis'] < t1 and (k + 1 == len(cs) or cs[k + 1]['valable_depuis'] > t0)]

    def renommer(self, sid, nom):
        self.cx.execute('UPDATE systemes SET nom=? WHERE id=?', (nom, sid)); self.cx.commit()

    def supprimer_systeme(self, sid):
        for tab in ('blocs', 'couverture', 'fichiers', 'configs', 'profils', 'acces'):
            self.cx.execute(f'DELETE FROM {tab} WHERE systeme_id=?', (sid,))
        self.cx.execute('DELETE FROM systemes WHERE id=?', (sid,))
        self.cx.commit()
        self._cache_cat.clear()
        self._cache_blocs.clear()

    def definir_profil(self, sid, profil):
        """Liste de log propre à ce système (lue dans l'export XML de la radio). None = standard."""
        if profil is None:
            self.cx.execute('DELETE FROM profils WHERE systeme_id=?', (sid,))
        else:
            self.cx.execute('INSERT OR REPLACE INTO profils VALUES (?,?)', (sid, json.dumps(profil)))
        self.cx.commit()

    def profil(self, sid):
        r = self.cx.execute('SELECT json FROM profils WHERE systeme_id=?', (sid,)).fetchone()
        return json.loads(r[0]) if r else None

    # ---------------------------------------------------------------- import des logs
    # ---------------------------------------------------------------- accès à la centrale (v1.1)
    def definir_acces(self, sid, adresse, utilisateur, mdp_protege):
        """mdp_protege : octets produits par elpro_remote.proteger_mdp() (jamais le mot de passe en clair)."""
        ex = self.acces(sid)
        self.cx.execute('INSERT OR REPLACE INTO acces VALUES (?,?,?,?,?,?)',
                        (sid, adresse.strip(), utilisateur.strip(), mdp_protege,
                         ex['derniere_recuperation'] if ex else None, ex['dernier_resultat'] if ex else None))
        self.cx.commit()

    def acces(self, sid):
        r = self.cx.execute('SELECT adresse, utilisateur, mdp, derniere_recuperation, dernier_resultat '
                            'FROM acces WHERE systeme_id=?', (sid,)).fetchone()
        if not r:
            return None
        return dict(zip(('adresse', 'utilisateur', 'mdp', 'derniere_recuperation', 'dernier_resultat'), r))

    def noter_recuperation(self, sid, t, resultat):
        self.cx.execute('UPDATE acces SET derniere_recuperation=?, dernier_resultat=? WHERE systeme_id=?',
                        (t, resultat, sid))
        self.cx.commit()

    def noms_fichiers(self, sid):
        """Noms des fichiers déjà importés (pour ne télécharger que les nouveaux)."""
        return {n for (n,) in self.cx.execute('SELECT nom FROM fichiers WHERE systeme_id=?', (sid,))}

    def importer_octets(self, sid, octets, nom, forcer_serie=False, progression=None):
        """Comme importer_fichier, à partir du contenu d'un fichier (téléchargé)."""
        try:
            logs = [analyser_csv(txt, n) for n, txt in _csv_depuis_octets(octets, nom)]
        except ErreurLog as e:
            return [{'fichier': nom, 'statut': 'erreur', 'message': str(e)}]
        for lg in logs:
            lg['nom'] = nom
        return [self.importer_log(sid, lg, forcer_serie, progression) for lg in logs]

    def importer_fichier(self, sid, chemin, forcer_serie=False, progression=None):
        """Importe un fichier .log/.zip/.csv. Renvoie une liste de rapports (un par log contenu)."""
        try:
            logs = lire_fichier_log(chemin)
        except ErreurLog as e:
            return [{'fichier': os.path.basename(chemin), 'statut': 'erreur', 'message': str(e)}]
        return [self.importer_log(sid, lg, forcer_serie, progression) for lg in logs]

    def importer_log(self, sid, lg, forcer_serie=False, progression=None):
        """lg : résultat de analyser_csv. Statuts : importe | deja_importe | deja_couvert | vide |
        serie_differente (rien importé : redemander avec forcer_serie=True après confirmation)."""
        rap = {'fichier': lg['nom'], 'serie': lg['serie'], 'avertissements': []}
        if not lg['lignes']:
            return dict(rap, statut='vide', message='Aucune ligne de données.')
        if self.cx.execute('SELECT 1 FROM fichiers WHERE systeme_id=? AND empreinte=?',
                           (sid, lg['empreinte'])).fetchone():
            return dict(rap, statut='deja_importe', message='Fichier déjà importé.')
        serie_sys = self.cx.execute('SELECT serie FROM systemes WHERE id=?', (sid,)).fetchone()[0]
        if lg['serie'] and serie_sys and lg['serie'] != serie_sys and not forcer_serie:
            return dict(rap, statut='serie_differente',
                        message=f"Ce log vient de la radio n° {lg['serie']}, alors que les logs de ce système "
                                f"viennent de la radio n° {serie_sys}. Mauvais système, ou radio remplacée ?")
        regs, avert = resoudre_colonnes(lg['colonnes'], self.profil(sid))
        rap['avertissements'] += avert
        cols = [(k, r) for k, r in enumerate(regs) if r is not None]
        ts = [t for t, _ in lg['lignes']]
        diffs = sorted(b - a for a, b in zip(ts, ts[1:]) if b > a)
        pas = diffs[len(diffs) // 2] if diffs else 30
        # lignes déjà couvertes par un import précédent : ignorées
        cov = [(a, b) for a, b in self.cx.execute(
            'SELECT debut, fin FROM couverture WHERE systeme_id=? AND fin>? AND debut<=? ORDER BY debut',
            (sid, ts[0], ts[-1]))]

        def couvert(t):
            return any(a <= t < b for a, b in cov)

        gardees = [(t, v) for t, v in lg['lignes'] if not couvert(t)]
        cur = self.cx.cursor()
        fid = cur.execute('INSERT INTO fichiers (systeme_id, nom, empreinte, serie, t_debut, t_fin, pas, nb_lignes, '
                          'nb_lignes_gardees, importe_le) VALUES (?,?,?,?,?,?,?,?,?,?)',
                          (sid, lg['nom'], lg['empreinte'], lg['serie'], ts[0], ts[-1] + pas, pas,
                           len(ts), len(gardees), maintenant())).lastrowid
        if not gardees:
            self.cx.commit()
            return dict(rap, statut='deja_couvert', message='Toutes les lignes étaient déjà importées.',
                        t_debut=ts[0], t_fin=ts[-1] + pas)
        # plages continues : écart > 1,5 pas = trou
        plages, prec, a = [], None, None
        lignes_val = []
        nouv = True
        for t, v in gardees:
            if prec is None or t - prec > 1.5 * pas:
                if prec is not None:
                    plages.append((a, prec + pas))
                a, nouv = t, True
            lignes_val.append((t, v, nouv))
            nouv, prec = False, t
        plages.append((a, prec + pas))
        dern = {}
        lots = []
        for n, (t, v, debut_plage) in enumerate(lignes_val):
            for k, r in cols:
                x = v[k]
                if debut_plage or dern.get(r, 'rien') != x:
                    lots.append((r, t, x))
                    dern[r] = x
            if progression and n % 500 == 0:
                progression(n, len(lignes_val))
        self._ecrire_points(cur, sid, lots)
        cur.executemany('INSERT OR REPLACE INTO couverture VALUES (?,?,?,?)', [(sid, a, b, fid) for a, b in plages])
        if lg['serie'] and (not serie_sys or forcer_serie):
            cur.execute('UPDATE systemes SET serie=? WHERE id=?', (lg['serie'], sid))
        self.cx.commit()
        self._cache_cat.clear()
        self._cache_blocs.clear()
        if len(gardees) < len(ts):
            rap['avertissements'].append(f'{len(ts) - len(gardees)} lignes déjà présentes ont été ignorées.')
        return dict(rap, statut='importe', message=f'{len(gardees)} lignes importées.',
                    t_debut=gardees[0][0], t_fin=gardees[-1][0] + pas, nb_points=len(lots))

    def _ecrire_points(self, cur, sid, lots):
        """Fusionne les nouveaux points (registre, t, v) dans les blocs mensuels."""
        par_bloc = {}
        for r, t, v in lots:
            par_bloc.setdefault((r, mois_de(t)), []).append((t, v))
        for (r, m), pts in par_bloc.items():
            ex = cur.execute('SELECT donnees FROM blocs WHERE systeme_id=? AND registre=? AND mois=?',
                             (sid, r, m)).fetchone()
            if ex:
                d = dict(decoder_bloc(ex[0], m))
                d.update(pts)
                pts = sorted(d.items())
            cur.execute('INSERT OR REPLACE INTO blocs VALUES (?,?,?,?,?)', (sid, r, m, len(pts), coder_bloc(pts, m)))

    def _bloc(self, sid, r, m):
        k = (sid, r, m)
        if k not in self._cache_blocs:
            if len(self._cache_blocs) > 5000:
                self._cache_blocs.clear()
            ex = self.cx.execute('SELECT donnees FROM blocs WHERE systeme_id=? AND registre=? AND mois=?',
                                 (sid, r, m)).fetchone()
            self._cache_blocs[k] = decoder_bloc(ex[0], m) if ex else []
        return self._cache_blocs[k]

    def _points(self, sid, r, t0, t1):
        """Dernier point <= t0, puis tous les points de ]t0, t1[."""
        m0, m1 = mois_de(t0), mois_de(max(t0, t1 - 1))
        pts = [p for m in range(m0, m1 + 1) for p in self._bloc(sid, r, m)]
        avant = [p for p in self._bloc(sid, r, m0) if p[0] <= t0]
        if not avant:
            ex = self.cx.execute('SELECT mois FROM blocs WHERE systeme_id=? AND registre=? AND mois<? '
                                 'ORDER BY mois DESC LIMIT 1', (sid, r, m0)).fetchone()
            if ex:
                avant = self._bloc(sid, r, ex[0])[-1:]
        return avant[-1:] + [p for p in pts if t0 < p[0] < t1]

    def nb_points(self, sid=None):
        q = 'SELECT COALESCE(SUM(n),0) FROM blocs' + (' WHERE systeme_id=?' if sid else '')
        return self.cx.execute(q, (sid,) if sid else ()).fetchone()[0]

    def fichiers(self, sid):
        return [dict(zip(('id', 'nom', 'serie', 't_debut', 't_fin', 'pas', 'nb_lignes', 'nb_lignes_gardees', 'importe_le'), r))
                for r in self.cx.execute('SELECT id, nom, serie, t_debut, t_fin, pas, nb_lignes, nb_lignes_gardees, '
                                         'importe_le FROM fichiers WHERE systeme_id=? ORDER BY t_debut', (sid,))]

    def compacter_base(self):
        """VACUUM : à proposer après une suppression de système."""
        self.cx.execute('VACUUM')

    # ---------------------------------------------------------------- lecture
    def periode_defaut(self, sid, maintenant=None, jours=JOURS_DEFAUT):
        """Période affichée à l'ouverture : le jour actuel + les `jours` jours précédents (jours entiers,
        heure suisse), jusqu'à la fin des données.
        - Données plus courtes que la fenêtre : la période commence au début des données.
        - Pas de données dans la fenêtre (logs anciens) : même fenêtre, mais calée sur le dernier jour de données.
        - Aucune donnée : None."""
        p = self.periode(sid)
        if not p:
            return None
        maintenant = maintenant or self._maintenant()
        t0 = debut_jour_local(maintenant, -jours)
        if p[1] <= t0:                                   # rien dans la fenêtre : on se cale sur les données
            t0 = debut_jour_local(p[1] - 1, -jours)
        return (max(t0, p[0]), p[1])

    @staticmethod
    def _maintenant():
        return maintenant()

    def periode(self, sid):
        r = self.cx.execute('SELECT MIN(debut), MAX(fin) FROM couverture WHERE systeme_id=?', (sid,)).fetchone()
        return None if r[0] is None else (r[0], r[1])

    def periode_par_defaut(self, sid, jours=7):
        """Période affichée à l'ouverture (v1.1) : la dernière semaine de données, du même jour de la
        semaine à la même heure (ex. lundi 09:17 -> lundi précédent 09:17), en heure suisse : 7 jours
        calendaires, donc 7 × 24 h ± 1 h lors d'un changement d'heure.
        Moins d'une semaine de données : toute la période. Aucune donnée : None."""
        p = self.periode(sid)
        if not p:
            return None
        return (max(p[0], reculer_jours(p[1], jours)), p[1])

    def couverture(self, sid, t0, t1):
        """Plages avec données dans [t0, t1), fusionnées."""
        iv = [(max(a, t0), min(b, t1)) for a, b in self.cx.execute(
            'SELECT debut, fin FROM couverture WHERE systeme_id=? AND fin>? AND debut<? ORDER BY debut', (sid, t0, t1))]
        return fusionner_intervalles(iv)

    def trous(self, sid, t0, t1):
        """Plages SANS données dans [t0, t1)."""
        res, t = [], t0
        for a, b in self.couverture(sid, t0, t1):
            if a > t:
                res.append((t, a))
            t = max(t, b)
        if t < t1:
            res.append((t, t1))
        return res

    def segments(self, sid, registre, t0, t1, cov=None):
        """Valeur brute du registre sur [t0, t1) : [(debut, fin, brut)], uniquement là où il y a des données."""
        if cov is None:
            cov = self.couverture(sid, t0, t1)
        if not cov:
            return []
        pts = self._points(sid, registre, t0, t1)
        segs = []
        for k, (t, v) in enumerate(pts):
            fin = pts[k + 1][0] if k + 1 < len(pts) else t1
            segs.append((max(t, t0), fin, v))
        return intersecter(segs, cov)

    def segments_decodes(self, sid, canal, t0, t1, cov=None):
        return compacter([(a, b, decoder(canal, v)) for a, b, v in self.segments(sid, canal['registre'], t0, t1, cov)])

    def courbe(self, sid, canal, t0, t1, n_max=2000):
        """Points prêts à tracer en escalier : (xs, ys), None dans ys = trou (pas de données).
        Au-delà de n_max segments, réduction min/max par tranche (le graphique reste fidèle aux extrêmes)."""
        segs = self.segments_decodes(sid, canal, t0, t1)
        xs, ys = [], []
        if len(segs) > n_max and not canal['binaire']:
            pas = (t1 - t0) / (n_max / 2)
            k = 0
            while k < len(segs):
                a0 = segs[k][0]
                tranche = []
                while k < len(segs) and segs[k][0] < a0 + pas:
                    tranche.append(segs[k]); k += 1
                vals = [v for _, _, v in tranche if v is not None]
                if xs and xs[-1] is not None and xs[-1] < tranche[0][0]:
                    xs.append(xs[-1]); ys.append(None)
                if vals:
                    lo, hi = min(vals), max(vals)
                    xs += [tranche[0][0], (tranche[0][0] + tranche[-1][1]) / 2]
                    ys += [lo, hi]
                xs.append(tranche[-1][1]); ys.append(vals[-1] if vals else None)
            return xs, ys
        fin_prec = None
        for a, b, v in segs:
            if fin_prec is not None and a > fin_prec:
                xs.append(fin_prec); ys.append(None)        # trou
            xs += [a, b]; ys += [v, v]
            fin_prec = b
        return xs, ys

    # ---------------------------------------------------------------- vue globale
    def etat_stations(self, sid, t0, t1):
        """Pour chaque station : segments d'état (SANS_DONNEES / COMM_PERDUE / DEGRADE / ALERTE / OK)."""
        cat = self.catalogue(sid, t1)
        cov = self.couverture(sid, t0, t1)
        res = []
        for S in cat['stations']:
            par_genre = {}
            for c in S['canaux']:
                if c['genre'] in ('COMFLAG', 'BATTV', 'MAINV') or c['genre'].startswith('FAIL_'):
                    par_genre.setdefault(c['genre'], []).append(c)
            listes, roles = [], []
            for g, cs in par_genre.items():
                for c in cs:
                    segs = self.segments(sid, c['registre'], t0, t1, cov)
                    # réduit d'abord chaque canal à « en défaut ou non » : beaucoup moins de segments
                    if g == 'BATTV':
                        segs = compacter([(x, y, (battv_volts(v) or 99) < BATTV_BAS) for x, y, v in segs])
                    elif g == 'MAINV':
                        segs = compacter([(x, y, v == 0) for x, y, v in segs])
                    else:
                        segs = compacter([(x, y, bool(v)) for x, y, v in segs])
                    listes.append(segs); roles.append(g)
            listes.append([(a, b, 1) for a, b in cov]); roles.append('_COUV')

            def etat(vals, roles=roles):
                d = dict()
                for g, v in zip(roles, vals):
                    d.setdefault(g, []).append(v)
                if not d['_COUV'][0]:
                    return 'SANS_DONNEES'
                if any(d.get('COMFLAG', [])):
                    return 'COMM_PERDUE'
                if any(v for g, vs in d.items() if g.startswith('FAIL_') for v in vs):
                    return 'DEGRADE'
                if any(d.get('BATTV', [])) or any(d.get('MAINV', [])):
                    return 'ALERTE'
                return 'OK'

            segs = combiner(listes, etat, t0, t1)
            res.append({'station': S['nom'], 'role': S['role'], 'segments': segs})
        return res

    def etat_systeme(self, sid, t0, t1):
        """Bande « système » : l'état le plus grave de toutes les stations."""
        st = self.etat_stations(sid, t0, t1)
        return combiner([s['segments'] for s in st],
                        lambda vs: min((v for v in vs if v), key=ETATS.index, default='SANS_DONNEES'), t0, t1)

    @staticmethod
    def par_cases(segments, t0, t1, n):
        """Réduction pour l'affichage d'une longue période : n cases, chacune = état le plus grave."""
        pas = (t1 - t0) / n
        res = []
        k = 0
        for i in range(n):
            a, b = t0 + i * pas, t0 + (i + 1) * pas
            pire = None
            while k < len(segments) and segments[k][1] <= a:
                k += 1
            j = k
            while j < len(segments) and segments[j][0] < b:
                v = segments[j][2]
                if pire is None or ETATS.index(v) < ETATS.index(pire):
                    pire = v
                j += 1
            res.append((a, b, pire or 'SANS_DONNEES'))
        return res

    # ---------------------------------------------------------------- synthèse
    def synthese(self, sid, t0, t1):
        """Chiffres clés de la période, par station et par canal."""
        cat = self.catalogue(sid, t1)
        cov = self.couverture(sid, t0, t1)
        t_donnees = duree([(a, b, 1) for a, b in cov])
        out = {'t0': t0, 't1': t1, 'duree': t1 - t0, 'duree_donnees': t_donnees,
               'couverture_pct': round(100.0 * t_donnees / (t1 - t0), 1) if t1 > t0 else 0,
               'trous': self.trous(sid, t0, t1), 'stations': [],
               'versions_config': self.versions_dans_periode(sid, t0, t1)}
        for S in cat['stations']:
            comm = []
            cf = [c for c in S['canaux'] if c['genre'] == 'COMFLAG']
            if cf:
                comm = self.segments(sid, cf[0]['registre'], t0, t1, cov)
            hors_perte = [(a, b, 1) for a, b, v in comm if not v] if cf else [(a, b, 1) for a, b in cov]
            st = {'station': S['nom'], 'role': S['role'], 'canaux': []}
            if cf:
                pertes = [(a, b) for a, b, v in comm if v]
                st['comm'] = {'disponibilite_pct': round(100.0 * duree(comm, lambda v: not v) / t_donnees, 2) if t_donnees else None,
                              'nb_pertes': len(pertes), 'duree_pertes': sum(b - a for a, b in pertes),
                              'plus_longue': max((b - a for a, b in pertes), default=0)}
            for c in S['canaux']:
                segs = self.segments_decodes(sid, c, t0, t1, cov)
                r = {'canal': c}
                if c['binaire']:
                    actifs = [(a, b) for a, b, v in segs if v]
                    # activation = passage 0 -> 1 (un segment actif en début de période compte aussi)
                    r.update(nb_activations=len(actifs), duree_active=sum(b - a for a, b in actifs),
                             actif_a_la_fin=bool(segs and segs[-1][2] and segs[-1][1] == t1))
                    if c['genre'] == 'MAINV':
                        coup = [(a, b) for a, b, v in segs if v == 0]
                        r.update(nb_coupures=len(coup), duree_coupures=sum(b - a for a, b in coup))
                else:
                    # valeurs prises hors pertes de communication (sinon valeur figée)
                    utiles = combiner([segs, hors_perte], lambda v: v[0] if v[1] else None, t0, t1) if cf else segs
                    vals = [(b - a, v) for a, b, v in utiles if v is not None]
                    if vals:
                        tot = sum(d for d, _ in vals)
                        r.update(min=min(v for _, v in vals), max=max(v for _, v in vals),
                                 moyenne=round(sum(d * v for d, v in vals) / tot, 2))
                        if c['genre'] == 'BATTV':
                            r['duree_basse'] = sum(d for d, v in vals if v < BATTV_BAS)
                        if c['genre'] == 'RSSI':
                            r['duree_faible'] = sum(d for d, v in vals if v < RSSI_FAIBLE)
                        if c['genre'] == 'RADAR':
                            r['duree_au_dessus_seuil'] = sum(d for d, v in vals if v >= c['seuil_haut'])
                    else:
                        r.update(min=None, max=None, moyenne=None)
                st['canaux'].append(r)
            out['stations'].append(st)
        return out

    # ---------------------------------------------------------------- journal
    def evenements(self, sid, t0, t1, stations=None, familles=None):
        """Journal chronologique : changements d'état des canaux binaires, passages de seuil batterie/RSSI,
        début et fin des trous de données. Filtres : noms de stations, codes de famille (FAMILLES)."""
        cat = self.catalogue(sid, t1)
        cov = self.couverture(sid, t0, t1)
        ev = []
        if familles is None or 'DONNEES' in familles:
            for a, b in self.trous(sid, t0, t1):
                if a > t0:
                    ev.append({'t': a, 'station': None, 'canal': None, 'gravite': 'info',
                               'message': f'Début d\'absence de données ({duree_texte(b - a)})'})
                if b < t1:
                    ev.append({'t': b, 'station': None, 'canal': None, 'gravite': 'info',
                               'message': 'Reprise des données'})
        for S in cat['stations']:
            if stations and S['nom'] not in stations:
                continue
            for c in S['canaux']:
                if familles and c['famille'] not in familles:
                    continue
                segs = self.segments_decodes(sid, c, t0, t1, cov)
                prec = None          # dernière valeur connue (conservée à travers les trous)
                for k, (a, b, v) in enumerate(segs):
                    if v is None:
                        continue
                    if prec is None or v == prec:
                        prec = v                       # état initial, ou inchangé après un trou
                        continue
                    if c['binaire']:
                        ev.append(self._ev_binaire(S, c, a, v))
                        if (v == 0) if c['genre'] == 'MAINV' else bool(v):
                            ev[-1]['duree'] = self._duree_etat(segs, k)
                    elif c['genre'] == 'BATTV':
                        if v < BATTV_BAS <= prec:
                            ev.append({'t': a, 'station': S['nom'], 'canal': c['nom'], 'genre': 'BATTV', 'gravite': 'alerte',
                                       'message': f'Batterie basse : {v:.2f} V'})
                        elif prec < BATTV_BAS <= v:
                            ev.append({'t': a, 'station': S['nom'], 'canal': c['nom'], 'genre': 'BATTV', 'gravite': 'info',
                                       'message': f'Batterie revenue à {v:.2f} V'})
                    elif c['genre'] == 'RADAR':
                        s = c['seuil_haut']
                        if v >= s > prec:
                            ev.append({'t': a, 'station': S['nom'], 'canal': c['nom'], 'genre': 'RADAR', 'gravite': 'alarme',
                                       'message': f"{c['libelle']} : seuil atteint ({v} {c['unite']})"})
                        elif prec >= s > v:
                            ev.append({'t': a, 'station': S['nom'], 'canal': c['nom'], 'genre': 'RADAR', 'gravite': 'info',
                                       'message': f"{c['libelle']} : sous le seuil ({v} {c['unite']})"})
                    prec = v
        # un échec de lecture qui commence ou finit en même temps que la perte de comm n'apporte rien
        comm = {(e['t'], e['station']) for e in ev if e.get('genre') == 'COMFLAG'}
        ev = [e for e in ev if not (str(e.get('genre', '')).startswith('FAIL_') and (e['t'], e['station']) in comm)]
        ev.sort(key=lambda e: (e['t'], e['station'] or '', e['canal'] or ''))
        return ev

    @staticmethod
    def _duree_etat(segs, k):
        """Durée continue de l'état commencé au segment k (s'arrête au premier trou ou changement)."""
        a, b, v = segs[k]
        j = k + 1
        while j < len(segs) and segs[j][0] == b and segs[j][2] == v:
            b = segs[j][1]; j += 1
        return b - a

    @staticmethod
    def _ev_binaire(S, c, t, v):
        g = c['genre']
        if g == 'COMFLAG':
            msg, grav = ('Perte de communication', 'defaut') if v else ('Communication rétablie', 'info')
        elif g == 'MAINV':
            msg, grav = ('Secteur rétabli', 'info') if v else ('Coupure secteur', 'alerte')
        elif g == 'DETECTION':
            msg, grav = (f"{c['libelle']} : activée", 'alarme') if v else (f"{c['libelle']} : retour au repos", 'info')
        elif g == 'COMMANDE':
            msg, grav = (f"{c['libelle']} : enclenchée", 'commande') if v else (f"{c['libelle']} : déclenchée", 'info')
        elif g.startswith('FAIL_'):
            msg, grav = (f"{c['libelle']}", 'defaut') if v else (f"{c['libelle']} : rétabli", 'info')
        else:
            msg, grav = f"{c['libelle']} = {v}", 'info'
        return {'t': t, 'station': S['nom'], 'canal': c['nom'], 'genre': g, 'valeur': v, 'gravite': grav, 'message': msg}

    # ---------------------------------------------------------------- export
    def exporter_csv(self, sid, canaux, t0, t1, chemin, pas=None):
        """Export des valeurs décodées, une ligne par pas (défaut : pas des logs), heure suisse, séparateur ;"""
        cov = self.couverture(sid, t0, t1)
        if pas is None:
            r = self.cx.execute('SELECT pas FROM fichiers WHERE systeme_id=? ORDER BY t_debut DESC LIMIT 1', (sid,)).fetchone()
            pas = r[0] if r else 30
        segs = [self.segments_decodes(sid, c, t0, t1, cov) for c in canaux]
        idx = [0] * len(canaux)
        with open(chemin, 'w', encoding='utf-8-sig', newline='') as f:
            f.write('Date et heure (Suisse);' + ';'.join(
                f"{c['station'] or ''} {c['libelle']}" + (f" [{c['unite']}]" if c['unite'] else '') for c in canaux) + '\n')
            for a, b in cov:
                t = a
                while t < b:
                    vals = []
                    for k, L in enumerate(segs):
                        while idx[k] < len(L) and L[idx[k]][1] <= t:
                            idx[k] += 1
                        v = L[idx[k]][2] if idx[k] < len(L) and L[idx[k]][0] <= t else None
                        vals.append('' if v is None else str(v).replace('.', ','))
                    f.write(heure_locale(t) + ';' + ';'.join(vals) + '\n')
                    t += pas

    def taille_fichier(self):
        return sum(os.path.getsize(p) for p in (self.chemin, self.chemin + '-wal') if os.path.exists(p))
