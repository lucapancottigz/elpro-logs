# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""
Moteur de génération ELPRO GeoAzimut (v2.3) — IMPLÉMENTATION DE RÉFÉRENCE.

Entrée  : un projet (dict, format décrit dans 03_Modele_de_donnees.md).
Sorties : - plan (dict)            -> utilisé par la page 2, le PDF et l'Excel
          - fichier .cdb (UTF-16)  -> ecrire_cdb(plan, chemin)
          - fichiers .sconf        -> ecrire_sconf(lignes, chemin, actif)
          - XML de chaque radio    -> ecrire_xml_radio(plan, S, chemin, ioplus_actif)   (v2.1)

Python 3.10+, bibliothèque standard uniquement.
NE PAS MODIFIER LES RÈGLES de ce fichier : elles ont été validées sur radio.
"""
import os, re, io, time, tarfile, secrets, string, datetime

# Mentions légales (affichées dans l'application, le PDF et l'Excel)
COPYRIGHT = '© 2026 Geoazimut SàRL. Tous droits réservés.'
SITE_WEB = 'https://geoazimut.com'

RESSOURCES = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'resources')

# ---------------------------------------------------------------- constantes
CRENEAU_S = 22               # durée d'un créneau de polling (s)
TIMEOUT_S = 20               # ResponseTimeout des lectures
FAILSAFE_COUNT = 17          # taille de chaque bloc fail-safe (volontaire)
MAX_RADIOS = 17
NTP = '195.176.26.204'
SENSIB_BATTV_BASE = 3276
ACK_FORT = (4, 4000)         # base + remotes qui poussent des alarmes/radars
ACK_DEFAUT = (3, 2000)
RESEAU = '192.168.1'
PASSERELLE = '192.168.1.1'

OP = {'NO_OP': 0, 'LOAD': 1, 'STOR': 2, 'SET': 3, 'RES': 4, 'AND': 5, 'OR': 6, 'XOR': 7, 'ADD': 8,
      'SUB': 9, 'MUL': 10, 'DIV': 11, 'GT': 12, 'GE': 13, 'EQ': 14, 'NE': 15, 'LE': 16, 'LT': 17,
      'JMP': 18, 'JMP_C': 19, 'CALL': 20, 'CALL_C': 21, 'RET': 22, 'RET_C': 23, 'FIN_BLOC': 24}

TYPES_ENTREE = {'CABLE': 1, 'LIDAR3': 3, 'LIDAR6': 6, 'ALARME_BT': 1, 'ENTREE': 1}
TYPES_SORTIE_SIMPLE = ('SIRENE', 'FLASH', 'SIRENE_FLASH', 'CAMERA', 'SPOT', 'SORTIE')
TYPES = set(TYPES_ENTREE) | set(TYPES_SORTIE_SIMPLE) | {'FEU', 'CAMERA_SPOT', 'RADAR', 'ENTREE_ANA', 'SORTIE_ANA'}

# ---- E/S analogiques génériques (v2.0) : mesure seule (pas d'alarme radio) et consigne de sortie analogique
# Entrée : AI1-AI4 en courant (0-20 mA, registres 30001-30004) ; AI3/AI4 en tension (0-5 V, registres 30009-30010).
#          Brut : courant 8192 + mA x 2048 (4 mA = 16384, 20 mA = 49152) ; tension 8192 + V x 8192 (0 V = 8192, 5 V = 49152).
# Sortie : AO1/AO2 (registres 40001-40002), 4-20 mA : 16384 = 4 mA, 49152 = 20 mA.
ANA_BASE = 35300             # mesures analogiques sur la base : 353nn
AO_BASE = 45000              # consignes de sortie analogique sur la base : 450nn (écrites par la supervision)
MAX_ANA, MAX_AO = 50, 20
ANA_POINTS = {'courant': (16384, 49152, 4, 20, 'mA'), 'tension': (8192, 49152, 0, 5, 'V')}
AO_POINTS = (16384, 49152, 4, 20, 'mA')


def registre_ai(p):
    """Registre radio d'une entrée analogique générique."""
    return 30000 + p['ai'] if p.get('mode', 'courant') == 'courant' else 30006 + p['ai']


def _series(ana):
    """Regroupe les entrées analogiques d'une radio en séries de registres consécutifs (une lecture par série)."""
    runs = []
    for A in ana:
        if runs and A['distant'] == runs[-1][-1]['distant'] + 1:
            runs[-1].append(A)
        else:
            runs.append([A])
    return runs


def io_ai(p):
    """Identifiant CConfig de l'entrée (page IO) : Ain1-4 en courant, Ain5/Ain6 = AI3/AI4 en tension."""
    return f"Ain{p['ai']}" if p.get('mode', 'courant') == 'courant' else f"Ain{p['ai'] + 2}"

# Sorties d'un feu : (clé JSON, libellé, base du registre de commande)
# Plan des commandes : rouge 401-410, orange clignotant 411-420, orange fixe 421-430,
# autres signalisations 431-440 (inchangé depuis les premiers sites), vert 441-450 (ajouté à la fin)
SORTIES_FEU = (('do_rouge', 'ROUGE', 400), ('do_orange_cli', 'OR_CLI', 410),
               ('do_orange_fixe', 'OR_FIXE', 420), ('do_vert', 'VERT', 440))
LIBELLES_FEU = {'ROUGE': 'rouge', 'OR_CLI': 'orange clignotant', 'OR_FIXE': 'orange fixe', 'VERT': 'vert'}

# Longueur maximale d'un nom de registre / de tag du tableau de bord : au-delà, la radio affiche un
# nom d'E/S par défaut (DIn1, DOut5…) à la place. Constaté sur radio (v2.1) : un tag de 16 caractères est
# remplacé, 15 passe ; les noms de registres (IOUsrCfg) acceptent 16 mais on garde la même règle partout.
NOM_MAX = 15


def nom_court(station, label, maxi=NOM_MAX):
    """'<station>_<label>' limité à `maxi` caractères : la station est raccourcie en premier
    (au moins 4 caractères), sinon seul le libellé est gardé.
    'SB-CA-SM1' + 'RADAR_LVL' -> 'SB-CA_RADAR_LVL' ; 'B-CAM01' + 'CAMON_SPOTON' -> 'CAMON_SPOTON'."""
    complet = f'{station}_{label}'
    if len(complet) <= maxi:
        return complet
    place = maxi - len(label) - 1
    if place >= 4:
        return f"{station[:place].rstrip('-_')}_{label}"
    return label[:maxi]                                  # libellé long : le nom de la station n'apparaît pas


def ma_vers_unite(ma, R):
    """Conversion mA -> unité de mesure du radar (échelle linéaire 4-20 mA)."""
    return R['mesure_4ma'] + (ma - 4.0) / 16.0 * (R['mesure_20ma'] - R['mesure_4ma'])


def unite_vers_ma(v, R):
    """Conversion unité de mesure -> mA (pour saisir les seuils dans l'unité du radar)."""
    return 4.0 + (v - R['mesure_4ma']) * 16.0 / (R['mesure_20ma'] - R['mesure_4ma'])
BASE_AUTRES = 430            # commandes autres signalisations : 431-440
FAILSAFE_COMMANDES = (401, 50)


def normaliser_projet(projet):
    """Met à jour un projet d'une ancienne version du format (modifie et retourne le dict).
    - feu à 3 sorties : l'ancienne sortie « do_orange » devient l'orange clignotant (« do_orange_cli »).
    À appeler à l'ouverture d'un fichier ; valider() et calculer_plan() l'appliquent aussi sur une copie."""
    for r in projet.get('radios', []):
        for p in r.get('peripheriques', []):
            if p.get('type') == 'FEU':
                if 'do_orange' in p:
                    p.setdefault('do_orange_cli', p['do_orange']); del p['do_orange']
                for cle, _l, _b in SORTIES_FEU:
                    p.setdefault(cle, None)
    return projet


def _normalise(projet):
    import copy
    return normaliser_projet(copy.deepcopy(projet))


RE_NOM = re.compile(r'^[A-Za-z0-9_-]{1,20}$')
RE_NOM_PERIPH = re.compile(r'^[A-Za-z0-9_]{1,15}$')
CARS_INTERDITS = set('<>&"\' ')


# ---------------------------------------------------------------- utilitaires
MOIS_EN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def _heure_us(d):
    """'5:28:39 PM' — indépendant de la langue de Windows (ne jamais utiliser %p / %b)."""
    h = d.hour % 12 or 12
    return f"{h}:{d.minute:02d}:{d.second:02d} {'AM' if d.hour < 12 else 'PM'}"


def date_cfgversion(d):
    """CfgVersion CConfig : '12-May-2026 5:28:39 PM'."""
    return f"{d.day}-{MOIS_EN[d.month - 1]}-{d.year} {_heure_us(d)}"


def date_projet(d):
    """Attribut Date de <CConfig> : '6/10/2026 8:00:42 AM' (jour/mois/année)."""
    return f"{d.day}/{d.month}/{d.year} {_heure_us(d)}"

def generer_cle(longueur=24):
    """Clé de chiffrement (WPA passphrase) : 24 caractères, sans < > & " ' ni espace."""
    alphabet = string.ascii_letters + string.digits + '!#$%()*+,-./:;=?@[]^_{|}~'
    while True:
        k = ''.join(secrets.choice(alphabet) for _ in range(longueur))
        if (any(c.islower() for c in k) and any(c.isupper() for c in k)
                and any(c.isdigit() for c in k) and any(not c.isalnum() for c in k)):
            return k


def nom_fichier(texte, defaut='projet'):
    """Nom de fichier propre : toute suite de caractères hors A-Z a-z 0-9 devient un seul '_',
    sans '_' au début ni à la fin.  'Demo Site - A' -> 'Demo_Site_A'."""
    import unicodedata
    texte = unicodedata.normalize('NFKD', texte or '').encode('ascii', 'ignore').decode('ascii')   # é -> e
    return re.sub(r'[^A-Za-z0-9]+', '_', texte).strip('_') or defaut


def ma_vers_brut(ma):
    """4 mA = 16384, 20 mA = 49152."""
    return int(round(16384 + (ma - 4.0) * 2048))


def nettoyer_commentaire(txt):
    """La page IO Plus refuse < > & " ' dans les commentaires."""
    return ''.join(c for c in txt if c not in '<>&"\'')[:60]


# ---------------------------------------------------------------- version de configuration
VERSION_DEFAUT = '1.0'
RE_VERSION = re.compile(r'^(\d{1,4})\.(\d{1,4})$')


def version_config(projet):
    """Version de configuration du projet ('X.Y'). Absente = '1.0'."""
    return projet.get('version_config') or VERSION_DEFAUT


def _contenu(projet):
    """Partie du projet qui définit la configuration (sans version ni historique), normalisée."""
    import json as _j
    c = _j.loads(_j.dumps({'systeme': projet.get('systeme', {}), 'radios': projet.get('radios', [])}))
    if not c['systeme'].get('ioplus_actif'):
        c['systeme'].pop('ioplus_actif', None)        # option absente = false : pas de différence pour les anciens projets
    return c


def _radios_appariees(anc, nouv):
    """Associe les radios de l'ancien et du nouveau projet.
    Par nom ; les noms restants sont considérés comme renommés s'ils occupent les mêmes positions.
    Retourne la liste des paires (ancienne, nouvelle) ou None si des radios ont été ajoutées/supprimées."""
    na = [r.get('nom') for r in anc]; nn = [r.get('nom') for r in nouv]
    if len(na) != len(nn):
        return None
    paires = []
    for i, (a, n) in enumerate(zip(anc, nouv)):
        if a.get('nom') == n.get('nom'):
            paires.append((a, n))
        elif a.get('nom') not in nn and n.get('nom') not in na:
            paires.append((a, n))                      # renommage sur place
        else:
            return None                                # déplacement, ajout ou suppression
    return paires


