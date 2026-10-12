"""Gestion de l'authentification et des appareils autorisés pour J.A.R.V.I.S.
Ce module sert de façade rétrocompatible déléguant au service cryptographique
`services.auth_service.auth_service` (Tokens JWT HS256, révocation Redis, tickets QR éphémères).
"""

import os
import json
from typing import Optional, Dict, Any

from config import AUTH_FILE, ACCESS_PASSWORD
from services.auth_service import auth_service, AuthService


def load_authorized_devices() -> dict:
    """Charge les anciens tokens autorisés depuis authorized_devices.json (rétrocompatibilité)."""
    return auth_service.load_legacy_authorized_devices()


def save_authorized_device(token: str, info: dict):
    """Enregistre un appareil dans le fichier JSON (historique/secours)."""
    tokens = load_authorized_devices()
    tokens[token] = info
    auth_service.save_legacy_authorized_devices(tokens)


def is_device_authorized(token: Optional[str]) -> bool:
    """Vérifie si un token est autorisé :
    - Token JWT valide et non révoqué dans Redis / mémoire locale.
    - Mot de passe maître (compatibilité agent local Windows).
    - Ancien token de transition : validé une dernière fois, converti en JWT
      et supprimé immédiatement de authorized_devices.json.
    """
    return auth_service.is_device_authorized_sync(token)


async def is_device_authorized_async(token: Optional[str]) -> bool:
    """Version asynchrone de vérification d'autorisation."""
    return await auth_service.is_device_authorized(token)


def create_qr_ticket() -> str:
    """Génère un ticket unique pour enregistrer l'appareil ayant scanné le QR Code (TTL court 5 min)."""
    return auth_service.create_qr_ticket_sync(ttl=300)


def register_device_via_qr(ticket: str, client_ip: str = "unknown", user_agent: str = "unknown") -> Optional[str]:
    """Enregistre l'appareil sans mot de passe si le ticket QR est valide et non expiré.
    Consomme le ticket (usage unique) et retourne un token JWT signé.
    """
    return auth_service.redeem_qr_ticket_sync(ticket, client_ip, user_agent)


def verify_and_generate_token(password: str, client_ip: str = "unknown", user_agent: str = "unknown") -> Optional[str]:
    """Vérifie le mot de passe maître et retourne un nouveau token JWT signé."""
    return auth_service.verify_and_generate_token(password, client_ip, user_agent)


def verify_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
    """Vérifie un token et retourne le payload décodé (synchrone)."""
    return auth_service.verify_token_sync(token)


async def verify_token_async(token: Optional[str]) -> Optional[Dict[str, Any]]:
    """Vérifie un token et retourne le payload décodé (asynchrone)."""
    return await auth_service.verify_token(token)
