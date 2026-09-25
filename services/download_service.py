"""Service de téléchargement sécurisé et transfert vers liseuse pour J.A.R.V.I.S.
Permet de télécharger des fichiers (documents, ebooks, médias) avec accord oral préalable
et de les acheminer automatiquement vers la liseuse de Pierre (Kindle, Kobo) via USB ou e-mail.
"""

import os
import re
import shutil
import httpx
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse, unquote

from config import BASE_DIR, STATIC_DIR, CHROME_PATH, PROFILE_DIR
from services.memory_service import memory_service
from services.email_service import send_email_async


# Répertoires dédiés aux téléchargements
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
EBOOKS_DIR = os.path.join(DOWNLOADS_DIR, "ebooks")
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(EBOOKS_DIR, exist_ok=True)


def _format_size(size_bytes: int) -> str:
    """Formate une taille d'octets en unité lisible (Ko, Mo, Go)."""
    if size_bytes < 1024:
        return f"{size_bytes} octets"
    elif size_bytes < 1024 * 1024:
        return f"{round(size_bytes / 1024, 1)} Ko"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{round(size_bytes / (1024 * 1024), 2)} Mo"
    else:
        return f"{round(size_bytes / (1024 * 1024 * 1024), 2)} Go"


def _sanitize_filename(name: str) -> str:
    """Nettoie le nom de fichier pour éviter les caractères invalides."""
    clean = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    return clean or "document_telecharge"


def detect_connected_ereader() -> Optional[Dict[str, str]]:
    """Détecte si une liseuse physique (Kindle, Kobo, Vivlio, Bookeen) est branchée en USB sur Windows."""
    import string
    available_drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\") and d != "C"]

    for drive in available_drives:
        try:
            # Vérification structure Kindle
            kindle_docs = os.path.join(drive, "documents")
            if os.path.isdir(kindle_docs):
                return {
                    "type": "Kindle",
                    "drive": drive,
                    "target_dir": kindle_docs,
                    "name": f"Kindle ({drive})"
                }

            # Vérification structure Kobo
            kobo_dir = os.path.join(drive, ".kobo")
            if os.path.isdir(kobo_dir) or os.path.isdir(os.path.join(drive, "books")):
                target = os.path.join(drive, "books") if os.path.isdir(os.path.join(drive, "books")) else drive
                return {
                    "type": "Kobo",
                    "drive": drive,
                    "target_dir": target,
                    "name": f"Kobo ({drive})"
                }

            # Vérification générique (dossier Books ou Ebooks sur clé/liseuse)
            for folder_name in ["Books", "Ebooks", "Documents", "livres"]:
                candidate = os.path.join(drive, folder_name)
                if os.path.isdir(candidate):
                    return {
                        "type": "Liseuse générique",
                        "drive": drive,
                        "target_dir": candidate,
                        "name": f"Périphérique {folder_name} ({drive})"
                    }
        except Exception:
            continue

    return None


