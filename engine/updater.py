# -*- coding: utf-8 -*-
# Copyright (c) 2026 Geoazimut SàRL (https://geoazimut.com). Tous droits réservés.
"""Mise à jour automatique d'ELPRO Logs et d'ELPRO Config depuis les releases GitHub.

Fichier IDENTIQUE dans les deux dépôts (engine/updater.py) : toute modification est livrée aux deux.
Bibliothèque standard uniquement (urllib, ssl, hashlib, json).

Principe :
  1. chercher()      : lit la dernière release publiée (API GitHub, sans compte : les dépôts sont publics) et
                       renvoie la nouvelle version, ou None si l'application est à jour.
  2. telecharger()   : télécharge l'installateur versionné (ELPRO_xxx_Setup_X.Y.Z.exe) et vérifie son
                       empreinte SHA-256 avec le SHA256SUMS.txt de la même release. Fichier refusé sinon.
  3. lancer_installation() : lance l'installateur Inno Setup en mode silencieux, puis l'application se ferme.
                       L'installateur demande lui-même l'autorisation Windows (UAC) : son manifeste est
                       « asInvoker », un refus n'est donc pas visible ici (rien n'est installé).
                       /RELANCER demande à l'installateur de relancer l'application à la fin.

Les erreurs prévues (réseau, release incomplète, empreinte fausse, annulation) lèvent ErreurMiseAJour,
dont le texte est affichable tel quel.
"""
import hashlib
import json
import os
import re
import ssl
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

DEPOT_LOGS = 'lucapancottigz/elpro-logs'
DEPOT_CONFIG = 'lucapancottigz/elpro-config'
PREFIXE_LOGS = 'ELPRO_Logs_Setup_'          # ELPRO_Logs_Setup_1.5.0.exe
PREFIXE_CONFIG = 'ELPRO_Config_Setup_'      # ELPRO_Config_Setup_1.7.0.exe
FICHIER_EMPREINTES = 'SHA256SUMS.txt'

API = 'https://api.github.com/repos/{depot}/releases/latest'
# Les téléchargements de github.com sont redirigés vers ces serveurs de GitHub : aucun autre hôte n'est accepté.
HOTES_AUTORISES = {'api.github.com', 'github.com', 'objects.githubusercontent.com',
                   'release-assets.githubusercontent.com'}
ARGUMENTS_INSTALLATION = ('/SILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CLOSEAPPLICATIONS', '/RELANCER')
DELAI_S = 15                    # délai réseau par requête
BLOC = 64 * 1024
INTERVALLE_H = 24               # vérification automatique au plus une fois par jour


class ErreurMiseAJour(Exception):
    """Erreur prévue : le message est destiné à l'utilisateur."""


# ---------------------------------------------------------------- versions
def version_tuple(texte):
    """'v1.5.0' ou '1.5.0' -> (1, 5, 0). ValueError si le texte n'est pas une version X.Y.Z."""
    m = re.fullmatch(r'\s*[vV]?(\d+)\.(\d+)\.(\d+)\s*', texte or '')
    if not m:
        raise ValueError(f'version illisible : {texte!r}')
    return tuple(int(x) for x in m.groups())


def est_plus_recente(candidate, actuelle):
    return version_tuple(candidate) > version_tuple(actuelle)


VARIABLE_TEST = 'ELPRO_VERSION_SIMULEE'


def version_pour_recherche(version_app, environ=None):
    """Version comparée aux releases : APP_VERSION, sauf si la variable d'environnement ELPRO_VERSION_SIMULEE
    contient une version valide (recette : simuler une ancienne version pour tester toute la chaîne)."""
    simulee = (environ if environ is not None else os.environ).get(VARIABLE_TEST, '')
    try:
        return '.'.join(map(str, version_tuple(simulee)))
    except ValueError:
        return version_app


def verification_due(derniere, maintenant=None, intervalle_h=INTERVALLE_H):
    """derniere : texte ISO 8601 de la dernière vérification automatique (QSettings), ou vide.
    True si aucune vérification depuis `intervalle_h` heures (ou date illisible / dans le futur)."""
    maintenant = maintenant or datetime.now(timezone.utc)
    try:
        d = datetime.fromisoformat(derniere)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return True
    return not (maintenant - timedelta(hours=intervalle_h) < d <= maintenant)


def maintenant_iso():
    """Texte à mémoriser après une vérification automatique (QSettings 'maj/derniere_verification')."""
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