def _types_periph(r):
    return sorted(p.get('type', '') for p in r.get('peripheriques', []))


def classer_modification(ancien, nouveau):
    """Compare deux projets. Retourne 'majeure', 'mineure' ou None (aucune modification).
    Majeure : radio ajoutée, supprimée ou déplacée dans la liste (les numéros de registres changent),
              périphérique ajouté, supprimé ou remplacé par un autre type,
              surveillance MAINV activée ou désactivée (un registre lu en plus ou en moins),
              tout registre existant de la base qui disparaît ou change de type ou de radio (ex. entrée d'un
              câble déplacée sur une remote, ce qui décale les 150nn). Un registre simplement AJOUTÉ (ex. sortie
              ajoutée à un feu) ne décale rien : mineure.
    Mineure : tout autre changement (sortie d'un périphérique, entrée qui ne décale aucun registre, entrée MAINV, IP, puissance, rôle,
              amont, nom, inversion, textes, clé...)."""
    a, n = _contenu(_normalise(ancien)), _contenu(_normalise(nouveau))
    if a == n:
        return None
    paires = _radios_appariees(a['radios'], n['radios'])
    if paires is None:
        return 'majeure'
    if any(_types_periph(x) != _types_periph(y) for x, y in paires):
        return 'majeure'
    if any(bool((x.get('mainv') or {}).get('actif')) != bool((y.get('mainv') or {}).get('actif')) for x, y in paires):
        return 'majeure'                               # MAINV activé/désactivé : un registre lu en plus ou en moins
    ca, cn = _carte_registres(ancien), _carte_registres(nouveau)
    if ca is not None and cn is not None and any(cn.get(adr) != v for adr, v in ca.items()):
        return 'majeure'                               # v1.9 : un registre existant disparaît ou change de sens (décalage)
    return 'mineure'


def _carte_registres(projet):
    """Plan de registres de la base : {adresse: identité}. None si le projet est invalide.
    Identité = type de registre + rang de la radio (pas son nom) + pour les détections et commandes,
    le périphérique désigné par son rang dans la liste de la radio (pas son nom) : renommer reste mineur,
    mais un registre qui désigne désormais un autre équipement est détecté."""
    try:
        pl = calculer_plan(projet)
    except Exception:
        return None
    carte = {}
    for S in pl['stations']:
        rangs = sorted(((p.get('nom', ''), i) for i, p in enumerate(S['periph'])), key=lambda x: -len(x[0]))

        def ident(label):
            for nom, i in rangs:
                if nom and (label == nom or label.startswith(nom + '_')):
                    return f'P{i}' + label[len(nom):]
            return label
        for d in S['detections']:
            carte[d['adresse']] = ('DET', S['index'], ident(d['label']) if d['label'] else ('LIBRE', d['di']))
        for c in S['commandes']:
            carte[c['adresse']] = ('CMD', S['index'], ident(c['label']))
        for X in S['ana']:
            carte[X['adresse']] = ('ANA', S['index'], ident(X['label']))
        for X in S['consignes']:
            carte[X['adresse']] = ('AO', S['index'], ident(X['label']))
    rang = {S['nom']: S['index'] for S in pl['stations']}
    for r in pl['registres']:
        carte.setdefault(r['adresse'], (r['type'], rang.get(r['station'])))
    return carte


def prochaine_version(version, niveau):
    """'2.3' + majeure -> '3.0' ; '2.3' + mineure -> '2.4' ; niveau None -> inchangée."""
    m = RE_VERSION.match(version or '') or RE_VERSION.match(VERSION_DEFAUT)
    x, y = int(m.group(1)), int(m.group(2))
    if niveau == 'majeure':
        return f'{x + 1}.0'
    if niveau == 'mineure':
        return f'{x}.{y + 1}'
    return f'{x}.{y}'


def preparer_generation(projet):
    """À appeler à chaque « Générer la configuration ».
    Compare au contenu de la dernière génération (projet['derniere_generation']) et incrémente la version.
    Première génération (pas d'historique) : la version reste celle du projet (1.0 par défaut).
    Retourne (nouveau_projet, niveau) ; le projet d'entrée n'est pas modifié."""
    p = _normalise(projet)
    ref = p.get('derniere_generation')
    niveau = classer_modification(ref, p) if ref is not None else None
    p['version_config'] = prochaine_version(version_config(p), niveau)
    p['derniere_generation'] = _contenu(p)
    return p, niveau


def base_nom_fichier(plan_ou_projet):
    """Préfixe commun des fichiers générés : <nom_projet>_V<version>.  ex. 'Demo_Site_A_V2.1'."""
    s = plan_ou_projet['systeme']
    return f"{nom_fichier(s['nom_projet'])}_V{plan_ou_projet.get('version_config') or VERSION_DEFAUT}"


# ---------------------------------------------------------------- validation
def valider(projet):
    """Retourne la liste des erreurs (liste vide = projet valide)."""
    projet = _normalise(projet)
    E = []
    s = projet.get('systeme', {})
    radios = projet.get('radios', [])
    if not s.get('nom_projet'):
        E.append('Système : le nom du projet est obligatoire.')
    if not re.match(r'^[A-Za-z0-9_-]{1,32}$', s.get('system_name', '')):
        E.append('Système : « System Name » obligatoire, lettres/chiffres/_/- , 32 caractères max.')
    pp = s.get('cle_chiffrement', '')
    if not (8 <= len(pp) <= 63) or ' ' in pp or not all(33 <= ord(c) <= 126 for c in pp):
        E.append('Système : clé de chiffrement de 8 à 63 caractères ASCII imprimables, sans espace.')
    if not (10 <= int(s.get('puissance_dbm', 34)) <= 40):
        E.append('Système : puissance entre 10 et 40 dBm.')
    textes = [v for v in s.values() if isinstance(v, str)] + [str(r.get(k) or '') for r in radios
                                                               for k in ('description', 'titre_page')]
    if any(']]>' in t for t in textes):
        E.append('Textes : la suite « ]]> » est interdite (fichiers XML des radios).')
    if not isinstance(s.get('ioplus_actif', False), bool):
        E.append('Système : « IO Plus activé » doit valoir true ou false.')
    if not RE_VERSION.match(version_config(projet)):
        E.append('Version de configuration : format X.Y attendu (ex. 2.1).')
    if not radios:
        E.append('Aucune radio.')
        return E
    if len(radios) > MAX_RADIOS:
        E.append(f'{len(radios)} radios : maximum {MAX_RADIOS}.')
    bases = [r for r in radios if r.get('role') == 'base']
    if len(bases) != 1:
        E.append('Il faut exactement une radio de rôle « base ».')
    elif radios[0].get('role') != 'base':
        E.append('La base doit être la première radio de la liste.')
    noms = [r.get('nom', '') for r in radios]
    for n in noms:
        if not RE_NOM.match(n):
            E.append(f'Radio « {n} » : nom de 1 à 20 caractères, lettres/chiffres/_/- uniquement.')
    if len(set(noms)) != len(noms):
        E.append('Deux radios portent le même nom.')
    ips = []
    for i, r in enumerate(radios):
        n = r.get('nom', f'#{i+1}')
        ip = r.get('ip_octet')
        if not isinstance(ip, int) or not (100 <= ip <= 254):
            E.append(f'{n} : dernier octet IP entre 100 et 254.')
        ips.append(ip)
        role = r.get('role')
        if role not in ('base', 'remote', 'repeater'):
            E.append(f'{n} : rôle inconnu « {role} ».')
        if role in ('remote', 'repeater'):
            am = r.get('amont')
            cible = next((x for x in radios if x.get('nom') == am), None)
            if cible is None or cible.get('role') not in ('base', 'repeater') or am == n:
                E.append(f'{n} : l\'amont doit être la base ou un repeater.')
        pw = r.get('puissance_dbm')
        if pw is not None and not (10 <= int(pw) <= 40):
            E.append(f'{n} : puissance entre 10 et 40 dBm.')
        # E/S
        di_used, do_used, ai_used, ao_used, noms_p = {}, {}, {}, {}, set()
        mv = r.get('mainv', {})
        if mv.get('actif'):
            di = mv.get('di', 8)
            if not 1 <= di <= 8:
                E.append(f'{n} : MAINV sur une DI entre 1 et 8.')
            di_used[di] = 'MAINV'
        for p in r.get('peripheriques', []):
            t, pn = p.get('type'), p.get('nom', '')
            if t not in TYPES:
                E.append(f'{n} : type de périphérique inconnu « {t} ».'); continue
            if not RE_NOM_PERIPH.match(pn):
                E.append(f'{n} : nom de périphérique « {pn} » : 1 à 15 caractères, lettres/chiffres/_.')
            if pn in noms_p:
                E.append(f'{n} : deux périphériques s\'appellent « {pn} ».')
            noms_p.add(pn)
            if t in TYPES_ENTREE:
                dis = p.get('di', [])
                if len(dis) != TYPES_ENTREE[t]:
                    E.append(f'{n}/{pn} : {TYPES_ENTREE[t]} entrée(s) DI attendue(s).')
                for d in dis:
                    if not 1 <= d <= 8: E.append(f'{n}/{pn} : DI{d} n\'existe pas (1 à 8).')
                    elif d in di_used: E.append(f'{n}/{pn} : DI{d} déjà utilisée par {di_used[d]}.')
                    else: di_used[d] = pn
            elif t == 'RADAR':
                a = p.get('ai')
                if a not in (1, 2, 3, 4): E.append(f'{n}/{pn} : AI1 à AI4 uniquement (4-20 mA).')
                elif a in ai_used: E.append(f'{n}/{pn} : AI{a} déjà utilisée par {ai_used[a]}.')
                else: ai_used[a] = pn
                sh = p.get('seuil_haut_ma')
                hy = p.get('hysteresis_ma', 0.8); va = p.get('variation_ma', 0.8); tm = p.get('tmin_s', 10)
                if sh is None or not (4.0 < sh < 20.0): E.append(f'{n}/{pn} : seuil haut entre 4 et 20 mA.')
                elif not (0.1 <= hy < sh - 4.0): E.append(f'{n}/{pn} : hystérésis entre 0,1 mA et (seuil − 4 mA).')
                if not (0.1 <= va <= 8.0): E.append(f'{n}/{pn} : variation entre 0,1 et 8 mA.')
                if not (1 <= tm <= 3600): E.append(f'{n}/{pn} : intervalle mini entre 1 et 3600 s.')
                m4, m20 = p.get('mesure_4ma'), p.get('mesure_20ma')
                if (m4 is None) != (m20 is None):
                    E.append(f'{n}/{pn} : échelle incomplète (mesure à 4 mA et mesure à 20 mA).')
                elif m4 is not None:
                    if not all(isinstance(x, (int, float)) for x in (m4, m20)) or m4 == m20:
                        E.append(f'{n}/{pn} : mesures à 4 mA et à 20 mA différentes et numériques.')
                    u = p.get('unite', 'cm')
                    if not (1 <= len(u) <= 8) or set(u) & CARS_INTERDITS:
                        E.append(f'{n}/{pn} : unité de 1 à 8 caractères, sans espace ni < > & " \'.')
            elif t == 'ENTREE_ANA':
                a, mode = p.get('ai'), p.get('mode', 'courant')
                if mode not in ('courant', 'tension'):
                    E.append(f'{n}/{pn} : mode « courant » (0-20 mA) ou « tension » (0-5 V).')
                elif a not in (1, 2, 3, 4) or (mode == 'tension' and a not in (3, 4)):
                    E.append(f'{n}/{pn} : AI1 à AI4 en courant, AI3 ou AI4 en tension.')
                elif a in ai_used: E.append(f'{n}/{pn} : AI{a} déjà utilisée par {ai_used[a]}.')
                else: ai_used[a] = pn
                E += _valider_echelle(n, pn, p)
                E += _valider_reglages_ai(n, pn, p)
            elif t == 'SORTIE_ANA':
                o = p.get('ao')
                if o not in (1, 2): E.append(f'{n}/{pn} : AO1 ou AO2 uniquement.')
                elif o in ao_used: E.append(f'{n}/{pn} : AO{o} déjà utilisée par {ao_used[o]}.')
                else: ao_used[o] = pn
                E += _valider_echelle(n, pn, p)
            else:
                dos = sorties_du_periph(p)
                for d in dos:
                    if d is None: continue
                    if not 1 <= d <= 8: E.append(f'{n}/{pn} : DO{d} n\'existe pas (1 à 8).')
                    elif d in do_used: E.append(f'{n}/{pn} : DO{d} déjà utilisée par {do_used[d]}.')
                    else: do_used[d] = pn
                if t == 'FEU' and (p.get('do_rouge') is None or
                                   (p.get('do_orange_cli') is None and p.get('do_orange_fixe') is None)):
                    E.append(f'{n}/{pn} : un feu a obligatoirement une sortie rouge et au moins une sortie orange '
                             f'(clignotant ou fixe).')
        radars = sorted(p['ai'] for p in r.get('peripheriques', []) if p.get('type') == 'RADAR' and p.get('ai') in (1, 2, 3, 4))
        if radars and radars != list(range(radars[0], radars[0] + len(radars))):
            E.append(f'{n} : les radars doivent être sur des AI consécutives (ex. AI1+AI2).')
    if len(set(ips)) != len(ips):
        E.append('Deux radios ont la même adresse IP.')
    # cycles d'amont
    par_nom = {r.get('nom'): r for r in radios}
    for r in radios:
        vus, c = set(), r
        while c and c.get('role') != 'base':
            if c.get('nom') in vus:
                E.append(f'{r.get("nom")} : boucle dans la chaîne d\'amont.'); break
            vus.add(c.get('nom')); c = par_nom.get(c.get('amont'))
    # capacités du plan de registres
    nb_feux = sum(1 for r in radios for p in r.get('peripheriques', []) if p.get('type') == 'FEU')
    nb_autres = sum(1 for r in radios for p in r.get('peripheriques', [])
                    if p.get('type') in TYPES_SORTIE_SIMPLE or p.get('type') == 'CAMERA_SPOT')
    if nb_feux > 10: E.append(f'{nb_feux} feux : maximum 10 (registres 401–430 et 441–450).')
    if nb_autres > 10: E.append(f'{nb_autres} signalisations autres : maximum 10 (registres 431–440).')
    nb_ana = sum(1 for r in radios for p in r.get('peripheriques', []) if p.get('type') == 'ENTREE_ANA')
    nb_ao = sum(1 for r in radios for p in r.get('peripheriques', []) if p.get('type') == 'SORTIE_ANA')
    if nb_ana > MAX_ANA: E.append(f'{nb_ana} entrées analogiques : maximum {MAX_ANA} (registres 35301–35350).')
    if nb_ao > MAX_AO: E.append(f'{nb_ao} sorties analogiques : maximum {MAX_AO} (registres 45001–45020).')
    nb_det = nombre_detections(radios)
    if nb_det > MAX_DETECTIONS:
        E.append(f'{nb_det} registres de détection nécessaires : maximum {MAX_DETECTIONS} (registres 15001–15100 ; '
                 f'au-delà ils chevaucheraient les comflags 151xx). Sur une remote, les entrées libres entre la '
                 f'première et la dernière entrée utilisée comptent aussi.')
    return E


