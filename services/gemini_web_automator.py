# DEPRECATED: remplacé par browser_agent
"""services/gemini_web_automator.py
Moteur d'Automatisation Gemini Web pour J.A.R.V.I.S. - Stark Industries.
Pilote l'interface officielle gemini.google.com via Chrome DevTools Protocol (CDP) /
Playwright connecté au profil Chrome réel de Pierre, sans aucun outil de vision.

Architecture :
- Mémoire persistante des coordonnées & sélecteurs DOM (data/gemini_ui_map.json).
- Détection de dérive de layout : re-calcul automatique via inspection du DOM si un clic
  ne produit pas l'état attendu.
- Polling non-bloquant pour détecter la fin de la recherche Deep Research.
- Livraison conditionnelle : affichage à l'écran (PC connecté) ou snapshot HTML + email
  (PC hors ligne).

Contraintes absolues respectées :
  1. Zéro modèle de vision – interactions uniquement par coordonnées et DOM.
  2. Non-bloquant – renvoie {status: launched_in_background} immédiatement, puis jalons via VoiceInjectionQueue.
  3. Auto-réparation – si un bouton est absent de ses coordonnées mémorisées, on inspecte le DOM,
     on recalcule les coordonnées et on met à jour le JSON.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import config
from config import BASE_DIR
from services.voice_injection_queue import voice_injection_queue, InjectionPriority

logger = logging.getLogger("jarvis.gemini_web_automator")

# ─── Chemins ──────────────────────────────────────────────────────────────────
UI_MAP_PATH = os.path.join(BASE_DIR, "data", "gemini_ui_map.json")
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)

# ─── Constantes ───────────────────────────────────────────────────────────────
CDP_URL = "http://localhost:9222"
GEMINI_URL = "https://gemini.google.com"
RESEARCH_POLL_INTERVAL = 5.0    # secondes entre chaque sonde de fin de recherche
RESEARCH_MAX_WAIT = 1200.0      # 20 minutes max d'attente
ACTION_CONFIRM_TIMEOUT = 3.0    # délai d'attente de confirmation post-clic
DOM_FALLBACK_TIMEOUT = 6000     # ms pour les localisations DOM de repli


# ──────────────────────────────────────────────────────────────────────────────
# Gestionnaire de la carte UI persistante
# ──────────────────────────────────────────────────────────────────────────────

class UIMapManager:
    """Charge, expose et met à jour en temps réel la carte des coordonnées de l'interface Gemini."""

    def __init__(self, path: str = UI_MAP_PATH):
        self._path = path
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Charge le JSON depuis le disque."""
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
        """Retourne la définition mémorisée d'une action (coordonnées + sélecteurs)."""
        return self._data.get("actions", {}).get(action_name, {})

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
# Automateur principal
# ──────────────────────────────────────────────────────────────────────────────