# ---------------------------------------------------------------- réseau
def url_autorisee(url):
    p = urllib.parse.urlparse(url or '')
    return p.scheme == 'https' and (p.hostname or '') in HOTES_AUTORISES


def ouvrir_url(url, user_agent):
    """Ouvre une URL HTTPS (redirections suivies). Renvoie la réponse urllib.
    Remplaçable dans les tests par une fonction de même signature."""
    req = urllib.request.Request(url, headers={'User-Agent': user_agent,
                                               'Accept': 'application/vnd.github+json'})
    return urllib.request.urlopen(req, timeout=DELAI_S, context=ssl.create_default_context())


def _ouvrir(url, user_agent, ouvrir):
    if not url_autorisee(url):
        raise ErreurMiseAJour(f'Adresse de téléchargement refusée : {url}')
    try:
        rep = ouvrir(url, user_agent)
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            raise ErreurMiseAJour('Trop de vérifications depuis cette connexion. Réessayez dans une heure.') from e
        if e.code == 404:
            raise ErreurMiseAJour('Aucune version publiée trouvée.') from e
        raise ErreurMiseAJour(f'Le serveur de mise à jour a répondu « {e.code} {e.reason} ».') from e
    except (urllib.error.URLError, OSError, ssl.SSLError) as e:
        raise ErreurMiseAJour('Pas de connexion au serveur de mise à jour (GitHub). '
                              'Vérifiez la connexion Internet.') from e
    final = rep.geturl() if hasattr(rep, 'geturl') else url
    if not url_autorisee(final):
        rep.close()
        raise ErreurMiseAJour(f'Adresse de téléchargement refusée : {final}')
    return rep


def _user_agent(prefixe):
    return 'GeoAzimut-' + prefixe.rstrip('_').replace('_Setup', '').replace('_', '-')   # GeoAzimut-ELPRO-Logs


# ---------------------------------------------------------------- recherche
def chercher(depot, version_actuelle, prefixe, ouvrir=ouvrir_url):
    """Dernière release publiée de `depot`. Renvoie None si elle n'est pas plus récente que
    `version_actuelle`, sinon un dict :
        version  'X.Y.Z'           notes   texte Markdown de la release (peut être vide)
        page     URL de la release  publiee date de publication (texte ISO) ou ''
        installateur {'nom', 'url', 'taille'}      empreintes URL de SHA256SUMS.txt
    Lève ErreurMiseAJour (réseau, réponse illisible, release incomplète)."""
    ua = _user_agent(prefixe)
    rep = _ouvrir(API.format(depot=depot), ua, ouvrir)
    try:
        data = json.loads(rep.read().decode('utf-8'))
    except ValueError as e:
        raise ErreurMiseAJour('Réponse illisible du serveur de mise à jour.') from e
    finally:
        rep.close()
    try:
        version = '.'.join(map(str, version_tuple(data.get('tag_name', ''))))
    except ValueError as e:
        raise ErreurMiseAJour(f'Numéro de version illisible dans la release : {data.get("tag_name")!r}') from e
    if data.get('draft') or data.get('prerelease') or not est_plus_recente(version, version_actuelle):
        return None
    actifs = {a.get('name'): a for a in data.get('assets') or []}
    nom = f'{prefixe}{version}.exe'
    if nom not in actifs or FICHIER_EMPREINTES not in actifs:
        raise ErreurMiseAJour(f'La version {version} est publiée mais incomplète ({nom} ou '
                              f'{FICHIER_EMPREINTES} manquant). Installez-la à la main depuis {data.get("html_url", "")}.')
    a = actifs[nom]
    return {'version': version, 'notes': data.get('body') or '', 'page': data.get('html_url', ''),
            'publiee': data.get('published_at') or '',
            'installateur': {'nom': nom, 'url': a.get('browser_download_url', ''), 'taille': int(a.get('size') or 0)},
            'empreintes': actifs[FICHIER_EMPREINTES].get('browser_download_url', ''),
            'user_agent': ua}


def a_proposer(info, version_ignoree):
    """True si `info` (résultat de chercher) doit être proposé à l'utilisateur lors de la vérification
    automatique. La recherche manuelle propose toujours, même une version ignorée."""
    return bool(info) and info['version'] != (version_ignoree or '')


# ---------------------------------------------------------------- téléchargement
def empreinte_attendue(texte, nom):
    """Lit un SHA256SUMS.txt (lignes « <64 hexa>  <nom> ») et renvoie l'empreinte de `nom` (minuscules)."""
    for ligne in texte.splitlines():
        m = re.fullmatch(r'\s*([0-9a-fA-F]{64})\s+\*?(.+?)\s*', ligne)
        if m and m.group(2) == nom:
            return m.group(1).lower()
    return None


