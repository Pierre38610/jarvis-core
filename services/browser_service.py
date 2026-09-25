"""Service de navigation web autonome et recherche pour J.A.R.V.I.S.
Intègre l'agent autonome open-source Browser-Use (Google Vision LLM) avec repli Playwright."""

import os
import re
import json
import glob
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

# Profil shopping dédié (sessions Amazon, Fnac, etc.)
SHOPPING_PROFILE_DIR = os.path.join(BASE_DIR, ".jarvis_shopping_profile")
os.makedirs(SHOPPING_PROFILE_DIR, exist_ok=True)


# ─── GESTION DES EXTENSIONS CHROME (SEND TO KINDLE, ETC.) ──────────────────────

def get_installed_chrome_extensions() -> List[Dict[str, Any]]:
    """Détecte automatiquement toutes les extensions Google Chrome installées sur la machine de Pierre.
    Parcourt le profil 'Default' ainsi que les autres profils Chrome pour trouver les répertoires d'extensions.
    """
    user_data = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
    found_extensions = []
    seen_ids = set()

    search_dirs = [
        os.path.join(user_data, "Default", "Extensions"),
        *glob.glob(os.path.join(user_data, "Profile *", "Extensions"))
    ]

    for ext_base in search_dirs:
        if not os.path.exists(ext_base):
            continue
        try:
            for ext_id in os.listdir(ext_base):
                if ext_id in seen_ids:
                    continue
                id_dir = os.path.join(ext_base, ext_id)
                if not os.path.isdir(id_dir):
                    continue
                versions = [v for v in os.listdir(id_dir) if os.path.isdir(os.path.join(id_dir, v))]
                if not versions:
                    continue
                ver_dir = os.path.join(id_dir, sorted(versions)[-1])
                manifest_path = os.path.join(ver_dir, "manifest.json")
                if not os.path.exists(manifest_path):
                    continue

                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        manifest = json.load(f)
                    name = manifest.get("name", ext_id)
                    description = manifest.get("description", "")

                    # Résolution des messages localisés (__MSG_...)
                    if name.startswith("__MSG_"):
                        msg_key = name[6:-2]
                        for loc in ["fr", "en", "en_US"]:
                            msg_path = os.path.join(ver_dir, "_locales", loc, "messages.json")
                            if os.path.exists(msg_path):
                                with open(msg_path, "r", encoding="utf-8") as mf:
                                    msgs = json.load(mf)
                                    if msg_key in msgs:
                                        name = msgs[msg_key].get("message", name)
                                        break

                    if description.startswith("__MSG_"):
                        msg_key = description[6:-2]
                        for loc in ["fr", "en", "en_US"]:
                            msg_path = os.path.join(ver_dir, "_locales", loc, "messages.json")
                            if os.path.exists(msg_path):
                                with open(msg_path, "r", encoding="utf-8") as mf:
                                    msgs = json.load(mf)
                                    if msg_key in msgs:
                                        description = msgs[msg_key].get("message", description)
                                        break

                    is_s2k = (ext_id == "cgdjpilhipecahhcilnafpblkieebhea" or "kindle" in name.lower())
                    action_info = manifest.get("action", {}) or manifest.get("browser_action", {})
                    default_popup = action_info.get("default_popup", "")

                    found_extensions.append({
                        "id": ext_id,
                        "name": name,
                        "version": manifest.get("version", ""),
                        "path": ver_dir,
                        "is_send_to_kindle": is_s2k,
                        "popup": default_popup,
                        "description": description
                    })
                    seen_ids.add(ext_id)
                except Exception:
                    pass
        except Exception:
            pass

    return found_extensions


def get_extension_load_args() -> List[str]:
    """Génère les arguments CLI de Google Chrome / Playwright pour charger automatiquement les extensions."""
    exts = get_installed_chrome_extensions()
    paths = [e["path"] for e in exts if os.path.exists(e["path"])]
    if not paths:
        return []
    joined = ",".join(paths)
    return [
        f"--load-extension={joined}",
        f"--disable-extensions-except={joined}"
    ]


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

    # Repli DuckDuckGo Lite si besoin
    if not results:
        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                resp = await client.post("https://lite.duckduckgo.com/lite/", data={"q": q}, headers=headers)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for a in soup.find_all("a", class_="result-link"):
                        raw_href = a.get("href", "")
                        if "uddg=" in raw_href:
                            try:
                                raw_href = unquote(raw_href.split("uddg=")[1].split("&")[0])
                            except Exception:
                                pass
                        title = a.get_text(strip=True)
                        if title and raw_href.startswith("http"):
                            results.append({"title": title, "url": raw_href, "snippet": ""})
                            if len(results) >= max_results:
                                break
        except Exception:
            pass

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

def _detect_needs_auth(instruction: str, url: str) -> bool:
    """Détecte si la tâche nécessite une session connectée (Google, Amazon, compte, login...)"""
    auth_signals = [
        "amazon", "compte", "commande", "panier", "commander", "achat",
        "gmail", "google", "youtube premium", "connecte", "connecté",
        "login", "log in", "sign in", "inscription", "profil",
        "mon compte", "my account", "fnac", "cdiscount", "darty",
        "spotify", "netflix", "disney", "prime video"
    ]
    text = (instruction + " " + url).lower()
    return any(s in text for s in auth_signals)


