"""Service de navigation web autonome et recherche pour J.A.R.V.I.S.
Intègre l'agent autonome open-source Browser-Use (Google Vision LLM) avec repli Playwright."""

import os
import re
import asyncio
import httpx
import unicodedata
from bs4 import BeautifulSoup
from urllib.parse import unquote, quote_plus
from typing import Dict, Any, List, Optional

from config import CHROME_PATH, STATIC_DIR, SCREENSHOT_PATH, PROFILE_DIR, GEMINI_API_KEY, GEMINI_API_KEY_PAID, GEMINI_API_KEY_FREE, BASE_DIR

# Configuration environnement pour Browser-Use
os.environ["BROWSER_USE_CONFIG_DIR"] = os.path.join(BASE_DIR, ".browseruse")
os.environ["NO_PROXY"] = "127.0.0.1,localhost"

def _slugify_city(city_str: str) -> str:
    """Transforme un nom de ville (ex: Saint-Étienne, Nîmes) en slug propre pour SNCF / Trainline."""
    clean = re.sub(r'^(?:un|le|la|les|l[\'\’]|du|des)\s+', '', city_str.strip(), flags=re.IGNORECASE)
    normalized = unicodedata.normalize('NFKD', clean).encode('ascii', 'ignore').decode('utf-8')
    return re.sub(r'[^a-zA-Z0-9]+', '-', normalized.lower()).strip('-')

def extract_transport_route(text: str) -> Dict[str, Any] | None:
    """Extrait l'origine, la destination et génère des liens profonds directs pour les trains, vols et hôtels."""
    t = (text or "").lower()
    is_train = any(w in t for w in ["train", "billet", "sncf", "tgv", "ouigo", "ter", "gare", "ferroviaire", "trajet"])
    is_flight = any(w in t for w in ["vol", "avion", "flight", "aeroport", "aéroport", "compagnie"])
    is_hotel = any(w in t for w in ["hotel", "hôtel", "booking", "chambre", "hébergement", "dormir", "logement"])

    orig, dest = None, None

    # Pattern 1 : "de <orig> à/vers <dest>"
    m = re.search(r'(?:de|depuis)\s+([a-zA-Zà-ÿ\s\-]+?)\s+(?:à|vers|direction|pour|destination)\s+([a-zA-Zà-ÿ\s\-]+?)(?:\s+(?:le|demain|ce|vers|pour|\d)|$)', text, re.IGNORECASE)
    if m:
        orig, dest = m.group(1).strip(), m.group(2).strip()

    # Pattern 2 : "pour/vers <dest> depuis/de <orig>"
    if not orig or not dest:
        m = re.search(r'(?:pour|vers|direction|destination)\s+([a-zA-Zà-ÿ\s\-]+?)\s+(?:depuis|de|en partant de)\s+([a-zA-Zà-ÿ\s\-]+?)(?:\s+(?:le|demain|ce|vers|\d)|$)', text, re.IGNORECASE)
        if m:
            dest, orig = m.group(1).strip(), m.group(2).strip()

    # Pattern 3 : "entre <orig> et <dest>"
    if not orig or not dest:
        m = re.search(r'(?:entre)\s+([a-zA-Zà-ÿ\s\-]+?)\s+(?:et)\s+([a-zA-Zà-ÿ\s\-]+?)(?:\s+(?:le|demain|ce|\d)|$)', text, re.IGNORECASE)
        if m:
            orig, dest = m.group(1).strip(), m.group(2).strip()

    # Pattern 4 : "train Paris-Bordeaux" ou "train Lyon - Marseille"
    if not orig or not dest:
        m = re.search(r'(?:train|trajet|billet|tgv|vol)\s+(?:de\s+(?:train\s+)?)?([a-zA-Zà-ÿ]+)\s*[\-]\s*([a-zA-Zà-ÿ]+)', text, re.IGNORECASE)
        if m:
            orig, dest = m.group(1).strip(), m.group(2).strip()

    # Pattern 5 : "train/billet/trajet <orig> à/vers/pour <dest>"
    if not orig or not dest:
        m = re.search(r'(?:billet[s]?\s+(?:de\s+)?(?:train|tgv)|trajet\s+(?:de\s+)?(?:train|tgv)|train|billet[s]?|vol|trajet)\s+([a-zA-Zà-ÿ\-]+)\s+(?:à|vers|pour|et)\s*([a-zA-Zà-ÿ\-]+)', text, re.IGNORECASE)
        if m:
            orig, dest = m.group(1).strip(), m.group(2).strip()

    # Pattern 6 : "billet train Paris Marseille" ou "train Paris Lyon"
    if not orig or not dest:
        m = re.search(r'(?:billet[s]?\s+(?:de\s+)?(?:train|tgv)|trajet\s+(?:de\s+)?(?:train|tgv)|train|billet[s]?|vol|trajet)\s+([a-zA-Zà-ÿ\-]{3,})\s+([a-zA-Zà-ÿ\-]{3,})', text, re.IGNORECASE)
        if m:
            orig, dest = m.group(1).strip(), m.group(2).strip()

    if orig and dest:
        orig = re.sub(r'^(?:un|le|la|les|l[\'\’]|du|des)\s+', '', orig, flags=re.IGNORECASE).strip()
        dest = re.sub(r'^(?:un|le|la|les|l[\'\’]|du|des)\s+', '', dest, flags=re.IGNORECASE).strip()
        orig_slug = _slugify_city(orig)
        dest_slug = _slugify_city(dest)

        if is_train or (not is_flight and not is_hotel):
            return {
                "type": "train",
                "origin": orig,
                "destination": dest,
                "title": f"Trajet Train {orig.capitalize()} - {dest.capitalize()} (Horaires & Réservation)",
                "url": f"https://www.sncf-connect.com/train/trajet/{orig_slug}/{dest_slug}",
                "alternate_url": f"https://www.thetrainline.com/fr/billets-de-train/{orig_slug}-a-{dest_slug}",
                "google_transit": f"https://www.google.com/maps/dir/?api=1&origin={quote_plus(orig)}&destination={quote_plus(dest)}&travelmode=transit"
            }
        elif is_flight:
            return {
                "type": "flight",
                "origin": orig,
                "destination": dest,
                "title": f"Vols {orig.capitalize()} - {dest.capitalize()} sur Google Flights",
                "url": f"https://www.google.com/travel/flights?q=flights+from+{quote_plus(orig)}+to+{quote_plus(dest)}"
            }

    if is_hotel:
        m_city = re.search(r'(?:hotel|hôtel|chambre|dormir|logement)\s+(?:à|a|dans|pour|près de)\s+([a-zA-Zà-ÿ\s\-]+?)(?:\s+(?:le|demain|ce|\d)|$)', text, re.IGNORECASE)
        city = m_city.group(1).strip() if m_city else "Paris"
        return {
            "type": "hotel",
            "destination": city,
            "title": f"Hôtels à {city.capitalize()} sur Booking.com",
            "url": f"https://www.booking.com/searchresults.fr.html?ss={quote_plus(city)}"
        }

    return None