def dossier_telechargement():
    return os.path.join(tempfile.gettempdir(), 'GeoAzimut_mise_a_jour')


def telecharger(info, dossier=None, progression=None, annule=None, ouvrir=ouvrir_url):
    """Télécharge l'installateur de `info` dans `dossier` et vérifie son SHA-256.
    progression(recus, total) est appelée pendant le téléchargement (total = 0 si inconnu) ;
    annule() -> True interrompt le téléchargement. Renvoie le chemin de l'installateur vérifié.
    En cas d'erreur ou d'annulation, aucun fichier partiel ne reste ; lève ErreurMiseAJour."""
    dossier = dossier or dossier_telechargement()
    nom, ua = info['installateur']['nom'], info.get('user_agent', 'GeoAzimut-ELPRO')
    rep = _ouvrir(info['empreintes'], ua, ouvrir)
    try:
        attendue = empreinte_attendue(rep.read(1 << 20).decode('utf-8', 'replace'), nom)
    finally:
        rep.close()
    if not attendue:
        raise ErreurMiseAJour(f'{nom} absent de {FICHIER_EMPREINTES} : téléchargement refusé.')

    os.makedirs(dossier, exist_ok=True)
    final = os.path.join(dossier, nom)
    partiel = final + '.part'
    h, recus = hashlib.sha256(), 0
    total = info['installateur'].get('taille') or 0
    try:
        rep = _ouvrir(info['installateur']['url'], ua, ouvrir)
        try:
            with open(partiel, 'wb') as f:
                while True:
                    if annule and annule():
                        raise ErreurMiseAJour('Téléchargement annulé.')
                    try:
                        bloc = rep.read(BLOC)
                    except (OSError, ssl.SSLError) as e:
                        raise ErreurMiseAJour('Connexion interrompue pendant le téléchargement.') from e
                    if not bloc:
                        break
                    f.write(bloc)
                    h.update(bloc)
                    recus += len(bloc)
                    if progression:
                        progression(recus, total)
        finally:
            rep.close()
        if total and recus != total:
            raise ErreurMiseAJour(f'Téléchargement incomplet ({recus} octets sur {total}).')
        if h.hexdigest() != attendue:
            raise ErreurMiseAJour('Le fichier téléchargé ne correspond pas à l\'empreinte publiée : '
                                  'il a été supprimé. Réessayez plus tard.')
        os.replace(partiel, final)
    except BaseException:
        if os.path.exists(partiel):
            os.remove(partiel)
        raise
    return final


# ---------------------------------------------------------------- installation
def arguments_installation():
    """Arguments passés à l'installateur Inno Setup (texte unique, pour os.startfile)."""
    return ' '.join(ARGUMENTS_INSTALLATION)


def lancer_installation(chemin, demarrer=None):
    """Lance l'installateur vérifié par ShellExecute (os.startfile). Le Setup Inno Setup démarre sans droits
    (manifeste « asInvoker ») puis demande lui-même l'autorisation Windows (UAC) : un refus à ce moment n'est
    pas visible ici. Lève ErreurMiseAJour si le lancement échoue (fichier absent, lancement refusé par Windows)."""
    if not os.path.isfile(chemin):
        raise ErreurMiseAJour(f'Installateur introuvable : {chemin}')
    demarrer = demarrer or os.startfile           # os.startfile n'existe que sous Windows
    try:
        demarrer(chemin, 'open', arguments_installation())
    except OSError as e:
        if getattr(e, 'winerror', None) == 1223:  # ERROR_CANCELLED : l'utilisateur a refusé la fenêtre UAC
            raise ErreurMiseAJour('Mise à jour annulée : l\'autorisation Windows a été refusée.') from e
        raise ErreurMiseAJour(f'Impossible de lancer l\'installateur : {e}') from e


def nettoyer(dossier=None, garder=None):
    """Supprime les anciens installateurs téléchargés (à appeler au démarrage). `garder` : nom à conserver."""
    dossier = dossier or dossier_telechargement()
    if not os.path.isdir(dossier):
        return
    for n in os.listdir(dossier):
        if n != garder and n.lower().endswith(('.exe', '.part')):
            try:
                os.remove(os.path.join(dossier, n))
            except OSError:
                pass                                # encore utilisé (installateur en cours) : sera retiré plus tard
