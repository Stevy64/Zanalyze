"""Paiement Premium SingPay : confirmation serveur avant octroi, jamais sur redirection."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from paris.models import PaiementPremium, Profil

BASE = 'https://gateway.singpay.ga/v1'


class PaiementIndisponible(RuntimeError):
    pass


def configuration() -> dict:
    return {
        'client_id': os.environ.get('ZANALYZ_SINGPAY_CLIENT_ID', '').strip(),
        'client_secret': os.environ.get('ZANALYZ_SINGPAY_CLIENT_SECRET', '').strip(),
        'wallet': os.environ.get('ZANALYZ_SINGPAY_WALLET', '').strip(),
        'distribution': os.environ.get('ZANALYZ_SINGPAY_DISTRIBUTION', '').strip(),
    }


def pret() -> bool:
    cfg = configuration()
    return all(cfg[k] for k in ('client_id', 'client_secret', 'wallet'))


def _appel(path: str, payload: dict | None = None) -> dict:
    cfg = configuration()
    if not pret():
        raise PaiementIndisponible('Paiement mobile indisponible pour le moment.')
    headers = {
        'x-client-id': cfg['client_id'], 'x-client-secret': cfg['client_secret'],
        'x-wallet': cfg['wallet'], 'Accept': 'application/json',
    }
    body = None
    if payload is not None:
        headers['Content-Type'] = 'application/json'
        body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(BASE + path, data=body, headers=headers,
                                 method='POST' if body is not None else 'GET')
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            value = json.loads(response.read().decode('utf-8'))
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise PaiementIndisponible('SingPay ne répond pas. Réessaie plus tard.') from exc
    if not isinstance(value, dict):
        raise PaiementIndisponible('Réponse SingPay invalide.')
    return value


def creer_lien(achat: PaiementPremium, retour: str) -> str:
    cfg = configuration()
    payload = {
        'portefeuille': cfg['wallet'], 'reference': str(achat.reference),
        'amount': achat.montant_xaf,
        'redirect_success': retour, 'redirect_error': retour,
    }
    if cfg['distribution']:
        payload['disbursement'] = cfg['distribution']
    result = _appel('/ext', payload)
    lien = result.get('link')
    if not isinstance(lien, str) or not lien.startswith('https://'):
        raise PaiementIndisponible('Lien SingPay indisponible.')
    host = urllib.parse.urlsplit(lien).hostname or ''
    if host != 'singpay.ga' and not host.endswith('.singpay.ga'):
        raise PaiementIndisponible('Domaine de paiement inattendu.')
    return lien


def _transaction_pour(achat: PaiementPremium, payload: dict) -> dict | None:
    operation = payload.get('transaction', payload)
    if not isinstance(operation, dict):
        return None
    if str(operation.get('reference') or '') != str(achat.reference):
        return None
    try:
        montant = Decimal(str(operation.get('amount')))
    except (InvalidOperation, TypeError):
        return None
    if montant != Decimal(achat.montant_xaf):
        return None
    wallet = operation.get('portefeuille')
    if isinstance(wallet, dict):
        wallet = wallet.get('_id') or wallet.get('id')
    if str(wallet or '') != configuration()['wallet']:
        return None
    return operation


def verifier_et_activer(achat: PaiementPremium) -> str:
    """Lit la transaction chez SingPay ; un callback ou une URL ne valent jamais preuve."""
    if achat.statut == 'paye':
        return 'paye'
    payload = _appel('/transaction/api/search/by-reference/' +
                     urllib.parse.quote(str(achat.reference), safe=''))
    operation = _transaction_pour(achat, payload)
    if operation is None:
        return achat.statut  # Rien n'est accordé sans référence, montant et wallet exacts.
    stage = str(operation.get('status') or '').lower()
    result = str(operation.get('result') or '').lower()
    if stage == 'refund':
        return achat.statut  # Une opération remboursée exige une revue manuelle.
    if stage != 'terminate' or result != 'success':
        return achat.statut
    with transaction.atomic():
        achat = PaiementPremium.objects.select_for_update().get(pk=achat.pk)
        if achat.statut == 'paye':
            return 'paye'
        profil, _ = Profil.objects.get_or_create(user=achat.user)
        profil = Profil.objects.select_for_update().get(pk=profil.pk)
        renouvellement = profil.a_deja_ete_premium
        if profil.abonnement_vip_actif:
            profil.prolonger_vip(mois=1)
        else:
            profil.activer_vip(mois=1)
        profil.enregistrer_acceptation_premium(
            type_evt='renouvellement' if renouvellement else 'premier',
            mois=1, note='Paiement SingPay ' + str(achat.reference),
        )
        profil.save(update_fields=['categorie', 'vip_depuis', 'vip_expire_le',
                                   'accueil_salon', 'premium_acceptations'])
        achat.statut = 'paye'
        achat.active_le = timezone.now()
        achat.singpay_id = str(operation.get('id') or operation.get('_id') or '')[:120]
        achat.save(update_fields=['statut', 'active_le', 'singpay_id', 'maj_le'])
    return 'paye'