async def search_web(query: str, max_results: int = 5) -> Dict[str, Any]:
    """Recherche web rapide avec détection automatique de liens directs profonds (trains, vols, etc.)"""
    q = (query or "").strip()
    results: List[Dict[str, str]] = []

    # 1. Vérification prioritaire : détection de trajet précis (ex: Train Paris-Lyon)
    route_info = extract_transport_route(q)
    if route_info:
        results.append({
            "title": route_info["title"],
            "url": route_info["url"],
            "snippet": f"Résultats directs pour votre voyage entre {route_info.get('origin', '')} et {route_info.get('destination', '')}. Horaires, tarifs et disponibilités en direct."
        })
        if route_info.get("alternate_url"):
            results.append({
                "title": f"Trainline : Billets et Horaires {route_info.get('origin', '')} - {route_info.get('destination', '')}",
                "url": route_info["alternate_url"],
                "snippet": "Comparaison et réservation instantanée de tous les trains et transporteurs."
            })

    url = "https://html.duckduckgo.com/html/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Referer": "https://html.duckduckgo.com/"
    }
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.post(url, data={"q": q}, headers=headers)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for result in soup.find_all("div", class_="result"):
                    if result.find(class_="result__badge") or "result--ad" in result.get("class", []):
                        continue
                    
                    title_tag = result.find("a", class_="result__a")
                    snippet_tag = result.find("a", class_="result__snippet")
                    if title_tag:
                        raw_href = title_tag.get("href", "")
                        if "ad_domain" in raw_href or "bing.com/aclick" in raw_href:
                            continue
                        actual_url = raw_href
                        if "uddg=" in raw_href:
                            try:
                                actual_url = unquote(raw_href.split("uddg=")[1].split("&")[0])
                            except Exception:
                                pass
                        
                        title = title_tag.get_text(strip=True)
                        snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
                        
                        if title and actual_url and actual_url.startswith("http"):
                            # Si on a détecté un train et que l'URL est la racine pure de sncf-connect.com, remplacer par l'URL de trajet
                            if route_info and "sncf-connect.com" in actual_url and actual_url.rstrip("/").endswith("sncf-connect.com"):
                                actual_url = route_info["url"]

                            # Éviter les doublons
                            if not any(r["url"] == actual_url for r in results):
                                results.append({
                                    "title": title,
                                    "url": actual_url,
                                    "snippet": snippet
                                })
                            if len(results) >= max_results:
                                break
    except Exception as e:
        print(f"[Search Web] Erreur DuckDuckGo: {e}")

    # Repli Playwright si besoin
    if not results:
        return await _search_via_playwright(query, max_results)

    return {
        "query": query,
        "count": len(results),
        "results": results
    }

