# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""
Récupération automatique des logs d'une centrale ELPRO 415U-2-C4 (v1.1) — IMPLÉMENTATION DE RÉFÉRENCE.

Constaté sur radio (firmware 2.59) :
  - authentification HTTP du navigateur (fenêtre « Ce site vous demande de vous connecter ») ;
  - /operator/main.asp       : page d'accueil, contient « Device Name » et « Serial Number » ;
  - /operator/Datalogs/      : liste des fichiers terminés « AAAAMMJJhhmmss-<DeviceName>-DAT.log »
                               (heure UTC de fermeture du fichier) ; le fichier en cours n'y figure pas ;
  - /operator/Datalogs/<nom> : le fichier (gzip -> tar -> data.csv).
  - La centrale ne garde qu'environ 160 fichiers (≈ 7 jours avec la liste de log standard).

Le tunnel WireGuard (un seul tunnel, une adresse par centrale) est activé à la main avant la récupération.
On vérifie TOUJOURS l'identité de la centrale (n° de série, nom) avant de télécharger : une adresse mal
saisie ne doit jamais faire importer les logs d'un autre site.

Python 3.10+, bibliothèque standard uniquement.
"""
import re, sys, base64, datetime, urllib.request, urllib.error, socket, html

import elpro_logs as L

ADRESSE_DEFAUT = ''            # propre à l'installation : saisie par l'utilisateur, jamais dans le dépôt
UTILISATEUR_DEFAUT = 'user'
CHEMIN_ACCUEIL = '/operator/main.asp'
CHEMIN_LISTE = '/operator/Datalogs/'
DELAI_S = 20
RETENTION_JOURS = 7          # ordre de grandeur constaté ; sert à l'alerte « récupérer bientôt »
RE_FICHIER = re.compile(r'(\d{14})-([^"/<>]+?)-DAT\.log')


class ErreurCentrale(Exception):
    """code : injoignable | acces_refuse | introuvable | erreur"""

    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


# --------------------------------------------------------------------------------------------
# Mot de passe : chiffré par Windows (DPAPI, lié au compte Windows de l'utilisateur)
# --------------------------------------------------------------------------------------------
def _dpapi(donnees, chiffrer):
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]

    ent = BLOB(len(donnees), ctypes.cast(ctypes.create_string_buffer(donnees, len(donnees)),
                                         ctypes.POINTER(ctypes.c_char)))
    sor = BLOB()
    crypt = ctypes.windll.crypt32
    f = crypt.CryptProtectData if chiffrer else crypt.CryptUnprotectData
    if not f(ctypes.byref(ent), None, None, None, None, 0x01, ctypes.byref(sor)):   # 0x01 = UI interdite
        raise OSError('Chiffrement Windows du mot de passe impossible.')
    try:
        return ctypes.string_at(sor.pbData, sor.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(sor.pbData)


def proteger_mdp(mdp):
    """Mot de passe -> octets à stocker. Sous Windows : DPAPI. Ailleurs (tests) : simple encodage."""
    if sys.platform == 'win32':
        return b'DPAPI:' + _dpapi(mdp.encode('utf-8'), True)
    return b'B64:' + base64.b64encode(mdp.encode('utf-8'))


def retrouver_mdp(protege):
    if not protege:
        return ''
    if protege.startswith(b'DPAPI:'):
        return _dpapi(protege[6:], False).decode('utf-8')
    if protege.startswith(b'B64:'):
        return base64.b64decode(protege[4:]).decode('utf-8')
    raise ValueError('Mot de passe enregistré illisible : saisissez-le à nouveau.')


# --------------------------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------------------------
def _url(adresse, chemin):
    a = adresse.strip().rstrip('/')
    if not a.startswith(('http://', 'https://')):
        a = 'http://' + a
    return a + chemin


class Session:
    """Connexion HTTP à une centrale (authentification Basic ou Digest, au choix du serveur)."""

    def __init__(self, adresse, utilisateur, mdp, delai=DELAI_S):
        self.adresse, self.delai = adresse, delai
        gm = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        gm.add_password(None, _url(adresse, '/'), utilisateur, mdp)
        self.ouvreur = urllib.request.build_opener(
            urllib.request.HTTPBasicAuthHandler(gm), urllib.request.HTTPDigestAuthHandler(gm),
            urllib.request.ProxyHandler({}))      # jamais de proxy : la centrale est dans le tunnel

    def lire(self, chemin):
        url = _url(self.adresse, chemin)
        try:
            with self.ouvreur.open(url, timeout=self.delai) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise ErreurCentrale('acces_refuse', 'La centrale refuse le nom d\'utilisateur ou le mot de passe.')
            if e.code == 404:
                raise ErreurCentrale('introuvable', f'Page introuvable sur la centrale : {chemin}')
            raise ErreurCentrale('erreur', f'Erreur HTTP {e.code} sur {chemin}.')
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as e:
            raise ErreurCentrale('injoignable',
                                 f'Centrale injoignable à l\'adresse {self.adresse}. '
                                 f'Le tunnel WireGuard est-il activé ? ({getattr(e, "reason", e)})')

    def identifier(self):
        """-> {'nom': Device Name, 'serie': Serial Number} lus sur la page d'accueil."""
        page = self.lire(CHEMIN_ACCUEIL).decode('cp1252', 'replace')

        def champ(lib):
            m = re.search(r'<td>\s*' + re.escape(lib) + r'\s*:?\s*</td>\s*<td>(.*?)</td>', page, re.S | re.I)
            return html.unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip() if m else ''
        return {'nom': champ('Device Name'), 'serie': champ('Serial Number')}

    def lister(self):
        """Fichiers de log terminés présents sur la centrale, du plus ancien au plus récent."""
        page = self.lire(CHEMIN_LISTE).decode('cp1252', 'replace')
        noms = sorted({m.group(0) for m in RE_FICHIER.finditer(page)})
        return noms

    def telecharger(self, nom):
        return self.lire(CHEMIN_LISTE + nom)