MAX_DETECTIONS = 100         # 15001-15100 ; 15101+ = comflags


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _valider_reglages_ai(n, pn, p):
    """Réglages avancés d'une entrée analogique (v2.3), facultatifs :
    etalonnage = {reg_bas, reg_haut, eng_bas, eng_haut} : conversion de la radio (CConfig : RegLow/RegHigh/EngLow/EngHigh,
                 d'où Zero et Span) ; la valeur du registre vaut reg_bas pour eng_bas et reg_haut pour eng_haut ;
    alarme_radio = {bas, haut, fenetre} : seuils de l'entrée dans la radio (SPLow/SPHigh/SPWindow)."""
    E = []
    et = p.get('etalonnage')
    if et is not None:
        ok = isinstance(et, dict) and all(_num(et.get(k)) for k in ('reg_bas', 'reg_haut', 'eng_bas', 'eng_haut'))
        if not ok or not (0 <= et['reg_bas'] < et['reg_haut'] <= 65535) or et['eng_bas'] == et['eng_haut'] \
                or int(et['reg_bas']) != et['reg_bas'] or int(et['reg_haut']) != et['reg_haut']:
            E.append(f'{n}/{pn} : étalonnage : registre bas < registre haut (entiers 0-65535), valeurs bas/haut différentes.')
        if p.get('mesure_bas') is not None or p.get('mesure_haut') is not None:
            E.append(f'{n}/{pn} : étalonnage et échelle ne se cumulent pas (l\'étalonnage donne déjà l\'échelle).')
        u = p.get('unite', 'V')
        if not (1 <= len(u) <= 8) or set(u) & CARS_INTERDITS:
            E.append(f'{n}/{pn} : unité de 1 à 8 caractères, sans espace ni < > & " \'.')
    al = p.get('alarme_radio')
    if al is not None:
        if not (isinstance(al, dict) and _num(al.get('bas')) and _num(al.get('haut')) and al['bas'] <= al['haut']
                and al.get('fenetre', 0) in (0, 1)):
            E.append(f'{n}/{pn} : alarme radio : seuil bas ≤ seuil haut, fenêtre 0 ou 1.')
    return E


def reglages_ai(p):
    """Champs de l'E/S de la radio pour une entrée analogique : {Zero, Span, RegLow, RegHigh, EngLow, EngHigh,
    SPLow, SPHigh, SPWindow} ; seuls les champs à changer sont présents (vide = réglage standard)."""
    r = {}
    et = p.get('etalonnage')
    if et:
        span = (et['reg_haut'] - et['reg_bas']) / (et['eng_haut'] - et['eng_bas'])
        r.update(Zero=_fmt(et['reg_bas'] - et['eng_bas'] * span), Span=_fmt(round(span, 5)),
                 RegLow=int(et['reg_bas']), RegHigh=int(et['reg_haut']),
                 EngLow=_fmt(et['eng_bas']), EngHigh=_fmt(et['eng_haut']))
    al = p.get('alarme_radio')
    if al:
        r.update(SPLow=_fmt(al['bas']), SPHigh=_fmt(al['haut']), SPWindow=int(al.get('fenetre', 0)))
    return r


def _valider_echelle(n, pn, p):
    """Échelle facultative d'une E/S analogique générique : mesure_bas / mesure_haut / unite."""
    E = []
    b, h = p.get('mesure_bas'), p.get('mesure_haut')
    if (b is None) != (h is None):
        E.append(f'{n}/{pn} : échelle incomplète (valeur basse et valeur haute).')
    elif b is not None:
        if not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (b, h)) or b == h:
            E.append(f'{n}/{pn} : valeurs basse et haute différentes et numériques.')
        u = p.get('unite', '')
        if not (1 <= len(u) <= 8) or set(u) & CARS_INTERDITS:
            E.append(f'{n}/{pn} : unité de 1 à 8 caractères, sans espace ni < > & " \'.')
    return E


def nombre_detections(radios):
    """Nombre de registres 150nn utilisés, compté exactement comme calculer_plan :
    base = entrées utilisées ; remote = de la plus petite à la plus grande entrée utilisée (trous compris)."""
    n = 0
    for r in radios:
        dis = set()
        for p in r.get('peripheriques', []):
            if p.get('type') in TYPES_ENTREE:
                dis.update(d for d in (p.get('di') or []) if isinstance(d, int))
        if dis:
            n += len(dis) if r.get('role') == 'base' else max(dis) - min(dis) + 1
    return n


def sorties_du_periph(p):
    t = p.get('type')
    if t == 'FEU':
        return [p.get(cle) for cle, _l, _b in SORTIES_FEU]
    if t == 'CAMERA_SPOT':
        return [p.get('do_camera'), p.get('do_spot')]
    if t in TYPES_SORTIE_SIMPLE:
        return [p.get('do')]
    return []