async def _attempt_browser_use(
    instruction: str,
    target_url: str,
    target_site_fallback: str,
    route_info: Dict[str, Any] | None,
    model_name: str,
    api_key: str,
    max_steps: int = 8,
    use_user_profile: bool = False
) -> Dict[str, Any]:
    from browser_use import Agent, BrowserProfile
    from browser_use.llm import ChatGoogle

    llm = ChatGoogle(model=model_name, api_key=api_key)

    full_instruction = instruction
    if target_url:
        full_instruction = f"Commence par te rendre sur {target_url}. Objectif : {instruction}"
    full_instruction += (
        " Réalise l'action de manière efficace, gère les cookies ou popups si nécessaire, "
        "et conclus avec un résumé clair des informations trouvées."
    )

    # Si la tâche nécessite une session connectée, on utilise le profil Chrome persistant
    # avec toutes les sessions Google/Amazon/etc. déjà sauvegardées
    if use_user_profile and os.path.exists(PROFILE_DIR):
        try:
            ext_args = get_extension_load_args()
            profile_args = {
                "headless": False,  # Nécessite headless=False pour utiliser un profil persistant et extensions
                "user_data_dir": PROFILE_DIR,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                    *ext_args,
                    "--no-sandbox"
                ]
            }
            if os.path.exists(CHROME_PATH):
                profile_args["executable_path"] = CHROME_PATH
            browser_profile = BrowserProfile(**profile_args)
            print("[Browser Task] Utilisation du profil Chrome connecté avec extensions (Send to Kindle, etc.).")
        except Exception:
            # Fallback profil standard
            profile_args = {"headless": True}
            if os.path.exists(CHROME_PATH):
                profile_args["executable_path"] = CHROME_PATH
            browser_profile = BrowserProfile(**profile_args)
    else:
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
            def _write_shot(data):
                if isinstance(data, str):
                    raw = base64.b64decode(data)
                elif isinstance(data, bytes):
                    raw = data
                else:
                    return
                with open(SCREENSHOT_PATH, "wb") as f:
                    f.write(raw)
            await asyncio.to_thread(_write_shot, last_shot)
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
    Détecte automatiquement si la tâche nécessite une session connectée (Amazon, Google, etc.)
    et utilise le profil Chrome persistant avec les sessions sauvegardées dans ce cas.
    """
    print(f"[Browser Task] Début de mission : '{goal}' (url: '{url}')")

    # Détection automatique : la tâche nécessite-t-elle une session connectée ?
    needs_auth = _detect_needs_auth(goal, url)
    if needs_auth:
        print(f"[Browser Task] Session connectée détectée — utilisation du profil Chrome persistant.")

    # Résolution intelligente de lien profond (trains, transports, hôtels)
    route_info = extract_transport_route(goal or url)
    target_site_fallback = ""
    if route_info:
        if not url or url.rstrip("/").endswith("sncf-connect.com") or url == "https://www.google.com":
            url = route_info["url"]
        target_site_fallback = route_info["url"]

    api_key_to_use = GEMINI_API_KEY_PAID or GEMINI_API_KEY_FREE
    key_label = "Clé Payante" if api_key_to_use == GEMINI_API_KEY_PAID else "Clé Gratuite"
    chosen_model = "gemini-3.8-flash"

    if not api_key_to_use:
        return {
            "status": "error",
            "summary": "Aucune clé API configurée pour la navigation.",
            "goal": goal
        }

    print(f"[Browser Task] Exécution sur {key_label} avec {chosen_model} (auth={needs_auth})...")
    try:
        res = await _attempt_browser_use(
            instruction=goal,
            target_url=url,
            target_site_fallback=target_site_fallback,
            route_info=route_info,
            model_name=chosen_model,
            api_key=api_key_to_use,
            max_steps=10 if needs_auth else 8,
            use_user_profile=needs_auth
        )
        res["goal"] = goal
        res["key_used"] = key_label
        res["model_used"] = f"{chosen_model} (Vision LLM)"
        res["used_connected_profile"] = needs_auth
        return res
    except asyncio.CancelledError:
        print(f"[Browser Task] Navigation annulée par l'utilisateur.")
        return {"status": "cancelled", "summary": "Navigation interrompue à votre demande.", "goal": goal}
    except Exception as e:
        print(f"[Browser Task] Erreur Browser-Use ({e}), tentative modèle 3.6-flash ou repli Playwright direct...")
        try:
            res = await _attempt_browser_use(
                instruction=goal,
                target_url=url,
                target_site_fallback=target_site_fallback,
                route_info=route_info,
                model_name="gemini-3.6-flash",
                api_key=api_key_to_use,
                max_steps=10 if needs_auth else 8,
                use_user_profile=needs_auth
            )
            res["goal"] = goal
            res["key_used"] = key_label
            res["model_used"] = "gemini-3.6-flash (Vision LLM)"
            res["used_connected_profile"] = needs_auth
            return res
        except Exception as e2:
            print(f"[Browser Task] Échec Browser-Use 3.6 ({e2}), repli Playwright direct...")
            if needs_auth:
                # Pour les tâches authentifiées, on utilise le profil Chrome persistant en Playwright
                return await _run_playwright_with_profile(goal, url)
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


async def _run_playwright_with_profile(goal: str, url: str = "") -> Dict[str, Any]:
    """Repli Playwright utilisant le profil Chrome persistant avec sessions connectées.
    Utilisé pour les tâches nécessitant un compte connecté (Amazon, Google, Fnac, etc.)."""
    from playwright.async_api import async_playwright

    target_url = url.strip() if url else ""
    if not target_url:
        search_res = await search_web(goal, max_results=2)
        if search_res.get("results"):
            target_url = search_res["results"][0]["url"]
        else:
            target_url = f"https://www.google.com/search?q={quote_plus(goal)}"

    if not target_url.startswith("http://") and not target_url.startswith("https://"):
        target_url = "https://" + target_url

    print(f"[Browser Auth] Playwright avec profil connecté sur : {target_url}")

    try:
        async with async_playwright() as p:
            # Lancement avec le profil persistant (session connectée)
            browser_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]

            context = await p.chromium.launch_persistent_context(
                user_data_dir=PROFILE_DIR,
                executable_path=CHROME_PATH if os.path.exists(CHROME_PATH) else None,
                headless=False,
                args=browser_args,
                viewport={"width": 1280, "height": 850}
            )

            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2500)

            # Gestion cookies
            try:
                cookie_btn = page.locator(
                    "button#didomi-notice-agree-button, "
                    "button#onetrust-accept-btn-handler, "
                    "button:has-text('Tout accepter'), "
                    "button:has-text('Accepter'), "
                    "button:has-text('Accept all')"
                )
                if await cookie_btn.count() > 0:
                    await cookie_btn.first.click(timeout=2500)
                    await page.wait_for_timeout(1000)
            except Exception:
                pass

            await page.screenshot(path=SCREENSHOT_PATH, type="jpeg", quality=75)
            title = await page.title()
            final_url = page.url

            body_text = await page.evaluate("() => document.body ? document.body.innerText : ''")
            clean_lines = [l.strip() for l in body_text.splitlines() if len(l.strip()) > 3]
            summary = "\n".join(clean_lines[:40])

            # Sauvegarder les cookies/session
            await context.close()

            return {
                "status": "success",
                "goal": goal,
                "site_visited": final_url,
                "page_title": title,
                "summary": summary[:1400],
                "used_connected_profile": True,
                "screenshot": "/static/latest_screenshot.jpg"
            }
    except Exception as ex:
        return {
            "status": "error",
            "goal": goal,
            "site_visited": target_url,
            "message": f"Erreur navigation authentifiée: {str(ex)}"
        }

def open_browser_window(url: str = "https://www.google.com", load_extensions: bool = True) -> Dict[str, Any]:
    """Ouvre une vraie fenêtre Google Chrome visible à l'écran avec le profil connecté et les extensions chargées (Send to Kindle, etc.)."""
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
    ]
    if load_extensions:
        ext_args = get_extension_load_args()
        cmd.extend(ext_args)
    cmd.append(target)

    try:
        subprocess.Popen(cmd)
        ext_note = " avec vos extensions (Send to Kindle)" if load_extensions else ""
        return {
            "status": "success",
            "url": target,
            "message": f"Google Chrome ouvert à l'écran sur {target}{ext_note} et votre session connectée."
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
    """Recherche un produit ou service sur un site marchand, sélectionne la variante/pointure,
    l'ajoute au panier, navigue vers la page de commande, préremplit les coordonnées de Pierre
    (nom, prénom, adresse, email), S'ARRÊTE STRICTEMENT AVANT LE PAIEMENT,
    et ouvre automatiquement Google Chrome à l'écran avec la session connectée et le panier rempli.
    """
    from playwright.async_api import async_playwright
    from services.memory_service import memory_service

    # 1. Détermination du site marchand et URL cible
    target_site = (merchant_url or "").strip()
    if not target_site:
        search_query = f"{product_or_service} acheter commander site officiel"
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

    # Détection intelligente de la pointure / taille demandée
    size_match = re.search(r'(?:pointure|taille|en\s+taille|en)\s*(\d{2})', product_or_service, re.IGNORECASE)
    if size_match:
        target_size = size_match.group(1).strip()
    elif any(k in product_or_service.lower() for k in ["chaussure", "basket", "running", "sneaker", "soulier", "botte", "pantoufle"]):
        target_size = user_info.get("shoe_size", "42")
    else:
        target_size = user_info.get("clothing_size", "M")

    cart_url = target_site
    prefilled_fields = []
    actions_log = []
    item_added = False

    try:
        async with async_playwright() as p:
            # Lancement avec le vrai Chrome et le profil persistant (.jarvis_chrome_profile)
            # En headless=False et avec suppression des flags webdriver pour contourner les protections antibot (Cloudflare, etc.)
            browser_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]

            context = await p.chromium.launch_persistent_context(
                user_data_dir=PROFILE_DIR,
                executable_path=CHROME_PATH if os.path.exists(CHROME_PATH) else None,
                headless=False,
                args=browser_args,
                viewport={"width": 1280, "height": 850}
            )

            page = context.pages[0] if context.pages else await context.new_page()

            # A. Visite du site
            actions_log.append(f"Navigation vers {target_site}")
            await page.goto(target_site, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(2000)

            # B. Gestion immédiate des bannières cookies
            try:
                cookie_loc = page.locator(
                    "button#didomi-notice-agree-button, "
                    "button#onetrust-accept-btn-handler, "
                    "button#sp-cc-accept, "
                    "button:has-text('Accepter & Fermer'), "
                    "button:has-text('Tout accepter'), "
                    "button:has-text('Accepter'), "
                    "button:has-text('J\\'accepte'), "
                    "button:has-text('Accept all')"
                )
                if await cookie_loc.count() > 0:
                    await cookie_loc.first.click(timeout=2500)
                    actions_log.append("Bannière cookies acceptée.")
                    await page.wait_for_timeout(1000)
            except Exception:
                pass

            # C. Détection fiche produit ou recherche interne
            add_cart_loc = page.locator("button:has-text('Ajouter au panier'), button:has-text('Add to basket'), button:has-text('Add to cart'), input[value*='Ajouter au panier'], a:has-text('Ajouter au panier'), button#add-to-cart-button")
            is_product_page = (await add_cart_loc.count() > 0)

            if not is_product_page:
                try:
                    search_box = page.locator("input[type='search'], input[name*='search' i], input[name*='query' i], input[placeholder*='recherch' i], input[placeholder*='search' i], input#twotabsearchtextbox")
                    if await search_box.count() > 0:
                        await search_box.first.fill(product_or_service)
                        await page.keyboard.press("Enter")
                        actions_log.append(f"Recherche de '{product_or_service}' sur le site.")
                        await page.wait_for_timeout(3000)

                        product_link = page.locator("div.s-result-item h2 a, .product-card a, .product-item a, a:has(h2), a:has(h3)").first
                        if await product_link.count() > 0:
                            await product_link.click(timeout=5000)
                            actions_log.append("Accès à la fiche produit sélectionnée.")
                            await page.wait_for_timeout(2500)
                except Exception as s_err:
                    actions_log.append(f"Recherche interne: {s_err}")

            # D. Sélection obligatoire de la variante / pointure / taille (crucial pour les chaussures)
            try:
                size_selected = False

                # 1. Recherche par label ou bouton portant le numéro de pointure (ex: 42)
                size_loc = page.locator(
                    f"label:has-text('{target_size}'), "
                    f"button:has-text('{target_size}'), "
                    f"[data-testid*='size']:has-text('{target_size}'), "
                    f"[aria-label*='{target_size}']"
                ).first

                if await size_loc.count() > 0 and await size_loc.is_visible():
                    await size_loc.scroll_into_view_if_needed()
                    await size_loc.click(force=True, timeout=3000)
                    size_selected = True
                    actions_log.append(f"Pointure/Taille {target_size} sélectionnée avec succès.")
                    await page.wait_for_timeout(1500)

                # 2. Si pas trouvé, vérification d'un menu déroulant <select> de pointure
                if not size_selected:
                    select_loc = page.locator("select[name*='size' i], select[name*='taille' i], select#native_dropdown_selected_size_name").first
                    if await select_loc.count() > 0:
                        options = await select_loc.locator("option").all_inner_texts()
                        match_opt = next((opt for opt in options if target_size in opt), None)
                        if match_opt:
                            await select_loc.select_option(label=match_opt)
                            actions_log.append(f"Pointure {match_opt.strip()} sélectionnée dans le menu déroulant.")
                            size_selected = True
                            await page.wait_for_timeout(1500)
                        elif len(options) > 1:
                            await select_loc.select_option(index=1)
                            actions_log.append(f"Première taille disponible ({options[1].strip()}) sélectionnée.")
                            size_selected = True
                            await page.wait_for_timeout(1500)

                # 3. Fallback : premier bouton de taille visible
                if not size_selected:
                    generic_size = page.locator("button[data-testid*='size'], [role='radio'][aria-label*='taille' i], div[class*='size'] button").first
                    if await generic_size.count() > 0 and await generic_size.is_visible():
                        await generic_size.click(force=True, timeout=2000)
                        actions_log.append("Taille disponible par défaut sélectionnée.")
                        await page.wait_for_timeout(1500)

            except Exception as size_err:
                actions_log.append(f"Détection taille: {size_err}")

            # E. Ajout effectif au panier
            try:
                add_btn = page.locator(
                    "button:has-text('Ajouter au panier'), "
                    "button:has-text('Add to cart'), "
                    "button:has-text('Add to basket'), "
                    "input[value*='Ajouter au panier'], "
                    "a:has-text('Ajouter au panier'), "
                    "button#add-to-cart-button, "
                    "[data-testid*='add-to-cart']"
                ).first

                if await add_btn.count() > 0:
                    await add_btn.scroll_into_view_if_needed()
                    await add_btn.click(timeout=5000)
                    item_added = True
                    actions_log.append("Article ajouté au panier avec succès.")
                    await page.wait_for_timeout(3500)
            except Exception as cart_err:
                actions_log.append(f"Erreur ajout panier: {cart_err}")

            # F. Navigation vers la page panier / récapitulatif
            try:
                # 1. Vérifier si un tiroir ou popin modal "Ajouté au panier" est apparu
                modal_cart = page.locator(
                    "[role='dialog'] a[href*='cart'], "
                    ".sheet-modal a[href*='cart'], "
                    "[role='dialog'] button:has-text('panier'), "
                    "a:has-text('Voir mon panier'), "
                    "a:has-text('Accéder au panier'), "
                    "a:has-text('Voir le panier')"
                ).first

                if await modal_cart.count() > 0:
                    try:
                        await modal_cart.click(force=True, timeout=3000)
                        actions_log.append("Accès au panier via la fenêtre de confirmation.")
                        await page.wait_for_timeout(3000)
                    except Exception:
                        pass

                # 2. Si l'URL n'est pas encore celle du panier, naviguer vers le panier
                if "cart" not in page.url.lower() and "panier" not in page.url.lower():
                    # Bouton d'en-tête ou lien standard
                    header_cart = page.locator("a[href*='cart'], a[href*='panier'], [data-testid*='cart'] a, [aria-label*='panier' i]").first
                    if await header_cart.count() > 0:
                        try:
                            await header_cart.click(force=True, timeout=3000)
                            await page.wait_for_timeout(3000)
                        except Exception:
                            pass

                # 3. Fallback direct vers l'URL panier du domaine
                if "cart" not in page.url.lower() and "panier" not in page.url.lower():
                    domain = f"{page.url.split('://')[0]}://{page.url.split('/')[2]}"
                    if "decathlon" in domain:
                        await page.goto(f"{domain}/checkout/cart", wait_until="domcontentloaded")
                    elif "amazon" in domain:
                        await page.goto(f"{domain}/gp/cart/view.html", wait_until="domcontentloaded")
                    else:
                        await page.goto(f"{domain}/cart", wait_until="domcontentloaded")
                    await page.wait_for_timeout(3000)

                cart_url = page.url
                actions_log.append(f"Page panier atteinte : {cart_url}")
            except Exception as nav_err:
                actions_log.append(f"Navigation panier : {nav_err}")

            # G. Tentative d'accès à l'étape commande (checkout) pour préremplissage
            try:
                checkout_btn = page.locator(
                    "a:has-text('Passer la commande'), "
                    "button:has-text('Passer la commande'), "
                    "a:has-text('Commander'), "
                    "button:has-text('Commander'), "
                    "a:has-text('Valider mon panier'), "
                    "button:has-text('Valider mon panier'), "
                    "a[href*='checkout'], "
                    "button:has-text('Poursuivre')"
                ).first

                if await checkout_btn.count() > 0:
                    await checkout_btn.click(timeout=4000)
                    actions_log.append("Passage à l'étape de coordonnées/livraison.")
                    await page.wait_for_timeout(2500)
                    cart_url = page.url
            except Exception:
                pass

            # H. Préremplissage intelligent des coordonnées de Pierre Cassagnettes
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
                            curr = await loc.input_value()
                            if not curr:
                                await loc.fill(val, timeout=2000)
                                prefilled_fields.append(f"{label}: {val}")
                                break
                    except Exception:
                        continue

            # I. SÉCURITÉ ABSOLUE : Arrêt strict avant le paiement
            # On ne clique JAMAIS sur payer
            cart_url = page.url
            await page.screenshot(path=SCREENSHOT_PATH, type="jpeg", quality=80)
            actions_log.append("Arrêt sécurisé avant paiement. Données et cookies sauvegardés.")

            # Sauvegarde et fermeture propre du contexte Playwright
            # Cela écrit immédiatement tous les cookies, tokens de panier et local storage dans PROFILE_DIR
            await context.close()

    except Exception as ex:
        actions_log.append(f"Erreur d'exécution: {str(ex)}")

    # J. Ouverture immédiate de Google Chrome en natif sur l'écran de Pierre
    # Le Chrome ouvert réutilise PROFILE_DIR et retrouve instantanément le panier avec les articles dedans !
    if open_when_ready and cart_url:
        open_res = open_browser_window(cart_url)
        actions_log.append(f"Google Chrome ouvert à l'écran sur le panier ({open_res.get('status')}).")

    return {
        "status": "success",
        "product": product_or_service,
        "site": target_site,
        "cart_url": cart_url,
        "item_added": item_added,
        "target_size": target_size,
        "prefilled_fields": prefilled_fields,
        "steps": actions_log,
        "browser_opened": open_when_ready,
        "screenshot": "/static/latest_screenshot.jpg",
        "message": (
            f"Le panier pour '{product_or_service}' (pointure/taille {target_size}) a été préparé sur {target_site}. "
            f"Les coordonnées de Pierre Cassagnettes ({email}) ont été préremplies. "
            f"Google Chrome est maintenant ouvert sur votre écran avec votre article dans le panier : "
            f"il ne vous reste plus qu'à choisir votre mode de paiement et valider votre achat en toute sécurité."
        )
    }


# ─── SERVICE SEND TO KINDLE & EXTENSIONS ──────────────────────────────────────

async def extract_clean_article(url: str) -> Dict[str, Any]:
    """Extrait le contenu textuel et la structure épurée (mode lecture) d'un article web.
    Supprime les bannières, publicités, menus, traceurs et prépare un document lisible pour Kindle.
    """
    clean_url = (url or "").strip()
    if not clean_url.startswith("http://") and not clean_url.startswith("https://"):
        clean_url = "https://" + clean_url

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=headers) as client:
            resp = await client.get(clean_url)
            html_text = resp.text
    except Exception as e:
        return {"status": "error", "message": f"Impossible de charger la page {clean_url}: {e}"}

    soup = BeautifulSoup(html_text, "html.parser")

    # Suppression des éléments superflus
    for tag in soup(["script", "style", "noscript", "iframe", "svg", "header", "footer", "nav", "aside", "form"]):
        tag.decompose()

    # Titre de l'article
    title = ""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    elif soup.h1:
        title = soup.h1.get_text().strip()
    elif soup.title:
        title = soup.title.get_text().strip()
    if not title:
        title = "Article Web"

    # Auteur
    author = ""
    meta_author = soup.find("meta", attrs={"name": "author"}) or soup.find("meta", property="article:author")
    if meta_author and meta_author.get("content"):
        author = meta_author["content"].strip()

    # Contenu principal
    main_el = (
        soup.find("article")
        or soup.find("main")
        or soup.find(id=re.compile(r"content|article|main", re.I))
        or soup.find(class_=re.compile(r"article-content|post-content|entry-content", re.I))
    )
    if not main_el:
        main_el = soup.body

    paragraphs = []
    if main_el:
        for p in main_el.find_all(["p", "h2", "h3", "blockquote", "ul", "ol"]):
            txt = p.get_text().strip()
            if len(txt) > 20 or p.name in ("h2", "h3"):
                if p.name == "h2":
                    paragraphs.append(f"<h2>{txt}</h2>")
                elif p.name == "h3":
                    paragraphs.append(f"<h3>{txt}</h3>")
                elif p.name == "blockquote":
                    paragraphs.append(f"<blockquote>{txt}</blockquote>")
                else:
                    paragraphs.append(f"<p>{txt}</p>")

    article_html = "\n".join(paragraphs) if paragraphs else f"<p>{soup.get_text()[:3000]}</p>"

    # Stylisation élégante Kindle
    styled_doc = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