async def download_file(
    url: str,
    filename: Optional[str] = None,
    confirmed_by_user: bool = False,
    subfolder: str = "downloads"
) -> Dict[str, Any]:
    """Télécharge un fichier depuis une URL avec accord préalable obligatoire de l'utilisateur."""
    target_url = (url or "").strip()
    if not target_url.startswith("http://") and not target_url.startswith("https://"):
        target_url = "https://" + target_url

    parsed = urlparse(target_url)
    domain = parsed.netloc

    # Détermination du nom de fichier par défaut
    if not filename:
        path_name = os.path.basename(parsed.path)
        if path_name and "." in path_name:
            filename = unquote(path_name)
        else:
            filename = "fichier_telecharge"

    filename = _sanitize_filename(filename)
    dest_dir = EBOOKS_DIR if "ebook" in subfolder.lower() else DOWNLOADS_DIR
    target_path = os.path.join(dest_dir, filename)

    # 1. Garde-fou d'accord oral obligatoire si non encore confirmé par Pierre
    if not confirmed_by_user:
        estimated_size_str = "taille inconnue"
        try:
            async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
                head_resp = await client.head(target_url)
                cl = head_resp.headers.get("Content-Length")
                if cl and cl.isdigit():
                    estimated_size_str = _format_size(int(cl))
                cd = head_resp.headers.get("Content-Disposition")
                if cd and "filename=" in cd:
                    raw_fn = cd.split("filename=")[1].strip('"\' ')
                    if raw_fn:
                        filename = _sanitize_filename(unquote(raw_fn))
        except Exception:
            pass

        return {
            "status": "requires_user_confirmation",
            "requires_oral_consent": True,
            "action": "download_file",
            "url": target_url,
            "filename": filename,
            "domain": domain,
            "estimated_size": estimated_size_str,
            "instruction_to_jarvis": (
                f"ATTENTION : Le téléchargement d'un fichier externe nécessite l'accord explicite de Pierre. "
                f"Explique à Pierre avec ta voix Aoede que tu as trouvé le fichier '{filename}' ({estimated_size_str}) sur le site {domain}, "
                f"et demande-lui directement son accord oral : 'M'autorisez-vous à télécharger ce fichier ?'. "
                f"Attends sa confirmation affirmative avant de relancer l'outil avec confirmed_by_user=True."
            )
        }

    # 2. Exécution du téléchargement une fois l'accord oral validé
    try:
        async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
            async with client.stream("GET", target_url) as response:
                if response.status_code >= 400:
                    return {
                        "status": "error",
                        "url": target_url,
                        "message": f"Erreur serveur HTTP {response.status_code} lors du téléchargement."
                    }

                # Récupération éventuelle du nom précis
                cd = response.headers.get("Content-Disposition")
                if cd and "filename=" in cd:
                    extracted = cd.split("filename=")[1].strip('"\' ')
                    if extracted:
                        filename = _sanitize_filename(unquote(extracted))
                        target_path = os.path.join(dest_dir, filename)

                total_downloaded = 0
                with open(target_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=16384):
                        f.write(chunk)
                        total_downloaded += len(chunk)

        formatted_size = _format_size(total_downloaded)
        return {
            "status": "success",
            "url": target_url,
            "filename": filename,
            "filepath": target_path,
            "size_bytes": total_downloaded,
            "size": formatted_size,
            "message": f"Fichier '{filename}' ({formatted_size}) téléchargé avec succès."
        }
    except Exception as e:
        return {
            "status": "error",
            "url": target_url,
            "message": f"Échec du téléchargement: {str(e)}"
        }


async def send_to_ereader(
    file_path: str,
    ereader_email: Optional[str] = None,
    method: str = "auto"
) -> Dict[str, Any]:
    """Transfère un ebook vers la liseuse de Pierre (Kindle, Kobo, etc.) via USB ou par e-mail direct."""
    resolved_path = os.path.abspath(file_path) if file_path else ""
    if not os.path.exists(resolved_path):
        # Chercher dans EBOOKS_DIR si seul le nom de fichier a été donné
        candidate = os.path.join(EBOOKS_DIR, os.path.basename(file_path))
        if os.path.exists(candidate):
            resolved_path = candidate
        else:
            return {
                "status": "error",
                "message": f"Fichier ebook introuvable à l'adresse {file_path}"
            }

    filename = os.path.basename(resolved_path)

    # 1. Méthode USB prioritaire si liseuse branchée et mode auto/usb
    if method in ("auto", "usb"):
        ereader_device = detect_connected_ereader()
        if ereader_device:
            dest_file = os.path.join(ereader_device["target_dir"], filename)
            try:
                shutil.copy2(resolved_path, dest_file)
                return {
                    "status": "success",
                    "channel": "usb",
                    "device": ereader_device["name"],
                    "filename": filename,
                    "target_path": dest_file,
                    "message": f"L'ebook '{filename}' a été transféré directement sur votre liseuse {ereader_device['name']} via USB."
                }
            except Exception as e:
                print(f"[E-Reader USB] Erreur copie: {e}")
                if method == "usb":
                    return {"status": "error", "message": f"Erreur lors de la copie USB: {e}"}

    # 2. Méthode Amazon Send to Kindle Web officiel (session connectée Pierre)
    if method in ("auto", "web", "amazon", "sendtokindle"):
        try:
            from services.browser_service import send_file_to_kindle_web
            web_res = await send_file_to_kindle_web(resolved_path, open_browser_if_needed=False)
            if web_res.get("status") == "success":
                return {
                    "status": "success",
                    "channel": "amazon_send_to_kindle_web",
                    "service": "Amazon Send to Kindle (Web officiel)",
                    "filename": filename,
                    "target_path": resolved_path,
                    "screenshot": web_res.get("screenshot"),
                    "message": f"L'ebook '{filename}' a été envoyé directement sur votre liseuse Kindle via la page Amazon Send to Kindle de votre compte."
                }
            elif method in ("web", "amazon", "sendtokindle"):
                return web_res
        except Exception as web_err:
            print(f"[Send to Kindle Web] Exception transfert : {web_err}")
            if method in ("web", "amazon", "sendtokindle"):
                return {"status": "error", "message": f"Erreur Send to Kindle Web : {web_err}"}

    # 3. Méthode E-mail (Send-to-Kindle par courriel ou envoi direct sur boîte mail)
    profile = memory_service.get_user_autofill_profile()
    target_email = (ereader_email or profile.get("ereader_email") or profile.get("email") or "pierrecassagnettes@gmail.com").strip()

    subject = f"Votre eBook J.A.R.V.I.S. : {filename}"
    body = (
        f"Bonjour Pierre,\n\n"
        f"Voici votre ebook **{filename}** récupéré et préparé par J.A.R.V.I.S.\n"
        f"Il est joint à ce courriel au format direct pour votre liseuse ou application de lecture (Kindle, Kobo, Calibre).\n\n"
        f"Titre : {filename}\n"
        f"Emplacement local : {resolved_path}\n"
    )

    email_res = await send_email_async(
        subject=subject,
        body=body,
        to_email=target_email,
        attachments=[resolved_path],
        is_html_report=True
    )

    channel_name = "Send-to-Kindle / E-mail Liseuse" if "@kindle.com" in target_email else f"E-mail ({target_email})"
    return {
        "status": "success",
        "channel": "email",
        "recipient": target_email,
        "filename": filename,
        "email_status": email_res.get("status"),
        "message": f"L'ebook '{filename}' a été envoyé avec succès vers votre liseuse ({channel_name})."
    }


