# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""
Moteur de génération ELPRO GeoAzimut (v1.8) — IMPLÉMENTATION DE RÉFÉRENCE.

Entrée  : un projet (dict, format décrit dans 03_Modele_de_donnees.md).
Sorties : - plan (dict)            -> utilisé par la page 2, le PDF et l'Excel
          - fichier .cdb (UTF-16)  -> ecrire_cdb(plan, chemin)
          - fichiers .sconf        -> ecrire_sconf(lignes, chemin)

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
TYPES = set(TYPES_ENTREE) | set(TYPES_SORTIE_SIMPLE) | {'FEU', 'CAMERA_SPOT', 'RADAR'}

# Sorties d'un feu : (clé JSON, libellé, base du registre de commande)
# Plan des commandes : rouge 401-410, orange clignotant 411-420, orange fixe 421-430,
# autres signalisations 431-440 (inchangé depuis les premiers sites), vert 441-450 (ajouté à la fin)
SORTIES_FEU = (('do_rouge', 'ROUGE', 400), ('do_orange_cli', 'OR_CLI', 410),
               ('do_orange_fixe', 'OR_FIXE', 420), ('do_vert', 'VERT', 440))
LIBELLES_FEU = {'ROUGE': 'rouge', 'OR_CLI': 'orange clignotant', 'OR_FIXE': 'orange fixe', 'VERT': 'vert'}

# Longueur maximale d'un nom de registre / de tag du tableau de bord : au-delà, la radio affiche un
# nom d'E/S par défaut (DIn1, DOut5…) à la place (constaté sur radio, noms de 19 caractères).
NOM_MAX = 16


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
RE_NOM_PERIPH = re.compile(r'^[A-Za-z0-9_]{1,16}$')
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
    return _j.loads(_j.dumps({'systeme': projet.get('systeme', {}), 'radios': projet.get('radios', [])}))


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
              surveillance MAINV activée ou désactivée (un registre lu en plus ou en moins).
    Mineure : tout autre changement (entrée/sortie d'un périphérique, entrée MAINV, IP, puissance, rôle,
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
    return 'mineure'


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
        di_used, do_used, ai_used, noms_p = {}, {}, {}, set()
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
                E.append(f'{n} : nom de périphérique « {pn} » : 1 à 16 caractères, lettres/chiffres/_.')
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
    return E


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
            'detections': [], 'commandes': [], 'radars': [],
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
        if S['commandes']: sequence.append(('SGNL', S, None))
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
            else:
                r0 = S['radars'][0]
                m = dict(nom=f"{S['nom']}_ReadRADAR", local=r0['adresse'], distant=30000 + r0['ai'], nb=len(S['radars']),
                         fail=int(f'157{xx}'), inv=0)
            m.update(dest=S['uid'], periode=T, offset=off, timeout=TIMEOUT_S)
            base['reads'].append(m)
            creneaux.append({'k': k + 1, 'offset': off, 'type': 'Lecture', 'mapping': m['nom'], 'station': S['nom'],
                             'ip': S['ip'], 'failreg': m['fail']})
        else:
            paires = [(c['adresse'], d) for c in S['commandes'] for d in c['do']]
            m = dict(nom=f"{S['nom']}-SGNL", dest=S['uid'], periode=T, offset=off, fail=int(f'155{xx}'),
                     paires=paires, inv=1 if S['inv_sorties'] else 0, ack=1)
            base['scatters'].append(m)
            creneaux.append({'k': k + 1, 'offset': off, 'type': 'Commandes', 'mapping': m['nom'], 'station': S['nom'],
                             'ip': S['ip'], 'failreg': m['fail']})
    # ---- mappings locaux de la base
    if base['commandes']:
        base['scatters'].insert(0, dict(nom=f"{base['nom']}-SGNL", dest='local', periode=0, offset=0, fail=15501,
                                        paires=[(c['adresse'], d) for c in base['commandes'] for d in c['do']],
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
    base['scatters'].append(dict(nom=f"{base['nom']}-DFTL", dest='local', periode=0, offset=0, fail=0,
                                 paires=dftl, inv=0, ack=1))
    base['failsafe'] = [FAILSAFE_COMMANDES] + [(int(f'15{f}01'), FAILSAFE_COUNT) for f in range(1, 8)]
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
                               ('156', bool(S['mainv']), 'MAINV'), ('157', bool(S['radars']), 'RADAR')):
            if cond:
                lignes.append(ligne('ADD', int(f'{fam}{xx}'), f"+ {S['nom']} {lab}_FAIL")); n += 1
        lignes.append(ligne('GE', n, 'Toutes les lectures en echec', I=1))
        if S['commandes']:
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


def tag(nom, registre, style, invert=0, haut=None):
    u, over, under, hi, lo, rp1, rp2, dp1, dp2 = style
    if hi is None: hi = haut
    return {'nom': nom[:NOM_MAX], 'registre': registre, 'unites': u, 'over': over, 'under': under, 'haut': hi,
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
        noms += [(r['adresse'], r['nom']) for r in registres]
        # dashboard base
        det = [r for X in st for r in X['detections'] if r['label']]
        g = [tag(d['nom'], d['adresse'], TAG_OK if d['type'] == 'CABLE' else TAG_ONOFF) for d in det]
        if g: tags += g; groupes.append(('Alarmes', len(g)))
        g = [tag_radar(R['nom'], R['adresse'], R) for X in st for R in X['radars']]
        if g: tags += g; groupes.append(('Radars', len(g)))
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
    s2, n = re.subn(rf'<{tag}(?: d="\w")?>[^<]*</{tag}>|<{tag}/>', C(tag, val), s, count=count)
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
def ecrire_sconf(lignes, chemin):
    assert len(lignes) <= 300, 'IO Plus : 300 lignes maximum'
    rows = ''.join('<tr>' + ''.join(f'<val><![CDATA[{x}]]></val>' for x in l) + '</tr>' for l in lignes)
    conf = ('<group name="Logic"><item name="version"><val><![CDATA[1]]></val></item>'
            '<item name="Enabled"><val><![CDATA[0]]></val></item>'
            '<table name="StatementList" ncols="6" maxrows="300">' + rows + '</table></group>\n')
    with tarfile.open(chemin, 'w:gz', format=tarfile.PAX_FORMAT) as tf:
        for nom, data in (('Logic.conf', conf.encode('utf-8')), ('Logic.version', b'1\n')):
            ti = tarfile.TarInfo(nom); ti.size = len(data); ti.mode = 0o666
            ti.uid = ti.gid = 0; ti.uname = ti.gname = 'root'; ti.mtime = int(time.time())
            tf.addfile(ti, io.BytesIO(data))
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


def generer_tout(projet, dossier):
    """Génère le .cdb et tous les .sconf dans `dossier`. Retourne (plan, liste_fichiers).
    Les noms contiennent la version de configuration du projet (voir preparer_generation)."""
    plan = calculer_plan(projet)
    os.makedirs(dossier, exist_ok=True)
    nom = base_nom_fichier(plan)
    v = plan['version_config']
    fichiers = [ecrire_cdb(plan, os.path.join(dossier, f'{nom}.cdb'))]
    for S in plan['stations']:
        if S['iop']:
            fichiers.append(ecrire_sconf(S['iop'], os.path.join(dossier, f'IOPlus_{S["nom"]}_V{v}_DESACTIVE.sconf')))
    return plan, fichiers


if __name__ == '__main__':
    import json, sys
    p = json.load(open(sys.argv[1], encoding='utf-8'))
    plan, f = generer_tout(p, sys.argv[2])
    print('\n'.join(f))