# ---------------------------------------------------------------- calcul du plan
def calculer_plan(projet):
    err = valider(projet)
    if err:
        raise ValueError('Projet invalide :\n- ' + '\n- '.join(err))
    projet = _normalise(projet)
    s = projet['systeme']
    radios = projet['radios']
    st = []
    for i, r in enumerate(radios):
        xx = f'{i + 1:02d}'
        st.append({
            'nom': r['nom'], 'uid': f'UID{i + 1}', 'index': i + 1, 'xx': xx, 'role': r['role'],
            'ip': f"{RESEAU}.{r['ip_octet']}", 'amont': r.get('amont', '') if r['role'] != 'base' else '',
            'puissance_dbm': int(r.get('puissance_dbm') or s.get('puissance_dbm', 34)),
            'titre_page': r.get('titre_page') or r['nom'],
            'description': r.get('description') or s.get('description', ''),
            'inv_entrees': bool(r.get('inversion_entrees')), 'inv_sorties': bool(r.get('inversion_sorties')),
            'mainv': r.get('mainv', {}) if r.get('mainv', {}).get('actif') else None,
            'periph': r.get('peripheriques', []),
            'reads': [], 'scatters': [], 'writes': [], 'failsafe': [], 'sensibilite': None,
            'noms_registres': [], 'noms_io': {}, 'debounce': {},
            'tags': [], 'groupes': [], 'iop': None, 'ack': ACK_DEFAUT,
            'detections': [], 'commandes': [], 'radars': [], 'ana': [], 'consignes': [],
        })
    base = st[0]
    registres = []          # table complète des registres de la base (Excel / PDF)

    pris = set()

    def nomu(station, label):
        """Nom court (NOM_MAX caractères) et unique sur le site."""
        n, i = nom_court(station, label), 2
        while n in pris:
            n = nom_court(station, label, NOM_MAX - len(str(i))) + str(i); i += 1
        pris.add(n)
        return n

    def reg(adr, nom, typ, station, desc):
        registres.append({'adresse': adr, 'nom': nom, 'type': typ, 'station': station, 'description': desc})

    # ---- détections 150nn (ordre des stations, puis DI croissante, trous = NON_UTILISE)
    nn = 0
    for S in st:
        dis = {}
        for p in S['periph']:
            t = p['type']
            if t in TYPES_ENTREE:
                for j, d in enumerate(p['di']):
                    lab = p['nom'] if TYPES_ENTREE[t] == 1 else f"{p['nom']}_{j + 1}"
                    dis[d] = (lab, t)
        if not dis:
            continue
        if S['role'] == 'base':
            ordre = sorted(dis)
        else:
            ordre = list(range(min(dis), max(dis) + 1))
        for d in ordre:
            nn += 1
            adr = 15000 + nn
            if d in dis:
                lab, t = dis[d]
                nom = nomu(S['nom'], lab)
            else:
                lab, t, nom = None, None, nomu(S['nom'], f"LIBRE_DI{d}")
            S['detections'].append({'di': d, 'adresse': adr, 'nom': nom, 'label': lab, 'type': t})
            reg(adr, nom, 'Détection', S['nom'], f'DI{d}' + ('' if lab else ' (non câblée)'))
    # ---- commandes : rouge 401-410, orange clignotant 411-420, orange fixe 421-430, autres 431-440, vert 441-450
    n_feu, n_autre = 0, 0
    for S in st:
        for p in S['periph']:
            t = p['type']
            if t == 'FEU':
                n_feu += 1
                for cle, coul, base_r in SORTIES_FEU:
                    if p.get(cle) is not None:
                        adr = base_r + n_feu
                        nom = nomu(S['nom'], f"{p['nom']}_{coul}")
                        S['commandes'].append({'adresse': adr, 'nom': nom, 'do': [p[cle]], 'label': f"{p['nom']}_{coul}",
                                              'genre': f'FEU_{coul}'})
                        reg(adr, nom, f"Commande feu {LIBELLES_FEU[coul]}",
                            S['nom'], f"DO{p[cle]}")
            elif t in TYPES_SORTIE_SIMPLE or t == 'CAMERA_SPOT':
                n_autre += 1
                adr = BASE_AUTRES + n_autre
                nom = nomu(S['nom'], p['nom'])
                dos = [p['do']] if t != 'CAMERA_SPOT' else [p['do_camera'], p['do_spot']]
                S['commandes'].append({'adresse': adr, 'nom': nom, 'do': dos, 'label': p['nom'], 'genre': t})
                reg(adr, nom, 'Commande signalisation', S['nom'], '+'.join(f'DO{d}' for d in dos))
    # ---- radars 352nn
    rn = 0
    for S in st:
        rad = sorted([p for p in S['periph'] if p['type'] == 'RADAR'], key=lambda p: p['ai'])
        for k, p in enumerate(rad, start=1):
            rn += 1
            adr = 35200 + rn
            nom = nomu(S['nom'], p['nom'])
            S['radars'].append({'k': k, 'ai': p['ai'], 'adresse': adr, 'nom': nom, 'label': p['nom'],
                                'force': 500 + k, 'bloc': 40500 + 10 * k,
                                'S_HAUT': ma_vers_brut(p['seuil_haut_ma']),
                                'S_BAS': ma_vers_brut(p['seuil_haut_ma'] - p.get('hysteresis_ma', 0.8)),
                                'D': int(round(p.get('variation_ma', 0.8) * 2048)),
                                'TMIN': int(p.get('tmin_s', 10)) * 4,
                                'seuil_haut_ma': p['seuil_haut_ma'], 'hysteresis_ma': p.get('hysteresis_ma', 0.8),
                                'variation_ma': p.get('variation_ma', 0.8), 'tmin_s': p.get('tmin_s', 10),
                                'mesure_4ma': p.get('mesure_4ma'), 'mesure_20ma': p.get('mesure_20ma'),
                                'unite': p.get('unite', 'cm') if p.get('mesure_20ma') is not None else 'mA'})
            R = S['radars'][-1]
            if R['mesure_20ma'] is not None:
                desc = (f"AI{p['ai']} : 16384 = 4 mA = {_fmt(R['mesure_4ma'])} {R['unite']}, "
                        f"49152 = 20 mA = {_fmt(R['mesure_20ma'])} {R['unite']}")
            else:
                desc = f"AI{p['ai']} : 16384 = 4 mA, 49152 = 20 mA"
            reg(adr, nom, 'Radar (brut 4-20 mA)', S['nom'], desc)

    # ---- entrées analogiques génériques 353nn et consignes de sortie analogique 450nn (v2.0)
    an = ao = 0
    for S in st:
        for p in sorted([p for p in S['periph'] if p['type'] == 'ENTREE_ANA'], key=registre_ai):
            an += 1
            mode = p.get('mode', 'courant')
            rp1, rp2, e1, e2, ue = ANA_POINTS[mode]
            A = {'adresse': ANA_BASE + an, 'nom': nomu(S['nom'], p['nom']), 'label': p['nom'], 'ai': p['ai'], 'mode': mode,
                 'distant': registre_ai(p), 'io': io_ai(p), 'rp1': rp1, 'rp2': rp2,
                 'dp1': p.get('mesure_bas', e1), 'dp2': p.get('mesure_haut', e2),
                 'unite': p.get('unite') if p.get('mesure_bas') is not None else ue,
                 'reglages': reglages_ai(p), 'alarme': p.get('alarme_radio')}
            et = p.get('etalonnage')
            if et:                                     # v2.3 : l'étalonnage de la radio donne l'échelle du registre
                A.update(rp1=int(et['reg_bas']), rp2=int(et['reg_haut']), dp1=et['eng_bas'], dp2=et['eng_haut'],
                         unite=p.get('unite', 'V'))
            S['ana'].append(A)
            ent = (f"AI{p['ai']} {'courant' if mode == 'courant' else 'tension'}, étalonnage" if et
                   else f"AI{p['ai']} {'0-20 mA' if mode == 'courant' else '0-5 V'}")
            reg(A['adresse'], A['nom'], 'Mesure analogique', S['nom'],
                f"{ent} : {A['rp1']} = {_fmt(A['dp1'])} {A['unite']}, {A['rp2']} = {_fmt(A['dp2'])} {A['unite']}")
        for p in sorted([p for p in S['periph'] if p['type'] == 'SORTIE_ANA'], key=lambda p: p['ao']):
            ao += 1
            rp1, rp2, e1, e2, ue = AO_POINTS
            c = {'adresse': AO_BASE + ao, 'nom': nomu(S['nom'], p['nom']), 'label': p['nom'], 'ao': p['ao'],
                 'distant': 40000 + p['ao'], 'io': f"Aot{p['ao']}", 'rp1': rp1, 'rp2': rp2,
                 'dp1': p.get('mesure_bas', e1), 'dp2': p.get('mesure_haut', e2),
                 'unite': p.get('unite') if p.get('mesure_bas') is not None else ue}
            S['consignes'].append(c)
            reg(c['adresse'], c['nom'], 'Consigne sortie analogique', S['nom'],
                f"AO{p['ao']} 4-20 mA : écrire {rp1} = {_fmt(c['dp1'])} {c['unite']} … {rp2} = {_fmt(c['dp2'])} {c['unite']}")

    # ---- registres d'état par station
    for S in st:
        xx = S['xx']
        reg(int(f'305{xx}'), nomu(S['nom'], 'BATTV'), 'Tension batterie', S['nom'], '8192 = 0 V, 49152 = 40 V')
        reg(int(f'351{xx}'), nomu(S['nom'], 'RSSI'), 'RSSI', S['nom'], 'dBm (valeur négative)')
        if S['mainv']:
            reg(int(f'105{xx}'), nomu(S['nom'], 'MAINV'), 'Secteur présent', S['nom'], f"DI{S['mainv'].get('di', 8)}")
        if S['role'] != 'base':
            reg(int(f'151{xx}'), nomu(S['nom'], 'COMFLAG'), 'Comflag (1 = perte comm)', S['nom'], 'calculé par IO Plus')
            # Les registres d'échec (152xx–157xx, 15501) restent utilisés par les mappings et l'IO Plus,
            # mais ne figurent pas dans la liste des registres : sans intérêt pour l'exploitation.

    # ---- créneaux de polling
    rem = st[1:]
    sequence = []
    for S in rem:
        sequence.append(('READ', S, 'BATTV')); sequence.append(('READ', S, 'RSSI'))
    for S in rem:
        if S['mainv']: sequence.append(('READ', S, 'MAINV'))
    for S in rem:
        if S['detections']: sequence.append(('READ', S, 'DET'))
    for S in rem:
        if S['radars']: sequence.append(('READ', S, 'RADAR'))
    for S in rem:
        for j, run in enumerate(_series(S['ana']), start=1):
            sequence.append(('READ', S, ('ANA', j, run)))
    for S in rem:
        if S['commandes'] or S['consignes']: sequence.append(('SGNL', S, None))
    T = max(1, len(sequence)) * CRENEAU_S
    creneaux = []
    for k, (typ, S, what) in enumerate(sequence):
        off = k * CRENEAU_S
        xx = S['xx']
        if typ == 'READ':
            if what == 'BATTV':
                m = dict(nom=f"{S['nom']}_ReadBATTV", local=int(f'305{xx}'), distant=30007, nb=1, fail=int(f'152{xx}'), inv=0)
            elif what == 'RSSI':
                m = dict(nom=f"{S['nom']}_ReadRSSI", local=int(f'351{xx}'), distant=30401, nb=1, fail=int(f'153{xx}'), inv=0)
            elif what == 'MAINV':
                m = dict(nom=f"{S['nom']}_ReadMAINV", local=int(f'105{xx}'), distant=10000 + S['mainv'].get('di', 8), nb=1, fail=int(f'156{xx}'), inv=0)
            elif what == 'DET':
                d0 = S['detections'][0]
                m = dict(nom=f"{S['nom']}_ReadDET", local=d0['adresse'], distant=10000 + d0['di'], nb=len(S['detections']),
                         fail=int(f'154{xx}'), inv=1 if S['inv_entrees'] else 0)
            elif isinstance(what, tuple):
                _, j, run = what
                m = dict(nom=f"{S['nom']}_ReadANA{j}", local=run[0]['adresse'], distant=run[0]['distant'], nb=len(run),
                         fail=int(f'158{xx}'), inv=0)
            else:
                r0 = S['radars'][0]
                m = dict(nom=f"{S['nom']}_ReadRADAR", local=r0['adresse'], distant=30000 + r0['ai'], nb=len(S['radars']),
                         fail=int(f'157{xx}'), inv=0)
            m.update(dest=S['uid'], periode=T, offset=off, timeout=TIMEOUT_S)
            base['reads'].append(m)
            creneaux.append({'k': k + 1, 'offset': off, 'type': 'Lecture', 'mapping': m['nom'], 'station': S['nom'],
                             'ip': S['ip'], 'failreg': m['fail']})
        else:
            paires = [(c['adresse'], d) for c in S['commandes'] for d in c['do']] + \
                     [(c['adresse'], c['distant']) for c in S['consignes']]
            m = dict(nom=f"{S['nom']}-SGNL", dest=S['uid'], periode=T, offset=off, fail=int(f'155{xx}'),
                     paires=paires, inv=1 if S['inv_sorties'] else 0, ack=1)
            base['scatters'].append(m)
            creneaux.append({'k': k + 1, 'offset': off, 'type': 'Commandes', 'mapping': m['nom'], 'station': S['nom'],
                             'ip': S['ip'], 'failreg': m['fail']})
    # ---- mappings locaux de la base
    if base['commandes'] or base['consignes']:
        base['scatters'].insert(0, dict(nom=f"{base['nom']}-SGNL", dest='local', periode=0, offset=0, fail=15501,
                                        paires=[(c['adresse'], d) for c in base['commandes'] for d in c['do']] +
                                               [(c['adresse'], c['distant']) for c in base['consignes']],
                                        inv=1 if base['inv_sorties'] else 0, ack=1))
    if base['detections']:
        base['scatters'].append(dict(nom=f"{base['nom']}-ALM", dest='local', periode=0, offset=0, fail=0,
                                     paires=[(10000 + d['di'], d['adresse']) for d in base['detections']],
                                     inv=1 if base['inv_entrees'] else 0, ack=1))
    dftl = []
    if base['mainv']:
        dftl.append((10000 + base['mainv'].get('di', 8), 10501))
    dftl += [(30007, 30501), (30401, 35101)]
    # radar sur la base : copie locale de l'entrée analogique dans son registre 352nn (pas d'IO Plus, pas de radio)
    dftl += [(30000 + R['ai'], R['adresse']) for R in base['radars']]
    dftl += [(A['distant'], A['adresse']) for A in base['ana']]          # entrée analogique générique sur la base
    base['scatters'].append(dict(nom=f"{base['nom']}-DFTL", dest='local', periode=0, offset=0, fail=0,
                                 paires=dftl, inv=0, ack=1))
    base['failsafe'] = [FAILSAFE_COMMANDES] + [(int(f'15{f}01'), FAILSAFE_COUNT) for f in range(1, 8)]
    if any(S['ana'] for S in rem):
        base['failsafe'].append((15801, FAILSAFE_COUNT))                # échecs de lecture analogique 158xx
    base['sensibilite'] = [(30007, 1, SENSIB_BATTV_BASE)]
    base['ack'] = ACK_FORT
    if base['mainv']:
        base['debounce'][f"Din{base['mainv'].get('di', 8)}"] = 0.5

    # ---- remotes / repeaters : écritures COS et radar
    for S in rem:
        if S['detections']:
            d0 = S['detections'][0]
            S['writes'].append(dict(nom='DET', dest='UID1', local=10000 + d0['di'], distant=d0['adresse'],
                                    nb=len(S['detections']), inv=1 if S['inv_entrees'] else 0, cos=1, force=0, ack=1))
        for R in S['radars']:
            S['writes'].append(dict(nom=f"RADAR{R['k']}", dest='UID1', local=30000 + R['ai'], distant=R['adresse'],
                                    nb=1, inv=0, cos=0, force=R['force'], ack=1))
        if S['detections'] or S['radars']:
            S['ack'] = ACK_FORT
        if S['radars']:
            S['iop'] = []
            for R in S['radars']:
                S['iop'] += bloc_radar(R)

    # ---- IO Plus de la base
    lignes = []
    for S in rem:
        xx = S['xx']
        lignes.append(ligne('LOAD', int(f'152{xx}'), f"{S['nom']} BATTV_FAIL"))
        n = 1
        for fam, cond, lab in (('153', True, 'RSSI'), ('154', bool(S['detections']), 'DET'),
                               ('156', bool(S['mainv']), 'MAINV'), ('157', bool(S['radars']), 'RADAR'),
                               ('158', bool(S['ana']), 'ANA')):
            if cond:
                lignes.append(ligne('ADD', int(f'{fam}{xx}'), f"+ {S['nom']} {lab}_FAIL")); n += 1
        lignes.append(ligne('GE', n, 'Toutes les lectures en echec', I=1))
        if S['commandes'] or S['consignes']:
            lignes.append(ligne('OR', int(f'155{xx}'), f"OU {S['nom']} SGNL_FAIL"))
        lignes.append(ligne('STOR', int(f'151{xx}'), f"{S['nom']} COMFLAG"))
    base['iop'] = lignes

    # ---- noms (UserIOsInfo), noms d'E/S, dashboards
    avertissements = []
    for S in st:
        construire_noms_et_dashboard(S, st, registres)
        avertissements += S.pop('_avert', [])

    return {'systeme': dict(s), 'stations': st, 'T': T, 'creneaux': creneaux,
            'avertissements': avertissements,
            'registres': sorted(registres, key=lambda r: r['adresse']),
            'genere_le': datetime.datetime.now().strftime('%d.%m.%Y %H:%M'),
            'version_config': version_config(projet)}