def clean_book_query(raw_query: str) -> str:
    """Nettoie la requête utilisateur pour les moteurs de livres (retire parenthèses explicatives, verbes de demande)."""
    if not raw_query:
        return ""
    q = raw_query.strip()
    # Retirer les commentaires entre parenthèses ex: (3ème livre de la série)
    q = re.sub(r'\(.*?\)', '', q).strip()
    # Retirer les formules de demande courantes
    patterns = [
        r'^(?:télécharge(?:-moi)?|télécharger|trouve(?:-moi)?|trouver|cherche(?:-moi)?|chercher|peux-tu me (?:télécharger|trouver)|mets(?:-moi)?|envoie(?:-moi)?)\s+',
        r'^(?:le livre|l\'ebook|l\'e-book|le roman|l\'ouvrage|l\'oeuvre|le tome)\s+',
        r'\s+(?:en e?pub|au format e?pub|en pdf|gratuit|telecharger)$',
    ]
    for p in patterns:
        q = re.sub(p, '', q, flags=re.I).strip()
    # Nettoyer les espaces multiples
    q = re.sub(r'\s+', ' ', q).strip()
    return q or raw_query.strip()


async def search_annas_archive(
    query: str,
    lang: str = "fr",
    ext: str = "epub",
    limit: int = 8
) -> List[Dict[str, Any]]:
    """Recherche des livres électroniques authentiques sur Anna's Archive (https://annas-archive.gl).
    Gère automatiquement la protection DDoS-Guard et filtre les formats (ePub par défaut).
    """
    from playwright.async_api import async_playwright
    import urllib.parse

    clean_query = clean_book_query(query)
    encoded_query = urllib.parse.quote_plus(clean_query)
    search_url = f"https://annas-archive.gl/search?q={encoded_query}&lang={lang}&ext={ext}"

    browser_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--window-size=1280,850",
        "--window-position=-2000,-2000"
    ]

    results = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                executable_path=CHROME_PATH if os.path.exists(CHROME_PATH) else None,
                args=browser_args
            )
            page = await browser.new_page()
            try:
                print(f"[Anna's Archive Search] Recherche '{clean_query}' sur {search_url}...")
                await page.goto(search_url, wait_until="domcontentloaded", timeout=25000)

                # Attente du passage de DDoS-Guard (vérification de l'url et du titre)
                for _ in range(15):
                    await page.wait_for_timeout(1000)
                    u = page.url
                    t = await page.title()
                    if "check=" not in u and "ddos" not in t.lower() and "loading" not in t.lower():
                        break

                await page.wait_for_timeout(2000)

                # Extraction ciblée des liens de livres DANS <main> (exclut le bandeau d'en-tête Recent Downloads)
                raw_items = await page.evaluate('''() => {
                    const list = [];
                    const container = document.querySelector('main') || document.body;
                    container.querySelectorAll('a[href*="/md5/"]').forEach(a => {
                        const href = a.href || '';
                        const text = a.innerText.trim().replace(/\\s+/g, ' ');
                        const match = href.match(/\\/md5\\/([a-f0-9]{32})/i);
                        // Ne conserver que les liens avec un vrai titre textuel (exclut les miniatures sans texte)
                        if (match && text.length > 3 && !list.some(x => x.md5 === match[1])) {
                            list.push({
                                title: text,
                                md5: match[1],
                                href: href
                            });
                        }
                    });
                    return list;
                }''')

                for item in raw_items[:limit]:
                    results.append({
                        "title": item["title"],
                        "md5": item["md5"],
                        "url": item["href"],
                        "source": "Anna's Archive",
                        "format": ext.upper()
                    })

            finally:
                await browser.close()
    except Exception as e:
        print(f"[Anna's Archive Search] Erreur recherche : {e}")

    return results


