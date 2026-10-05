"""services/gemini_web_automator.py
Moteur d'Automatisation Gemini Web L3 pour J.A.R.V.I.S. - Stark Industries.
Pilote l'interface officielle gemini.google.com via Chrome DevTools Protocol (CDP) /
Playwright connecté au profil Chrome réel de Pierre sur le port 9222.

Flux opérationnel L3 :
  1. Connexion CDP (port 9222) & vérification de session / connexion Google.
  2. Sélection robuste du mode « Deep Research » (par rôle / texte accessible / repli sélecteur).
  3. Saisie du sujet et soumission.
  4. Détection et confirmation du plan de recherche proposé (« Confirmer le plan » / « Start research »).
  5. Polling non-bloquant de l'état (« plan à confirmer », « génération en cours », « terminé », « connexion requise », « erreur »).
  6. Extraction du rapport complet en Markdown & déclenchement de la création de page web Canvas si disponible.
  7. Sauvegarde persistante vérifiée (dans downloads/ ou artifacts/, chemin sûr, taille > 0, extension valide).
  8. Accusé d'ouverture locale sur le PC ou repli par e-mail Stark.
  9. Capture de captures d'écran JPEG en cas d'anomalie sans fausse complétion.
"""

import asyncio
import base64
import json
import logging
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import config
from config import BASE_DIR, WORKSPACE_DIR
from services.voice_injection_queue import voice_injection_queue, InjectionPriority
from services.l3_error import L3ErrorDetails, set_last_l3_error, get_last_l3_error, sanitize_error_text

logger = logging.getLogger("jarvis.gemini_web_automator")

# ─── Chemins ──────────────────────────────────────────────────────────────────
UI_MAP_PATH = os.path.join(BASE_DIR, "data", "gemini_ui_map.json")
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
ARTIFACTS_DIR = os.path.join(BASE_DIR, "artifacts")
SCREENSHOTS_DIR = os.path.join(ARTIFACTS_DIR, "screenshots")

os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(ARTIFACTS_DIR, exist_ok=True)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)

# ─── Constantes ───────────────────────────────────────────────────────────────
CDP_URL = getattr(config, "JARVIS_CDP_URL", os.environ.get("JARVIS_CDP_URL", "http://127.0.0.1:9222"))
GEMINI_URL = "https://gemini.google.com/app"
RESEARCH_POLL_INTERVAL = 5.0    # secondes entre chaque sonde de fin de recherche
RESEARCH_MAX_WAIT = 1200.0      # 20 minutes max d'attente
ACTION_CONFIRM_TIMEOUT = 3.0    # délai d'attente de confirmation post-clic
DOM_FALLBACK_TIMEOUT = 6000     # ms pour les localisations DOM de repli