def heure_fichier(nom):
    """« 20261019071714-B-BASE-DAT.log » -> seconde UTC de fermeture du fichier."""
    m = RE_FICHIER.search(nom)
    return L.utc_depuis_texte(datetime.datetime.strptime(m.group(1), '%Y%m%d%H%M%S').strftime('%Y-%m-%d %H:%M:%S'))


def _norm(txt):
    return re.sub(r'[^A-Z0-9]', '', (txt or '').upper())


# --------------------------------------------------------------------------------------------
# Récupération complète
# --------------------------------------------------------------------------------------------
def recuperer(magasin, sid, forcer=False, progression=None, annuler=None, session=None):
    """Télécharge et importe les logs de la centrale du système sid qui ne sont pas encore dans la base.

    progression(n, total, nom) : appelée avant chaque fichier. annuler() -> True pour arrêter.
    forcer=True : importer même si la centrale connectée ne semble pas être celle du système
                  (à proposer seulement après confirmation de l'utilisateur).
    Renvoie un rapport : statut (ok | rien_de_nouveau | injoignable | acces_refuse | introuvable |
    mauvaise_centrale | non_configure | annule | erreur), message, centrale, disponibles, nouveaux,
    imports (rapports d'import), plus_ancien (seconde UTC) et alerte (texte ou None)."""
    rap = {'statut': 'erreur', 'message': '', 'centrale': None, 'disponibles': 0, 'nouveaux': 0,
           'imports': [], 'plus_ancien': None, 'alerte': None}
    acc = magasin.acces(sid)
    if session is None:
        if not acc or not acc['adresse']:
            return dict(rap, statut='non_configure',
                        message='Adresse de la centrale non renseignée (Système › Connexion à la centrale).')
        try:
            session = Session(acc['adresse'], acc['utilisateur'] or UTILISATEUR_DEFAUT, retrouver_mdp(acc['mdp']))
        except (ValueError, OSError):
            return dict(rap, statut='non_configure',
                        message='Mot de passe enregistré illisible sur ce PC ou pour ce compte Windows : '
                                'saisissez-le à nouveau (Système › Connexion à la centrale).')
    try:
        # 1. identité de la centrale connectée
        ident = session.identifier()
        rap['centrale'] = ident
        serie_sys = magasin.cx.execute('SELECT serie FROM systemes WHERE id=?', (sid,)).fetchone()[0]
        base = magasin.catalogue(sid)['stations'][0]['nom']
        if serie_sys:
            ok = _norm(ident['serie']) == _norm(serie_sys)
            attendu = f'radio n° {serie_sys}'
        else:
            ok = _norm(ident['nom']) == _norm(base)
            attendu = f'centrale {base}'
        if not ok and not forcer:
            rap.update(statut='mauvaise_centrale',
                       message=f"La centrale connectée est {ident['nom'] or '?'} (n° {ident['serie'] or '?'}), "
                               f"alors que ce système attend la {attendu}. L'adresse saisie est-elle la bonne ?")
            return _fin(magasin, sid, rap)
        # 2. liste et fichiers nouveaux
        noms = session.lister()
        rap['disponibles'] = len(noms)
        if noms:
            rap['plus_ancien'] = heure_fichier(noms[0])
        deja = magasin.noms_fichiers(sid)
        nouveaux = [n for n in noms if n not in deja]
        rap['nouveaux'] = len(nouveaux)
        # 3. téléchargement + import, du plus ancien au plus récent
        for k, nom in enumerate(nouveaux):
            if annuler and annuler():
                rap.update(statut='annule', message=f'Récupération arrêtée après {k} fichier(s).')
                return _fin(magasin, sid, rap)
            if progression:
                progression(k, len(nouveaux), nom)
            octets = session.telecharger(nom)
            imp = magasin.importer_octets(sid, octets, nom, forcer_serie=forcer)
            rap['imports'] += imp
            if any(r['statut'] == 'serie_differente' for r in imp):
                rap.update(statut='mauvaise_centrale', message=imp[0]['message'])
                return _fin(magasin, sid, rap)
        if progression:
            progression(len(nouveaux), len(nouveaux), '')
        nb_ok = sum(1 for r in rap['imports'] if r['statut'] == 'importe')
        erreurs = [r for r in rap['imports'] if r['statut'] == 'erreur']
        if not nouveaux:
            rap.update(statut='rien_de_nouveau', message='Aucun nouveau fichier sur la centrale.')
        else:
            rap.update(statut='ok', message=f'{nb_ok} fichier(s) importé(s) sur {len(nouveaux)} nouveau(x).'
                       + (f' {len(erreurs)} en erreur.' if erreurs else ''))
        # 4. logs effacés par la centrale avant d'avoir été récupérés ?
        p = magasin.periode(sid)
        if p and rap['plus_ancien'] and nouveaux:
            avant = [r for r in rap['imports'] if r.get('t_debut')]
            premier = min((r['t_debut'] for r in avant), default=None)
            fin_avant = magasin.cx.execute(
                'SELECT MAX(fin) FROM couverture WHERE systeme_id=? AND debut<?', (sid, premier or 0)).fetchone()[0]
            if premier and fin_avant and premier - fin_avant > 3600:
                rap['alerte'] = (f'Trou de {L.duree_texte(premier - fin_avant)} avant {L.heure_locale(premier)} : '
                                 f'la centrale avait déjà effacé ces logs. Récupérez au moins une fois par semaine.')
        return _fin(magasin, sid, rap)
    except ErreurCentrale as e:
        rap.update(statut=e.code, message=e.message)
        return _fin(magasin, sid, rap)