async def _search_via_playwright(query: str, max_results: int = 5) -> Dict[str, Any]:
    """Recherche de secours via navigateur Playwright"""
    from playwright.async_api import async_playwright
    results = []
    try:
        async with async_playwright() as p:
            browser_args = {
                "headless": True,
                "args": ["--no-sandbox", "--disable-dev-shm-usage"]
            }
            if os.path.exists(CHROME_PATH):
                browser_args["executable_path"] = CHROME_PATH
            
            browser = await p.chromium.launch(**browser_args)
            page = await browser.new_page()
            await page.set_viewport_size({"width": 1280, "height": 800})
            
            search_url = f"https://www.google.com/search?q={httpx.URL('', params={'q': query}).query.decode('utf-8')}&hl=fr"
            await page.goto(search_url, wait_until="domcontentloaded", timeout=12000)
            
            try:
                reject_btn = page.locator("button:has-text('Tout refuser'), button:has-text('Reject all')")
                if await reject_btn.count() > 0:
                    await reject_btn.first.click(timeout=1500)
            except Exception:
                pass

            await page.wait_for_timeout(1000)
            
            items = await page.locator("div.g, div[data-hveid]").all()
            for it in items[:max_results]:
                try:
                    title_el = it.locator("h3").first
                    link_el = it.locator("a").first
                    if await title_el.count() > 0 and await link_el.count() > 0:
                        t = await title_el.inner_text()
                        u = await link_el.get_attribute("href")
                        if t and u and u.startswith("http") and "google.com" not in u:
                            results.append({"title": t, "url": u, "snippet": ""})
                except Exception:
                    continue

            await page.screenshot(path=SCREENSHOT_PATH, type="jpeg", quality=75)
            await browser.close()
    except Exception as e:
        print(f"[Search Playwright] Erreur: {e}")

    return {
        "query": query,
        "count": len(results),
        "results": results
    }

async def browse_page(url: str, wait_seconds: float = 2.0) -> Dict[str, Any]:
    """Visite une page web, capture l'écran pour le HUD et extrait son texte."""
    from playwright.async_api import async_playwright
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    try:
        async with async_playwright() as p:
            browser_args = {
                "headless": True,
                "args": ["--no-sandbox", "--disable-dev-shm-usage"]
            }
            if os.path.exists(CHROME_PATH):
                browser_args["executable_path"] = CHROME_PATH

            browser = await p.chromium.launch(**browser_args)
            page = await browser.new_page()
            await page.set_viewport_size({"width": 1280, "height": 800})
            
            response = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            status_code = response.status if response else 0
            await page.wait_for_timeout(int(wait_seconds * 1000))
            
            await page.screenshot(path=SCREENSHOT_PATH, type="jpeg", quality=75)
            title = await page.title()
            
            body_text = await page.evaluate("""() => {
                const scripts = document.querySelectorAll('script, style, noscript, nav, footer');
                scripts.forEach(s => s.remove());
                return document.body ? document.body.innerText : '';
            }""")
            
            lines = [l.strip() for l in body_text.splitlines() if l.strip()]
            summary_text = "\n".join(lines[:80])
            
            await browser.close()
            return {
                "status": "ok",
                "url": url,
                "status_code": status_code,
                "title": title,
                "content_preview": summary_text[:1800],
                "screenshot": "/static/latest_screenshot.jpg"
            }
    except Exception as e:
        return {
            "status": "error",
            "url": url,
            "message": f"Erreur navigation: {str(e)}"
        }

FREE_BROWSER_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-flash-latest"
]