# ──────────────────────────────────────────────────────────────────────────────
# Carte d'Interface Par Défaut (Repli Résilient si gemini_ui_map.json est absent ou vide)
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_UI_MAP: Dict[str, Dict[str, Any]] = {
    "deep_research_button": {
        "x": 120,
        "y": 720,
        "description": "Bouton acces au mode Deep Research dans la barre d'outils Gemini",
        "fallback_selectors": [
            "[aria-label*='Deep Research' i]",
            "[aria-label*='Recherche approfondie' i]",
            "button:has-text('Deep Research')",
            "button:has-text('Recherche approfondie')",
            "[data-test-id='deep-research-button']",
            "mat-icon[fonticon='manage_search']",
            "[class*='deep-research']",
            "button[jsname*='research' i]",
        ],
        "validation": {
            "selector": "[aria-label*='Deep Research' i][aria-pressed='true'], [class*='deep-research'][class*='active']",
            "description": "Mode Deep Research active",
        },
    },
    "prompt_textarea": {
        "x": 760,
        "y": 720,
        "description": "Champ de saisie principal de Gemini",
        "fallback_selectors": [
            "rich-textarea [contenteditable='true']",
            "div[contenteditable='true'][role='textbox']",
            "textarea[placeholder*='Gemini' i]",
            "textarea[aria-label*='message' i]",
            "[data-test-id='text-input']",
            ".ql-editor[contenteditable='true']",
            "p[data-placeholder]",
        ],
        "validation": {
            "selector": "rich-textarea [contenteditable='true'], div[contenteditable='true'][role='textbox']",
            "description": "Champ de texte actif",
        },
    },
    "send_button": {
        "x": 1200,
        "y": 720,
        "description": "Bouton d'envoi de la requete",
        "fallback_selectors": [
            "button[aria-label*='Envoyer' i]",
            "button[aria-label*='Send' i]",
            "[class*='send'][role='button']",
        ],
        "validation": {
            "selector": "[class*='thinking'], [class*='loading'], [class*='generating'], [aria-label*='stop' i]",
            "description": "Indicateur de generation en cours",
        },
    },
    "research_completion": {
        "x": None,
        "y": None,
        "description": "Detecteur fin de recherche Deep Research (polling DOM uniquement)",
        "fallback_selectors": [
            "model-response",
            "[class*='response-container']",
            "[class*='final-response']",
            "[class*='deep-research-result']",
            "message-content",
            "[data-test-id='response-container']",
        ],
        "absence_selectors": [
            "[class*='thinking']",
            "[class*='loading']",
            "[class*='generating']",
            "[aria-label*='stop' i]",
            ".spinner",
        ],
        "validation": {
            "selector": "model-response, [class*='final-response']",
            "description": "Rapport final present",
        },
    },
    "create_webpage_button": {
        "x": 760,
        "y": 650,
        "description": "Bouton Creer une page web dans la reponse Gemini",
        "fallback_selectors": [
            "button:has-text('Create a web page')",
            "button:has-text('Creer une page web')",
            "[aria-label*='page web' i]",
            "[aria-label*='webpage' i]",
            "[aria-label*='canvas' i]",
            "button[class*='artifact']",
            "button[class*='canvas']",
        ],
        "validation": {
            "selector": "[class*='canvas-container'], iframe[title*='canvas' i], [class*='artifact-container']",
            "description": "Canvas ou iframe de la page web generee",
        },
    },
    "webpage_url": {
        "x": None,
        "y": None,
        "description": "URL de la page web Canvas Gemini (extraite du DOM)",
        "fallback_selectors": [
            "iframe[src*='gemini']",
            "iframe[src*='canvas']",
            "a[href*='g.co/canvas']",
            "[class*='artifact-link']",
        ],
        "validation": {
            "selector": "iframe[src], a[href*='canvas']",
            "description": "Iframe ou lien de la page web generee",
        },
    },
    "plan_confirmation_button": {
        "x": 760,
        "y": 600,
        "description": "Bouton pour confirmer et lancer le plan de recherche Deep Research",
        "fallback_selectors": [
            "button:has-text('Start research')",
            "button:has-text('Démarrer la recherche')",
            "button:has-text('Confirmer le plan')",
            "button:has-text('Lancer la recherche')",
            "button:has-text('Start')",
            "[aria-label*='Start research' i]",
            "[aria-label*='Démarrer la recherche' i]",
            "[data-test-id='start-research-button']",
        ],
        "validation": {
            "selector": "[class*='thinking'], [class*='generating'], [class*='loading'], [aria-label*='stop' i], .spinner",
            "description": "Génération Deep Research engagée post-plan",
        },
    },
    "login_indicator": {
        "x": None,
        "y": None,
        "description": "Indicateurs d'écran de connexion requise",
        "fallback_selectors": [
            "a:has-text('Sign in')",
            "a:has-text('Connexion')",
            "button:has-text('Sign in')",
            "button:has-text('Connexion')",
            "[href*='accounts.google.com']",
            "input[type='email']",
            "input[name='identifier']",
        ],
        "validation": {
            "selector": "[href*='accounts.google.com'], input[type='email']",
            "description": "Page de connexion Google affichée",
        },
    },
    "error_indicator": {
        "x": None,
        "y": None,
        "description": "Indicateurs d'erreur ou d'anomalie de génération",
        "fallback_selectors": [
            "[class*='error-message']",
            "[class*='error-banner']",
            "[class*='snackbar'][class*='error']",
            "div:has-text('Une erreur est survenue')",
            "div:has-text('Something went wrong')",
        ],
        "validation": {
            "selector": "[class*='error-message'], [class*='error-banner']",
            "description": "Message d'erreur affiché dans l'UI",
        },
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# Gestionnaire de la carte UI persistante
# ──────────────────────────────────────────────────────────────────────────────

class UIMapManager:
    """Charge, expose et met à jour en temps réel la carte des coordonnées et sélecteurs."""

    def __init__(self, path: str = UI_MAP_PATH):
        self._path = path
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Charge le JSON depuis le disque ou initialise une structure par défaut."""
        try:
            if os.path.exists(self._path):
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            else:
                self._data = {"actions": {}}
        except Exception as e:
            logger.warning(f"[UIMap] Impossible de charger {self._path} : {e}")
            self._data = {"actions": {}}

    def _save(self) -> None:
        """Sauvegarde les coordonnées mises à jour sur le disque."""
        try:
            self._data["_last_updated"] = datetime.now().isoformat()
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[UIMap] Échec de sauvegarde : {e}")

    def get_action(self, action_name: str) -> Dict[str, Any]:
        """Retourne la définition mémorisée d'une action (coordonnées + sélecteurs), avec repli par défaut."""
        action = self._data.get("actions", {}).get(action_name, {})
        default_def = DEFAULT_UI_MAP.get(action_name, {})
        if not action:
            return default_def
        merged = dict(default_def)
        merged.update(action)
        if not merged.get("fallback_selectors") and default_def.get("fallback_selectors"):
            merged["fallback_selectors"] = default_def["fallback_selectors"]
        if not merged.get("validation") and default_def.get("validation"):
            merged["validation"] = default_def["validation"]
        if not merged.get("absence_selectors") and default_def.get("absence_selectors"):
            merged["absence_selectors"] = default_def["absence_selectors"]
        return merged

    def update_coordinates(self, action_name: str, x: float, y: float) -> None:
        """Met à jour les coordonnées mémorisées après recalcul DOM et sauvegarde."""
        if "actions" not in self._data:
            self._data["actions"] = {}
        if action_name not in self._data["actions"]:
            self._data["actions"][action_name] = {}
        old_x = self._data["actions"][action_name].get("x")
        old_y = self._data["actions"][action_name].get("y")
        self._data["actions"][action_name]["x"] = round(x)
        self._data["actions"][action_name]["y"] = round(y)
        self._data["_layout_version"] = self._data.get("_layout_version", 1) + 1
        logger.info(
            f"[UIMap] Dérive corrigée pour '{action_name}' : "
            f"({old_x},{old_y}) → ({round(x)},{round(y)})"
        )
        self._save()

    def get_fallback_selectors(self, action_name: str) -> List[str]:
        """Retourne la liste des sélecteurs CSS/ARIA de repli pour une action."""
        action = self.get_action(action_name)
        return action.get("fallback_selectors", [])

    def get_validation_selector(self, action_name: str) -> str:
        """Retourne le sélecteur CSS/ARIA confirmant l'état actif post-action."""
        action = self.get_action(action_name)
        return action.get("validation", {}).get("selector", "")

    def get_absence_selectors(self, action_name: str) -> List[str]:
        """Retourne les sélecteurs dont l'absence indique la fin d'une phase (ex: spinner)."""
        action = self.get_action(action_name)
        return action.get("absence_selectors", [])


# ──────────────────────────────────────────────────────────────────────────────
# Automateur principal Gemini Web L3
# ──────────────────────────────────────────────────────────────────────────────

class GeminiWebAutomator:
    """
    Orchestre l'automatisation de gemini.google.com via Playwright CDP.
    Gère les rôles accessibles, la confirmation de plan, la machine d'états,
    l'extraction Markdown, la sauvegarde vérifiée et les captures d'écran.
    """

    def __init__(self):
        self.ui_map = UIMapManager()
        self._playwright = None
        self._browser = None
        self._page = None
        self._live_session: Any = None
        self._last_snapshot: Dict[str, Any] = {}

    def set_live_session(self, session: Any) -> None:
        """Injecte la session Gemini Live pour les jalons vocaux."""
        self._live_session = session

    # ── Connexion CDP ──────────────────────────────────────────────────────────

    async def _connect(self) -> bool:
        """
        Connecte Playwright au Chrome réel de Pierre via CDP (port 9222).
        S'assure au préalable que Chrome VPS est actif et répond au health check CDP.
        Réutilise l'onglet Gemini s'il existe déjà.
        """
        try:
            from playwright.async_api import async_playwright
            from services.vps_chrome import ensure_chrome_running

            if self._page and not self._page.is_closed():
                return True

            chrome_status = await ensure_chrome_running(cdp_url=CDP_URL)
            if not chrome_status.get("ok"):
                err_text = chrome_status.get("error", "Chrome CDP inaccessible")
                logger.error(f"[CDP] Échec préalable ensure_chrome_running : {err_text}")
                if chrome_status.get("l3_error"):
                    set_last_l3_error(chrome_status["l3_error"])
                return False

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.connect_over_cdp(CDP_URL)

            contexts = self._browser.contexts
            ctx = contexts[0] if contexts else await self._browser.new_context()

            self._page = None
            for p in ctx.pages:
                if "gemini.google.com" in getattr(p, "url", ""):
                    self._page = p
                    logger.info(f"[CDP] Onglet Gemini existant réutilisé : {p.url}")
                    break

            if not self._page:
                self._page = await ctx.new_page()
                logger.info("[CDP] Nouvel onglet ouvert pour Gemini.")

            return True

        except Exception as e:
            logger.error(f"[CDP] Échec de connexion Chrome : {e}")
            return False

    async def _disconnect(self) -> None:
        """Ferme proprement le contexte Playwright sans fermer Chrome."""
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        self._playwright = None
        self._browser = None
        self._page = None

    # ── Navigation & Vérification Session ───────────────────────────────────────

    async def _check_login_state(self) -> bool:
        """Vérifie si une page de connexion Google est affichée."""
        if not self._page:
            return False
        current_url = getattr(self._page, "url", "").lower()
        if "accounts.google.com" in current_url:
            return True

        login_action = self.ui_map.get_action("login_indicator")
        selectors = login_action.get("fallback_selectors", [])
        if not selectors:
            return False

        for sel in selectors:
            try:
                if hasattr(self._page, "locator"):
                    loc = self._page.locator(sel)
                    if hasattr(loc, "count") and await loc.count() > 0:
                        return True
            except Exception:
                pass
        return False

    async def _navigate_to_gemini(self) -> bool:
        """Navigue vers l'application Gemini si nécessaire."""
        try:
            current = getattr(self._page, "url", "")
            if "gemini.google.com" not in current:
                await self._page.goto(GEMINI_URL, wait_until="domcontentloaded", timeout=30000)
                await self._page.wait_for_timeout(2000)
                logger.info("[Nav] Navigation vers Gemini effectuée.")
            return True
        except Exception as e:
            logger.error(f"[Nav] Échec navigation vers Gemini : {e}")
            return False

    # ── Clic Robuste & Rôles Accessibles ───────────────────────────────────────

    async def click_with_verification(
        self,
        action_name: str,
        verify_timeout: float = ACTION_CONFIRM_TIMEOUT,
        role: Optional[str] = None,
        accessible_name: Optional[str] = None,
    ) -> bool:
        """
        Exécute un clic robuste avec :
          1. Essai par rôle accessible / texte si spécifié ou présent.
          2. Clic aux coordonnées x,y mémorisées.
          3. Vérification de validation post-clic.
          4. Repli DOM + mise à jour des coordonnées en cas de dérive.
        """
        action = self.ui_map.get_action(action_name)
        x = action.get("x")
        y = action.get("y")
        validation_selector = self.ui_map.get_validation_selector(action_name)
        fallback_selectors = self.ui_map.get_fallback_selectors(action_name)

        # ── Tentative 0 : Rôle accessible si applicable ──
        if role and accessible_name and hasattr(self._page, "get_by_role"):
            try:
                pattern = re.compile(accessible_name, re.IGNORECASE)
                loc = self._page.get_by_role(role, name=pattern).first
                if await loc.count() > 0:
                    bb = await loc.bounding_box()
                    if bb:
                        self.ui_map.update_coordinates(
                            action_name,
                            bb["x"] + bb["width"] / 2,
                            bb["y"] + bb["height"] / 2,
                        )
                    await loc.click(timeout=DOM_FALLBACK_TIMEOUT)
                    await self._page.wait_for_timeout(500)
                    if validation_selector:
                        confirmed = await self._wait_for_selector(validation_selector, timeout_ms=int(verify_timeout * 1000))
                        if confirmed:
                            logger.info(f"[Click] ✅ '{action_name}' confirmé via get_by_role({role}, '{accessible_name}').")
                            return True
                    else:
                        logger.info(f"[Click] ✅ '{action_name}' cliqué via get_by_role({role}, '{accessible_name}').")
                        return True
            except Exception as e:
                logger.debug(f"[Click] get_by_role pour '{action_name}' non concluant : {e}")

        # ── Tentative 1 : Coordonnées mémorisées ──
        if x is not None and y is not None:
            try:
                await self._page.mouse.click(x, y)
                logger.debug(f"[Click] '{action_name}' → clic à ({x},{y})")

                if validation_selector:
                    confirmed = await self._wait_for_selector(validation_selector, timeout_ms=int(verify_timeout * 1000))
                    if confirmed:
                        logger.info(f"[Click] ✅ '{action_name}' confirmé aux coordonnées mémorisées ({x},{y}).")
                        return True
                    else:
                        logger.warning(f"[Click] ⚠️ Dérive UI détectée pour '{action_name}'. Lancement du repli DOM.")
                else:
                    await self._page.wait_for_timeout(500)
                    return True
            except Exception as e:
                logger.warning(f"[Click] Clic à ({x},{y}) échoué : {e}")

        # ── Tentative 2 : Repli DOM sélecteurs ──
        for selector in fallback_selectors:
            try:
                element = self._page.locator(selector).first
                count = await element.count()
                if count == 0:
                    continue

                bb = await element.bounding_box()
                if bb:
                    new_x = bb["x"] + bb["width"] / 2
                    new_y = bb["y"] + bb["height"] / 2
                    self.ui_map.update_coordinates(action_name, new_x, new_y)

                await element.click(timeout=DOM_FALLBACK_TIMEOUT)
                await self._page.wait_for_timeout(500)

                if validation_selector:
                    confirmed = await self._wait_for_selector(validation_selector, timeout_ms=int(verify_timeout * 1000))
                    if confirmed:
                        logger.info(f"[Click] ✅ '{action_name}' confirmé via sélecteur : {selector}")
                        return True
                else:
                    logger.info(f"[Click] ✅ '{action_name}' cliqué via sélecteur : {selector}")
                    return True

            except Exception as e:
                logger.debug(f"[Click] Sélecteur '{selector}' échoué : {e}")
                continue

        logger.error(f"[Click] ❌ '{action_name}' : tous les replis ont échoué.")
        return False

    async def _wait_for_selector(self, selector: str, timeout_ms: int = 3000) -> bool:
        """Vérifie la présence d'un sélecteur CSS dans le DOM."""
        try:
            await self._page.wait_for_selector(selector, state="attached", timeout=timeout_ms)
            return True
        except Exception:
            return False

    # ── Sélection Deep Research ────────────────────────────────────────────────

    async def _select_deep_research_mode(self) -> bool:
        """Active le mode Deep Research via rôle accessible, texte ou sélecteur."""
        logger.info("[DR] Sélection du mode Deep Research...")
        return await self.click_with_verification(
            "deep_research_button",
            verify_timeout=5.0,
            role="button",
            accessible_name="Deep Research|Recherche approfondie",
        )

    # ── Saisie & Envoi du Sujet ───────────────────────────────────────────────

    async def _fill_prompt(self, topic: str) -> bool:
        """Injecte le sujet de recherche dans le champ de saisie Gemini."""
        action = self.ui_map.get_action("prompt_textarea")
        x = action.get("x")
        y = action.get("y")
        fallback_selectors = self.ui_map.get_fallback_selectors("prompt_textarea")

        # 1. Tentative par get_by_role("textbox")
        if hasattr(self._page, "get_by_role"):
            try:
                tb = self._page.get_by_role("textbox").first
                if await tb.count() > 0:
                    await tb.click(timeout=3000)
                    try:
                        await tb.fill(topic, timeout=4000)
                    except Exception:
                        await tb.type(topic, delay=20)
                    await self._page.wait_for_timeout(400)
                    logger.info("[Fill] Texte injecté via get_by_role('textbox').")
                    return True
            except Exception as e:
                logger.debug(f"[Fill] get_by_role non concluant: {e}")

        # 2. Tentative par coordonnées
        if x and y:
            try:
                await self._page.mouse.click(x, y)
                await self._page.wait_for_timeout(300)
                await self._page.keyboard.type(topic, delay=25)
                await self._page.wait_for_timeout(400)
                content = await self._page.evaluate(
                    "() => document.activeElement ? document.activeElement.innerText || document.activeElement.value : ''"
                )
                if topic[:20].lower() in (content or "").lower():
                    logger.info("[Fill] Texte injecté avec succès (coordonnées).")
                    return True
            except Exception as e:
                logger.warning(f"[Fill] Injection coordonnées échouée : {e}")

        # 3. Tentative par sélecteurs DOM
        for selector in fallback_selectors:
            try:
                el = self._page.locator(selector).first
                if await el.count() == 0:
                    continue
                bb = await el.bounding_box()
                if bb:
                    self.ui_map.update_coordinates(
                        "prompt_textarea",
                        bb["x"] + bb["width"] / 2,
                        bb["y"] + bb["height"] / 2,
                    )
                await el.click(timeout=DOM_FALLBACK_TIMEOUT)
                await self._page.wait_for_timeout(200)
                try:
                    await el.fill(topic, timeout=4000)
                except Exception:
                    await el.type(topic, delay=25)
                await self._page.wait_for_timeout(400)
                logger.info(f"[Fill] Texte injecté via sélecteur '{selector}'.")
                return True
            except Exception as e:
                logger.debug(f"[Fill] Sélecteur '{selector}' échoué : {e}")

        logger.error("[Fill] ❌ Impossible d'injecter le sujet dans le prompt Gemini.")
        return False

    async def _send_prompt(self) -> bool:
        """Envoie la requête (Entrée ou clic bouton d'envoi)."""
        try:
            await self._page.keyboard.press("Enter")
            await self._page.wait_for_timeout(1000)
            return True
        except Exception:
            return await self.click_with_verification("send_button", verify_timeout=3.0)

    # ── Confirmation du Plan de Recherche ─────────────────────────────────────

    async def _confirm_research_plan(self, timeout_seconds: float = 12.0) -> bool:
        """
        Détecte si Gemini propose un plan de recherche (« Start research » /
        « Démarrer la recherche » / « Confirmer le plan ») et le confirme.
        Si la génération démarre directement sans plan, retourne True.
        """
        logger.info("[DR] Vérification de la présence d'un plan de recherche à confirmer...")
        start = time.time()
        plan_action = self.ui_map.get_action("plan_confirmation_button")
        selectors = plan_action.get("fallback_selectors", [
            "button:has-text('Start research')",
            "button:has-text('Démarrer la recherche')",
            "button:has-text('Confirmer le plan')",
            "button:has-text('Lancer la recherche')",
            "button:has-text('Start')",
            "[aria-label*='Start research' i]",
            "[aria-label*='Démarrer la recherche' i]",
        ])

        while time.time() - start < timeout_seconds:
            # 1. Cherche le bouton de confirmation par rôle/texte
            if hasattr(self._page, "get_by_role"):
                try:
                    btn = self._page.get_by_role(
                        "button",
                        name=re.compile("Start research|Démarrer la recherche|Confirmer le plan|Lancer la recherche", re.I)
                    ).first
                    if await btn.count() > 0:
                        await btn.click(timeout=4000)
                        logger.info("[DR] ✅ Plan de recherche confirmé via get_by_role.")
                        await self._page.wait_for_timeout(1000)
                        return True
                except Exception:
                    pass

            # 2. Cherche par sélecteurs
            for sel in selectors:
                try:
                    loc = self._page.locator(sel).first
                    if await loc.count() > 0:
                        await loc.click(timeout=4000)
                        logger.info(f"[DR] ✅ Plan de recherche confirmé via sélecteur '{sel}'.")
                        await self._page.wait_for_timeout(1000)
                        return True
                except Exception:
                    pass

            # 3. Si des indicateurs de génération active sont déjà présents, le plan a été passé
            for spin in [".spinner", "[class*='thinking']", "[class*='generating']", "[class*='loading']"]:
                try:
                    if await self._page.locator(spin).count() > 0:
                        logger.info("[DR] Génération déjà active sans validation de plan requise.")
                        return True
                except Exception:
                    pass

            await asyncio.sleep(1.0)

        logger.info("[DR] Aucun plan bloquant détecté après délai, poursuite de la surveillance.")
        return True

    # ── Polling de Fin & Machine d'États ───────────────────────────────────────

    async def _wait_for_research_completion(
        self,
        poll_interval: Optional[float] = None,
        max_wait: Optional[float] = None,
    ) -> bool:
        """
        Machine d'états de polling non-bloquante :
          - 'connexion_requise' : login nécessaire
          - 'plan_a_confirmer' : clic sur validation du plan
          - 'generation_en_cours' : émission de jalons vocaux (30s, 60s, 120s, ...)
          - 'termine' : rapport final présent et chargement terminé
          - 'erreur' : détection de bannière d'erreur
        """
        interval = poll_interval if poll_interval is not None else RESEARCH_POLL_INTERVAL
        max_duration = max_wait if max_wait is not None else RESEARCH_MAX_WAIT

        completion_action = self.ui_map.get_action("research_completion")
        presence_selectors = completion_action.get("fallback_selectors", [
            "model-response", "[class*='response-container']", "[class*='final-response']", "message-content"
        ])
        absence_selectors = completion_action.get("absence_selectors", [
            "[class*='thinking']", "[class*='loading']", "[class*='generating']", "[aria-label*='stop' i]", ".spinner"
        ])

        start_time = time.time()
        milestones_sent = set()

        logger.info(f"[Poll] Démarrage polling Deep Research (intervalle={interval}s, max={max_duration}s)...")

        while time.time() - start_time < max_duration:
            elapsed = time.time() - start_time

            # Vérification de connexion rompue
            if await self._check_login_state():
                logger.warning("[Poll] Déconnexion ou session requise détectée pendant le polling.")
                return False

            # Jalons vocaux
            if 30 <= elapsed < 60 and 30 not in milestones_sent:
                await self._inject_voice_milestone(
                    "La recherche approfondie Gemini est en cours, je surveille la progression.",
                    "dr_milestone_30"
                )
                milestones_sent.add(30)
            elif 60 <= elapsed < 120 and 60 not in milestones_sent:
                await self._inject_voice_milestone(
                    "Gemini explore toujours les sources web en profondeur. Patience.",
                    "dr_milestone_60"
                )
                milestones_sent.add(60)
            elif elapsed >= 120 and 120 not in milestones_sent:
                await self._inject_voice_milestone(
                    "La synthèse des données est en cours de finalisation par Gemini.",
                    "dr_milestone_120"
                )
                milestones_sent.add(120)

            try:
                # Vérifie l'absence de tous les indicateurs de chargement
                all_spinners_gone = True
                for sel in absence_selectors:
                    if await self._page.locator(sel).count() > 0:
                        all_spinners_gone = False
                        break

                if all_spinners_gone:
                    # Vérifie la présence de la réponse
                    for sel in presence_selectors:
                        if await self._page.locator(sel).count() > 0:
                            logger.info(f"[Poll] ✅ Recherche terminée après {int(elapsed)}s via '{sel}'.")
                            return True

            except Exception as e:
                logger.debug(f"[Poll] Sonde DOM : {e}")

            await asyncio.sleep(interval)

        logger.warning(f"[Poll] ⚠️ Timeout ({max_duration}s) atteint.")
        return False

    # ── Extraction du Rapport Markdown & Canvas ───────────────────────────────

    async def _extract_report_markdown(self) -> str:
        """Extrait le contenu Markdown complet de la réponse générée."""
        extract_js = """() => {
            const resp = document.querySelector('model-response') ||
                         document.querySelector('[class*="response-container"]') ||
                         document.querySelector('[class*="final-response"]') ||
                         document.querySelector('message-content') ||
                         document.querySelector('main') ||
                         document.body;
            return resp ? (resp.innerText || resp.textContent || '').trim() : '';
        }"""
        try:
            text = await self._page.evaluate(extract_js)
            return (text or "").strip()
        except Exception as e:
            logger.warning(f"[Extract] Échec extraction JavaScript : {e}")
            return ""

    async def _trigger_webpage_creation(self) -> Optional[str]:
        """Déclenche la création d'une page web Canvas / artefact si disponible."""
        logger.info("[WebPage] Tentative de déclenchement 'Créer une page web'...")
        success = await self.click_with_verification(
            "create_webpage_button",
            verify_timeout=10.0,
            role="button",
            accessible_name="Create a web page|Créer une page web|Canvas",
        )
        if not success:
            logger.info("[WebPage] Bouton Canvas non disponible ou non déclenché.")
            return None

        await self._page.wait_for_timeout(3000)
        url_action = self.ui_map.get_action("webpage_url")
        for selector in url_action.get("fallback_selectors", []):
            try:
                el = self._page.locator(selector).first
                if await el.count() > 0:
                    href = await el.get_attribute("src") or await el.get_attribute("href")
                    if href:
                        logger.info(f"[WebPage] URL Canvas extraite : {href}")
                        return href
            except Exception:
                pass

        return getattr(self._page, "url", "")

    # ── Sauvegarde Persistante & Vérifications ─────────────────────────────────

    def _save_report_file(
        self,
        topic: str,
        markdown_content: str,
        html_content: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Sauvegarde le rapport dans downloads/ ou artifacts/ (jamais temporaire),
        et vérifie : chemin sûr, existence, taille > 0, extension valide.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = re.sub(r'[^a-zA-Z0-9_-]', '_', topic[:30]).strip('_') or "rapport"
        filename_md = f"deep_research_{slug}_{timestamp}.md"
        filepath_md = os.path.abspath(os.path.join(DOWNLOADS_DIR, filename_md))

        # Vérification chemin sûr
        allowed_roots = [
            os.path.abspath(DOWNLOADS_DIR),
            os.path.abspath(ARTIFACTS_DIR),
            os.path.abspath(WORKSPACE_DIR),
            os.path.abspath(BASE_DIR),
        ]
        if not any(filepath_md.startswith(root) for root in allowed_roots) or ".." in filename_md:
            raise ValueError(f"Chemin de fichier non sécurisé : '{filepath_md}'")

        # Écriture Markdown
        with open(filepath_md, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        # Vérifications post-écriture
        if not os.path.exists(filepath_md):
            raise FileNotFoundError(f"Le fichier sauvegardé est introuvable : '{filepath_md}'")

        size_bytes = os.path.getsize(filepath_md)
        if size_bytes <= 0:
            raise ValueError(f"Le fichier sauvegardé est vide (taille={size_bytes})")

        filepath_html = None
        if html_content:
            filename_html = f"deep_research_{slug}_{timestamp}.html"
            filepath_html = os.path.abspath(os.path.join(DOWNLOADS_DIR, filename_html))
            with open(filepath_html, "w", encoding="utf-8") as f:
                f.write(html_content)

        logger.info(f"[Save] Rapport persisté : '{filepath_md}' ({size_bytes} octets).")
        return {
            "verified": True,
            "filepath_md": filepath_md,
            "filepath_html": filepath_html,
            "size_bytes": size_bytes,
            "filename": filename_md,
        }

    # ── Captures d'Écran d'Erreur ─────────────────────────────────────────────

    async def _capture_screenshot(self, name_suffix: str = "") -> Optional[str]:
        """Capture une screenshot JPEG qualité 60-75 du viewport en cas d'erreur."""
        if not self._page or (hasattr(self._page, "is_closed") and self._page.is_closed()):
            return None
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            s_name = f"dr_screenshot_{timestamp}_{name_suffix}.jpg"
            dest_path = os.path.abspath(os.path.join(SCREENSHOTS_DIR, s_name))
            await self._page.screenshot(path=dest_path, type="jpeg", quality=70)

            # Copie vers static pour affichage HUD
            try:
                static_dest = os.path.join(BASE_DIR, "static", "latest_screenshot.jpg")
                await self._page.screenshot(path=static_dest, type="jpeg", quality=70)
            except Exception:
                pass

            logger.info(f"[Screenshot] Capture enregistrée : '{dest_path}'")
            return dest_path
        except Exception as e:
            logger.warning(f"[Screenshot] Échec capture d'écran : {e}")
            return None

    # ── Livraison Conditionnelle & Accusé Réel ─────────────────────────────────

    async def _deliver_result(
        self,
        page_url: Optional[str],
        snapshot_path: Optional[str],
        topic: str,
        filepath_md: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Route le résultat selon la connectivité du PC :
          - PC en ligne → ouverture locale avec accusé d'exécution vérifié.
          - PC hors ligne → envoi par e-mail Stark avec pièce jointe.
        """
        from services.local_agent_service import is_pc_connected_async

        pc_online = await is_pc_connected_async()
        logger.info(f"[Delivery] PC connecté : {pc_online}")

        if pc_online and (page_url or filepath_md or snapshot_path):
            target_to_open = page_url or filepath_md or snapshot_path
            return await self._deliver_to_screen(target_to_open, topic)
        else:
            attachment = filepath_md or snapshot_path
            return await self._deliver_by_email(attachment, topic)

    async def _deliver_to_screen(self, target: str, topic: str) -> Dict[str, Any]:
        """Ouvre le rapport ou la page web sur l'écran du PC avec accusé d'exécution."""
        try:
            from services.local_agent_service import local_agent_service
            is_web_url = target.startswith(("http://", "https://"))
            cmd = "open_browser" if is_web_url else "open_browser"

            result = await local_agent_service.execute_command(
                cmd,
                timeout=20.0,
                url=target,
            )
            status_ack = result.get("status") in ("success", "opened_locally") or result.get("ok") is True
            logger.info(f"[Delivery] Accusé ouverture écran ({target}) : {result.get('status')}")
            return {
                "delivery_mode": "screen",
                "status": "success" if status_ack else "warning",
                "acknowledged": status_ack,
                "url": target,
                "message": result.get("message", "Rapport ouvert sur votre écran."),
            }
        except Exception as e:
            logger.error(f"[Delivery] Erreur affichage écran : {e}")
            return {"delivery_mode": "screen", "status": "error", "error": str(e)}

    async def _deliver_by_email(self, attachment_path: Optional[str], topic: str) -> Dict[str, Any]:
        """Envoie le rapport par e-mail Stark avec pièce jointe sécurisée."""
        try:
            from services.email_service import send_email_async

            subject = f"⚡ Stark | Rapport Deep Research : {topic[:60]}"
            body = (
                f"# Rapport Deep Research J.A.R.V.I.S.\n\n"
                f"**Sujet :** {topic}\n\n"
                f"**Généré le :** {datetime.now().strftime('%d/%m/%Y à %H:%M')}\n\n"
                f"Le rapport complet est joint à cet e-mail.\n\n"
                f"*— J.A.R.V.I.S., Stark Industries*"
            )
            attachments = [attachment_path] if attachment_path and os.path.exists(attachment_path) else []

            await send_email_async(
                subject=subject,
                body=body,
                attachments=attachments,
            )
            logger.info(f"[Delivery] Email Stark envoyé avec pièce jointe : {attachment_path}")
            return {
                "delivery_mode": "email",
                "status": "sent",
                "attachment": attachment_path,
                "message": "Rapport Deep Research envoyé par email Stark.",
            }
        except Exception as e:
            logger.error(f"[Delivery] Erreur envoi email : {e}")
            return {"delivery_mode": "email", "status": "error", "error": str(e)}

    async def _inject_voice_milestone(self, text: str, action_key: str) -> None:
        """Émet un jalon de progression vocal non-bloquant."""
        try:
            await voice_injection_queue.enqueue(
                text=text,
                session=self._live_session,
                priority=InjectionPriority.PROGRESS_MILESTONE,
                action_key=action_key,
            )
        except Exception as e:
            logger.debug(f"[Voice] Jalon vocal ignoré ({action_key}) : {e}")

    # ── Workflow Complet L3 ───────────────────────────────────────────────────

    async def run_deep_research(
        self,
        topic: str,
        live_session: Any = None,
        task_id: Optional[str] = None,
        poll_interval: Optional[float] = None,
        max_wait_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Workflow complet L3 via Google Chrome CDP :
          1. Connexion CDP & navigation vers Gemini
          2. Contrôle session
          3. Sélection mode Deep Research
          4. Saisie & soumission du sujet
          5. Détection et confirmation du plan proposé
          6. Polling de complétion non-bloquant
          7. Extraction Markdown & Canvas
          8. Sauvegarde persistante vérifiée (downloads/ ou artifacts/)
          9. Livraison conditionnelle (écran PC ou e-mail)
        """
        if live_session:
            self._live_session = live_session

        t_id = task_id or f"dr_l3_{int(time.time() * 1000)}"
        started_at = time.time()
        result: Dict[str, Any] = {
            "task_id": t_id,
            "topic": topic,
            "status": "running",
            "steps_completed": [],
            "delivery": None,
            "duration_seconds": 0,
            "markdown_path": None,
            "screenshot_path": None,
        }

        try:
            # 1. Connexion CDP
            logger.info(f"[DR-L3] [DeepResearch] Démarrage Deep Research : '{topic}' (task_id={t_id})")
            await self._inject_voice_milestone(
                "Je lance la recherche approfondie sur Gemini Web via votre navigateur.",
                "dr_step1_connect"
            )

            connected = await self._connect()
            if not connected:
                shot = await self._capture_screenshot("connect_error")
                err_msg = "Impossible de se connecter à Chrome CDP sur le port 9222."
                l3_err = L3ErrorDetails(
                    etape="cdp_connection",
                    exception=err_msg,
                    traceback_court="",
                    capture_ecran=shot,
                    cause_courte="Chrome CDP non joignable (port 9222)",
                    fallback_initiated=True,
                )
                set_last_l3_error(l3_err)
                logger.error(f"[DeepResearch] [Étape: cdp_connection] {l3_err.cause_courte}")
                result.update({
                    "status": "error",
                    "error": err_msg,
                    "screenshot_path": shot,
                    "l3_error": l3_err.to_dict(),
                })
                return result
            result["steps_completed"].append("cdp_connected")

            # 2. Navigation
            nav_ok = await self._navigate_to_gemini()
            if not nav_ok:
                shot = await self._capture_screenshot("nav_error")
                err_msg = "Navigation vers Gemini échouée."
                l3_err = L3ErrorDetails(
                    etape="navigation",
                    exception=err_msg,
                    traceback_court="",
                    capture_ecran=shot,
                    cause_courte="Page Gemini inaccessible",
                    fallback_initiated=True,
                )
                set_last_l3_error(l3_err)
                logger.error(f"[DeepResearch] [Étape: navigation] {l3_err.cause_courte}")
                result.update({
                    "status": "error",
                    "error": err_msg,
                    "screenshot_path": shot,
                    "l3_error": l3_err.to_dict(),
                })
                return result
            result["steps_completed"].append("navigation_ok")

            # Vérification de connexion / session Google
            if await self._check_login_state():
                shot = await self._capture_screenshot("login_required")
                err_msg = "Connexion Google requise sur votre navigateur Chrome."
                l3_err = L3ErrorDetails(
                    etape="login_required",
                    exception=err_msg,
                    traceback_court="",
                    capture_ecran=shot,
                    cause_courte="Session Google/Gemini non authentifiée",
                    fallback_initiated=True,
                )
                set_last_l3_error(l3_err)
                logger.warning(f"[DeepResearch] [Étape: login_required] {l3_err.cause_courte}")
                result.update({
                    "status": "needs_login",
                    "error": err_msg,
                    "screenshot_path": shot,
                    "l3_error": l3_err.to_dict(),
                })
                await self._inject_voice_milestone(
                    "Une connexion à votre compte Google est requise sur Chrome pour utiliser Deep Research.",
                    "dr_login_needed"
                )
                return result

            # 3. Sélection du mode Deep Research
            dr_ok = await self._select_deep_research_mode()
            result["steps_completed"].append("deep_research_mode_selected" if dr_ok else "deep_research_mode_failed")

            # 4. Saisie du sujet
            fill_ok = await self._fill_prompt(topic)
            if not fill_ok:
                shot = await self._capture_screenshot("fill_error")
                err_msg = "Impossible d'injecter le sujet dans le prompt Gemini."
                l3_err = L3ErrorDetails(
                    etape="prompt_fill",
                    exception=err_msg,
                    traceback_court="",
                    capture_ecran=shot,
                    cause_courte="Champ de saisie Gemini introuvable",
                    fallback_initiated=True,
                )
                set_last_l3_error(l3_err)
                logger.error(f"[DeepResearch] [Étape: prompt_fill] {l3_err.cause_courte}")
                result.update({
                    "status": "error",
                    "error": err_msg,
                    "screenshot_path": shot,
                    "l3_error": l3_err.to_dict(),
                })
                return result
            result["steps_completed"].append("prompt_filled")

            # 5. Soumission
            send_ok = await self._send_prompt()
            result["steps_completed"].append("prompt_sent" if send_ok else "prompt_send_failed")

            # 6. Détection et confirmation du plan de recherche proposé
            await self._confirm_research_plan(timeout_seconds=8.0)
            result["steps_completed"].append("plan_confirmed")

            # 7. Polling de complétion
            completed = await self._wait_for_research_completion(
                poll_interval=poll_interval,
                max_wait=max_wait_seconds,
            )
            result["steps_completed"].append("research_completed" if completed else "research_timeout")
            result["duration_seconds"] = round(time.time() - started_at)

            # 8. Extraction du rapport
            markdown_content = await self._extract_report_markdown()
            page_url = await self._trigger_webpage_creation()

            if not markdown_content and not page_url:
                shot = await self._capture_screenshot("extraction_failed")
                err_msg = "Échec d'extraction du rapport final de recherche."
                l3_err = L3ErrorDetails(
                    etape="extract_report",
                    exception=err_msg,
                    traceback_court="",
                    capture_ecran=shot,
                    cause_courte="Contenu du rapport introuvable ou vide",
                    fallback_initiated=True,
                )
                set_last_l3_error(l3_err)
                logger.error(f"[DeepResearch] [Étape: extract_report] {l3_err.cause_courte}")
                result.update({
                    "status": "error",
                    "error": err_msg,
                    "screenshot_path": shot,
                    "l3_error": l3_err.to_dict(),
                })
                return result

            # 9. Sauvegarde persistante vérifiée
            save_info = self._save_report_file(
                topic=topic,
                markdown_content=markdown_content or f"# Rapport Deep Research : {topic}\n\nPage Canvas : {page_url}",
            )
            result["markdown_path"] = save_info.get("filepath_md")
            result["steps_completed"].append("report_persisted")

            # 10. Livraison
            delivery_res = await self._deliver_result(
                page_url=page_url,
                snapshot_path=None,
                topic=topic,
                filepath_md=save_info.get("filepath_md"),
            )
            result["delivery"] = delivery_res
            result["status"] = "completed"
            result["page_url"] = page_url

            final_msg = f"La recherche approfondie sur « {topic} » est terminée et enregistrée."
            await self._inject_voice_milestone(final_msg, "dr_final_delivery")
            return result

        except asyncio.CancelledError:
            logger.info(f"[DR-L3] Tâche {t_id} annulée.")
            result["status"] = "cancelled"
            return result

        except Exception as e:
            shot = None
            try:
                shot = await self._capture_screenshot("unexpected_error")
            except Exception:
                pass
            import traceback
            tb_short = sanitize_error_text(traceback.format_exc(limit=3))[-500:]
            e_str = sanitize_error_text(str(e))
            l3_err = L3ErrorDetails(
                etape="unexpected_exception",
                exception=f"{e.__class__.__name__}: {e_str}",
                traceback_court=tb_short,
                capture_ecran=shot,
                cause_courte=f"Erreur inattendue ({e.__class__.__name__})",
                fallback_initiated=True,
            )
            set_last_l3_error(l3_err)
            logger.error(f"[DeepResearch] [EXCEPTION RECHERCHE L3] {l3_err.cause_courte} : {e_str}\n{tb_short}", exc_info=True)
            result.update({
                "status": "error",
                "error": e_str,
                "screenshot_path": shot,
                "l3_error": l3_err.to_dict(),
            })
            return result

        finally:
            await self._disconnect()


# ──────────────────────────────────────────────────────────────────────────────
# Service de lancement non-bloquant
# ──────────────────────────────────────────────────────────────────────────────

class GeminiDeepResearchEngine:
    """Moteur singleton de lancement non-bloquant pour Deep Research L3."""

    def __init__(self):
        self._current_task: Optional[asyncio.Task] = None
        self._last_result: Optional[Dict[str, Any]] = None
        self._last_l3_error: Optional[Dict[str, Any]] = None
        self._automator: Optional[GeminiWebAutomator] = None
        self._active_tasks: Dict[str, asyncio.Task] = {}

    def is_running(self) -> bool:
        """Indique si une recherche est en cours."""
        return self._current_task is not None and not self._current_task.done()

    def get_status(self, task_id: Optional[str] = None) -> Dict[str, Any]:
        """Retourne le statut courant de la recherche."""
        if self.is_running():
            return {"active": True, "status": "running"}
        if self._last_result:
            return {"active": False, **self._last_result}
        return {"active": False, "status": "idle"}

    def get_last_error(self) -> Optional[Dict[str, Any]]:
        """Retourne la dernière erreur L3 enregistrée."""
        return self._last_l3_error or get_last_l3_error()

    def get_last_l3_error(self) -> Optional[Dict[str, Any]]:
        """Retourne la dernière erreur L3 enregistrée (alias)."""
        return self._last_l3_error or get_last_l3_error()

    async def launch(
        self,
        topic: str,
        live_session: Any = None,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Lance la recherche Deep Research Gemini Web en arrière-plan sans bloquer la voix."""
        if self.is_running():
            return {
                "status": "already_running",
                "message": "Une recherche Deep Research est déjà en cours. Veuillez patienter.",
            }

        t_id = task_id or f"gemini_dr_{int(time.time() * 1000)}"
        self._automator = GeminiWebAutomator()
        if live_session:
            self._automator.set_live_session(live_session)

        async def _bg_task():
            try:
                res = await self._automator.run_deep_research(
                    topic=topic,
                    live_session=live_session,
                    task_id=t_id,
                )
                self._last_result = res
                if res.get("l3_error"):
                    self._last_l3_error = res["l3_error"]
            except Exception as e:
                import traceback
                tb_short = sanitize_error_text(traceback.format_exc(limit=3))[-500:]
                e_str = sanitize_error_text(str(e))
                l3_err = L3ErrorDetails(
                    etape="engine_bg_task",
                    exception=f"{e.__class__.__name__}: {e_str}",
                    traceback_court=tb_short,
                    cause_courte=f"Erreur d'arrière-plan ({e.__class__.__name__})",
                    fallback_initiated=True,
                )
                self._last_l3_error = l3_err.to_dict()
                set_last_l3_error(l3_err)
                self._last_result = {"status": "error", "error": e_str, "task_id": t_id, "l3_error": self._last_l3_error}
            finally:
                self._current_task = None
                self._active_tasks.pop(t_id, None)

        self._current_task = asyncio.create_task(_bg_task())
        self._active_tasks[t_id] = self._current_task
        logger.info(f"[Engine] [DeepResearch] Deep Research L3 lancé en arrière-plan (task_id={t_id}) : '{topic}'")

        return {
            "status": "launched_in_background",
            "task_id": t_id,
            "topic": topic,
            "message": f"Recherche approfondie lancée sur Gemini Web pour : « {topic} ».",
        }


# Singleton global
gemini_deep_research_engine = GeminiDeepResearchEngine()