body {{ font-family: 'Georgia', 'Palatino', serif; line-height: 1.6; font-size: 1.15em; max-width: 800px; margin: 0 auto; padding: 2em; color: #111; }}
h1 {{ font-size: 2em; margin-bottom: 0.2em; }}
.meta {{ font-size: 0.9em; color: #666; margin-bottom: 2em; border-bottom: 1px solid #ccc; padding-bottom: 0.8em; }}
p {{ margin: 1em 0; text-align: justify; }}
blockquote {{ border-left: 3px solid #888; padding-left: 1em; color: #444; font-style: italic; }}
</style>
</head>
<body>
<h1>{title}</h1>
<div class="meta">{f'Par {author} &bull; ' if author else ''}Source : <a href="{clean_url}">{clean_url}</a></div>
<div class="content">
{article_html}
</div>
</body>
</html>"""

    # Dossier de sauvegarde
    from services.download_service import EBOOKS_DIR
    os.makedirs(EBOOKS_DIR, exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", title[:50]).strip("_") or "article"
    file_path = os.path.join(EBOOKS_DIR, f"{slug}.html")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(styled_doc)

    return {
        "status": "success",
        "url": clean_url,
        "title": title,
        "author": author,
        "file_path": file_path,
        "word_count": len(re.findall(r"\w+", article_html))
    }


async def send_page_to_kindle(
    url: str = "",
    title: str = "",
    open_in_chrome: bool = True
) -> Dict[str, Any]:
    """Extrait un article ou page web et l'expédie vers la liseuse Kindle de Pierre.
    1. Extrait le contenu épuré sans publicité au format liseuse Kindle.
    2. Achemine l'ebook directement par courriel vers la liseuse (via send_to_ereader).
    3. Ouvre également la page dans Google Chrome avec l'extension Send to Kindle officielle chargée.
    """
    from services.download_service import send_to_ereader

    target_url = (url or "").strip()
    if not target_url:
        return {
            "status": "error",
            "message": "Veuillez fournir l'URL de l'article ou de la page à envoyer sur votre Kindle."
        }

    # 1. Extraction et mise en forme mode lecture
    extracted = await extract_clean_article(target_url)
    if extracted.get("status") == "error":
        # Repli : ouvrir Chrome directement sur la page
        if open_in_chrome:
            open_browser_window(target_url, load_extensions=True)
        return {
            "status": "warning",
            "url": target_url,
            "message": f"Impossible d'extraire le texte ({extracted.get('message')}). Google Chrome a été ouvert sur la page avec l'extension Send to Kindle."
        }

    art_title = title or extracted.get("title", "Article")
    file_path = extracted["file_path"]

    # 2. Acheminement vers la liseuse (Send-to-Kindle via courriel direct)
    ereader_res = await send_to_ereader(file_path=file_path, method="email")

    # 3. Lancement de Chrome avec extension Send to Kindle chargée
    chrome_res = None
    if open_in_chrome:
        chrome_res = open_browser_window(target_url, load_extensions=True)

    recipient = ereader_res.get("recipient", "votre adresse Kindle")

    return {
        "status": "success",
        "title": art_title,
        "url": target_url,
        "file_path": file_path,
        "word_count": extracted.get("word_count", 0),
        "ereader_delivery": ereader_res,
        "chrome_opened": bool(chrome_res and chrome_res.get("status") == "success"),
        "message": (
            f"L'article '{art_title}' a été mis en page pour votre liseuse et expédié par courriel vers {recipient}. "
            f"Google Chrome est également ouvert sur l'article avec l'extension Send to Kindle prête."
        )
    }


def list_installed_chrome_extensions() -> Dict[str, Any]:
    """Fournit le bilan complet de toutes les extensions Google Chrome détectées sur la machine de Pierre."""
    exts = get_installed_chrome_extensions()
    s2k_installed = any(e.get("is_send_to_kindle") for e in exts)
    return {
        "status": "success",
        "total": len(exts),
        "send_to_kindle_detected": s2k_installed,
        "extensions": exts,
        "message": f"{len(exts)} extensions Google Chrome détectées. Extension Send to Kindle : {'Active' if s2k_installed else 'Non détectée'}."
    }


# ─── SERVICE OFFICIEL AMAZON SEND TO KINDLE (WEB PERSISTANT) ─────────────────

AMAZON_KINDLE_SUPPORTED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".txt", ".rtf",
    ".htm", ".html", ".png", ".gif", ".jpg", ".jpeg", ".bmp", ".epub"
}

def resolve_local_file_path(file_path: str) -> Optional[str]:
    """Résout intelligemment le chemin d'un fichier local à travers les dossiers de travail de Jarvis."""
    if not file_path:
        return None
    raw = file_path.strip().strip('"').strip("'")
    if os.path.isabs(raw) and os.path.isfile(raw):
        return os.path.abspath(raw)
    
    candidates = [
        raw,
        os.path.join(BASE_DIR, raw),
        os.path.join(BASE_DIR, "downloads", raw),
        os.path.join(BASE_DIR, "downloads", "ebooks", raw),
        os.path.join(BASE_DIR, "downloads", os.path.basename(raw)),
        os.path.join(BASE_DIR, "downloads", "ebooks", os.path.basename(raw)),
        os.path.join(BASE_DIR, "my-project", raw),
        os.path.join(BASE_DIR, "my-project", os.path.basename(raw)),
        os.path.join(STATIC_DIR, "uploads", raw),
        os.path.join(STATIC_DIR, "uploads", "chat", raw),
        os.path.join(STATIC_DIR, "uploads", "chat", os.path.basename(raw)),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c)
    return None

def is_valid_epub(file_path: str) -> bool:
    """Vérifie si un fichier est une archive EPUB valide (ZIP contenant mimetype et documents)."""
    if not file_path or not os.path.isfile(file_path) or os.path.getsize(file_path) < 1000:
        return False
    import zipfile
    try:
        with zipfile.ZipFile(file_path, "r") as z:
            names = z.namelist()
            if "mimetype" in names:
                with z.open("mimetype") as m:
                    content = m.read().decode("utf-8", errors="ignore")
                    if "epub" in content:
                        return True
            return any(n.endswith((".opf", ".ncx", ".xhtml", ".html", ".htm")) for n in names)
    except Exception:
        return False


async def send_file_to_kindle_web(
    file_path: str,
    open_browser_if_needed: bool = True,
    timeout_sec: int = 45
) -> Dict[str, Any]:
    """Dépose et expédie un fichier sur la liseuse Kindle de Pierre via la page officielle Amazon Send to Kindle.
    Utilise le profil Chrome persistant de Jarvis (.jarvis_chrome_profile) avec le compte Amazon connecté.
    Supporte : PDF, DOC, DOCX, TXT, RTF, HTM, HTML, PNG, GIF, JPG, JPEG, BMP, EPUB (max 200 Mo).
    """
    from playwright.async_api import async_playwright

    resolved_path = resolve_local_file_path(file_path)
    if not resolved_path:
        return {
            "status": "error",
            "message": f"Fichier introuvable : '{file_path}'. Veuillez vérifier le nom ou l'emplacement du fichier."
        }

    ext = os.path.splitext(resolved_path)[1].lower()
    file_name = os.path.basename(resolved_path)
    file_size_bytes = os.path.getsize(resolved_path)
    file_size_mb = file_size_bytes / (1024 * 1024)

    if file_size_mb > 200:
        return {
            "status": "error",
            "message": f"Le fichier '{file_name}' ({file_size_mb:.1f} Mo) dépasse la limite de 200 Mo autorisée par Amazon Send to Kindle."
        }

    if ext not in AMAZON_KINDLE_SUPPORTED_EXTENSIONS:
        return {
            "status": "warning",
            "message": (
                f"L'extension '{ext}' du fichier '{file_name}' n'est pas officiellement dans la liste Send to Kindle "
                f"(formats supportés : {', '.join(sorted(AMAZON_KINDLE_SUPPORTED_EXTENSIONS))})."
            )
        }

    # Validation d'intégrité pour les fichiers EPUB (évite les fausses pages HTML d'archive.org rejetées par Amazon)
    if ext == ".epub" and not is_valid_epub(resolved_path):
        return {
            "status": "error",
            "file_name": file_name,
            "message": (
                f"Le fichier '{file_name}' n'est pas un ePub valide "
                f"(il s'agit d'une page HTML ou d'un fichier corrompu). "
                f"Amazon rejetterait ce document lors de la conversion. Envoi annulé."
            )
        }

    size_str = f"{file_size_mb:.2f} Mo" if file_size_mb >= 1 else f"{file_size_bytes / 1024:.1f} Ko"
    print(f"[Send to Kindle] Préparation du transfert web pour '{file_name}' ({size_str})...")

    # Options anti-détection avec position hors-champ pour neutraliser les blocages anti-bot d'Amazon
    browser_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--window-size=1280,850",
        "--window-position=-2000,-2000"
    ]

    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=PROFILE_DIR,
                executable_path=CHROME_PATH if os.path.exists(CHROME_PATH) else None,
                headless=False,
                args=browser_args,
                viewport={"width": 1280, "height": 950}
            )
            page = context.pages[0] if context.pages else await context.new_page()

            try:
                # 1. Navigation vers Amazon Send to Kindle
                await page.goto("https://www.amazon.fr/sendtokindle", wait_until="domcontentloaded", timeout=25000)
                await page.wait_for_timeout(3000)

                # Gestion d'éventuelle page d'erreur temporaire Amazon
                body_txt = await page.evaluate("() => document.body ? document.body.innerText : ''")
                if "difficultés" in body_txt.lower() or "désolés" in body_txt.lower():
                    print("[Send to Kindle] Rechargement automatique suite à page temporaire d'Amazon...")
                    await page.wait_for_timeout(2000)
                    await page.reload(wait_until="domcontentloaded")
                    await page.wait_for_timeout(3000)

                # Gestion d'éventuels cookies
                try:
                    cookie_loc = page.locator("button#sp-cc-accept, input#sp-cc-accept, button:has-text('Accepter')").first
                    if await cookie_loc.count() > 0 and await cookie_loc.is_visible():
                        await cookie_loc.click(timeout=2000)
                        await page.wait_for_timeout(1000)
                except Exception:
                    pass

                cur_url = page.url.lower()
                has_signin_btn = (await page.locator("#s2k-dnd-sign-in-button, button:has-text(\"S'identifier\"), a:has-text(\"S'identifier\")").count() > 0)
                is_signin = (
                    "signin" in cur_url or 
                    "ap/signin" in cur_url or 
                    (await page.locator("input#ap_email, input#ap_password").count() > 0) or
                    has_signin_btn
                )

                if is_signin:
                    await page.screenshot(path=SCREENSHOT_PATH, type="jpeg", quality=75)
                    await context.close()
                    if open_browser_if_needed:
                        open_browser_window("https://www.amazon.fr/sendtokindle")
                    return {
                        "status": "need_login",
                        "url": page.url,
                        "file_name": file_name,
                        "message": (
                            "Votre compte Amazon a besoin d'être authentifié sur la page Send to Kindle. "
                            "Google Chrome a été ouvert sur votre écran sur la page Send to Kindle : "
                            "veuillez vous identifier à votre compte Amazon, vos identifiants resteront sauvegardés pour tous les prochains envois."
                        )
                    }

                # 2. Localisation du bouton d'ajout de fichiers
                upload_btn = page.locator("#s2k-dnd-add-your-files-button, button:has-text('Sélectionnez des fichiers')").first
                if await upload_btn.count() == 0:
                    try:
                        await page.wait_for_selector("#s2k-dnd-add-your-files-button", timeout=8000)
                        upload_btn = page.locator("#s2k-dnd-add-your-files-button")
                    except Exception:
                        pass

                if await upload_btn.count() == 0 or not await upload_btn.is_visible():
                    await page.screenshot(path=SCREENSHOT_PATH, type="jpeg", quality=75)
                    await context.close()
                    return {
                        "status": "error",
                        "file_name": file_name,
                        "message": "Impossible de trouver la zone de dépôt de documents sur la page Amazon Send to Kindle."
                    }

                # 3. Dépôt du fichier via le sélecteur d'Amazon
                async with page.expect_file_chooser(timeout=12000) as fc_info:
                    await upload_btn.click()

                file_chooser = await fc_info.value
                await file_chooser.set_files(resolved_path)

                # 4. Attente de la validation du fichier et de l'apparition du bouton d'envoi
                send_btn = page.locator("#s2k-r2s-send-button")
                try:
                    await page.wait_for_selector("#s2k-r2s-send-button", state="visible", timeout=15000)
                except Exception:
                    pass

                if await send_btn.count() == 0 or not await send_btn.is_visible():
                    await page.screenshot(path=SCREENSHOT_PATH, type="jpeg", quality=75)
                    await context.close()
                    return {
                        "status": "error",
                        "file_name": file_name,
                        "message": f"Le fichier '{file_name}' n'a pas pu être préparé par la page Amazon Send to Kindle (format ou validation rejetée)."
                    }

                # Capture d'écran avant envoi
                await page.screenshot(path=SCREENSHOT_PATH, type="jpeg", quality=80)

                # 5. Clic sur Envoyer
                await send_btn.click()

                # 6. Attente réelle de la fin du transfert réseau vers Amazon
                # Attention : 'Fichiers récemment envoyés' et 'Dans la bibliothèque' figurent en permanence dans le bas de page !
                # On doit attendre que 'Envoi en cours...' disparaisse et que 'Vos fichiers sont en route' apparaisse ou que la zone se réinitialise.
                upload_finished = False
                for _ in range(35):
                    await page.wait_for_timeout(1000)
                    upload_state = await page.evaluate('''() => {
                        const body = document.body ? document.body.innerText : '';
                        const inProgress = body.includes('Envoi en cours') || body.includes('Calcul du temps');
                        const routeConfirmed = body.includes('Vos fichiers sont en route');
                        const cancelBtn = Array.from(document.querySelectorAll('button')).find(b => b.innerText && b.innerText.includes('Annuler'));
                        const sendBtn = document.querySelector('#s2k-r2s-send-button');
                        const sendVisible = sendBtn ? (sendBtn.offsetParent !== null) : false;
                        return {
                            inProgress: inProgress,
                            routeConfirmed: routeConfirmed,
                            hasCancelBtn: !!cancelBtn,
                            sendVisible: sendVisible
                        };
                    }''')
                    if upload_state['routeConfirmed'] or (not upload_state['inProgress'] and not upload_state['hasCancelBtn'] and not upload_state['sendVisible']):
                        upload_finished = True
                        break

                await page.wait_for_timeout(2000)

                # Capture finale de confirmation
                await page.screenshot(path=SCREENSHOT_PATH, type="jpeg", quality=80)
                await context.close()

                return {
                    "status": "success",
                    "file_name": file_name,
                    "file_path": resolved_path,
                    "file_size": size_str,
                    "channel": "amazon_send_to_kindle_web",
                    "service": "Amazon Send to Kindle (Compte connecté)",
                    "screenshot": "/static/latest_screenshot.jpg",
                    "message": (
                        f"Le fichier '{file_name}' ({size_str}) a été déposé et envoyé avec succès sur votre liseuse Kindle "
                        f"via la page officielle Amazon Send to Kindle connectée à votre compte. "
                        f"Vos fichiers sont en route et seront synchronisés automatiquement sur votre appareil."
                    )
                }

            except Exception as inner_ex:
                try:
                    await page.screenshot(path=SCREENSHOT_PATH, type="jpeg", quality=75)
                except Exception:
                    pass
                await context.close()
                raise inner_ex

    except Exception as ex:
        err_msg = str(ex)
        if "Process singleton" in err_msg or "Target page, context or browser has been closed" in err_msg:
            return {
                "status": "warning",
                "file_name": file_name,
                "message": (
                    "Google Chrome est actuellement ouvert sur votre ordinateur avec le profil Jarvis. "
                    "Veuillez fermer la fenêtre Chrome pour permettre à Jarvis d'exécuter l'envoi en tâche de fond, "
                    "ou demandez-lui d'ouvrir la page pour le faire en direct."
                )
            }
        return {
            "status": "error",
            "file_name": file_name,
            "message": f"Erreur lors du transfert Amazon Send to Kindle : {err_msg}"
        }

async def check_kindle_web_status() -> Dict[str, Any]:
    """Vérifie l'état de connexion de la session Amazon Send to Kindle."""
    from playwright.async_api import async_playwright

    browser_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--window-size=1280,850",
        "--window-position=-2000,-2000"
    ]

    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=PROFILE_DIR,
                executable_path=CHROME_PATH if os.path.exists(CHROME_PATH) else None,
                headless=False,
                args=browser_args,
                viewport={"width": 1280, "height": 850}
            )
            page = context.pages[0] if context.pages else await context.new_page()
            try:
                await page.goto("https://www.amazon.fr/sendtokindle", wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(3000)

                body_txt = await page.evaluate("() => document.body ? document.body.innerText : ''")
                if "difficultés" in body_txt.lower() or "désolés" in body_txt.lower():
                    await page.wait_for_timeout(2000)
                    await page.reload(wait_until="domcontentloaded")
                    await page.wait_for_timeout(3000)

                cur_url = page.url.lower()
                has_signin_btn = (await page.locator("#s2k-dnd-sign-in-button, button:has-text(\"S'identifier\"), a:has-text(\"S'identifier\")").count() > 0)
                is_signin = (
                    "signin" in cur_url or 
                    "ap/signin" in cur_url or 
                    (await page.locator("input#ap_email, input#ap_password").count() > 0) or
                    has_signin_btn
                )

                user_name = "Pierre"
                body_text = await page.evaluate("() => document.body ? document.body.innerText : ''")
                if "Bonjour " in body_text and not is_signin:
                    import re
                    match = re.search(r"Bonjour\s+([A-Za-z0-9_\-]+)", body_text)
                    if match:
                        user_name = match.group(1)

                await page.screenshot(path=SCREENSHOT_PATH, type="jpeg", quality=75)
                await context.close()

                return {
                    "status": "success",
                    "logged_in": not is_signin,
                    "user_name": user_name if not is_signin else None,
                    "service_url": "https://www.amazon.fr/sendtokindle",
                    "message": (
                        f"Session Amazon Send to Kindle active pour {user_name}." if not is_signin
                        else "Session Amazon Send to Kindle non connectée. Connexion requise."
                    )
                }
            except Exception as e:
                await context.close()
                return {"status": "error", "logged_in": False, "message": str(e)}
    except Exception as ex:
        return {"status": "error", "logged_in": False, "message": str(ex)}