class GeminiWebAutomator:
    """
    Orchestre l'automatisation de gemini.google.com via Playwright CDP.
    Mémorise les coordonnées, détecte les dérives, s'auto-répare.
    """

    def __init__(self):
        self.ui_map = UIMapManager()
        self._playwright = None
        self._browser = None
        self._page = None
        self._live_session: Any = None  # Session Gemini Live pour jalons vocaux

    def set_live_session(self, session: Any) -> None:
        """Injecte la session Gemini Live pour les jalons vocaux de progression."""
        self._live_session = session

    # ── Connexion CDP ──────────────────────────────────────────────────────────

    async def _connect(self) -> bool:
        """
        Connecte Playwright au Chrome réel de Pierre via CDP (port 9222).
        Réutilise la connexion existante si elle est toujours valide.
        Retourne True si la connexion est établie.
        """
        try:
            from playwright.async_api import async_playwright

            # Teste si la connexion existante est encore valide
            if self._page and not self._page.is_closed():
                return True

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.connect_over_cdp(CDP_URL)

            # Utilise le premier contexte existant (profil connecté de Pierre)
            contexts = self._browser.contexts
            ctx = contexts[0] if contexts else await self._browser.new_context()

            # Cherche un onglet Gemini existant ou en crée un nouveau
            self._page = None
            for p in ctx.pages:
                if "gemini.google.com" in p.url:
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

    # ── Navigation ────────────────────────────────────────────────────────────

    async def _navigate_to_gemini(self) -> bool:
        """Navigue vers gemini.google.com si on n'y est pas déjà."""
        try:
            current = self._page.url
            if "gemini.google.com" not in current:
                await self._page.goto(GEMINI_URL, wait_until="domcontentloaded", timeout=30000)
                await self._page.wait_for_timeout(2000)
                logger.info("[Nav] Navigation vers gemini.google.com effectuée.")
            return True
        except Exception as e:
            logger.error(f"[Nav] Échec navigation vers Gemini : {e}")
            return False

    # ── Clic avec vérification et auto-réparation ──────────────────────────────

    async def click_with_verification(
        self,
        action_name: str,
        verify_timeout: float = ACTION_CONFIRM_TIMEOUT,
    ) -> bool:
        """
        Exécute un clic robuste avec auto-réparation en cas de dérive UI.

        Stratégie :
          1. Clic aux coordonnées x,y mémorisées.
          2. Attente de l'état de validation (verify_timeout secondes).
          3. Si l'état n'apparaît pas → détection de dérive → localisation DOM via
             sélecteurs de repli → extraction de la bounding box → mise à jour du JSON
             → re-clic.
        """
        action = self.ui_map.get_action(action_name)
        x = action.get("x")
        y = action.get("y")
        validation_selector = self.ui_map.get_validation_selector(action_name)
        fallback_selectors = self.ui_map.get_fallback_selectors(action_name)

        # ── Tentative 1 : Clic aux coordonnées mémorisées ──
        if x is not None and y is not None:
            try:
                await self._page.mouse.click(x, y)
                logger.debug(f"[Click] '{action_name}' → clic à ({x},{y})")

                if validation_selector:
                    confirmed = await self._wait_for_selector(validation_selector, timeout_ms=int(verify_timeout * 1000))
                    if confirmed:
                        logger.info(f"[Click] ✅ '{action_name}' confirmé aux coordonnées mémorisées.")
                        return True
                    else:
                        logger.warning(f"[Click] ⚠️ Dérive UI détectée pour '{action_name}'. Lancement du repli DOM.")
                else:
                    # Pas de sélecteur de validation → on accepte le clic par défaut
                    await self._page.wait_for_timeout(500)
                    return True
            except Exception as e:
                logger.warning(f"[Click] Clic à ({x},{y}) échoué : {e}")

        # ── Tentative 2 : Repli DOM (sélecteurs de repli) ──
        for selector in fallback_selectors:
            try:
                element = self._page.locator(selector).first
                count = await element.count()
                if count == 0:
                    continue

                # Extrait la bounding box pour mettre à jour les coordonnées
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
                        logger.info(f"[Click] ✅ '{action_name}' confirmé via sélecteur de repli : {selector}")
                        return True
                else:
                    logger.info(f"[Click] ✅ '{action_name}' cliqué via sélecteur de repli : {selector}")
                    return True

            except Exception as e:
                logger.debug(f"[Click] Sélecteur de repli '{selector}' échoué : {e}")
                continue

        logger.error(f"[Click] ❌ '{action_name}' : tous les replis ont échoué.")
        return False

    async def _wait_for_selector(self, selector: str, timeout_ms: int = 3000) -> bool:
        """Vérifie la présence d'un sélecteur CSS dans le DOM avec un timeout court."""
        try:
            await self._page.wait_for_selector(selector, state="attached", timeout=timeout_ms)
            return True
        except Exception:
            return False

    # ── Injection de texte ────────────────────────────────────────────────────

    async def _fill_prompt(self, topic: str) -> bool:
        """
        Injecte le sujet de recherche dans le champ de saisie Gemini.
        Essaie d'abord les coordonnées mémorisées, puis les sélecteurs de repli.
        """
        action = self.ui_map.get_action("prompt_textarea")
        x = action.get("x")
        y = action.get("y")
        fallback_selectors = self.ui_map.get_fallback_selectors("prompt_textarea")

        # Tentative par coordonnées
        if x and y:
            try:
                await self._page.mouse.click(x, y)
                await self._page.wait_for_timeout(300)
                await self._page.keyboard.type(topic, delay=30)
                await self._page.wait_for_timeout(500)
                # Vérification : le texte est bien dans le DOM
                content = await self._page.evaluate(
                    "() => document.activeElement ? document.activeElement.innerText || document.activeElement.value : ''"
                )
                if topic[:20].lower() in (content or "").lower():
                    logger.info(f"[Fill] Texte injecté avec succès (coordonnées).")
                    return True
            except Exception as e:
                logger.warning(f"[Fill] Injection par coordonnées échouée : {e}")

        # Tentative par sélecteurs DOM
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
                # On préfère fill() pour les vrais textarea, keyboard.type() pour contenteditable
                try:
                    await el.fill(topic, timeout=5000)
                except Exception:
                    await el.type(topic, delay=30)
                await self._page.wait_for_timeout(500)
                logger.info(f"[Fill] Texte injecté via sélecteur '{selector}'.")
                return True
            except Exception as e:
                logger.debug(f"[Fill] Sélecteur '{selector}' échoué : {e}")

        logger.error("[Fill] ❌ Impossible d'injecter le sujet dans le prompt Gemini.")
        return False

    # ── Polling de fin de recherche ───────────────────────────────────────────

    async def _wait_for_research_completion(self) -> bool:
        """
        Boucle de polling non-bloquante observant le DOM pour détecter la fin de la recherche.
        Condition de fin :
          - TOUS les sélecteurs d'absence (spinner, thinking...) ont disparu, ET
          - AU MOINS UN sélecteur de présence (réponse finale) est présent.
        Retourne True si la recherche est terminée, False si timeout.
        """
        completion_action = self.ui_map.get_action("research_completion")
        presence_selectors = completion_action.get("fallback_selectors", [])
        absence_selectors = completion_action.get("absence_selectors", [])

        start_time = time.time()
        milestone_30_sent = False
        milestone_60_sent = False
        milestone_120_sent = False

        logger.info("[Poll] Démarrage du polling de fin de Deep Research...")

        while time.time() - start_time < RESEARCH_MAX_WAIT:
            elapsed = time.time() - start_time

            # Jalons vocaux intermédiaires
            if not milestone_30_sent and elapsed > 30:
                await self._inject_voice_milestone(
                    "La recherche approfondie Gemini est en cours, je vérifierai les résultats dans quelques instants.",
                    "dr_milestone_30"
                )
                milestone_30_sent = True
            if not milestone_60_sent and elapsed > 60:
                await self._inject_voice_milestone(
                    "La recherche approfondie continue, Gemini explore encore les sources. Patience.",
                    "dr_milestone_60"
                )
                milestone_60_sent = True
            if not milestone_120_sent and elapsed > 120:
                await self._inject_voice_milestone(
                    "La recherche est très complète. Gemini analyse toujours les données. Je vous préviendrai dès la fin.",
                    "dr_milestone_120"
                )
                milestone_120_sent = True

            try:
                # Vérifie l'absence de tous les indicateurs de chargement
                all_spinners_gone = True
                for sel in absence_selectors:
                    count = await self._page.locator(sel).count()
                    if count > 0:
                        all_spinners_gone = False
                        break

                if all_spinners_gone:
                    # Vérifie la présence d'au moins un indicateur de réponse finale
                    for sel in presence_selectors:
                        count = await self._page.locator(sel).count()
                        if count > 0:
                            logger.info(f"[Poll] ✅ Recherche terminée après {int(elapsed)}s. Détecteur : '{sel}'")
                            return True

            except Exception as e:
                logger.debug(f"[Poll] Erreur de sonde DOM : {e}")

            await asyncio.sleep(RESEARCH_POLL_INTERVAL)

        logger.warning(f"[Poll] ⚠️ Timeout ({RESEARCH_MAX_WAIT}s) atteint sans détection de fin de recherche.")
        return False

    # ── Extraction de page web ────────────────────────────────────────────────

    async def _trigger_webpage_creation(self) -> Optional[str]:
        """
        Clique sur le bouton 'Créer une page web' de Gemini (Canvas/artifact).
        Retourne l'URL ou le src de l'iframe générée si disponible, None sinon.
        """
        logger.info("[WebPage] Déclenchement de la création de page web Canvas Gemini...")
        success = await self.click_with_verification(
            "create_webpage_button",
            verify_timeout=10.0,
        )
        if not success:
            logger.warning("[WebPage] Le bouton 'Créer une page web' n'a pas pu être cliqué.")
            return None

        # Attend l'apparition du canvas/iframe
        await self._page.wait_for_timeout(3000)

        # Extrait l'URL du canvas depuis les sélecteurs mémorisés
        url_action = self.ui_map.get_action("webpage_url")
        for selector in url_action.get("fallback_selectors", []):
            try:
                el = self._page.locator(selector).first
                if await el.count() == 0:
                    continue
                href = await el.get_attribute("src") or await el.get_attribute("href")
                if href:
                    logger.info(f"[WebPage] URL Canvas extraite : {href}")
                    return href
            except Exception:
                pass

        # Fallback : URL courante de l'onglet
        current_url = self._page.url
        logger.info(f"[WebPage] URL courante utilisée : {current_url}")
        return current_url

    async def _capture_page_snapshot(self) -> Optional[str]:
        """
        Capture le contenu HTML complet de la page courante et le sauvegarde
        dans downloads/ avec un horodatage. Équivalent de Ctrl+S.
        Retourne le chemin local du fichier HTML sauvegardé.
        """
        try:
            html_content = await self._page.content()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"deep_research_export_{timestamp}.html"
            filepath = os.path.join(DOWNLOADS_DIR, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html_content)
            size_kb = len(html_content) / 1024
            logger.info(f"[Snapshot] Page HTML sauvegardée : {filepath} ({size_kb:.1f} Ko)")
            return filepath
        except Exception as e:
            logger.error(f"[Snapshot] Échec de la capture HTML : {e}")
            return None

    # ── Livraison conditionnelle ───────────────────────────────────────────────

    async def _deliver_result(
        self,
        page_url: Optional[str],
        snapshot_path: Optional[str],
        topic: str,
    ) -> Dict[str, Any]:
        """
        Route le résultat selon la connectivité du PC de Pierre :
          - PC connecté → focus Chrome + navigation vers l'URL du Canvas.
          - PC hors ligne → snapshot HTML + envoi email Stark.
        """
        from services.local_agent_service import is_pc_connected_async

        pc_online = await is_pc_connected_async()
        logger.info(f"[Delivery] PC connecté : {pc_online}")

        if pc_online and page_url:
            return await self._deliver_to_screen(page_url, topic)
        else:
            if not snapshot_path:
                snapshot_path = await self._capture_page_snapshot()
            return await self._deliver_by_email(snapshot_path, topic)

    async def _deliver_to_screen(self, page_url: str, topic: str) -> Dict[str, Any]:
        """
        Ouvre la page web générée sur l'écran de Pierre via l'agent local CDP.
        """
        try:
            from services.local_agent_service import local_agent_service
            result = await local_agent_service.execute_command(
                "execute_cdp_browser_action",
                timeout=20.0,
                url=page_url,
                actions=[],
                instruction=f"Affichage du rapport Deep Research : {topic}",
                task_id=f"dr_delivery_{int(time.time())}",
            )
            logger.info(f"[Delivery] Résultat affichage écran : {result.get('status')}")
            return {
                "delivery_mode": "screen",
                "status": result.get("status", "success"),
                "url": page_url,
                "message": result.get("message", "Page web ouverte sur votre écran."),
            }
        except Exception as e:
            logger.error(f"[Delivery] Erreur affichage écran : {e}")
            return {"delivery_mode": "screen", "status": "error", "error": str(e)}

    async def _deliver_by_email(self, snapshot_path: Optional[str], topic: str) -> Dict[str, Any]:
        """
        Envoie le rapport Deep Research par email Stark avec le fichier HTML en pièce jointe.
        """
        try:
            from services.email_service import send_email_async

            subject = f"⚡ Stark | Rapport Deep Research : {topic[:60]}"
            body = (
                f"# Rapport Deep Research J.A.R.V.I.S.\n\n"
                f"**Sujet :** {topic}\n\n"
                f"**Généré le :** {datetime.now().strftime('%d/%m/%Y à %H:%M')}\n\n"
                f"Le rapport complet est joint à cet e-mail en pièce jointe HTML.\n"
                f"Ouvrez le fichier joint dans votre navigateur pour consulter la page web générée par Gemini.\n\n"
                f"*— J.A.R.V.I.S., Stark Industries*"
            )
            attachments = [snapshot_path] if snapshot_path and os.path.exists(snapshot_path) else []

            await send_email_async(
                subject=subject,
                body=body,
                attachments=attachments,
            )
            logger.info(f"[Delivery] Email Stark envoyé avec pièce jointe : {snapshot_path}")
            return {
                "delivery_mode": "email",
                "status": "sent",
                "attachment": snapshot_path,
                "message": "Rapport Deep Research envoyé par email Stark.",
            }
        except Exception as e:
            logger.error(f"[Delivery] Erreur envoi email : {e}")
            return {"delivery_mode": "email", "status": "error", "error": str(e)}

    # ── Jalons vocaux ─────────────────────────────────────────────────────────

    async def _inject_voice_milestone(self, text: str, action_key: str) -> None:
        """Émet un jalon de progression dans la file vocale Live (Aoede) de manière non-bloquante."""
        try:
            await voice_injection_queue.enqueue(
                text=text,
                session=self._live_session,
                priority=InjectionPriority.PROGRESS_MILESTONE,
                action_key=action_key,
            )
        except Exception as e:
            logger.debug(f"[Voice] Jalon vocal ignoré ({action_key}) : {e}")

    # ── Workflow principal ────────────────────────────────────────────────────

    async def run_deep_research(
        self,
        topic: str,
        live_session: Any = None,
    ) -> Dict[str, Any]:
        """
        Workflow complet de Deep Research via Gemini Web.

        Étapes :
          1. Connexion CDP à Chrome et navigation vers gemini.google.com.
          2. Sélection du mode Deep Research.
          3. Injection du sujet et envoi.
          4. Polling non-bloquant jusqu'à la fin de la recherche.
          5. Clic sur 'Créer une page web'.
          6. Livraison conditionnelle (écran ou email).

        Retourne un dict avec le statut final et les détails.
        """
        if live_session:
            self._live_session = live_session

        started_at = time.time()
        result: Dict[str, Any] = {
            "topic": topic,
            "status": "running",
            "steps_completed": [],
            "delivery": None,
            "duration_seconds": 0,
        }

        try:
            # ── Étape 1 : Connexion CDP ──
            logger.info(f"[DR] Démarrage Deep Research via Gemini Web : '{topic}'")
            await self._inject_voice_milestone(
                "Je lance la recherche approfondie sur Gemini Web. J'accède à l'interface.",
                "dr_step1_connect"
            )

            connected = await self._connect()
            if not connected:
                await self._inject_voice_milestone(
                    "Je n'arrive pas à accéder à Google Chrome. Vérifiez que Chrome est ouvert avec le port de débogage actif.",
                    "dr_connect_error"
                )
                return {**result, "status": "error", "error": "Impossible de se connecter à Chrome CDP."}

            result["steps_completed"].append("cdp_connected")
            logger.info("[DR] ✅ Étape 1 : CDP connecté.")

            # ── Étape 2 : Navigation ──
            nav_ok = await self._navigate_to_gemini()
            if not nav_ok:
                return {**result, "status": "error", "error": "Navigation vers gemini.google.com échouée."}
            result["steps_completed"].append("navigation_ok")

            # ── Étape 3 : Activation du mode Deep Research ──
            await self._inject_voice_milestone(
                "Je sélectionne le mode Deep Research sur l'interface Gemini.",
                "dr_step3_mode"
            )
            dr_ok = await self.click_with_verification("deep_research_button", verify_timeout=5.0)
            if not dr_ok:
                logger.warning("[DR] Le mode Deep Research n'a pas pu être sélectionné. On continue quand même.")
            result["steps_completed"].append("deep_research_mode_selected" if dr_ok else "deep_research_mode_failed")

            # ── Étape 4 : Injection du sujet ──
            fill_ok = await self._fill_prompt(topic)
            if not fill_ok:
                return {**result, "status": "error", "error": "Impossible d'injecter le sujet dans le prompt Gemini."}
            result["steps_completed"].append("prompt_filled")

            # ── Étape 5 : Envoi (touche Entrée) ──
            try:
                await self._page.keyboard.press("Enter")
                await self._page.wait_for_timeout(1000)
            except Exception:
                # Fallback : clic sur le bouton send
                await self.click_with_verification("send_button", verify_timeout=3.0)

            result["steps_completed"].append("prompt_sent")
            await self._inject_voice_milestone(
                f"La recherche approfondie sur '{topic}' est lancée sur Gemini. J'attends les résultats.",
                "dr_step5_sent"
            )
            logger.info("[DR] ✅ Étape 5 : Requête envoyée. Polling de fin de recherche démarré.")

            # ── Étape 6 : Polling de fin ──
            completed = await self._wait_for_research_completion()
            if not completed:
                await self._inject_voice_milestone(
                    "La recherche a dépassé le délai maximum. Je vais tout de même tenter de récupérer les résultats.",
                    "dr_timeout_warn"
                )

            result["steps_completed"].append("research_completed" if completed else "research_timeout")
            result["duration_seconds"] = round(time.time() - started_at)

            # ── Étape 7 : Création de la page web ──
            await self._inject_voice_milestone(
                "Excellent ! La recherche est terminée. Je génère maintenant la page web avec les résultats.",
                "dr_step7_webpage"
            )
            page_url = await self._trigger_webpage_creation()
            result["steps_completed"].append("webpage_created" if page_url else "webpage_creation_failed")

            # Snapshot de secours si la page web n'a pas été générée
            snapshot_path = None
            if not page_url:
                logger.warning("[DR] Création de page web échouée. Capture HTML de secours.")
                snapshot_path = await self._capture_page_snapshot()

            # ── Étape 8 : Livraison conditionnelle ──
            delivery_result = await self._deliver_result(page_url, snapshot_path, topic)
            result["delivery"] = delivery_result
            result["status"] = "completed"
            result["page_url"] = page_url

            # Jalon vocal final
            mode = delivery_result.get("delivery_mode", "unknown")
            if mode == "screen":
                final_msg = (
                    f"La recherche approfondie sur '{topic}' est terminée et la page web est affichée sur votre écran."
                )
            elif mode == "email":
                final_msg = (
                    f"La recherche sur '{topic}' est terminée. Votre PC était hors ligne, "
                    f"j'ai envoyé le rapport complet par email Stark à votre adresse."
                )
            else:
                final_msg = f"La recherche approfondie sur '{topic}' est terminée."

            await self._inject_voice_milestone(final_msg, "dr_final_delivery")
            logger.info(f"[DR] ✅ Deep Research terminé : {result}")
            return result

        except asyncio.CancelledError:
            logger.info("[DR] Tâche Deep Research annulée.")
            result["status"] = "cancelled"
            return result

        except Exception as e:
            logger.error(f"[DR] Erreur inattendue : {e}", exc_info=True)
            result["status"] = "error"
            result["error"] = str(e)
            await self._inject_voice_milestone(
                f"Une erreur inattendue est survenue pendant la recherche approfondie. Détail : {e}",
                "dr_unexpected_error"
            )
            return result

        finally:
            await self._disconnect()