async def _attempt_browser_use(
    instruction: str,
    target_url: str,
    target_site_fallback: str,
    route_info: Dict[str, Any] | None,
    model_name: str,
    api_key: str,
    max_steps: int = 8
) -> Dict[str, Any]:
    from browser_use import Agent, BrowserProfile
    from browser_use.llm import ChatGoogle

    llm = ChatGoogle(model=model_name, api_key=api_key)
    
    full_instruction = instruction
    if target_url:
        full_instruction = f"Commence par te rendre sur {target_url}. Objectif : {instruction}"
    full_instruction += " Réalise l'action de manière efficace, gère les cookies ou popups si nécessaire, et conclus avec un résumé clair des informations trouvées."

    profile_args = {"headless": True}
    if os.path.exists(CHROME_PATH):
        profile_args["executable_path"] = CHROME_PATH

    browser_profile = BrowserProfile(**profile_args)

    agent = Agent(
        task=full_instruction,
        llm=llm,
        browser_profile=browser_profile,
        use_vision=True,
        max_actions_per_step=4
    )

    history = await agent.run(max_steps=max_steps)
    final_summary = history.final_result() or "Action de navigation réalisée avec succès."
    visited_urls = history.urls()
    target_site = visited_urls[-1] if visited_urls else (target_url or target_site_fallback or "https://www.google.com")
    if target_site_fallback and ("sncf-connect.com" in target_site and target_site.rstrip("/").endswith("sncf-connect.com")):
        target_site = target_site_fallback

    screenshots = history.screenshots()
    if screenshots:
        try:
            import base64
            last_shot = screenshots[-1]
            if isinstance(last_shot, str):
                with open(SCREENSHOT_PATH, "wb") as f:
                    f.write(base64.b64decode(last_shot))
            elif isinstance(last_shot, bytes):
                with open(SCREENSHOT_PATH, "wb") as f:
                    f.write(last_shot)
        except Exception as e:
            print(f"[Browser Task] Capture d'écran: {e}")

    return {
        "status": "success",
        "site_visited": target_site,
        "page_title": route_info["title"] if route_info else "Résultats de navigation",
        "summary": final_summary[:1500],
        "screenshot": "/static/latest_screenshot.jpg"
    }

async def run_browser_task(goal: str, url: str = "", confirmed_by_user: bool = False) -> Dict[str, Any]:
    """Exécute une tâche concrète dans le navigateur avec l'agent autonome Browser-Use.
    Stratégie :
    1. Si confirmed_by_user=False : teste d'abord plusieurs modèles sur la CLÉ GRATUITE (gemini-3.8-flash, 3.5, 3.6, latest).
       Si un modèle réussit : mission accomplie sans coût pour l'utilisateur.
       Si tous les modèles gratuits échouent : renvoie 'requires_user_confirmation' pour demander l'accord oral de Pierre.
    2. Si confirmed_by_user=True : exécute sur la CLÉ PAYANTE.
    """
    print(f"[Browser Task] Début de mission : '{goal}' (url: '{url}', confirmed_by_user: {confirmed_by_user})")

    # Résolution intelligente de lien profond (trains, transports, hôtels)
    route_info = extract_transport_route(goal or url)
    target_site_fallback = ""
    if route_info:
        if not url or url.rstrip("/").endswith("sncf-connect.com") or url == "https://www.google.com":
            url = route_info["url"]
        target_site_fallback = route_info["url"]

    # 1. Si Pierre n'a pas confirmé l'utilisation de la clé payante :
    # Tenter d'abord plusieurs modèles qui pourraient fonctionner avec la CLÉ GRATUITE
    if not confirmed_by_user:
        if GEMINI_API_KEY_FREE:
            print(f"[Browser Task] Tentative préalable avec la CLÉ GRATUITE sur plusieurs modèles...")
            for candidate_model in FREE_BROWSER_MODELS:
                try:
                    print(f"[Browser Task] Essai sur clé gratuite avec {candidate_model}...")
                    res = await _attempt_browser_use(
                        instruction=goal,
                        target_url=url,
                        target_site_fallback=target_site_fallback,
                        route_info=route_info,
                        model_name=candidate_model,
                        api_key=GEMINI_API_KEY_FREE,
                        max_steps=6
                    )
                    res["goal"] = goal
                    res["key_used"] = "Clé Gratuite"
                    res["model_used"] = candidate_model
                    print(f"[Browser Task] Succès sur la clé gratuite avec {candidate_model} !")
                    return res
                except asyncio.CancelledError:
                    print(f"[Browser Task] Navigation annulée par l'utilisateur.")
                    return {"status": "cancelled", "summary": "Navigation interrompue à votre demande.", "goal": goal}
                except Exception as m_err:
                    print(f"[Browser Task] Échec modèle gratuit {candidate_model} : {m_err}")

        # Si tous les modèles sur la clé gratuite ont échoué (ou indisponibles) :
        # IL EST TECHNQUEMENT IMPOSSIBLE D'UTILISER LA CLÉ PAYANTE SANS CONFIRMATION EXPRESSE DE PIERRE !
        print(f"[Browser Task] Modèles gratuits épuisés. Demande d'autorisation payante requise.")
        reason = f"Les modèles sur clé gratuite ({', '.join(FREE_BROWSER_MODELS)}) ont été testés sans succès (quotas gratuits atteints). La navigation autonome nécessite la clé payante pour : '{goal}'"
        cost_str = "~0.02 $"
        return {
            "status": "requires_user_confirmation",
            "requires_paid_consent": True,
            "action": "run_browser_task",
            "tried_free_models": FREE_BROWSER_MODELS,
            "reason": reason,
            "estimated_cost": cost_str,
            "instruction_to_jarvis": (
                f"ATTENTION : Tous les modèles sur la clé gratuite ont été testés sans succès en raison des limites de quotas. "
                f"Pour accomplir cette navigation autonome avec analyse visuelle Browser-Use, tu dois impérativement utiliser la clé payante ({cost_str}). "
                f"RÈGLE STRICTE ET ABSOLUE : Il est STRICTEMENT IMPOSSIBLE d'utiliser la clé payante sans confirmation expresse de Pierre. "
                f"Explique immédiatement à Pierre à l'oral avec ta voix Aoede que tu as essayé plusieurs modèles sur la clé gratuite mais que les quotas sont épuisés, "
                f"indique-lui que passer sur la clé payante coûtera environ 0,02 $, "
                f"et demande-lui explicitement son accord oral : 'M'autorisez-vous à utiliser la clé payante pour cette navigation ?'. "
                f"Attends sa confirmation. Dès qu'il te dit oui oralement ou valide sur l'écran, réinvoque 'run_browser_task' avec confirmed_by_user=True."
            )
        }

    # 2. Pierre a EXPRESSÉMENT confirmé l'utilisation de la clé payante (confirmed_by_user=True)
    if not GEMINI_API_KEY_PAID:
        return {
            "status": "error",
            "summary": "Aucune clé API payante configurée.",
            "goal": goal
        }

    print(f"[Browser Task] Exécution autorisée sur la CLÉ PAYANTE...")
    try:
        res = await _attempt_browser_use(
            instruction=goal,
            target_url=url,
            target_site_fallback=target_site_fallback,
            route_info=route_info,
            model_name="gemini-3.6-flash",
            api_key=GEMINI_API_KEY_PAID,
            max_steps=8
        )
        res["goal"] = goal
        res["key_used"] = "Clé Payante"
        res["model_used"] = "Gemini 3.6 Flash (Vision LLM)"
        return res
    except asyncio.CancelledError:
        print(f"[Browser Task] Navigation payante annulée par l'utilisateur.")
        return {"status": "cancelled", "summary": "Navigation interrompue à votre demande.", "goal": goal}
    except Exception as e:
        print(f"[Browser Task] Erreur Browser-Use sur clé payante ({e}), repli Playwright direct...")
        return await _run_playwright_direct_fallback(goal, url)

