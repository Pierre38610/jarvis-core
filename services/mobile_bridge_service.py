"""services/mobile_bridge_service.py
Service de communication unidirectionnelle avec le smartphone Samsung S24 de Pierre via webhooks MacroDroid.
Gère le réveil des applications et le transfert d'itinéraires GPS.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set

import httpx

import config

logger = logging.getLogger("jarvis.mobile_bridge")

ALLOWED_MODES: Set[str] = {"driving", "walking", "bicycling", "transit"}


@dataclass
class BridgeResult:
    ok: bool
    status: Optional[int]
    reason: str


class MobileBridgeService:
    """Service singleton gérant les déclenchements MacroDroid vers le smartphone de Pierre."""

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        """Retourne le client httpx asynchrone partagé (instancié paresseusement)."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=4.0)
        return self._client

    async def aclose(self) -> None:
        """Ferme proprement le client httpx s'il est ouvert."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _trigger(self, identifier: str, params: Optional[Dict[str, Any]] = None, base_url_override: Optional[str] = None) -> BridgeResult:
        """Déclenche un webhook MacroDroid avec gestion d'un retry unique sur timeout/erreur réseau."""
        device_id = getattr(config, "MACRODROID_DEVICE_ID", "").strip()
        base_url = (base_url_override or getattr(config, "MACRODROID_BASE_URL", "https://ask.macrodroid.com")).strip().rstrip("/")

        if not device_id:
            logger.warning("[MobileBridge] Déclenchement impossible : pont mobile non configuré (MACRODROID_DEVICE_ID vide)")
            return BridgeResult(ok=False, status=None, reason="pont mobile non configuré")

        url = f"{base_url}/{device_id}/{identifier}"
        client = self._get_client()

        # SÉCURITÉ ABSOLUE : ne JAMAIS logger le DEVICE_ID ou l'URL complète non masquée
        logger.info("[MobileBridge] Déclenchement webhook mobile action=%s", identifier)

        for attempt in range(2):
            try:
                response = await client.get(url, params=params, timeout=6.0)
                if 200 <= response.status_code < 300:
                    logger.info("[MobileBridge] Webhook action=%s exécuté avec succès (HTTP %d)", identifier, response.status_code)
                    return BridgeResult(ok=True, status=response.status_code, reason="ok")
                else:
                    logger.warning("[MobileBridge] Webhook action=%s refusé par le serveur (HTTP %d)", identifier, response.status_code)
                    return BridgeResult(ok=False, status=response.status_code, reason=f"HTTP {response.status_code}")
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RequestError) as exc:
                err_type = "timeout" if isinstance(exc, httpx.TimeoutException) else "network_error"
                if attempt == 0:
                    logger.warning("[MobileBridge] Webhook action=%s échec tentative 1 (%s), nouvel essai...", identifier, err_type)
                    continue
                logger.error("[MobileBridge] Webhook action=%s échec définitif (%s)", identifier, err_type)
                return BridgeResult(ok=False, status=None, reason=err_type)
            except Exception as exc:
                logger.error("[MobileBridge] Erreur inattendue action=%s : %s", identifier, type(exc).__name__)
                return BridgeResult(ok=False, status=None, reason=f"error: {type(exc).__name__}")

        return BridgeResult(ok=False, status=None, reason="unknown_error")

    async def wake_spotify_on_phone(self) -> BridgeResult:
        """Envoie le signal MacroDroid pour réveiller et ouvrir Spotify sur le smartphone."""
        res = await self._trigger("Jarvis_spotify")
        if not res.ok:
            alt_res = await self._trigger("jarvis_spotify")
            if alt_res.ok:
                return alt_res
        return res

    async def launch_maps_navigation(self, destination: str, mode: str = "driving") -> BridgeResult:
        """Envoie le signal MacroDroid pour lancer un itinéraire Google Maps vers la destination demandée."""
        if mode not in ALLOWED_MODES:
            mode = "driving"
        params = {"dest": destination, "mode": mode}
        res = await self._trigger("Jarvis maps", params)
        if not res.ok:
            for alt in ("Jarvis_maps", "jarvis_maps"):
                alt_res = await self._trigger(alt, params)
                if alt_res.ok:
                    return alt_res
        return res


mobile_bridge_service = MobileBridgeService()
