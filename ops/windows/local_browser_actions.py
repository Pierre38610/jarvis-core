"""local_browser_actions.py
Pont CDP Playwright pour l'agent local Jarvis.
Gère les interactions de navigation, snapshots DOM balisés data-jarvis-id,
exécutions d'actions pas-à-pas et captures d'écran sur le Chrome réel de l'utilisateur.
"""

import base64
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("jarvis.browser_bridge")

SNAPSHOT_JS = """() => {
    // a) supprime les anciens attributs data-jarvis-id
    const prevElements = document.querySelectorAll('[data-jarvis-id]');
    for (let i = 0; i < prevElements.length; i++) {
        prevElements[i].removeAttribute('data-jarvis-id');
    }

    // b) sélectionne les éléments interactifs cibles
    const selector = 'a, button, input, textarea, select, [role=button], [role=link], [role=tab], [role=checkbox], [role=option], [contenteditable=true], [onclick]';
    const all = Array.from(document.querySelectorAll(selector));

    const viewportHeight = window.innerHeight || (document.documentElement ? document.documentElement.clientHeight : 800) || 800;
    const maxBottom = viewportHeight * 2; // dans le viewport ou jusqu'à 1 écran en dessous

    const visibleElements = [];
    for (const el of all) {
        const rect = el.getBoundingClientRect();
        // c) largeur et hauteur > 0, dans le viewport ou jusqu'à 1 écran en dessous, visibility != hidden
        if (rect.width <= 0 || rect.height <= 0) continue;
        if (rect.bottom < 0 || rect.top > maxBottom) continue;
        const style = window.getComputedStyle(el);
        if (style.visibility === 'hidden' || style.display === 'none') continue;

        visibleElements.push(el);
        if (visibleElements.length >= 150) break;
    }

    // d) numérote de 1 à 150 au maximum, pose data-jarvis-id, produit une ligne au format S3
    const lines = [];
    for (let i = 0; i < visibleElements.length; i++) {
        const id = i + 1;
        const el = visibleElements[i];
        el.setAttribute('data-jarvis-id', String(id));

        const tag = el.tagName.toLowerCase();
        const role = el.getAttribute('role') || '';

        let rawText = (el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim();
        rawText = rawText.replace(/\\s+/g, ' ');
        if (rawText.length > 80) {
            rawText = rawText.slice(0, 80);
        }

        let line = '';
        if (tag === 'a' || role === 'link') {
            let href = el.getAttribute('href') || '';
            if (href.length > 60) {
                href = href.slice(0, 60);
            }
            line = `[${id}] link "${rawText}"${href ? ' href=' + href : ''}`;
        } else if (tag === 'button' || role === 'button') {
            line = `[${id}] button "${rawText}"`;
        } else if (tag === 'input') {
            const inputType = el.getAttribute('type') || 'text';
            const placeholder = el.getAttribute('placeholder') || '';
            const val = el.value || '';
            let extra = '';
            if (placeholder) extra += ` placeholder="${placeholder.slice(0, 40)}"`;
            extra += ` value="${val.slice(0, 40)}"`;
            line = `[${id}] input[${inputType}]${extra}`;
        } else if (tag === 'textarea') {
            const placeholder = el.getAttribute('placeholder') || '';
            const val = el.value || '';
            let extra = '';
            if (placeholder) extra += ` placeholder="${placeholder.slice(0, 40)}"`;
            extra += ` value="${val.slice(0, 40)}"`;
            line = `[${id}] textarea${extra}`;
        } else if (tag === 'select') {
            line = `[${id}] select value="${(el.value || '').slice(0, 40)}"`;
        } else {
            const typeLabel = role ? role : tag;
            line = `[${id}] ${typeLabel} "${rawText}"`;
        }
        lines.push(line);
    }

    const bodyText = (document.body ? (document.body.innerText || document.body.textContent || '') : '').trim();
    const textTruncated = bodyText.slice(0, 1500);

    return {
        url: window.location.href,
        title: document.title,
        elements: lines.join('\\n'),
        text: textTruncated
    };
}"""