def ligne(op, val, cmt='', I=0, N=0):
    return (OP[op], I, N, 0, val, nettoyer_commentaire(cmt))


def bloc_radar(R):
    """36 lignes par radar. Sauts relatifs (I=1) comptés depuis la ligne du saut (validé sur radio)."""
    B = R['bloc']; VAL, ALM, TMR, NEW, TRIG = B + 1, B + 2, B + 4, B + 5, B + 6
    A = 30000 + R['ai']; F = R['force']; n = R['label']
    L = [
        ligne('LOAD', TMR, f'{n} tempo'),
        ligne('JMP_C', 4, 'tempo nulle = evaluation', I=1, N=1),
        ligne('SUB', 1, '', I=1),
        ligne('STOR', TMR),
        ligne('JMP', 32, 'tempo en cours = fin', I=1),
        ligne('LOAD', ALM, 'etat precedent'),
        ligne('STOR', NEW),
        ligne('LOAD', A, f'{n} valeur'),
        ligne('GE', R['S_HAUT'], 'seuil haut', I=1),
        ligne('SET', NEW),
        ligne('LOAD', A),
        ligne('LE', R['S_BAS'], 'seuil bas', I=1),
        ligne('RES', NEW),
        ligne('LOAD', NEW),
        ligne('NE', ALM, 'changement etat'),
        ligne('STOR', TRIG),
        ligne('LOAD', A, 'ecart avec valeur envoyee'),
        ligne('GE', VAL),
        ligne('JMP_C', 4, '', I=1),
        ligne('LOAD', VAL),
        ligne('SUB', A),
        ligne('JMP', 3, '', I=1),
        ligne('LOAD', A),
        ligne('SUB', VAL),
        ligne('GE', R['D'], 'variation sup ou egale D', I=1),
        ligne('OR', TRIG),
        ligne('JMP_C', 10, 'rien = fin', I=1, N=1),
        ligne('LOAD', A, 'ENVOI'),
        ligne('STOR', VAL),
        ligne('LOAD', NEW),
        ligne('STOR', ALM),
        ligne('LOAD', F),
        ligne('XOR', 1, 'inversion', I=1),
        ligne('STOR', F, f'{n} FORCE'),
        ligne('LOAD', R['TMIN'], 'tempo mini', I=1),
        ligne('STOR', TMR),
    ]
    assert len(L) == 36
    return L


MAX_TAGS = 50                # tableau de bord ELPRO : 50 tags au maximum (table Tags, maxrows 50)
TAG_OK = ('OK/NOK', 2, 0, 1, 0, 16384, 49152, 0, 100)
TAG_ONOFF = ('ON/OFF', 2, 0, 1, 0, 16384, 49152, 0, 100)
TAG_VB = ('V', 16, 9, 14.5, 11.5, 8192, 49152, 0, 40)
TAG_RSSI = ('dBm', 0, -150, -20, -95, 0, 150, 0, -150)
TAG_MA = ('mA', 21, 3.5, None, 3.8, 16384, 49152, 4, 20)


def _fmt(x):
    """1000.0 -> '1000' ; 12.5 -> '12.5'."""
    return f'{x:g}'


def tag_radar(nom, registre, R):
    """Tag de tableau de bord d'un radar : en mA, ou dans l'unité de mesure si une échelle est définie.
    Alarme haute = seuil ; alarme basse = 3,8 mA (capteur en défaut) ; hors plage < 3,5 mA ou > 21 mA."""
    if R.get('mesure_20ma') is None:
        return tag(nom, registre, TAG_MA, haut=R['seuil_haut_ma'])
    c = lambda ma: round(ma_vers_unite(ma, R), 1)
    hi, lo = c(R['seuil_haut_ma']), c(3.8)
    style = (R['unite'], c(21), c(3.5), hi, lo, 16384, 49152, _fmt(R['mesure_4ma']), _fmt(R['mesure_20ma']))
    return tag(nom, registre, style)


def tag_ana(nom, registre, X):
    """Tag d'une E/S analogique générique (mesure ou consigne) : échelle de l'utilisateur, sans alarme
    (les seuils d'alarme sont gérés par le datalogger) : alarmes placées sur les limites hors plage."""
    bas, haut = sorted((X['dp1'], X['dp2']))
    marge = (haut - bas) * 0.1
    over, under = _fmt(haut + marge), _fmt(bas - marge)
    al = X.get('alarme')                      # v2.3 : seuils de l'entrée dans la radio, repris sur le tableau de bord
    hi, lo = (_fmt(al['haut']), _fmt(al['bas'])) if al else (over, under)
    return tag(nom, registre, (X['unite'], over, under, hi, lo, X['rp1'], X['rp2'], _fmt(X['dp1']), _fmt(X['dp2'])))


def tag(nom, registre, style, invert=0, haut=None):
    u, over, under, hi, lo, rp1, rp2, dp1, dp2 = style
    if hi is None: hi = haut
    return {'nom': nom[:NOM_MAX].rstrip(' -_'), 'registre': registre, 'unites': u, 'over': over, 'under': under, 'haut': hi,
            'bas': lo, 'invert': invert, 'rp1': rp1, 'rp2': rp2, 'dp1': dp1, 'dp2': dp2}


def construire_noms_et_dashboard(S, st, registres):
    noms = [(30009, 'AI3 (0-5V)'), (30010, 'AI4 (0-5V)')]
    tags, groupes = [], []
    if S['role'] == 'base':
        noms += [(30007, 'BATTV'), (30401, 'RSSI')]
        if S['mainv']: noms.append((10000 + S['mainv'].get('di', 8), 'MAINV'))
        for d in S['detections']:
            noms.append((10000 + d['di'], d['label'] or f"DI{d['di']}"))
        for c in S['commandes']:
            for do in c['do']: noms.append((do, c['label']))
        noms += [(A['distant'], A['label']) for A in S['ana']] + [(c['distant'], c['label']) for c in S['consignes']]
        noms += [(r['adresse'], r['nom']) for r in registres]
        # dashboard base
        det = [r for X in st for r in X['detections'] if r['label']]
        g = [tag(d['nom'], d['adresse'], TAG_OK if d['type'] == 'CABLE' else TAG_ONOFF) for d in det]
        if g: tags += g; groupes.append(('Alarmes', len(g)))
        g = [tag_radar(R['nom'], R['adresse'], R) for X in st for R in X['radars']]
        if g: tags += g; groupes.append(('Radars', len(g)))
        g = [tag_ana(A['nom'], A['adresse'], A) for X in st for A in X['ana']]
        if g: tags += g; groupes.append(('Mesures', len(g)))
        g = [tag_ana(c['nom'], c['adresse'], c) for X in st for c in X['consignes']]
        if g: tags += g; groupes.append(('Consignes AO', len(g)))
        # une seule commande de chaque genre (feu rouge, orange clignotant, orange fixe, vert, sirène…) :
        # le tableau de bord de la base est limité à 50 tags
        vus, g = set(), []
        for X in st:
            for c in X['commandes']:
                if c['genre'] not in vus:
                    vus.add(c['genre']); g.append(tag(c['nom'], c['adresse'], TAG_ONOFF))
        if g: tags += g; groupes.append(('Signalisations', len(g)))
        g = [tag(f"MAINV {X['nom']}", int(f"105{X['xx']}"), TAG_OK) for X in st if X['mainv']]
        if g: tags += g; groupes.append(('Status - MAINV', len(g)))
        g = [tag(f"VBATT {X['nom']}", int(f"305{X['xx']}"), TAG_VB) for X in st]
        tags += g; groupes.append(('Status - BATTV', len(g)))
        g = [tag(f"RSSI {X['nom']}", int(f"351{X['xx']}"), TAG_RSSI) for X in st[1:]]
        if g: tags += g; groupes.append(('Status - RSSI', len(g)))
        g = [tag(f"CFLAG {X['nom']}", int(f"151{X['xx']}"), TAG_OK) for X in st[1:]]
        if g: tags += g; groupes.append(('Status - FLAGC', len(g)))
        # limite ELPRO : 50 tags. Au-delà, les RSSI sont retirés en premier.
        if len(tags) > MAX_TAGS:
            n_rssi = dict(groupes).get('Status - RSSI', 0)
            tags = [t for t in tags if t['unites'] != 'dBm']
            groupes = [gr for gr in groupes if gr[0] != 'Status - RSSI']
            S['_avert'] = [f"Tableau de bord de {S['nom']} : {len(tags) + n_rssi} éléments pour {MAX_TAGS} au maximum. "
                           f"Les {n_rssi} RSSI ont été retirés (registres 351xx toujours disponibles)."]
            if len(tags) > MAX_TAGS:
                S['_avert'].append(f"Tableau de bord de {S['nom']} : encore {len(tags)} éléments après retrait des RSSI ; "
                                   f"seuls les {MAX_TAGS} premiers sont gardés.")
                tags = tags[:MAX_TAGS]
                reste, groupes2 = MAX_TAGS, []
                for nomg, nb in groupes:
                    if reste > 0: groupes2.append((nomg, min(nb, reste))); reste -= nb
                groupes = groupes2
    else:
        if S['mainv']: noms.append((10000 + S['mainv'].get('di', 8), 'MAINV'))
        g = []
        for d in S['detections']:
            if d['label']:
                noms.append((10000 + d['di'], d['label']))
                g.append(tag(d['label'], 10000 + d['di'], TAG_OK if d['type'] == 'CABLE' else TAG_ONOFF))
        if g: tags += g; groupes.append(('Alarmes', len(g)))
        g = []
        for R in S['radars']:
            noms.append((30000 + R['ai'], R['label']))
            g.append(tag_radar(R['label'], 30000 + R['ai'], R))
        if g: tags += g; groupes.append(('Radars', len(g)))
        g = []
        for c in S['commandes']:
            for do in c['do']:
                noms.append((do, c['label']))
                g.append(tag(c['label'], do, TAG_ONOFF))
        if g: tags += g; groupes.append(('Signalisation', len(g)))
        g = []
        for A in S['ana']:
            noms.append((A['distant'], A['label'])); g.append(tag_ana(A['label'], A['distant'], A))
        if g: tags += g; groupes.append(('Mesures', len(g)))
        g = []
        for c in S['consignes']:
            noms.append((c['distant'], c['label'])); g.append(tag_ana(c['label'], c['distant'], c))
        if g: tags += g; groupes.append(('Consignes AO', len(g)))
        g = []
        if S['mainv']: g.append(tag('Alim.', 10000 + S['mainv'].get('di', 8), TAG_OK))
        g += [tag('Batterie', 30007, TAG_VB), tag('RSSI', 30401, TAG_RSSI)]
        tags += g; groupes.append(('Statut', len(g)))
    # noms des E/S physiques (page IO de CConfig)
    if S['mainv']: S['noms_io'][f"Din{S['mainv'].get('di', 8)}"] = 'MAINV'
    for d in S['detections']:
        if d['label']: S['noms_io'][f"Din{d['di']}"] = d['label'][:20]
    for c in S['commandes']:
        for do in c['do']: S['noms_io'][f"Dot{do}"] = c['label'][:20]
    for R in S['radars']: S['noms_io'][f"Ain{R['ai']}"] = R['label'][:20]
    for X in S['ana'] + S['consignes']: S['noms_io'][X['io']] = X['label'][:20]
    # v2.3 : les noms par défaut de 30009/30010 cèdent la place à une entrée analogique en tension sur AI3/AI4
    surcharge = {X['distant'] for X in S['ana']}
    noms = [x for x in noms[:2] if x[0] not in surcharge] + noms[2:]
    vus, propre = set(), []
    for a, n in noms:
        if a not in vus:
            vus.add(a); propre.append((a, n))
    S['noms_registres'] = propre
    S['tags'], S['groupes'] = tags, groupes