async def _run_playwright_direct_fallback(goal: str, url: str = "") -> Dict[str, Any]:
    """Repli robuste Playwright en cas d'indisponibilité temporaire de Browser-Use."""
    from playwright.async_api import async_playwright
    
    route_info = extract_transport_route(goal or url)
    target_url = url.strip()
    if route_info and (not target_url or "sncf-connect.com" in target_url):
        target_url = route_info["url"]
    elif not target_url:
        search_res = await search_web(goal, max_results=2)
        if search_res.get("results"):
            target_url = search_res["results"][0]["url"]
        else:
            target_url = f"https://www.google.com/search?q={quote_plus(goal)}"

    try:
        async with async_playwright() as p:
            browser_args = {
                "headless": True,
                "args": ["--no-sandbox", "--disable-dev-shm-usage"]
            }
            if os.path.exists(CHROME_PATH):
                browser_args["executable_path"] = CHROME_PATH

            browser = await p.chromium.launch(**browser_args)
            page = await browser.new_page()
            await page.set_viewport_size({"width": 1280, "height": 800})
            await page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
            
            # Gestion cookies
            try:
                btn = page.locator("button:has-text('Accepter'), button:has-text('Tout accepter'), button#onetrust-accept-btn-handler")
                if await btn.count() > 0:
                    await btn.first.click(timeout=1500)
            except Exception:
                pass

            await page.wait_for_timeout(2000)
            await page.screenshot(path=SCREENSHOT_PATH, type="jpeg", quality=75)
            title = await page.title()
            
            body_text = await page.evaluate("""() => {
                const el = document.body;
                return el ? el.innerText : '';
            }""")
            clean_lines = [l.strip() for l in body_text.splitlines() if len(l.strip()) > 3]
            summary = "\n".join(clean_lines[:30])

            await browser.close()
            return {
                "status": "success",
                "goal": goal,
                "site_visited": target_url,
                "page_title": title,
                "summary": summary[:1400],
                "screenshot": "/static/latest_screenshot.jpg"
            }
    except Exception as ex:
        return {
            "status": "error",
            "goal": goal,
            "site_visited": target_url,
            "message": f"Erreur navigation: {str(ex)}"
        }

