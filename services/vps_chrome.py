"""services/vps_chrome.py
Gestionnaire Python du Chrome Headless / CDP persistant sur VPS pour J.A.R.V.I.S.
Assure un health check explicite du port CDP (9222) et le redémarrage sécurisé du service systemd
avant le lancement de tâches de recherche Deep Research L3.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
import time
from typing import Any, Callable, Dict, Optional, Tuple

import httpx

import config
from services.l3_error import L3ErrorDetails, set_last_l3_error, sanitize_error_text

logger = logging.getLogger("jarvis.vps_chrome")

# ─── Configuration par défaut ──────────────────────────────────────────────────
DEFAULT_CDP_HOST = getattr(config, "JARVIS_CDP_HOST", os.environ.get("JARVIS_CDP_HOST", "127.0.0.1"))
DEFAULT_CDP_PORT = int(getattr(config, "JARVIS_CDP_PORT", os.environ.get("JARVIS_CDP_PORT", 9222)))
DEFAULT_CDP_URL = getattr(
    config,
    "JARVIS_CDP_URL",
    os.environ.get("JARVIS_CDP_URL", f"http://{DEFAULT_CDP_HOST}:{DEFAULT_CDP_PORT}"),
)
DEFAULT_SERVICE_NAME = getattr(
    config,
    "JARVIS_VPS_CHROME_SERVICE",
    os.environ.get("JARVIS_VPS_CHROME_SERVICE", "jarvis-chrome"),
)

DEFAULT_HEALTH_CHECK_TIMEOUT = 2.0
DEFAULT_MAX_WAIT_SECONDS = 12.0
DEFAULT_RESTART_TIMEOUT = 8.0


# ─── Exceptions ───────────────────────────────────────────────────────────────

class VPSChromeError(Exception):
    """Exception de base pour les erreurs liées au cycle de vie de Chrome VPS."""

    def __init__(self, message: str, l3_error: Optional[L3ErrorDetails] = None):
        super().__init__(message)
        self.l3_error = l3_error


class VPSChromeUnavailableError(VPSChromeError):
    """Levée lorsque Chrome CDP reste inaccessible après les tentatives de démarrage."""

    pass


# ─── Helpers d'URL et Configuration ──────────────────────────────────────────

def get_effective_cdp_url(override_url: Optional[str] = None) -> str:
    """Résout l'URL CDP cible à partir des arguments, de la config ou de l'environnement."""
    if override_url:
        return override_url.rstrip("/")
    configured = getattr(config, "JARVIS_CDP_URL", None) or os.environ.get("JARVIS_CDP_URL")
    if configured:
        return configured.rstrip("/")
    host = getattr(config, "JARVIS_CDP_HOST", None) or os.environ.get("JARVIS_CDP_HOST", "127.0.0.1")
    port = getattr(config, "JARVIS_CDP_PORT", None) or os.environ.get("JARVIS_CDP_PORT", 9222)
    return f"http://{host}:{port}".rstrip("/")


def get_vps_service_name(override_name: Optional[str] = None) -> str:
    """Résout le nom de l'unité systemd Chrome."""
    if override_name:
        return override_name
    return getattr(
        config,
        "JARVIS_VPS_CHROME_SERVICE",
        os.environ.get("JARVIS_VPS_CHROME_SERVICE", DEFAULT_SERVICE_NAME),
    )


# ─── Health Check CDP ─────────────────────────────────────────────────────────