def recuperer_tout(magasin, progression=None, annuler=None):
    """Récupère tous les systèmes dont la connexion est configurée, l'un après l'autre.
    progression(systeme_nom, n, total, nom_fichier). Une centrale injoignable n'arrête pas les suivantes ;
    une centrale « mauvaise » n'est jamais forcée. Renvoie [(systeme, rapport)]."""
    res = []
    for S in magasin.systemes():
        acc = magasin.acces(S['id'])
        if not acc or not acc['adresse']:
            continue
        if annuler and annuler():
            break
        p = (lambda n, t, nom, nm=S['nom']: progression(nm, n, t, nom)) if progression else None
        res.append((S, recuperer(magasin, S['id'], progression=p, annuler=annuler)))
    return res


def _fin(magasin, sid, rap):
    if magasin.acces(sid):
        magasin.noter_recuperation(sid, L.maintenant(), rap['statut'])
    return rap


def rappel_necessaire(magasin, sid, maintenant=None):
    """Texte d'avertissement si la dernière donnée date de plus de RETENTION_JOURS - 2 jours, sinon None."""
    p = magasin.periode(sid)
    if not p:
        return None
    age = (maintenant or L.maintenant()) - p[1]
    if age > (RETENTION_JOURS - 2) * 86400:
        return (f'Dernières données il y a {L.duree_texte(age)}. La centrale ne garde qu\'environ '
                f'{RETENTION_JOURS} jours de logs : récupérez-les rapidement.')
    return None