# ──────────────────────────────────────────────────────────────────────────────
# Service de lancement non-bloquant
# ──────────────────────────────────────────────────────────────────────────────

class GeminiDeepResearchEngine:
    """
    Moteur de Deep Research via Gemini Web.
    Expose un point d'entrée non-bloquant : lance la recherche en arrière-plan
    et retourne immédiatement {status: launched_in_background}.
    """

    def __init__(self):
        self._current_task: Optional[asyncio.Task] = None
        self._last_result: Optional[Dict[str, Any]] = None
        self._automator: Optional[GeminiWebAutomator] = None

    def is_running(self) -> bool:
        """Indique si une recherche est en cours."""
        return (
            self._current_task is not None
            and not self._current_task.done()
        )

    def get_status(self) -> Dict[str, Any]:
        """Retourne le statut courant de la recherche."""
        if self.is_running():
            return {"active": True, "status": "running"}
        if self._last_result:
            return {"active": False, **self._last_result}
        return {"active": False, "status": "idle"}

    async def launch(
        self,
        topic: str,
        live_session: Any = None,
    ) -> Dict[str, Any]:
        """
        Lance la recherche Deep Research Gemini Web en arrière-plan.
        Retourne immédiatement {status: launched_in_background} pour permettre
        à Aoede d'accuser réception en moins de 300ms.
        """
        if self.is_running():
            return {
                "status": "already_running",
                "message": "Une recherche Deep Research est déjà en cours. Veuillez patienter.",
            }

        self._automator = GeminiWebAutomator()
        if live_session:
            self._automator.set_live_session(live_session)

        async def _bg_task():
            try:
                res = await self._automator.run_deep_research(
                    topic=topic,
                    live_session=live_session,
                )
                self._last_result = res
            except Exception as e:
                self._last_result = {"status": "error", "error": str(e)}
            finally:
                self._current_task = None

        self._current_task = asyncio.create_task(_bg_task())
        logger.info(f"[Engine] Deep Research via Gemini Web lancé en arrière-plan : '{topic}'")

        return {
            "status": "launched_in_background",
            "topic": topic,
            "message": (
                f"Recherche approfondie lancée sur Gemini Web pour : '{topic}'. "
                "Je vous informerai vocalement de la progression et de la livraison."
            ),
        }


# Singleton global
gemini_deep_research_engine = GeminiDeepResearchEngine()