async def download_from_annas_archive(
    md5: str,
    target_filename: Optional[str] = None,
    timeout_sec: int = 120
) -> Dict[str, Any]:
    """Télécharge un ePub authentique depuis Anna's Archive via le serveur partenaire avec compte à rebours.
    Valide l'intégrité de l'archive ePub une fois le téléchargement terminé.
    """
    from playwright.async_api import async_playwright
    from services.browser_service import is_valid_epub

    slow_url = f"https://annas-archive.gl/slow_download/{md5}/0/0"
    browser_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--window-size=1280,850",
        "--window-position=-2000,-2000"
    ]

    dl_url = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                executable_path=CHROME_PATH if os.path.exists(CHROME_PATH) else None,
                args=browser_args
            )
            page = await browser.new_page()
            try:
                print(f"[Anna's Archive DL] Connexion à {slow_url}...")
                await page.goto(slow_url, wait_until="domcontentloaded", timeout=25000)

                # Attente du passage de DDoS-Guard
                for _ in range(15):
                    await page.wait_for_timeout(1000)
                    u = page.url
                    t = await page.title()
                    if "check=" not in u and "ddos" not in t.lower() and "loading" not in t.lower():
                        break

                # Surveillance du compte à rebours (généralement 15 à 70 secondes)
                for _ in range(85):
                    await page.wait_for_timeout(1000)
                    try:
                        text = await page.evaluate("() => document.body ? document.body.innerText : ''")
                        if "wait " not in text.lower():
                            break
                    except Exception:
                        # Redirection détectée lors de l'expiration du compte à rebours
                        await page.wait_for_timeout(2500)
                        break

                await page.wait_for_timeout(2500)

                # Localisation du lien direct de téléchargement
                dl_url = await page.evaluate('''() => {
                    const links = Array.from(document.querySelectorAll('a')).map(a => a.href || '');
                    const target = links.find(h => h.includes('.epub') || h.includes('/download/'));
                    return target || null;
                }''')

                if not dl_url:
                    return {
                        "status": "error",
                        "message": "Lien de téléchargement direct introuvable sur la page d'Anna's Archive."
                    }

                print(f"[Anna's Archive DL] Lien direct localisé : {dl_url[:75]}...")

            finally:
                await browser.close()

        # Téléchargement effectif du flux binaire ePub via HTTP
        async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, follow_redirects=True, timeout=60.0) as client:
            resp = await client.get(dl_url)
            if resp.status_code != 200 or len(resp.content) < 1000:
                return {
                    "status": "error",
                    "message": f"Échec HTTP lors du téléchargement du livre ({resp.status_code})."
                }

            # Nommage propre du fichier
            if not target_filename:
                cd = resp.headers.get("Content-Disposition", "")
                if "filename=" in cd:
                    raw_fn = cd.split("filename=")[1].strip('"\' ')
                    target_filename = _sanitize_filename(unquote(raw_fn))
                else:
                    target_filename = f"ebook_{md5[:8]}.epub"

            if not target_filename.lower().endswith(".epub"):
                target_filename += ".epub"

            dest_path = os.path.join(EBOOKS_DIR, target_filename)
            with open(dest_path, "wb") as f:
                f.write(resp.content)

        # Validation stricte de l'ePub (vérification archive ZIP + structure EPUB)
        if not is_valid_epub(dest_path):
            try:
                os.remove(dest_path)
            except Exception:
                pass
            return {
                "status": "error",
                "message": "Le fichier téléchargé n'est pas une archive ePub valide. Téléchargement invalidé pour protéger votre liseuse."
            }

        size_str = _format_size(os.path.getsize(dest_path))
        print(f"[Anna's Archive DL] ePub valide téléchargé avec succès : {target_filename} ({size_str})")
        return {
            "status": "success",
            "filename": target_filename,
            "filepath": dest_path,
            "size": size_str,
            "size_bytes": os.path.getsize(dest_path),
            "source": "Anna's Archive (ePub validé)"
        }

    except Exception as e:
        print(f"[Anna's Archive DL] Erreur téléchargement : {e}")
        return {
            "status": "error",
            "message": f"Erreur lors du téléchargement depuis Anna's Archive : {e}"
        }