async def check_cdp_health(
    cdp_url: Optional[str] = None,
    timeout: float = DEFAULT_HEALTH_CHECK_TIMEOUT,
    client: Optional[httpx.AsyncClient] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """
    Effectue une vérification explicite de santé du port CDP via l'endpoint /json/version.
    Retourne (True, metadata) si Chrome répond avec succès (HTTP 200),
    ou (False, error_details) en cas d'indisponibilité ou timeout.
    """
    url = get_effective_cdp_url(cdp_url)
    endpoint = f"{url}/json/version"

    close_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=timeout)
        close_client = True

    try:
        resp = await client.get(endpoint)
        if resp.status_code == 200:
            try:
                data = resp.json()
            except Exception:
                data = {"raw": resp.text}
            browser_ver = data.get("Browser", "Chrome/Unknown")
            logger.debug(f"[VPSChrome] Health check CDP OK sur {url} : {browser_ver}")
            return True, data
        else:
            err = f"HTTP {resp.status_code}: {resp.text[:200]}"
            logger.debug(f"[VPSChrome] Health check CDP KO sur {url} ({err})")
            return False, {"error": err, "status_code": resp.status_code}
    except Exception as e:
        safe_msg = sanitize_error_text(str(e))
        logger.debug(f"[VPSChrome] Health check CDP échec sur {url} : {safe_msg}")
        return False, {"error": safe_msg, "exception": e.__class__.__name__}
    finally:
        if close_client:
            await client.aclose()


async def is_cdp_available(
    cdp_url: Optional[str] = None,
    timeout: float = DEFAULT_HEALTH_CHECK_TIMEOUT,
    client: Optional[httpx.AsyncClient] = None,
) -> bool:
    """Helper booléen retournant True si Chrome DevTools Protocol est disponible."""
    is_ok, _ = await check_cdp_health(cdp_url=cdp_url, timeout=timeout, client=client)
    return is_ok


# ─── Redémarrage du Service Systemd ───────────────────────────────────────────

async def restart_vps_chrome_service(
    service_name: Optional[str] = None,
    command_runner: Optional[Callable] = None,
    timeout: float = DEFAULT_RESTART_TIMEOUT,
) -> Tuple[bool, str]:
    """
    Déclenche le redémarrage du service systemd sur le VPS de manière sécurisée et non bloquante.
    Sur Linux, invoque systemctl restart ou sudo systemctl restart.
    Ne tente pas d'exécuter systemctl sur les environnements non-Linux (développement local Windows).
    """
    s_name = get_vps_service_name(service_name)

    # 1. Runner injecté (tests ou commandes personnalisées)
    if command_runner is not None:
        try:
            if asyncio.iscoroutinefunction(command_runner):
                res = await asyncio.wait_for(command_runner(s_name), timeout=timeout)
            else:
                res = command_runner(s_name)
            if isinstance(res, tuple):
                return bool(res[0]), str(res[1])
            return bool(res), "Commande de redémarrage injectée exécutée"
        except Exception as e:
            err = sanitize_error_text(str(e))
            logger.warning(f"[VPSChrome] Échec de la commande injectée : {err}")
            return False, err

    # 2. Vérification de la plateforme hôte
    if sys.platform != "linux":
        msg = f"Redémarrage automatique systemd ignoré sur OS non-Linux ({sys.platform})."
        logger.info(f"[VPSChrome] {msg}")
        return False, msg

    # 3. Exécution Linux (systemctl / sudo systemctl)
    cmd: list[str]
    is_root = (os.geteuid() == 0) if hasattr(os, "geteuid") else False
    if is_root:
        cmd = ["systemctl", "restart", s_name]
    elif shutil.which("sudo"):
        cmd = ["sudo", "-n", "systemctl", "restart", s_name]
    else:
        cmd = ["systemctl", "--user", "restart", s_name]

    cmd_str = " ".join(cmd)
    logger.info(f"[VPSChrome] Exécution de la commande : {cmd_str}")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_data, stderr_data = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            msg = f"Timeout ({timeout}s) dépassé lors du redémarrage de {s_name}."
            logger.error(f"[VPSChrome] {msg}")
            return False, msg

        if proc.returncode == 0:
            logger.info(f"[VPSChrome] ✔ Service systemd '{s_name}' redémarré avec succès.")
            return True, f"Service '{s_name}' redémarré avec succès."
        else:
            err_output = stderr_data.decode("utf-8", errors="replace").strip()
            msg = f"Code sortie {proc.returncode} : {sanitize_error_text(err_output)}"
            logger.warning(f"[VPSChrome] ⚠️ Échec redémarrage service '{s_name}' : {msg}")
            return False, msg

    except Exception as e:
        err = sanitize_error_text(str(e))
        logger.error(f"[VPSChrome] Erreur lors du redémarrage du service '{s_name}' : {err}")
        return False, err