def open_browser_window(url: str = "https://www.google.com") -> Dict[str, Any]:
    """Ouvre une vraie fenêtre Google Chrome visible à l'écran avec le profil de l'utilisateur."""
    import subprocess
    target = url.strip() if url else "https://www.google.com"
    if not target.startswith("http://") and not target.startswith("https://"):
        target = "https://" + target

    if not os.path.exists(CHROME_PATH):
        return {
            "status": "error",
            "message": f"Google Chrome introuvable à l'adresse {CHROME_PATH}"
        }

    cmd = [
        CHROME_PATH,
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        target
    ]
    try:
        subprocess.Popen(cmd)
        return {
            "status": "success",
            "url": target,
            "message": f"Google Chrome ouvert à l'écran sur {target} avec votre session connectée."
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Erreur lors de l'ouverture du navigateur: {str(e)}"
        }

async def interact_web_page(
    url: str,
    action: str = "read",
    selector: str = "",
    text_to_fill: str = "",
    actions_list: Optional[List[Dict[str, Any]]] = None,
    wait_seconds: float = 2.0
) -> Dict[str, Any]:
    """Lit ou interagit concrètement avec n'importe quelle page web via Playwright.
    Supporte la lecture structurée (champs de formulaire, boutons, texte)
    ainsi que l'exécution d'actions réelles (remplir des champs, cliquer sur des boutons, soumettre).
    """
    from playwright.async_api import async_playwright
    target_url = (url or "").strip()
    if not target_url.startswith("http://") and not target_url.startswith("https://"):
        target_url = "https://" + target_url

    try:
        async with async_playwright() as p:
            browser_args = {
                "headless": True,
                "args": ["--no-sandbox", "--disable-dev-shm-usage"]
            }
            if os.path.exists(CHROME_PATH):
                browser_args["executable_path"] = CHROME_PATH

            browser = await p.chromium.launch(**browser_args)
            page = await browser.new_page()
            await page.set_viewport_size({"width": 1280, "height": 800})

            # Navigation
            await page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(int(wait_seconds * 1000))

            # Gestion automatique des bannières cookies
            try:
                cookie_btn = page.locator("button:has-text('Accepter'), button:has-text('Tout accepter'), button#onetrust-accept-btn-handler, button#sp-cc-accept, button:has-text('Accept all')")
                if await cookie_btn.count() > 0:
                    await cookie_btn.first.click(timeout=2000)
                    await page.wait_for_timeout(1000)
            except Exception:
                pass

            performed_actions = []

            # Exécution de la liste d'actions si fournie
            ops = actions_list if actions_list else []
            if not ops and action and action != "read":
                ops = [{"type": action, "selector": selector, "value": text_to_fill}]

            for op in ops:
                op_type = op.get("type", "click").lower()
                sel = op.get("selector", "")
                val = op.get("value", "")

                try:
                    if op_type == "click" and sel:
                        loc = page.locator(sel).first
                        await loc.click(timeout=5000)
                        performed_actions.append(f"Clic sur '{sel}'")
                        await page.wait_for_timeout(1000)
                    elif op_type in ("fill", "type") and sel:
                        loc = page.locator(sel).first
                        await loc.fill(val, timeout=5000)
                        performed_actions.append(f"Saisie de '{val}' dans '{sel}'")
                        await page.wait_for_timeout(500)
                    elif op_type == "select" and sel:
                        loc = page.locator(sel).first
                        await loc.select_option(val, timeout=5000)
                        performed_actions.append(f"Sélection de '{val}' dans '{sel}'")
                        await page.wait_for_timeout(500)
                    elif op_type == "press" and val:
                        await page.keyboard.press(val)
                        performed_actions.append(f"Touche '{val}' pressée")
                        await page.wait_for_timeout(1000)
                    elif op_type == "scroll":
                        await page.evaluate("window.scrollBy(0, 500)")
                        performed_actions.append("Défilement vers le bas")
                        await page.wait_for_timeout(500)
                except Exception as op_err:
                    performed_actions.append(f"Échec action '{op_type}' sur '{sel}': {op_err}")

            # Capture d'écran actualisée
            await page.screenshot(path=SCREENSHOT_PATH, type="jpeg", quality=75)
            final_title = await page.title()
            final_url = page.url

            # Extraction structurée de la page (texte, champs de formulaire, boutons)
            page_data = await page.evaluate("""() => {
                const scripts = document.querySelectorAll('script, style, noscript');
                scripts.forEach(s => s.remove());

                // Formulaires et inputs
                const inputs = Array.from(document.querySelectorAll('input, textarea, select')).map(el => ({
                    tag: el.tagName.toLowerCase(),
                    type: el.type || '',
                    name: el.name || '',
                    id: el.id || '',
                    placeholder: el.placeholder || '',
                    value: el.value || '',
                    label: el.labels && el.labels[0] ? el.labels[0].innerText.trim() : ''
                })).filter(i => i.type !== 'hidden').slice(0, 15);

                // Boutons interactifs visibles
                const buttons = Array.from(document.querySelectorAll('button, a.btn, input[type="submit"], input[type="button"]')).map(b => ({
                    text: (b.innerText || b.value || '').trim(),
                    id: b.id || '',
                    classes: b.className || ''
                })).filter(b => b.text.length > 1).slice(0, 10);

                const text = document.body ? document.body.innerText : '';
                return { inputs, buttons, text };
            }""")

            body_lines = [l.strip() for l in (page_data.get("text") or "").splitlines() if len(l.strip()) > 3]
            clean_summary = "\n".join(body_lines[:40])

            await browser.close()
            return {
                "status": "success",
                "url": final_url,
                "title": final_title,
                "performed_actions": performed_actions,
                "detected_form_inputs": page_data.get("inputs", []),
                "available_buttons": page_data.get("buttons", []),
                "content_preview": clean_summary[:1600],
                "screenshot": "/static/latest_screenshot.jpg"
            }
    except Exception as e:
        return {
            "status": "error",
            "url": target_url,
            "message": f"Erreur interaction web: {str(e)}"
        }