# ---------------------------------------------------------------- écriture .cdb
def C(tag, val):
    return f'<{tag} d="C">{val}</{tag}>'


def _set(s, tag, val, count=1):
    # remplacement par fonction : le texte est inséré tel quel (un « \ » n'est pas interprété par re)
    s2, n = re.subn(rf'<{tag}(?: d="\w")?>[^<]*</{tag}>|<{tag}/>', lambda _m: C(tag, val), s, count=count)
    if n == 0: raise KeyError(tag)
    return s2


def _table(s, name, rows, close='\n\t\t\t\t\t'):
    # une table ne contient que des <tr> ; motif robuste (la table Sensitivity contient un champ Sensitivity)
    m = re.search(rf'<{name}(?: d="D")?>\s*(?:<tr>.*?</tr>\s*)*</{name}>|<{name}/>', s, re.S)
    if not m: raise KeyError(name)
    return s[:m.start()] + f'<{name} d="D">' + ''.join(rows) + close + f'</{name}>' + s[m.end():]


def _dest(dest):
    if dest == 'local':
        return '          <DstIPAddress>127.0.0.1</DstIPAddress>\n          <IPDeviceID></IPDeviceID>\n'
    return f'          {C("UnitID", dest)}\n          <IPDeviceID>eth0</IPDeviceID>\n'


def _row_read(m):
    return ('\n        <tr>\n          <Enabled>1</Enabled>\n' f'          <Name>{m["nom"]}</Name>\n' + _dest(m['dest']) +
            f'          {C("Invert", m["inv"])}\n'
            f'          {C("UpdatePeriod", m["periode"])}\n          {C("UpdateOffset", m["offset"])}\n'
            f'          {C("ResponseTimeout", m["timeout"])}\n          <ForceReg>0</ForceReg>\n'
            f'          {C("FailReg", m["fail"])}\n          {C("FirstLocalReg", m["local"])}\n'
            f'          {C("FirstRemoteReg", m["distant"])}\n          {C("RegCount", m["nb"])}\n        </tr>')


def _row_scatter(m):
    s = ('\n        <tr>\n          <Enabled>1</Enabled>\n' f'          <Name>{m["nom"]}</Name>\n' + _dest(m['dest']) +
         f'          {C("Ack", m["ack"])}\n          {C("Invert", m["inv"])}\n'
         f'          {C("UpdatePeriod", m["periode"])}\n          {C("UpdateOffset", m["offset"])}\n'
         '          <COSDelay>1</COSDelay>\n          <COSEnabled>1</COSEnabled>\n'
         '          <COSResetsUpdateTimer>0</COSResetsUpdateTimer>\n          <ForceReg>0</ForceReg>\n'
         f'          {C("FailReg", m["fail"])}\n')
    for i in range(1, 33):
        if i <= len(m['paires']):
            l, r = m['paires'][i - 1]; s += f'          {C(f"LReg{i}", l)}\n          {C(f"RReg{i}", r)}\n'
        else:
            s += f'          <LReg{i}>0</LReg{i}>\n          <RReg{i}>0</RReg{i}>\n'
    return s + '        </tr>'


def _row_write(m):
    return ('\n        <tr>\n          <Enabled>1</Enabled>\n' f'          <Name>{m["nom"]}</Name>\n' + _dest(m['dest']) +
            f'          {C("Ack", m["ack"])}\n          {C("Invert", m["inv"])}\n'
            f'          {C("UpdatePeriod", 0)}\n          <UpdateOffset>0</UpdateOffset>\n'
            f'          <COSDelay>1</COSDelay>\n          {C("COSEnabled", m["cos"])}\n'
            f'          <COSResetsUpdateTimer>0</COSResetsUpdateTimer>\n          {C("ForceReg", m["force"])}\n'
            f'          <FailReg>0</FailReg>\n          {C("FirstLocalReg", m["local"])}\n'
            f'          {C("FirstRemoteReg", m["distant"])}\n          {C("RegCount", m["nb"])}\n        </tr>')


def _row_fs(first, count):
    return ('\n      <tr>\n' f'        {C("FirstRegister", first)}\n        {C("Count", count)}\n'
            f'        {C("TimeOut", 0)}\n        {C("InitialiseAtStart", 1)}\n        {C("StateStartup", 0)}\n'
            '        <InvalidateOnFail>0</InvalidateOnFail>\n' f'        {C("StateFail", 0)}\n      </tr>')


def _row_tag(t):
    return ('\n        <tr>\n' f'          {C("Name", t["nom"])}\n          {C("Register", t["registre"])}\n'
            '          <DisplayType>0</DisplayType>\n' f'          {C("Units", t["unites"])}\n'
            f'          {C("OverRangeValue", t["over"])}\n          {C("UnderRangeValue", t["under"])}\n'
            f'          {C("HighAlarm", t["haut"])}\n          {C("LowAlarm", t["bas"])}\n          {C("Invert", t["invert"])}\n'
            f'          {C("RegisterPt1", t["rp1"])}\n          {C("RegisterPt2", t["rp2"])}\n'
            f'          {C("DisplayPt1", t["dp1"])}\n          {C("DisplayPt2", t["dp2"])}\n        </tr>')


def _serial(mod, port, mode, rate):
    i = mod.find(f'<{port}>'); j = mod.find(f'</{port}>', i)
    blk = mod[i:j]
    spans = [(m.start(), m.end()) for m in re.finditer(r'<(modbus|modbusProprietory|serialgateway|hartparams)>.*?</\1>', blk, re.S)]
    for tag, val in (('Mode', mode), ('DataRate', rate)):
        for m in re.finditer(rf'<{tag}(?: d="C")?>(\d+)</{tag}>', blk):
            if not any(a <= m.start() < b for a, b in spans):
                blk = blk[:m.start()] + C(tag, val) + blk[m.end():]
                break
        else:
            raise KeyError(f'{port}/{tag}')
    return mod[:i] + blk + mod[j:]