# ─── Orchestrateur Principal ──────────────────────────────────────────────────

async def ensure_chrome_running(
    cdp_url: Optional[str] = None,
    max_wait: float = DEFAULT_MAX_WAIT_SECONDS,
    health_check_timeout: float = DEFAULT_HEALTH_CHECK_TIMEOUT,
    restart_if_down: bool = True,
    http_client: Optional[httpx.AsyncClient] = None,
    restart_func: Optional[Callable] = None,
) -> Dict[str, Any]:
    """
    S'assure que Google Chrome CDP est disponible et réactif avant de démarrer une tâche L3.

    Étapes :
      1. Health check initial sur l'endpoint CDP /json/version.
      2. Si actif : retour immédiat (status="healthy").
      3. Si inactif et restart_if_down : déclenchement du redémarrage du service systemd.
      4. Polling avec backoff borné (0.5s -> 2.0s) jusqu'à max_wait.
      5. Si opérationnel : retour status="restarted".
      6. Si indisponible : génération de L3ErrorDetails (P2), enregistrement global et retour status="unavailable".
    """
    url = get_effective_cdp_url(cdp_url)
    logger.info(f"[VPSChrome] Vérification de l'état de Chrome CDP sur {url}...")

    # 1. Health check initial
    is_healthy, version_info = await check_cdp_health(
        cdp_url=url,
        timeout=health_check_timeout,
        client=http_client,
    )

    if is_healthy:
        logger.info(
            f"[VPSChrome] ✔ Chrome CDP est sain et joignable sur {url} "
            f"({version_info.get('Browser', 'Chrome')})"
        )
        return {
            "ok": True,
            "status": "healthy",
            "cdp_url": url,
            "restarted": False,
            "version_info": version_info,
            "error": None,
            "l3_error": None,
        }

    logger.warning(
        f"[VPSChrome] ⚠️ Chrome CDP inaccessible sur {url} "
        f"({version_info.get('error', 'non joignable')})."
    )

    if not restart_if_down:
        err_msg = f"Chrome CDP indisponible sur {url} et redémarrage automatique désactivé."
        l3_err = L3ErrorDetails(
            etape="cdp_connection",
            exception=err_msg,
            cause_courte="Chrome CDP non joignable (redémarrage désactivé)",
            fallback_initiated=True,
        )
        set_last_l3_error(l3_err)
        return {
            "ok": False,
            "status": "unavailable",
            "cdp_url": url,
            "restarted": False,
            "version_info": None,
            "error": err_msg,
            "l3_error": l3_err.to_dict(),
        }

    # 2. Déclenchement du redémarrage
    logger.info("[VPSChrome] Tentative de relance du service Chrome VPS...")
    restart_ok, restart_msg = await restart_vps_chrome_service(command_runner=restart_func)
    if not restart_ok:
        logger.warning(
            f"[VPSChrome] La commande de redémarrage a retourné : {restart_msg}. "
            f"Début du polling d'attente..."
        )

    # 3. Polling avec backoff borné
    start_time = time.time()
    interval = 0.5
    attempts = 0

    while (time.time() - start_time) < max_wait:
        attempts += 1
        await asyncio.sleep(interval)

        is_healthy, version_info = await check_cdp_health(
            cdp_url=url,
            timeout=health_check_timeout,
            client=http_client,
        )
        if is_healthy:
            elapsed = time.time() - start_time
            logger.info(
                f"[VPSChrome] ✔ Chrome CDP opérationnel après redémarrage "
                f"({elapsed:.2f}s, {attempts} sondes)."
            )
            return {
                "ok": True,
                "status": "restarted",
                "cdp_url": url,
                "restarted": True,
                "version_info": version_info,
                "duration_seconds": round(elapsed, 2),
                "error": None,
                "l3_error": None,
            }

        interval = min(interval * 1.5, 2.0)

    # 4. Échec après expiration du délai
    elapsed = time.time() - start_time
    err_msg = f"Chrome CDP non joignable sur {url} après redémarrage et {elapsed:.1f}s d'attente."
    l3_err = L3ErrorDetails(
        etape="cdp_connection",
        exception=err_msg,
        traceback_court="",
        cause_courte="Chrome CDP VPS indisponible après relance",
        fallback_initiated=True,
    )
    set_last_l3_error(l3_err)
    logger.error(f"[VPSChrome] [Étape: cdp_connection] {l3_err.cause_courte} : {err_msg}")

    return {
        "ok": False,
        "status": "unavailable",
        "cdp_url": url,
        "restarted": True,
        "version_info": None,
        "duration_seconds": round(elapsed, 2),
        "error": err_msg,
        "l3_error": l3_err.to_dict(),
    }


