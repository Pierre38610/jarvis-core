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

from config import BASE_DIR, STATIC_DIR
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

    # 2. Méthode E-mail (Send-to-Kindle ou envoi direct sur boîte mail)
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


async def search_and_download_ebook(
    query: str,
    source_url: Optional[str] = None,
    confirmed_by_user: bool = False,
    send_to_reader: bool = True,
    ereader_email: Optional[str] = None
) -> Dict[str, Any]:
    """Recherche un ebook (EPUB / PDF), demande confirmation puis le télécharge et l'envoie sur la liseuse."""
    from services.browser_service import search_web
    
    ebook_url = source_url or ""
    ebook_title = query

    if not ebook_url:
        search_res = await search_web(f"{query} ebook gratuit epub pdf download")
        results = search_res.get("results", [])
        if results:
            ebook_url = results[0]["url"]
            ebook_title = results[0]["title"]
        else:
            return {
                "status": "error",
                "message": f"Aucun lien de téléchargement direct trouvé pour '{query}'."
            }

    # Détection de l'extension
    ext = ".epub" if "epub" in query.lower() or "epub" in ebook_url.lower() else (".pdf" if "pdf" in query.lower() else ".epub")
    clean_title = _sanitize_filename(re.sub(r'[^a-zA-Z0-9à-ÿ\s\-]', '', query)).replace(" ", "_")
    target_filename = f"{clean_title}{ext}"

    # Téléchargement sécurisé
    dl_res = await download_file(
        url=ebook_url,
        filename=target_filename,
        confirmed_by_user=confirmed_by_user,
        subfolder="ebooks"
    )

    if dl_res.get("status") == "requires_user_confirmation":
        dl_res["instruction_to_jarvis"] = (
            f"Pierre a demandé à télécharger l'ebook '{query}'. "
            f"Tu as localisé l'ebook au format {ext} sur {dl_res.get('domain', 'le web')}. "
            f"Demande-lui explicitement son accord oral avec ta voix Aoede : "
            f"'J'ai trouvé l'ebook {query} prêt à être téléchargé. M'autorisez-vous à le télécharger et à l'envoyer sur votre liseuse ?'. "
            f"Dès sa confirmation, réinvoque search_and_download_ebook avec confirmed_by_user=True."
        )
        return dl_res

    if dl_res.get("status") == "success" and send_to_reader:
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