class BrowserBridge:
    """Garde UNE connexion CDP réutilisée et un dictionnaire task_id -> page."""

    def __init__(self, cdp_url: str = "http://localhost:9222"):
        self.cdp_url = cdp_url
        self._playwright = None
        self._browser = None
        self._tasks: Dict[str, Any] = {}

    async def _ensure_browser(self):
        """Assure la connexion CDP vers l'instance Chrome de l'utilisateur."""
        if self._browser:
            try:
                if hasattr(self._browser, "is_connected") and self._browser.is_connected():
                    return self._browser
            except Exception:
                pass

        from playwright.async_api import async_playwright
        if not self._playwright:
            self._playwright = await async_playwright().start()

        self._browser = await self._playwright.chromium.connect_over_cdp(self.cdp_url)
        return self._browser

    async def _get_page(self, task_id: str):
        """Récupère l'onglet associé à une tâche active."""
        page = self._tasks.get(task_id)
        if not page:
            raise ValueError(f"Aucune page active pour la tâche '{task_id}'")
        if hasattr(page, "is_closed") and page.is_closed():
            self._tasks.pop(task_id, None)
            raise ValueError(f"La page pour la tâche '{task_id}' a été fermée")
        return page

    async def browser_open_task(self, task_id: str, start_url: str = "") -> Dict[str, Any]:
        """Ouvre un NOUVEL onglet dans le contexte existant (browser.contexts[0]),
        va sur start_url (ou about:blank), renvoie {ok, url}.
        """
        browser = await self._ensure_browser()
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await context.new_page()

        target_url = (start_url or "").strip()
        if not target_url:
            target_url = "about:blank"
        elif not target_url.startswith(("http://", "https://", "about:")):
            target_url = f"https://{target_url}"

        if target_url != "about:blank":
            await page.goto(target_url, wait_until="domcontentloaded", timeout=25000)
        else:
            await page.goto("about:blank")

        self._tasks[task_id] = page
        current_url = getattr(page, "url", target_url)
        return {"ok": True, "url": current_url}

    async def browser_snapshot(self, task_id: str) -> Dict[str, Any]:
        """Exécute le script d'observation DOM : balise data-jarvis-id (1..150),
        filtre les éléments visibles, et renvoie {ok, url, title, elements, text}.
        """
        page = await self._get_page(task_id)
        res = await page.evaluate(SNAPSHOT_JS)
        if isinstance(res, dict):
            res["ok"] = True
            return res

        return {
            "ok": True,
            "url": getattr(page, "url", ""),
            "title": await page.title() if hasattr(page, "title") else "",
            "elements": "",
            "text": ""
        }

    async def browser_act(self, task_id: str, actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Exécute les actions dans l'ordre (types de S4 sauf extract).
        Ciblage par le sélecteur [data-jarvis-id="N"].
        Utilise click/fill/press Enter/select_option avec un timeout de 8 s.
        Après chaque action, attend wait_for_load_state("domcontentloaded", timeout=8000) en ignorant le timeout.
        Renvoie une liste de {action, ok, error?}. S'arrête à la première erreur.
        Type extract : renvoie innerText de main, article ou body, tronqué à 60000 caractères.
        """
        page = await self._get_page(task_id)
        results: List[Dict[str, Any]] = []

        for act in actions:
            act_type = (act.get("type") or "").strip().lower()
            try:
                if act_type == "click":
                    target_id = act.get("id")
                    selector = f'[data-jarvis-id="{target_id}"]'
                    await page.click(selector, timeout=8000)

                elif act_type == "type":
                    target_id = act.get("id")
                    text = act.get("text", "")
                    selector = f'[data-jarvis-id="{target_id}"]'
                    await page.fill(selector, text, timeout=8000)
                    if act.get("enter"):
                        await page.press(selector, "Enter", timeout=8000)

                elif act_type == "select":
                    target_id = act.get("id")
                    val = str(act.get("value", ""))
                    selector = f'[data-jarvis-id="{target_id}"]'
                    await page.select_option(selector, value=val, timeout=8000)

                elif act_type == "scroll":
                    direction = (act.get("direction") or "down").lower()
                    if direction == "up":
                        await page.evaluate("window.scrollBy(0, -window.innerHeight * 0.8)")
                    else:
                        await page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")

                elif act_type == "goto":
                    url = (act.get("url") or "").strip()
                    if url:
                        if not url.startswith(("http://", "https://", "about:")):
                            url = f"https://{url}"
                        await page.goto(url, wait_until="domcontentloaded", timeout=8000)

                elif act_type == "wait":
                    secs = min(max(float(act.get("seconds", 1)), 0.0), 120.0)
                    if hasattr(page, "wait_for_timeout"):
                        await page.wait_for_timeout(secs * 1000)

                elif act_type == "back":
                    await page.go_back(timeout=8000)

                elif act_type == "extract":
                    extract_js = """() => {
                        const el = document.querySelector('main') || document.querySelector('article') || document.body;
                        return el ? (el.innerText || el.textContent || '').slice(0, 60000) : '';
                    }"""
                    extracted_text = await page.evaluate(extract_js)
                    results.append({"action": act, "ok": True, "text": extracted_text})

                    # Attente optionnelle de synchronisation
                    if hasattr(page, "wait_for_load_state"):
                        try:
                            await page.wait_for_load_state("domcontentloaded", timeout=8000)
                        except Exception:
                            pass
                    continue

                else:
                    raise ValueError(f"Type d'action non supporté : '{act_type}'")

                # Après chaque action, attends wait_for_load_state("domcontentloaded", timeout=8000) en ignorant le timeout
                if hasattr(page, "wait_for_load_state"):
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=8000)
                    except Exception:
                        pass

                results.append({"action": act, "ok": True})

            except Exception as e:
                logger.warning(f"[BrowserBridge] Échec action '{act_type}': {e}")
                results.append({"action": act, "ok": False, "error": str(e)})
                break

        return results

    async def browser_screenshot(self, task_id: str) -> Dict[str, Any]:
        """Capture JPEG qualité 60, viewport seulement, renvoyée en base64."""
        page = await self._get_page(task_id)
        image_bytes = await page.screenshot(type="jpeg", quality=60, full_page=False)
        b64_str = base64.b64encode(image_bytes).decode("utf-8")
        return {
            "ok": True,
            "image": b64_str,
            "screenshot": b64_str
        }

    async def browser_focus(self, task_id: str) -> Dict[str, Any]:
        """Met l'onglet de la tâche au premier plan."""
        page = await self._get_page(task_id)
        await page.bring_to_front()
        return {"ok": True}

    async def browser_close_task(self, task_id: str) -> Dict[str, Any]:
        """Oublie la page sans fermer l'onglet."""
        self._tasks.pop(task_id, None)
        return {"ok": True}


# Instance globale pour jarvis_local_agent
browser_bridge = BrowserBridge()