async def search_and_download_ebook(
    query: str,
    source_url: Optional[str] = None,
    confirmed_by_user: bool = False,
    send_to_reader: bool = True,
    ereader_email: Optional[str] = None
) -> Dict[str, Any]:
    """Recherche un ebook (EPUB / PDF) en priorité sur Anna's Archive, demande confirmation orale
    puis le télécharge et l'envoie automatiquement sur la liseuse Kindle de Pierre.
    """
    from services.browser_service import is_valid_epub, search_web

    # 1. Si source_url commence par "annas:<md5>", téléchargement direct depuis Anna's Archive
    if source_url and source_url.startswith("annas:"):
        md5 = source_url.split("annas:")[1].strip()
        clean_title = _sanitize_filename(re.sub(r'[^a-zA-Z0-9à-ÿ\s\-]', '', query)).replace(" ", "_")
        target_filename = f"{clean_title}.epub"
        dl_res = await download_from_annas_archive(md5, target_filename=target_filename)
        if dl_res.get("status") == "success" and send_to_reader:
            reader_res = await send_to_ereader(dl_res["filepath"], ereader_email=ereader_email)
            if reader_res.get("status") != "success":
                return {
                    "status": "error",
                    "action": "ebook_download_success_send_failed",
                    "filename": dl_res["filename"],
                    "filepath": dl_res.get("filepath"),
                    "download": dl_res,
                    "ereader_delivery": reader_res,
                    "message": f"L'ePub '{dl_res['filename']}' a bien été téléchargé mais le transfert vers la liseuse a échoué : {reader_res.get('message')}."
                }
            return {
                "status": "success",
                "action": "ebook_download_and_sent",
                "filename": dl_res["filename"],
                "filepath": dl_res.get("filepath"),
                "download": dl_res,
                "ereader_delivery": reader_res,
                "message": f"L'ePub authentique '{dl_res['filename']}' a été téléchargé depuis Anna's Archive et {reader_res.get('message', 'transféré sur votre liseuse')}."
            }
        return dl_res

    # 2. Recherche prioritaire sur Anna's Archive (https://annas-archive.gl/)
    annas_results = await search_annas_archive(query, lang="fr", ext="epub")
    if annas_results:
        best_match = annas_results[0]
        # Demande d'accord oral obligatoire avant tout téléchargement
        if not confirmed_by_user:
            return {
                "status": "requires_user_confirmation",
                "requires_oral_consent": True,
                "action": "download_ebook",
                "query": query,
                "book_title": best_match["title"],
                "source": "Anna's Archive",
                "format": "ePub",
                "source_url": f"annas:{best_match['md5']}",
                "instruction_to_jarvis": (
                    f"Pierre a demandé l'ebook '{query}'. "
                    f"Tu as localisé l'ePub complet et authentique '{best_match['title']}' sur Anna's Archive. "
                    f"Demande-lui explicitement son accord oral avec ta voix Aoede : "
                    f"'J'ai trouvé l'ePub authentique de {best_match['title']} sur Anna's Archive. M'autorisez-vous à le télécharger et à l'envoyer sur votre liseuse ?'. "
                    f"Dès sa confirmation orale affirmative, réinvoque search_and_download_ebook avec confirmed_by_user=True et source_url='annas:{best_match['md5']}'."
                )
            }
        else:
            clean_title = _sanitize_filename(re.sub(r'[^a-zA-Z0-9à-ÿ\s\-]', '', query)).replace(" ", "_")
            dl_res = await download_from_annas_archive(best_match["md5"], target_filename=f"{clean_title}.epub")
            if dl_res.get("status") == "success" and send_to_reader:
                reader_res = await send_to_ereader(dl_res["filepath"], ereader_email=ereader_email)
                if reader_res.get("status") != "success":
                    return {
                        "status": "error",
                        "action": "ebook_download_success_send_failed",
                        "filename": dl_res["filename"],
                        "filepath": dl_res.get("filepath"),
                        "download": dl_res,
                        "ereader_delivery": reader_res,
                        "message": f"L'ePub '{dl_res['filename']}' a bien été téléchargé mais le transfert vers la liseuse a échoué : {reader_res.get('message')}."
                    }
                return {
                    "status": "success",
                    "action": "ebook_download_and_sent",
                    "filename": dl_res["filename"],
                    "filepath": dl_res.get("filepath"),
                    "download": dl_res,
                    "ereader_delivery": reader_res,
                    "message": f"L'ePub authentique '{dl_res['filename']}' a été téléchargé depuis Anna's Archive et {reader_res.get('message', 'transféré sur votre liseuse')}."
                }
            return dl_res

    # 3. Fallback recherche web classique
    ebook_url = source_url or ""
    if not ebook_url:
        search_res = await search_web(f"{query} ebook gratuit epub download")
        results = search_res.get("results", [])
        if results:
            ebook_url = results[0]["url"]
        else:
            return {
                "status": "error",
                "message": f"Aucun livre électronique trouvé pour '{query}' sur Anna's Archive ou sur le web."
            }

    ext = ".epub" if "epub" in query.lower() or "epub" in ebook_url.lower() else (".pdf" if "pdf" in query.lower() else ".epub")
    clean_title = _sanitize_filename(re.sub(r'[^a-zA-Z0-9à-ÿ\s\-]', '', query)).replace(" ", "_")
    target_filename = f"{clean_title}{ext}"

    dl_res = await download_file(
        url=ebook_url,
        filename=target_filename,
        confirmed_by_user=confirmed_by_user,
        subfolder="ebooks"
    )

    if dl_res.get("status") == "requires_user_confirmation":
        dl_res["instruction_to_jarvis"] = (
            f"Pierre a demandé l'ebook '{query}'. "
            f"Tu as trouvé une source au format {ext} sur {dl_res.get('domain', 'le web')}. "
            f"Demande-lui son accord oral avec ta voix Aoede : "
            f"'J'ai trouvé une édition de {query}. M'autorisez-vous à la télécharger et à l'envoyer sur votre liseuse ?'. "
            f"Dès sa confirmation, relance avec confirmed_by_user=True."
        )
        return dl_res

    if dl_res.get("status") == "success":
        # Validation stricte du format ePub pour éviter d'envoyer des pages HTML corrompues à Amazon
        if ext == ".epub" and not is_valid_epub(dl_res["filepath"]):
            try:
                os.remove(dl_res["filepath"])
            except Exception:
                pass
            return {
                "status": "error",
                "message": f"Le fichier téléchargé pour '{query}' n'est pas un ePub valide (page web ou redirection). Envoi vers la Kindle refusé."
            }

        if send_to_reader:
            reader_res = await send_to_ereader(dl_res["filepath"], ereader_email=ereader_email)
            return {
                "status": "success",
                "action": "ebook_download_and_sent",
                "filename": dl_res["filename"],
                "download": dl_res,
                "ereader_delivery": reader_res,
                "message": f"L'ebook '{dl_res['filename']}' a été téléchargé et {reader_res.get('message', 'transféré sur votre liseuse')}."
            }

    return dl_res


def list_downloaded_files(subfolder: str = "") -> List[Dict[str, Any]]:
    """Liste tous les fichiers présents dans les dossiers de téléchargements de J.A.R.V.I.S."""
    target_dir = EBOOKS_DIR if "ebook" in subfolder.lower() else DOWNLOADS_DIR
    files = []
    if os.path.exists(target_dir):
        for fname in os.listdir(target_dir):
            fpath = os.path.join(target_dir, fname)
            if os.path.isfile(fpath):
                st = os.stat(fpath)
                files.append({
                    "name": fname,
                    "path": fpath,
                    "size_bytes": st.st_size,
                    "size": _format_size(st.st_size),
                    "created_at": st.st_ctime
                })
    files.sort(key=lambda x: x["created_at"], reverse=True)
    return files