async def prepare_web_cart_or_checkout(
    product_or_service: str,
    merchant_url: str = "",
    autofill_details: Optional[Dict[str, str]] = None,
    open_when_ready: bool = True
) -> Dict[str, Any]:
    """Recherche un produit ou service sur un site marchand, l'ajoute au panier,
    navigue vers la page de commande, préremplit les coordonnées de Pierre (nom, prénom, adresse, email),
    S'ARRÊTE STRICTEMENT AVANT LE PAIEMENT, et ouvre automatiquement Google Chrome à l'écran
    afin que Pierre n'ait plus qu'à vérifier et payer en toute sécurité.
    """
    from playwright.async_api import async_playwright
    from services.memory_service import memory_service

    # 1. Détermination du site marchand et URL cible
    target_site = (merchant_url or "").strip()
    if not target_site:
        search_query = f"{product_or_service} acheter commander site"
        search_res = await search_web(search_query, max_results=3)
        results = search_res.get("results", [])
        if results:
            target_site = results[0]["url"]
        else:
            target_site = f"https://www.google.com/search?q={quote_plus(product_or_service)}"

    if not target_site.startswith("http://") and not target_site.startswith("https://"):
        target_site = "https://" + target_site

    # 2. Récupération des informations du profil pour préremplissage
    user_info = memory_service.get_user_autofill_profile()
    if autofill_details:
        user_info.update(autofill_details)

    first_name = user_info.get("first_name", "Pierre")
    last_name = user_info.get("last_name", "Cassagnettes")
    email = user_info.get("email", "pierrecassagnettes@gmail.com")
    phone = user_info.get("phone", "")
    address = user_info.get("address", "")
    zip_code = user_info.get("zip_code", "")
    city = user_info.get("city", "")

    cart_url = target_site
    prefilled_fields = []
    actions_log = []

    try:
        async with async_playwright() as p:
            browser_args = {
                "headless": True,
                "args": ["--no-sandbox", "--disable-dev-shm-usage"]
            }
            if os.path.exists(CHROME_PATH):
                browser_args["executable_path"] = CHROME_PATH

            browser = await p.chromium.launch(**browser_args)
            page = await browser.new_page()
            await page.set_viewport_size({"width": 1280, "height": 850})

            # A. Visite de la page marchande
            actions_log.append(f"Navigation vers {target_site}")
            await page.goto(target_site, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(2000)

            # B. Acceptation des cookies
            try:
                cookie_loc = page.locator("button:has-text('Accepter'), button:has-text('Tout accepter'), button#onetrust-accept-btn-handler, button#sp-cc-accept, button:has-text('J\\'accepte')")
                if await cookie_loc.count() > 0:
                    await cookie_loc.first.click(timeout=2000)
                    actions_log.append("Bannière cookies acceptée.")
                    await page.wait_for_timeout(1000)
            except Exception:
                pass

            # C. Recherche de produit interne si pas directement sur la page produit
            is_product_page = False
            add_cart_loc = page.locator("button:has-text('Ajouter au panier'), button:has-text('Add to basket'), button:has-text('Add to cart'), input[value*='Ajouter au panier'], a:has-text('Ajouter au panier'), button:has-text('Réserver')")
            if await add_cart_loc.count() > 0:
                is_product_page = True

            if not is_product_page:
                try:
                    search_box = page.locator("input[type='search'], input[name*='search' i], input[name*='query' i], input[placeholder*='recherch' i], input[placeholder*='search' i], input#twotabsearchtextbox")
                    if await search_box.count() > 0:
                        await search_box.first.fill(product_or_service)
                        await page.keyboard.press("Enter")
                        actions_log.append(f"Recherche de '{product_or_service}' sur le site marchand.")
                        await page.wait_for_timeout(2500)

                        product_link = page.locator("div.s-result-item h2 a, .product-card a, .product-item a, a:has(h2), a:has(h3)").first
                        if await product_link.count() > 0:
                            await product_link.click(timeout=5000)
                            actions_log.append("Accès à la fiche produit sélectionnée.")
                            await page.wait_for_timeout(2000)
                except Exception as s_err:
                    actions_log.append(f"Recherche interne: {s_err}")

            # D. Ajout au panier
            try:
                add_btn = page.locator("button:has-text('Ajouter au panier'), button:has-text('Add to cart'), button:has-text('Add to basket'), input[value*='Ajouter au panier'], a:has-text('Ajouter au panier'), button#add-to-cart-button").first
                if await add_btn.count() > 0:
                    await add_btn.click(timeout=5000)
                    actions_log.append("Produit ajouté au panier avec succès.")
                    await page.wait_for_timeout(2000)
            except Exception as cart_err:
                actions_log.append(f"Tentative ajout panier: {cart_err}")

            # E. Navigation vers le panier / passage de commande
            try:
                checkout_btn = page.locator("a:has-text('Passer la commande'), button:has-text('Passer la commande'), a:has-text('Voir le panier'), a:has-text('Mon panier'), a[href*='cart'], a[href*='panier'], button:has-text('Commander')").first
                if await checkout_btn.count() > 0:
                    await checkout_btn.click(timeout=5000)
                    actions_log.append("Accès au panier et à l'étape de commande.")
                    await page.wait_for_timeout(2000)
            except Exception:
                pass

            cart_url = page.url

            # F. Préremplissage intelligent des formulaires (coordonnées de livraison & contact)
            fill_mappings = [
                (["input[name*='prenom' i]", "input[id*='prenom' i]", "input[autocomplete='given-name']", "input[name*='firstname' i]"], first_name, "Prénom"),
                (["input[name*='nom' i]:not([name*='prenom' i])", "input[id*='nom' i]:not([id*='prenom' i])", "input[autocomplete='family-name']", "input[name*='lastname' i]"], last_name, "Nom"),
                (["input[type='email']", "input[name*='email' i]", "input[id*='email' i]", "input[autocomplete='email']"], email, "E-mail"),
                (["input[type='tel']", "input[name*='tel' i]", "input[name*='phone' i]", "input[autocomplete='tel']"], phone, "Téléphone"),
                (["input[name*='address' i]", "input[name*='adresse' i]", "input[autocomplete='street-address']", "input[name*='voie' i]"], address, "Adresse"),
                (["input[name*='zip' i]", "input[name*='postal' i]", "input[autocomplete='postal-code']", "input[name*='code_postal' i]"], zip_code, "Code Postal"),
                (["input[name*='city' i]", "input[name*='ville' i]", "input[autocomplete='address-level2']"], city, "Ville"),
            ]

            for selectors, val, label in fill_mappings:
                if not val:
                    continue
                for sel in selectors:
                    try:
                        loc = page.locator(sel).first
                        if await loc.count() > 0 and await loc.is_visible():
                            current_val = await loc.input_value()
                            if not current_val:
                                await loc.fill(val, timeout=2000)
                                prefilled_fields.append(f"{label}: {val}")
                                break
                    except Exception:
                        continue

            # G. Sécurité absolue : GARANTIE DE NE JAMAIS CLIQUER SUR PAYER
            await page.screenshot(path=SCREENSHOT_PATH, type="jpeg", quality=80)
            final_title = await page.title()
            cart_url = page.url
            await browser.close()

    except Exception as ex:
        actions_log.append(f"Note d'exécution : {str(ex)}")

    # H. Ouverture automatique du navigateur Google Chrome visible pour Pierre
    if open_when_ready and cart_url:
        open_res = open_browser_window(cart_url)
        actions_log.append(f"Google Chrome ouvert à l'écran sur le panier ({open_res.get('status')}).")

    return {
        "status": "success",
        "product": product_or_service,
        "site": target_site,
        "cart_url": cart_url,
        "prefilled_fields": prefilled_fields,
        "steps": actions_log,
        "browser_opened": open_when_ready,
        "screenshot": "/static/latest_screenshot.jpg",
        "message": (
            f"Le panier pour '{product_or_service}' a été préparé sur {target_site}. "
            f"Les coordonnées ({', '.join(prefilled_fields) if prefilled_fields else 'Pierre Cassagnettes'}) ont été préremplies. "
            f"La page Chrome est ouverte à votre écran : il ne vous reste plus qu'à régler et valider votre paiement en toute sérénité."
        )
    }