# ─── Détection de Session Google / Gemini (P5) ───────────────────────────────

LOGIN_INDICATOR_SELECTORS = [
    "a:has-text('Sign in')",
    "a:has-text('Connexion')",
    "button:has-text('Sign in')",
    "button:has-text('Connexion')",
    "a[href*='accounts.google.com/signin']",
    "a[href*='accounts.google.com/ServiceLogin']",
    "input[type='email']",
    "input[name='identifier']",
]

GEMINI_ACTIVE_SELECTORS = [
    "rich-textarea",
    "div[contenteditable='true'][role='textbox']",
    "button[aria-label*='Deep Research' i]",
    "button[aria-label*='Recherche approfondie' i]",
    "[data-test-id='text-input']",
    "model-response",
    "chat-window",
]


async def check_gemini_session(
    cdp_url: Optional[str] = None,
    timeout: float = 15.0,
    browser_connector: Optional[Callable] = None,
    navigate_if_needed: bool = True,
) -> Dict[str, Any]:
    """
    Vérifie si une session Google / Gemini Web est active et authentifiée sur Chrome CDP (P5).
    Ne tente aucune saisie de mot de passe, ni validation de formulaire ou de MFA.
    Ne logue et n'expose jamais de cookies, tokens ou identifiants.

    Retourne un dict structuré :
      {
        "ok": bool,              # True si la session est active, False sinon
        "status": str,           # 'active' | 'login_required' | 'unavailable' | 'unknown' | 'error'
        "exit_code": int,        # 0 (active), 1 (login requis/inconnu), 2 (CDP indisponible/erreur)
        "message": str,          # Message utilisateur explicatif
        "current_url": Optional[str],
        "error": Optional[str],
      }
    """
    target_url = get_effective_cdp_url(cdp_url)
    logger.info(f"[VPSChrome] Vérification de la session Google Gemini sur {target_url}...")

    # 1. Vérification de santé CDP préalable
    is_healthy, _ = await check_cdp_health(cdp_url=target_url, timeout=min(timeout, 3.0))
    if not is_healthy:
        msg = f"Chrome CDP inaccessible sur {target_url}. Assurez-vous que le service systemd est actif."
        logger.warning(f"[VPSChrome] [Session Gemini] {msg}")
        return {
            "ok": False,
            "status": "unavailable",
            "exit_code": 2,
            "message": msg,
            "current_url": None,
            "error": "Chrome CDP unreachable",
        }

    pw_instance = None
    browser_instance = None
    created_page = False

    try:
        # 2. Connexion Playwright CDP
        if browser_connector is not None:
            if asyncio.iscoroutinefunction(browser_connector):
                browser_instance = await browser_connector(target_url)
            else:
                browser_instance = browser_connector(target_url)
        else:
            from playwright.async_api import async_playwright
            pw_instance = await async_playwright().start()
            browser_instance = await pw_instance.chromium.connect_over_cdp(target_url)

        contexts = getattr(browser_instance, "contexts", [])
        if contexts:
            ctx = contexts[0]
        elif hasattr(browser_instance, "new_context"):
            ctx = await browser_instance.new_context()
        else:
            ctx = None

        page = None
        if ctx and hasattr(ctx, "pages"):
            for p in ctx.pages:
                p_url = getattr(p, "url", "")
                if "gemini.google.com" in p_url or "accounts.google.com" in p_url:
                    page = p
                    break

        if not page and ctx and hasattr(ctx, "new_page") and navigate_if_needed:
            page = await ctx.new_page()
            created_page = True
            if hasattr(page, "goto"):
                await page.goto(
                    "https://gemini.google.com/app",
                    wait_until="domcontentloaded",
                    timeout=int(timeout * 1000),
                )
                if hasattr(page, "wait_for_timeout"):
                    await page.wait_for_timeout(1500)

        if not page:
            msg = "Aucun onglet de navigation n'a pu être inspecté."
            return {
                "ok": False,
                "status": "error",
                "exit_code": 2,
                "message": msg,
                "current_url": None,
                "error": msg,
            }

        curr_url = getattr(page, "url", "") or ""
        safe_url = sanitize_error_text(curr_url)

        # 3. Détection de page d'authentification Google explicite
        if "accounts.google.com" in curr_url.lower() and not ("signout" in curr_url.lower() or "continue=" in curr_url.lower()):
            msg = "Connexion Google requise : redirection vers accounts.google.com détectée."
            logger.info(f"[VPSChrome] [Session Gemini] {msg}")
            return {
                "ok": False,
                "status": "login_required",
                "exit_code": 1,
                "message": msg,
                "current_url": safe_url,
                "error": None,
            }

        # 4. Détection d'indicateurs de connexion dans le DOM
        login_detected = False
        if hasattr(page, "locator"):
            for sel in LOGIN_INDICATOR_SELECTORS:
                try:
                    loc = page.locator(sel)
                    if hasattr(loc, "count"):
                        cnt = await loc.count()
                        if cnt > 0:
                            is_real_login = True
                            if hasattr(loc, "first") and hasattr(loc.first, "get_attribute"):
                                try:
                                    href = await loc.first.get_attribute("href") or ""
                                    if href.startswith("/app/") or "signout" in href.lower():
                                        is_real_login = False
                                except Exception:
                                    pass
                            if is_real_login:
                                login_detected = True
                                break
                except Exception:
                    pass

        if login_detected:
            msg = "Connexion Google requise : bouton ou formulaire de connexion détecté sur l'interface."
            logger.info(f"[VPSChrome] [Session Gemini] {msg}")
            return {
                "ok": False,
                "status": "login_required",
                "exit_code": 1,
                "message": msg,
                "current_url": safe_url,
                "error": None,
            }

        # 5. Détection d'interface Gemini active
        if "gemini.google.com" in curr_url.lower():
            msg = "Session Google Gemini active et authentifiée."
            logger.info(f"[VPSChrome] [Session Gemini] ✔ {msg}")
            return {
                "ok": True,
                "status": "active",
                "exit_code": 0,
                "message": msg,
                "current_url": safe_url,
                "error": None,
            }
            msg = "Session Google Gemini active et authentifiée."
            logger.info(f"[VPSChrome] [Session Gemini] ✔ {msg}")
            return {
                "ok": True,
                "status": "active",
                "exit_code": 0,
                "message": msg,
                "current_url": safe_url,
                "error": None,
            }

        # 6. Page inconnue
        msg = f"Page non reconnue sur {safe_url} (attendu: gemini.google.com)."
        logger.warning(f"[VPSChrome] [Session Gemini] ⚠️ {msg}")
        return {
            "ok": False,
            "status": "unknown",
            "exit_code": 1,
            "message": msg,
            "current_url": safe_url,
            "error": None,
        }

    except Exception as e:
        safe_err = sanitize_error_text(str(e))
        msg = f"Erreur lors de la vérification de session Gemini : {safe_err}"
        logger.error(f"[VPSChrome] [Session Gemini] ❌ {msg}")
        return {
            "ok": False,
            "status": "error",
            "exit_code": 2,
            "message": msg,
            "current_url": None,
            "error": safe_err,
        }
    finally:
        if pw_instance and hasattr(pw_instance, "stop"):
            try:
                await pw_instance.stop()
            except Exception:
                pass