def _unite_xml(S, plan, gabarit):
    s = plan['systeme']
    u = gabarit.replace('{{NOM}}', S['nom']).replace('{{UID}}', S['uid'])
    base = S['role'] == 'base'
    mode = {'base': 0, 'repeater': 1, 'remote': 2}[S['role']]
    ips = [X['ip'] for X in plan['stations']]
    oct_ = sorted(int(ip.rsplit('.', 1)[1]) for ip in ips)
    # réseau
    u = re.sub(r'(<wifi0>\s*<Enabled>1</Enabled>\s*)<IP_Address>[^<]*</IP_Address>', r'\g<1>' + C('IP_Address', S['ip']), u, count=1)
    u = re.sub(r'(<eth0>\s*<Enabled>1</Enabled>\s*)<IP_Address>[^<]*</IP_Address>', r'\g<1>' + C('IP_Address', S['ip']), u, count=1)
    u = _set(u, 'Gateway_IP', PASSERELLE)
    u = _set(u, 'StartIP', f'{RESEAU}.{oct_[0]}')
    u = _set(u, 'EndIP', f'{RESEAU}.{oct_[-1]}')
    g = u.find('<group name="networking">')
    net = u[g:]
    net = _set(net, 'UpstreamDeviceName', S['amont'])
    net = _set(net, 'SystemName', s['system_name'])
    net = _set(net, 'Passphrase', s['cle_chiffrement'])
    net = _set(net, 'DeviceMode', mode)
    net = _set(net, 'TXPower', S['puissance_dbm'])
    net = _set(net, 'Data_Rates_1_1', 0 if base else 4)
    net = _set(net, 'Base_Rates_1_1', 0 if base else 1)
    u = u[:g] + net
    # identification
    u = _set(u, 'CfgVersion', date_cfgversion(datetime.datetime.now()))
    u = _set(u, 'Owner', s.get('proprietaire', ''))
    u = _set(u, 'Contact', s.get('contact', ''))
    u = _set(u, 'Description', S['description'])
    u = _set(u, 'Location', s.get('localisation', ''))
    # série + champs propres à la base (relevés sur les sites en service)
    if base:
        u = _serial(u, 'ttyS0', 0, 11); u = _serial(u, 'ttyS1', 0, 9)
        g = u.find('<group name="networking">'); u = u[:g] + _set(u[g:], 'ProMeshMode', 0)
        g = u.find('<Server>'); assert u.rfind('<modbus>', 0, g) > u.rfind('</serial>', 0, g) > 0
        u = u[:g] + _set(u[g:], 'Enabled', 1)     # serveur Modbus TCP de la base
        g = u.find('<IO ID="VBatt1">'); h = u.find('</IO>', g)
        u = u[:g] + _set(_set(u[g:h], 'SPHigh', 14.6), 'SPWindow', 1) + u[h:]
    # réglages avancés des entrées analogiques (v2.3)
    for A in S['ana']:
        if A['reglages']:
            g = u.find(f'<IO ID="{A["io"]}">'); h = u.find('</IO>', g)
            blk = u[g:h]
            for champ, val in A['reglages'].items():
                blk = _set(blk, champ, val)
            u = u[:g] + blk + u[h:]
    # E/S : noms, anti-rebond
    for io, nom in S['noms_io'].items():
        u, n = re.subn(rf'(<IO ID="{io}">\s*)<Name>[^<]*</Name>', r'\g<1>' + C('Name', nom), u, count=1)
        assert n == 1, io
    for io, val in S['debounce'].items():
        u, n = re.subn(rf'(<IO ID="{io}">\s*<Name(?: d="C")?>[^<]*</Name>\s*)<DebounceTime>[^<]*</DebounceTime>',
                       r'\g<1>' + C('DebounceTime', val), u, count=1)
        assert n == 1, io
    u = re.sub(r'<UserIOsInfo>.*?</UserIOsInfo>', '<UserIOsInfo>' + ''.join(
        f'\n        <tr>\n          {C("Addr", a)}\n          {C("Name", n)}\n        </tr>' for a, n in S['noms_registres'])
        + '\n      </UserIOsInfo>', u, count=1, flags=re.S)
    # fail-safe
    if S['failsafe']:
        u = _table(u, 'UpdateFailures', [_row_fs(a, c) for a, c in S['failsafe']], close='\n    ')
    # mappings
    if S['writes']: u = _table(u, 'WriteMapping', [_row_write(m) for m in S['writes']])
    if S['reads']: u = _table(u, 'ReadMapping', [_row_read(m) for m in S['reads']])
    if S['scatters']: u = _table(u, 'ScatterMapping', [_row_scatter(m) for m in S['scatters']])
    if S['sensibilite']:
        u = _table(u, 'Sensitivity', [f'\n        <tr>\n          {C("FirstRegister", a)}\n          {C("Count", c)}\n'
                                      f'          {C("Sensitivity", v)}\n        </tr>' for a, c, v in S['sensibilite']], close='\n      ')
    u = _set(u, 'RadioTxAckCount', S['ack'][0])
    u = _set(u, 'RadioTxAckTimeout', S['ack'][1])
    # dashboard
    u = _set(u, 'PageTitle', S['titre_page'])
    u = _table(u, 'DashboardTags', [_row_tag(t) for t in S['tags']], close='\n      ')
    u = _table(u, 'DashboardGroups', [f'\n        <tr>\n          {C("Name", n)}\n          {C("Count", c)}\n        </tr>'
                                      for n, c in S['groupes']], close='\n      ')
    return u


def _xml_echap(txt):
    return str(txt).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def ecrire_cdb(plan, chemin):
    with open(os.path.join(RESSOURCES, 'unit_template.xml'), encoding='utf-8') as f:
        gab_u = f.read()
    with open(os.path.join(RESSOURCES, 'project_template.xml'), encoding='utf-8') as f:
        gab_p = f.read()
    # les textes libres sont échappés pour XML
    plan_x = dict(plan); plan_x['systeme'] = {k: _xml_echap(v) if isinstance(v, str) else v
                                               for k, v in plan['systeme'].items()}
    unites = ''.join(_unite_xml(dict(S, description=_xml_echap(S['description']), titre_page=_xml_echap(S['titre_page'])),
                                plan_x, gab_u).rstrip() + '\n\t\t\t' for S in plan['stations'])
    now = datetime.datetime.now()
    txt = (gab_p.replace('{{DATE}}', date_projet(now))
           .replace('{{NOM_PROJET}}', _xml_echap(plan['systeme']['nom_projet']))
           .replace('{{IDNUMB}}', str(len(plan['stations'])))
           .replace('{{UNITES}}', unites.rstrip()))
    import xml.etree.ElementTree as ET
    ET.fromstring(txt.replace('encoding="UTF-16"', '', 1).encode('utf-8'))      # contrôle de bonne forme
    with open(chemin, 'w', encoding='utf-16', newline='\r\n') as f:
        f.write(txt.replace('\r\n', '\n'))
    return chemin


# ---------------------------------------------------------------- écriture .sconf
def ecrire_sconf(lignes, chemin, actif=False):
    """Fichier IO Plus (.sconf). actif=False (défaut) : logique livrée désactivée."""
    assert len(lignes) <= 300, 'IO Plus : 300 lignes maximum'
    rows = ''.join('<tr>' + ''.join(f'<val><![CDATA[{x}]]></val>' for x in l) + '</tr>' for l in lignes)
    conf = ('<group name="Logic"><item name="version"><val><![CDATA[1]]></val></item>'
            f'<item name="Enabled"><val><![CDATA[{1 if actif else 0}]]></val></item>'
            '<table name="StatementList" ncols="6" maxrows="300">' + rows + '</table></group>\n')
    with tarfile.open(chemin, 'w:gz', format=tarfile.PAX_FORMAT) as tf:
        for nom, data in (('Logic.conf', conf.encode('utf-8')), ('Logic.version', b'1\n')):
            ti = tarfile.TarInfo(nom); ti.size = len(data); ti.mode = 0o666
            ti.uid = ti.gid = 0; ti.uname = ti.gname = 'root'; ti.mtime = int(time.time())
            tf.addfile(ti, io.BytesIO(data))
    return chemin


# ---------------------------------------------------------------- XML de chaque radio (v2.1)
# Format E2Config : celui de l'export « Save configuration » de la page web de la radio. Le fichier se charge
# directement dans la radio (page web) et contient tout : réseau, E/S, mappings, fail-safe, tableau de bord,
# IO Plus (actif ou non selon l'option) et, sur la base, la liste du datalog.
# Gabarit : resources/radio_template.xml (export d'une radio firmware 2.59, sans aucune donnée de site).
LISTE_LOG = [('COMFLAGS', 15101, 20), ('BATTV_FAIL', 15201, 20), ('RSSI_FAIL', 15301, 20),
             ('DET_FAIL', 15401, 20), ('FEUX_FAIL', 15501, 20), ('MAINV_FAIL', 15601, 20),
             ('BATTV', 30501, 20), ('RSSI', 35101, 20), ('DET', 15001, 20), ('FEUX', 401, 20),
             ('MAINV', 10501, 20), ('CABLE2', 15021, 20), ('RADAR', 35201, 20), ('FEUX2', 421, 20),
             ('FEUX3', 441, 10), ('RADAR_FAIL', 15701, 20)]
# liste standard des centrales, identique sur tous les sites (noms reconnus par ELPRO Logs)
LOG_REGLAGES = {'Scan Rate': 30, 'Records per File': 2880}     # à saisir à la main : absents de l'export XML
# lignes AIn du XML -> ID d'E/S CConfig (index 0 = registre 30001)
_AIN_IDS = ['Ain1', 'Ain2', 'Ain3', 'Ain4', 'VSupply', 'V24', 'VBatt1', 'VExt', 'Ain5', 'Ain6']


def liste_log(plan):
    """Liste du datalog de la base : liste standard + E/S analogiques si le site en a (v2.0)."""
    L = list(LISTE_LOG)
    na = sum(len(S['ana']) for S in plan['stations'])
    nc = sum(len(S['consignes']) for S in plan['stations'])
    if na:
        L += [('ANA', ANA_BASE + 1, min(na, 20)), ('ANA_FAIL', 15801, 17)]
    if nc:
        L.append(('AO', AO_BASE + 1, min(nc, 20)))
    return L


def _e2_trouver(root, *chemin):
    e = root
    for n in chemin:
        t = [c for c in e if c.get('name') == n]
        if len(t) != 1:
            raise KeyError('/'.join(chemin))
        e = t[0]
    return e


def _e2_item(root, chemin, val):
    e = _e2_trouver(root, *chemin)
    assert e.tag == 'item', chemin
    e.find('val').text = str(val)


def _e2_table(root, chemin, lignes):
    import xml.etree.ElementTree as ET
    t = _e2_trouver(root, *chemin)
    assert t.tag == 'table', chemin
    nc, mx = int(t.get('ncols')), int(t.get('maxrows'))
    if len(lignes) > mx:
        raise ValueError(f"{'/'.join(chemin)} : {len(lignes)} lignes, maximum {mx}")
    for tr in list(t):
        t.remove(tr)
    for l in lignes:
        assert len(l) == nc, (chemin, l)
        tr = ET.SubElement(t, 'tr')
        for v in l:
            ET.SubElement(tr, 'val').text = str(v)


def _e2_texte(root):
    """Sérialise comme la radio : indentation 2 espaces, valeurs en CDATA, une ligne par <tr>."""
    out = ['<?xml version="1.0" encoding="utf-8"?>']

    def cd(v):
        v = v or ''
        if ']]>' in v:
            raise ValueError(f'Texte interdit dans un XML de radio : « ]]> » ({v})')
        return f'<val><![CDATA[{v}]]></val>'

    def rec(e, ind):
        sp = '  ' * ind
        at = ''.join(f' {k}="{v}"' for k, v in e.attrib.items())
        if e.tag == 'item':
            out.extend([f'{sp}<item{at}>', f'{sp}  {cd(e.find("val").text)}', f'{sp}</item>'])
        elif e.tag == 'table':
            out.append(f'{sp}<table{at}>')
            out.extend(f'{sp}  <tr>' + ''.join(cd(v.text) for v in tr.findall('val')) + '</tr>' for tr in e.findall('tr'))
            out.append(f'{sp}</table>')
        else:
            out.append(f'{sp}<{e.tag}{at}>')
            for c in e:
                rec(c, ind + 1)
            out.append(f'{sp}</{e.tag}>')
    rec(root, 0)
    return '\n'.join(out) + '\n'


