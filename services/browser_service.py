"""Service de navigation web autonome et recherche pour J.A.R.V.I.S.
Intègre l'agent autonome open-source Browser-Use (Google Vision LLM) avec repli Playwright."""

import os
import re
import asyncio
import httpx
import unicodedata
from bs4 import BeautifulSoup
from urllib.parse import unquote, quote_plus
from typing import Dict, Any, List

from config import CHROME_PATH, STATIC_DIR, SCREENSHOT_PATH, PROFILE_DIR, GEMINI_API_KEY, GEMINI_API_KEY_PAID, BASE_DIR

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

async def run_browser_task(goal: str, url: str = "") -> Dict[str, Any]:
    """Exécute une tâche concrète dans le navigateur avec l'agent autonome Browser-Use."""
    print(f"[Browser Task] Début de mission autonome : '{goal}' (url de départ: '{url}')")

    # Résolution intelligente de lien profond (trains, transports, hôtels)
    route_info = extract_transport_route(goal or url)
    target_site_fallback = ""
    if route_info:
        if not url or url.rstrip("/").endswith("sncf-connect.com") or url == "https://www.google.com":
            url = route_info["url"]
        target_site_fallback = route_info["url"]
    
    # 1. Tentative avec l'Agent Autonome Browser-Use
    try:
        from browser_use import Agent, BrowserProfile
        from browser_use.llm import ChatGoogle

        llm = ChatGoogle(model="gemini-3.6-flash", api_key=GEMINI_API_KEY_PAID or GEMINI_API_KEY)
        
        # Contexte enrichi pour l'agent autonome
        full_instruction = goal
        if url:
            full_instruction = f"Commence par te rendre sur {url}. Objectif : {goal}"
        
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

        # Exécution de l'agent (maximum 8 étapes pour rester rapide et réactif à l'oral)
        history = await agent.run(max_steps=8)
        
        final_summary = history.final_result() or "Action de navigation réalisée avec succès."
        visited_urls = history.urls()
        
        target_site = visited_urls[-1] if visited_urls else (url or target_site_fallback or "https://www.google.com")
        # Si le site visité final est une page d'accueil vide alors qu'un lien profond direct existe, privilégier le lien profond
        if target_site_fallback and ("sncf-connect.com" in target_site and target_site.rstrip("/").endswith("sncf-connect.com")):
            target_site = target_site_fallback

        # Sauvegarde de la dernière capture pour le HUD
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
            "goal": goal,
            "site_visited": target_site,
            "page_title": route_info["title"] if route_info else "Résultats de navigation",
            "summary": final_summary[:1500],
            "screenshot": "/static/latest_screenshot.jpg"
        }

    except Exception as e:
        print(f"[Browser Task] Repli sur agent Playwright direct suite à: {e}")

    # 2. Repli fluide sur Playwright direct
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