def xml_radio(plan, S, ioplus_actif=False, maintenant=None):
    """Texte du XML E2Config de la station S (élément de plan['stations'])."""
    import xml.etree.ElementTree as ET
    with open(os.path.join(RESSOURCES, 'radio_template.xml'), encoding='utf-8') as f:
        r = ET.fromstring(f.read().encode('utf-8'))
    s = plan['systeme']
    base = S['role'] == 'base'
    ip_de = {X['uid']: X['ip'] for X in plan['stations']}
    dest = lambda d: '127.0.0.1' if d == 'local' else ip_de[d]
    oct_ = sorted(int(X['ip'].rsplit('.', 1)[1]) for X in plan['stations'])
    N, W = ('networking',), ('networking', 'wifi0')
    # réseau
    for ch, v in ((N + ('eth0', 'IP_Address'), S['ip']), (W + ('IP_Address',), S['ip']),
                  (N + ('Gateway_IP',), PASSERELLE),
                  (N + ('Filter', 'EasyFilter', 'StartIP'), f'{RESEAU}.{oct_[0]}'),
                  (N + ('Filter', 'EasyFilter', 'EndIP'), f'{RESEAU}.{oct_[-1]}'),
                  (W + ('WPA', 'Passphrase'), s['cle_chiffrement']),
                  (W + ('Radio', 'TXPower'), S['puissance_dbm']),
                  (W + ('Radio', 'Data_Rates_1_1'), 0 if base else 4),
                  (W + ('Radio', 'Base_Rates_1_1'), 0 if base else 1),
                  (W + ('DeviceMode',), {'base': 0, 'repeater': 1, 'remote': 2}[S['role']]),
                  (W + ('ProMeshMode',), 0 if base else 1),
                  (W + ('SystemName',), s['system_name']),
                  (W + ('UpstreamDeviceName',), S['amont']),
                  # identification
                  (('identification', 'DeviceName'), S['nom']),
                  (('identification', 'Owner'), s.get('proprietaire', '')),
                  (('identification', 'Contact'), s.get('contact', '')),
                  (('identification', 'Description'), S['description']),
                  (('identification', 'Location'), s.get('localisation', '')),
                  (('identification', 'CfgVersion'), date_cfgversion(maintenant or datetime.datetime.now())),
                  # série et serveur Modbus (valeurs relevées sur les sites en service)
                  (('serial', 'ttyS0', 'DataRate'), 11 if base else 6),
                  (('serial', 'ttyS1', 'DataRate'), 9 if base else 6),
                  (('modbus', 'Server', 'Enabled'), 1 if base else 0),
                  # radio maillée, tableau de bord
                  (('ELPROMesh', 'AckTxCount'), S['ack'][0]),
                  (('ELPROMesh', 'AckTimeout'), S['ack'][1]),
                  (('HMI', 'PageTitle'), S['titre_page'])):
        _e2_item(r, ch, v)
    # E/S : noms, anti-rebond, seuils de la batterie de la base
    lignes_io = {'DIn': _e2_trouver(r, 'IO', 'DIn'), 'DOt': _e2_trouver(r, 'IO', 'DOt'),
                 'AOt': _e2_trouver(r, 'IO', 'AOt'), 'AIn': _e2_trouver(r, 'IO', 'AIn')}

    def ligne_io(io):
        if io[:3] in ('Din', 'Dot', 'Aot'):
            t, i = {'Din': 'DIn', 'Dot': 'DOt', 'Aot': 'AOt'}[io[:3]], int(io[3:]) - 1
        else:
            t, i = 'AIn', _AIN_IDS.index(io)
        return list(lignes_io[t].findall('tr'))[i].findall('val')
    for io, nom in S['noms_io'].items():
        ligne_io(io)[0].text = str(nom)
    for io, val in S['debounce'].items():
        ligne_io(io)[1].text = str(val)
    if base:
        v = ligne_io('VBatt1'); v[5].text = '14.6'; v[7].text = '1'
    col = {'Zero': 1, 'Span': 2, 'SPLow': 4, 'SPHigh': 5, 'SPWindow': 7}      # colonnes de la table AIn
    for A in S['ana']:
        v = ligne_io(A['io'])
        for champ, val in A['reglages'].items():
            if champ in col:
                v[col[champ]].text = str(val)
    _e2_table(r, ('IO', 'IOUsrCfg', 'IOUsrCfgTable'), S['noms_registres'])
    # fail-safe, mappings, sensibilité
    _e2_table(r, ('FailSafe', 'ConfigTable'), [(a, c, 0, 1, 0, 0, 0) for a, c in S['failsafe']])
    _e2_table(r, ('ELPROMesh', 'WriteMapping'), [
        (1, m['nom'], dest(m['dest']), m['ack'], m['inv'], 0, 0, 1, m['cos'], 0, m['force'], 0,
         m['local'], m['distant'], m['nb']) for m in S['writes']])
    _e2_table(r, ('ELPROMesh', 'ReadMapping'), [
        (1, m['nom'], dest(m['dest']), m['inv'], m['periode'], m['offset'], m['timeout'], 0, m['fail'],
         m['local'], m['distant'], m['nb']) for m in S['reads']])
    sc = []
    for m in S['scatters']:
        paires = [x for l, rr in m['paires'] for x in (l, rr)]
        sc.append((1, m['nom'], dest(m['dest']), m['ack'], m['inv'], m['periode'], m['offset'], 1, 1, 0, 0,
                   m['fail'], *paires, *([0] * (64 - len(paires)))))
    _e2_table(r, ('ELPROMesh', 'ScatterMapping'), sc)
    if S['sensibilite']:
        _e2_table(r, ('ELPROMesh', 'Sensitivity'), S['sensibilite'])
    # tableau de bord
    _e2_table(r, ('HMI', 'Tags'), [(t['nom'], t['registre'], 0, t['unites'], t['over'], t['under'], t['haut'],
                                    t['bas'], t['invert'], t['rp1'], t['rp2'], t['dp1'], t['dp2']) for t in S['tags']])
    _e2_table(r, ('HMI', 'Groups'), S['groupes'])
    # IO Plus : toujours présent (une radio qui avait une logique la perd si la station n'en a pas)
    iop = S['iop'] or []
    _e2_item(r, ('Logic', 'Enabled'), 1 if (ioplus_actif and iop) else 0)
    _e2_table(r, ('Logic', 'StatementList'), iop)
    # datalog : sur la base seulement ; groupe retiré des autres radios (leur export n'en a pas, anciens firmwares compris)
    if base:
        _e2_table(r, ('DataLog', 'Records'), [(1, n, a, c) for n, a, c in liste_log(plan)])
    else:
        r.remove(_e2_trouver(r, 'DataLog'))
    return _e2_texte(r)


def nom_fichier_xml(plan, S):
    return f"{base_nom_fichier(plan)}_{re.sub(r'[^A-Za-z0-9_-]+', '_', S['nom'])}.xml"


def ecrire_xml_radio(plan, S, chemin, ioplus_actif=False):
    with open(chemin, 'w', encoding='utf-8', newline='\n') as f:
        f.write(xml_radio(plan, S, ioplus_actif))
    return chemin


# ---------------------------------------------------------------- import d'un .cdb existant
class ProjetProtege(Exception):
    pass


def lire_texte_cdb(chemin):
    with open(chemin, 'rb') as f:
        b = f.read()
    if b[:2] in (b'\xff\xfe', b'\xfe\xff'):
        return b.decode('utf-16')
    return b.decode('utf-8-sig')


def importer_cdb(chemin):
    """Lit un .cdb existant et retourne (projet, avertissements).
    Remplit : système, radios (nom, rôle, amont, IP, puissance, titre), MAINV si une DI s'appelle MAINV.
    Ne déduit PAS les périphériques (liste vide)."""
    import xml.etree.ElementTree as ET
    txt = lire_texte_cdb(chemin)
    if '<DBE>' in txt[:5000]:
        raise ProjetProtege('Projet protégé par mot de passe : enregistrer une copie sans protection dans CConfig.')
    root = ET.fromstring(re.sub(r'encoding="[^"]+"', '', txt, count=1).encode('utf-8'))
    av = []
    def val(u, chemin_xml, defaut=''):
        e = u.find(chemin_xml)
        return (e.text or '').strip() if e is not None else defaut
    W = './group[@name="networking"]/group[@name="wifi0"]'
    radios = []
    for u in root.iter('Unit'):
        nom = u.get('name')
        mode = val(u, W + '/DeviceMode', '2')
        role = {'0': 'base', '1': 'repeater', '2': 'remote'}.get(mode, 'remote')
        ip = val(u, './Networking/wifi0/IP_Address')
        if not ip.startswith(RESEAU + '.'):
            av.append(f'{nom} : IP {ip} hors du réseau {RESEAU}.x, à corriger.')
        try:
            octet = int(ip.rsplit('.', 1)[1])
        except Exception:
            octet = None; av.append(f'{nom} : IP illisible.')
        mainv = None
        for io in u.findall('./IOs/IO'):
            if (io.get('ID') or '').startswith('Din') and (io.findtext('Name') or '').strip().upper() == 'MAINV':
                mainv = int(io.get('ID')[3:])
        radios.append({
            'nom': nom, 'role': role, 'amont': val(u, W + '/UpstreamDeviceName') if role != 'base' else '',
            'ip_octet': octet, 'puissance_dbm': int(float(val(u, W + '/group[@name="Radio"]/TXPower', '34'))),
            'titre_page': val(u, './Dashboard/PageTitle'),
            'mainv': {'actif': True, 'di': mainv} if mainv else {'actif': False},
            'inversion_entrees': False, 'inversion_sorties': False, 'peripheriques': [],
            '_ident': {k: val(u, f'./group[@name="identification"]/{k}') for k in ('Owner', 'Contact', 'Description', 'Location')},
            '_system_name': val(u, W + '/SystemName'), '_cle': val(u, W + '/group[@name="WPA"]/Passphrase'),
        })
    bases = [r for r in radios if r['role'] == 'base']
    if len(bases) != 1:
        av.append(f'{len(bases)} base(s) trouvée(s) : il en faut exactement une.')
    radios.sort(key=lambda r: 0 if r['role'] == 'base' else 1)        # base en tête, ordre du fichier conservé ensuite
    b = radios[0] if radios else {}
    puissance = b.get('puissance_dbm', 34)
    systeme = {
        'nom_projet': root.findtext('./DB/Details/Name') or '',
        'system_name': b.get('_system_name', ''), 'cle_chiffrement': b.get('_cle', ''),
        'puissance_dbm': puissance,
        'proprietaire': b.get('_ident', {}).get('Owner', ''), 'contact': b.get('_ident', {}).get('Contact', ''),
        'description': b.get('_ident', {}).get('Description', ''), 'localisation': b.get('_ident', {}).get('Location', ''),
    }
    for r in radios:
        if r['puissance_dbm'] == puissance:
            r['puissance_dbm'] = None                 # = puissance générale
        if r['titre_page'] == r['nom']:
            r['titre_page'] = ''
        for k in ('_ident', '_system_name', '_cle'):
            r.pop(k, None)
    av.append('Les périphériques ne sont pas importés : les ajouter radio par radio.')
    return {'version': 1, 'version_config': VERSION_DEFAUT, 'systeme': systeme, 'radios': radios}, av


def ioplus_actif(projet_ou_plan):
    """Option générale du projet (v2.1) : IO Plus livré activé dans les .sconf et les XML. Défaut : désactivé."""
    return bool(projet_ou_plan.get('systeme', {}).get('ioplus_actif', False))


def nom_fichier_sconf(plan, S):
    """IOPlus_<radio>_V<version>_ACTIVE.sconf ou ..._DESACTIVE.sconf selon l'option IO Plus."""
    return f"IOPlus_{S['nom']}_V{plan['version_config']}_{'ACTIVE' if ioplus_actif(plan) else 'DESACTIVE'}.sconf"


def ecrire_sconf_tous(plan, dossier):
    """Écrit le .sconf de chaque station qui a une logique IO Plus. Retourne la liste des chemins."""
    return [ecrire_sconf(S['iop'], os.path.join(dossier, nom_fichier_sconf(plan, S)), ioplus_actif(plan))
            for S in plan['stations'] if S['iop']]


def ecrire_xml_radios(plan, dossier):
    """Écrit le XML de chaque radio (v2.1). Retourne la liste des chemins."""
    return [ecrire_xml_radio(plan, S, os.path.join(dossier, nom_fichier_xml(plan, S)), ioplus_actif(plan))
            for S in plan['stations']]


def generer_tout(projet, dossier):
    """Génère le .cdb, les .sconf et le XML de chaque radio dans `dossier`. Retourne (plan, liste_fichiers).
    Les noms contiennent la version de configuration du projet (voir preparer_generation).
    IO Plus actif ou non selon systeme.ioplus_actif (suffixe ACTIVE / DESACTIVE des .sconf)."""
    plan = calculer_plan(projet)
    os.makedirs(dossier, exist_ok=True)
    fichiers = [ecrire_cdb(plan, os.path.join(dossier, f'{base_nom_fichier(plan)}.cdb'))]
    fichiers += ecrire_sconf_tous(plan, dossier)
    fichiers += ecrire_xml_radios(plan, dossier)
    return plan, fichiers

if __name__ == '__main__':
    import json, sys
    p = json.load(open(sys.argv[1], encoding='utf-8'))
    plan, f = generer_tout(p, sys.argv[2])
    print('\n'.join(f))
