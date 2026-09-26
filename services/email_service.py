"""Service d'expédition de courriels et de rapports exécutifs pour J.A.R.V.I.S.
Permet d'envoyer des e-mails stylisés Stark Industries contenant du texte,
des rapports d'analyse, des captures d'écran et des pièces jointes à Pierre Cassagnettes.
"""

import os
import sys
import time
import json
import uuid
import smtplib
import asyncio
import mimetypes
from datetime import datetime
import imaplib
import email
from email.header import decode_header
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parsedate_to_datetime
from typing import List, Dict, Any, Optional

from config import (
    BASE_DIR,
    WORKSPACE_DIR,
    CHAT_UPLOADS_DIR,
    DEFAULT_RECIPIENT_EMAIL,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    SMTP_USE_TLS,
    EMAIL_SENDER_NAME,
    EMAIL_OUTBOX_DIR,
    SCREENSHOT_PATH,
    STATIC_DIR,
    IMAP_HOST,
    IMAP_PORT,
    IMAP_SSL
)

# Enregistrement des types MIME enrichis (ePub, Office, etc.)
mimetypes.init()
mimetypes.add_type("application/epub+zip", ".epub")
mimetypes.add_type("application/x-mobipocket-ebook", ".mobi")
mimetypes.add_type("application/vnd.amazon.ebook", ".azw3")
mimetypes.add_type("application/pdf", ".pdf")
mimetypes.add_type("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx")
mimetypes.add_type("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx")
mimetypes.add_type("application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx")
mimetypes.add_type("text/csv", ".csv")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("text/markdown", ".md")

DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
EBOOKS_DIR = os.path.join(DOWNLOADS_DIR, "ebooks")
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(EBOOKS_DIR, exist_ok=True)


def _format_markdown_to_html(text: str) -> str:
    """Convertit simplement du texte brut ou du markdown basique en HTML propre."""
    lines = text.strip().split("\n")
    html_parts = []
    in_list = False
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append("<br>")
            continue
            
        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                html_parts.append("<ul style='margin: 8px 0; padding-left: 24px; color: #cbd5e1;'>")
                in_list = True
            item_text = stripped[2:]
            # Remplace le gras **texte**
            import re
            item_text = re.sub(r'\*\*(.*?)\*\*', r'<strong style="color: #38bdf8;">\1</strong>', item_text)
            html_parts.append(f"<li style='margin-bottom: 4px;'>{item_text}</li>")
        elif stripped.startswith("### "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<h3 style='color: #38bdf8; margin: 16px 0 8px 0; font-size: 16px;'>{stripped[4:]}</h3>")
        elif stripped.startswith("## "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<h2 style='color: #00f0ff; margin: 20px 0 10px 0; font-size: 18px; border-bottom: 1px solid rgba(56,189,248,0.2); padding-bottom: 4px;'>{stripped[3:]}</h2>")
        elif stripped.startswith("# "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<h1 style='color: #00f0ff; margin: 24px 0 12px 0; font-size: 22px;'>{stripped[2:]}</h1>")
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            import re
            p_text = re.sub(r'\*\*(.*?)\*\*', r'<strong style="color: #38bdf8;">\1</strong>', stripped)
            html_parts.append(f"<p style='margin: 6px 0; line-height: 1.6; color: #e2e8f0;'>{p_text}</p>")
            
    if in_list:
        html_parts.append("</ul>")
        
    return "\n".join(html_parts)


def build_stark_html_report(
    subject: str,
    body: str,
    recipient: str,
    attachments_info: Optional[List[str]] = None,
    has_screenshot: bool = False
) -> str:
    """Génère un e-mail au design Stark Industries HUD haute fidélité."""
    now_str = datetime.now().strftime("%d/%m/%Y à %H:%M:%S")
    formatted_body = _format_markdown_to_html(body)
    
    attachments_html = ""
    if attachments_info:
        items = "".join([
            f"<li style='margin: 4px 0; color: #38bdf8;'><span style='color: #94a3b8;'>Fichier joint :</span> <strong>{att}</strong></li>"
            for att in attachments_info
        ])
        attachments_html = f"""
        <div style="margin-top: 24px; padding: 14px 18px; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 8px;">
          <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: #0284c7; font-weight: bold; margin-bottom: 6px;">Pièces Jointes & Fichiers Transmis</div>
          <ul style="margin: 0; padding-left: 20px; font-size: 13px;">
            {items}
          </ul>
        </div>
        """

    screenshot_banner = ""
    if has_screenshot:
        screenshot_banner = """
        <div style="margin-top: 14px; padding: 8px 12px; background: rgba(2, 132, 199, 0.15); border-left: 3px solid #38bdf8; border-radius: 4px; font-size: 12px; color: #7dd3fc;">
          <span style="font-weight: bold;">Capture visuelle incluse :</span> La capture d'écran demandée est jointe à ce courriel.
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <title>{subject}</title>
</head>
<body style="margin: 0; padding: 20px; background-color: #0b0f19; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #f8fafc;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width: 650px; margin: 0 auto; background: #111827; border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 14px; overflow: hidden; box-shadow: 0 10px 40px rgba(0, 0, 0, 0.7);">
    <!-- En-tête HUD Stark -->
    <tr>
      <td style="padding: 24px 30px; background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); border-bottom: 2px solid #0284c7;">
        <table width="100%" cellspacing="0" cellpadding="0">
          <tr>
            <td>
              <div style="font-size: 10px; font-weight: 800; letter-spacing: 2px; color: #38bdf8; text-transform: uppercase;">STARK INDUSTRIES • AI PROTOCOL 10</div>
              <div style="font-size: 24px; font-weight: 800; letter-spacing: 1px; color: #ffffff; margin-top: 4px;">J.A.R.V.I.S.</div>
            </td>
            <td align="right">
              <span style="display: inline-block; padding: 4px 10px; border-radius: 20px; background: rgba(56, 189, 248, 0.15); border: 1px solid #38bdf8; color: #38bdf8; font-size: 11px; font-weight: 700; letter-spacing: 1px;">TRANSMISSION</span>
            </td>
          </tr>
        </table>
      </td>
    </tr>

    <!-- Carte Métadonnées -->
    <tr>
      <td style="padding: 18px 30px; background: rgba(15, 23, 42, 0.6); border-bottom: 1px solid rgba(56, 189, 248, 0.15); font-size: 12px; color: #94a3b8;">
        <table width="100%" cellspacing="0" cellpadding="0">
          <tr>
            <td><strong style="color: #cbd5e1;">Destinataire :</strong> {recipient}</td>
            <td align="right"><strong style="color: #cbd5e1;">Date :</strong> {now_str}</td>
          </tr>
        </table>
      </td>
    </tr>

    <!-- Contenu du Rapport -->
    <tr>
      <td style="padding: 30px; font-size: 14px;">
        <div style="font-size: 18px; font-weight: 700; color: #00f0ff; margin-bottom: 16px; letter-spacing: 0.5px;">
          {subject}
        </div>

        {screenshot_banner}

        <div style="margin-top: 16px;">
          {formatted_body}
        </div>

        {attachments_html}
      </td>
    </tr>

    <!-- Pied de page Stark Industries -->
    <tr>
      <td style="padding: 20px 30px; background: #0f172a; border-top: 1px solid rgba(56, 189, 248, 0.2); font-size: 11px; color: #64748b; text-align: center;">
        <div style="letter-spacing: 1px; color: #94a3b8; font-weight: 600;">J.A.R.V.I.S. — SYSTÈME AUTONOME DE GESTION & D'ASSISTANCE</div>
        <div style="margin-top: 4px;">Ce message est généré automatiquement par votre agent Stark AI sur votre demande expresse.</div>
        <div style="margin-top: 8px; color: #0284c7;">© Stark Industries • All Rights Reserved</div>
      </td>
    </tr>
  </table>
</body>
</html>
"""
    return html


def capture_current_screen() -> Optional[str]:
    """Capture l'écran actuel sous Windows si Pillow est présent."""
    try:
        from PIL import ImageGrab
        screenshot = ImageGrab.grab()
        target_path = os.path.join(STATIC_DIR, "screen_capture.jpg")
        screenshot.save(target_path, "JPEG", quality=85)
        return target_path
    except Exception as e:
        print(f"[Email Service] Erreur lors de la capture d'écran: {e}")
        if os.path.exists(SCREENSHOT_PATH):
            return SCREENSHOT_PATH
        return None


def resolve_attachment_path(att_input: Any) -> Optional[str]:
    """Résout de façon intelligente et exhaustive un chemin ou un nom de pièce jointe.
    
    Prend en compte :
    - Chemins absolus ou relatifs existants
    - Noms simples ou partiels dans downloads/, downloads/ebooks/, static/, chat/, etc.
    - Mots-clés ('latest', 'dernier', 'dernier_ebook') pour récupérer le dernier fichier créé
    - URLs http/https (téléchargement temporaire automatique)
    - Correspondance insensible à la casse et par mots-clés
    - Relais PC Windows local si le serveur tourne sur VPS et que le PC est connecté
    """
    if not att_input:
        return None

    # Extraction si l'élément est un dictionnaire
    if isinstance(att_input, dict):
        att_input = att_input.get("path") or att_input.get("filepath") or att_input.get("filename") or att_input.get("file") or att_input.get("name")
        if not att_input:
            return None

    import re
    from urllib.parse import unquote

    att_clean = str(att_input).strip().strip("'\"")
    if att_clean.startswith("file://"):
        att_clean = att_clean[7:].lstrip("/")
        if sys.platform == "win32" and len(att_clean) > 2 and att_clean[1] == ":":
            pass
        else:
            att_clean = "/" + att_clean

    if not att_clean:
        return None

    # 1. Vérification si chemin d'accès direct valide
    if os.path.exists(att_clean) and os.path.isfile(att_clean):
        return os.path.abspath(att_clean)

    direct_base = os.path.join(BASE_DIR, att_clean)
    if os.path.exists(direct_base) and os.path.isfile(direct_base):
        return os.path.abspath(direct_base)

    # 2. Gestion des URLs distantes ou locales (/downloads/...)
    if att_clean.startswith("http://") or att_clean.startswith("https://"):
        if "/downloads/" in att_clean:
            remainder = att_clean.split("/downloads/", 1)[1].split("?")[0]
            candidate = os.path.join(DOWNLOADS_DIR, unquote(remainder))
            if os.path.exists(candidate) and os.path.isfile(candidate):
                return os.path.abspath(candidate)
        try:
            import httpx
            with httpx.Client(timeout=20.0, follow_redirects=True) as client:
                resp = client.get(att_clean)
                if resp.status_code == 200 and resp.content:
                    url_name = os.path.basename(att_clean.split("?")[0]) or "document_joint.bin"
                    save_path = os.path.join(DOWNLOADS_DIR, url_name)
                    with open(save_path, "wb") as f_dl:
                        f_dl.write(resp.content)
                    return os.path.abspath(save_path)
        except Exception as url_err:
            print(f"[Email Service] Erreur téléchargement pièce jointe URL {att_clean} : {url_err}")

    # 3. Normalisation des préfixes virtuels (/downloads/, /static/)
    norm_att = att_clean.replace("\\", "/")
    if norm_att.startswith("/downloads/") or norm_att.startswith("downloads/"):
        rel_part = norm_att.split("downloads/", 1)[1]
        c = os.path.join(DOWNLOADS_DIR, rel_part)
        if os.path.exists(c) and os.path.isfile(c):
            return os.path.abspath(c)

    if norm_att.startswith("/static/") or norm_att.startswith("static/"):
        rel_part = norm_att.split("static/", 1)[1]
        c = os.path.join(STATIC_DIR, rel_part)
        if os.path.exists(c) and os.path.isfile(c):
            return os.path.abspath(c)

    # 4. Dossiers standards de prospection
    search_dirs = [
        DOWNLOADS_DIR,
        EBOOKS_DIR,
        STATIC_DIR,
        CHAT_UPLOADS_DIR,
        WORKSPACE_DIR,
        EMAIL_OUTBOX_DIR,
        os.path.join(BASE_DIR, "artifacts"),
        os.path.expanduser("~/Downloads"),
        os.path.expanduser("~/Documents"),
        os.path.expanduser("~/Desktop"),
    ]

    base_name = os.path.basename(att_clean)
    for sdir in search_dirs:
        if not os.path.exists(sdir):
            continue
        for candidate_path in (os.path.join(sdir, att_clean), os.path.join(sdir, base_name)):
            if os.path.exists(candidate_path) and os.path.isfile(candidate_path):
                # Récupération de la casse réelle sur le système de fichiers
                try:
                    c_dir = os.path.dirname(candidate_path)
                    c_base_l = os.path.basename(candidate_path).lower()
                    for f in os.listdir(c_dir):
                        if f.lower() == c_base_l:
                            return os.path.abspath(os.path.join(c_dir, f))
                except Exception:
                    pass
                return os.path.abspath(candidate_path)

    # 5. Gestion des mots-clés temporels ('latest', 'dernier', 'dernier_ebook')
    att_lower = att_clean.lower()
    if att_lower in ("latest", "dernier", "recent", "dernier_fichier", "dernier_document", "dernier_telechargement", "last", "fichier", "document"):
        recent_candidates = []
        for root_dir in (DOWNLOADS_DIR, EBOOKS_DIR, CHAT_UPLOADS_DIR):
            if not os.path.exists(root_dir):
                continue
            for root, _, files in os.walk(root_dir):
                for f in files:
                    fp = os.path.join(root, f)
                    if os.path.isfile(fp) and not f.startswith("."):
                        try:
                            recent_candidates.append((fp, os.path.getmtime(fp)))
                        except Exception:
                            pass
        if recent_candidates:
            recent_candidates.sort(key=lambda x: x[1], reverse=True)
            return os.path.abspath(recent_candidates[0][0])

    if att_lower in ("dernier_ebook", "latest_ebook", "ebook", "livre"):
        recent_ebooks = []
        if os.path.exists(EBOOKS_DIR):
            for f in os.listdir(EBOOKS_DIR):
                fp = os.path.join(EBOOKS_DIR, f)
                if os.path.isfile(fp) and f.lower().endswith((".epub", ".pdf", ".mobi", ".azw3")):
                    try:
                        recent_ebooks.append((fp, os.path.getmtime(fp)))
                    except Exception:
                        pass
        if recent_ebooks:
            recent_ebooks.sort(key=lambda x: x[1], reverse=True)
            return os.path.abspath(recent_ebooks[0][0])

    # 6. Correspondance insensible à la casse
    target_clean = base_name.lower()
    for sdir in search_dirs:
        if not os.path.exists(sdir):
            continue
        try:
            for fname in os.listdir(sdir):
                fpath = os.path.join(sdir, fname)
                if os.path.isfile(fpath) and fname.lower() == target_clean:
                    return os.path.abspath(fpath)
        except Exception:
            pass

    # 7. Correspondance avec ajout d'extensions courantes si omise
    common_exts = (".pdf", ".epub", ".xlsx", ".docx", ".pptx", ".txt", ".csv", ".json", ".png", ".jpg", ".jpeg", ".html", ".zip")
    if not any(target_clean.endswith(ext) for ext in common_exts):
        for sdir in search_dirs:
            if not os.path.exists(sdir):
                continue
            try:
                for fname in os.listdir(sdir):
                    fpath = os.path.join(sdir, fname)
                    if os.path.isfile(fpath):
                        fn_l = fname.lower()
                        for ext in common_exts:
                            if fn_l == f"{target_clean}{ext}":
                                return os.path.abspath(fpath)
            except Exception:
                pass

    # 8. Correspondance sémantique / sous-chaîne (ex: 'Second Foundation' pour 'Second_Foundation_Isaac_Asimov.epub')
    target_tokens = [t for t in re.split(r'[\s_\-\.]+', target_clean) if len(t) > 2]
    matched_candidates = []
    for sdir in search_dirs:
        if not os.path.exists(sdir):
            continue
        try:
            for fname in os.listdir(sdir):
                fpath = os.path.join(sdir, fname)
                if os.path.isfile(fpath) and not fname.startswith("."):
                    fn_l = fname.lower()
                    if target_clean in fn_l:
                        try:
                            matched_candidates.append((fpath, os.path.getmtime(fpath)))
                        except Exception:
                            matched_candidates.append((fpath, 0))
                    elif target_tokens and all(token in fn_l for token in target_tokens):
                        try:
                            matched_candidates.append((fpath, os.path.getmtime(fpath)))
                        except Exception:
                            matched_candidates.append((fpath, 0))
        except Exception:
            pass

    if matched_candidates:
        matched_candidates.sort(key=lambda x: x[1], reverse=True)
        return os.path.abspath(matched_candidates[0][0])

    # 9. Repli agent local PC si connecté (extraction à distance depuis le PC de bureau)
    try:
        from services.local_agent_service import local_agent_service, is_pc_connected
        if is_pc_connected():
            fetch_res = local_agent_service.execute_command_sync(
                "fetch_file",
                timeout=8.0,
                filename=att_clean,
                filepath=att_clean
            )
            if isinstance(fetch_res, dict) and fetch_res.get("status") == "success" and fetch_res.get("file_b64"):
                import base64
                pc_dir = os.path.join(DOWNLOADS_DIR, "from_pc")
                os.makedirs(pc_dir, exist_ok=True)
                out_name = fetch_res.get("filename") or base_name
                out_path = os.path.join(pc_dir, out_name)
                with open(out_path, "wb") as f_out:
                    f_out.write(base64.b64decode(fetch_res["file_b64"]))
                print(f"[Email Service] Fichier '{out_name}' transféré avec succès depuis le PC Windows local vers le serveur.")
                return os.path.abspath(out_path)
    except Exception as pc_err:
        print(f"[Email Service] Tentative fetch_file PC ignorée : {pc_err}")

    return None


def send_email(
    subject: str,
    body: str,
    to_email: Optional[str] = None,
    attachments: Optional[Any] = None,
    include_screenshot: bool = False,
    is_html_report: bool = True
) -> Dict[str, Any]:
    """Prépare et expédie un courriel avec résolution intelligente des pièces jointes et archivage outbox.
    
    Args:
        subject: Sujet de l'e-mail
        body: Contenu textuel ou rapport markdown
        to_email: Adresse du destinataire (défaut: pierrecassagnettes@gmail.com)
        attachments: Chemin, nom de fichier ou liste de documents à joindre
        include_screenshot: Si True, prend/joint une capture visuelle
        is_html_report: Si True, formate en HTML Stark Industries
    """
    recipient = (to_email or DEFAULT_RECIPIENT_EMAIL).strip()
    if not recipient:
        recipient = "pierrecassagnettes@gmail.com"

    # 1. Normalisation résiliente de la liste des pièces jointes demandées
    requested_attachments: List[str] = []
    if attachments:
        if isinstance(attachments, str):
            att_str = attachments.strip()
            if att_str.startswith("[") and att_str.endswith("]"):
                try:
                    parsed = json.loads(att_str)
                    if isinstance(parsed, list):
                        requested_attachments = [str(x) for x in parsed if x]
                except Exception:
                    requested_attachments = [att_str]
            elif "," in att_str:
                requested_attachments = [x.strip() for x in att_str.split(",") if x.strip()]
            elif att_str:
                requested_attachments = [att_str]
        elif isinstance(attachments, (list, tuple, set)):
            for item in attachments:
                if isinstance(item, dict):
                    v = item.get("path") or item.get("filename") or item.get("name") or item.get("file")
                    if v:
                        requested_attachments.append(str(v).strip())
                elif item:
                    requested_attachments.append(str(item).strip())

    # 2. Résolution active des fichiers sur le système
    resolved_attachments: List[str] = []
    missing_attachments: List[str] = []

    for req_att in requested_attachments:
        found_path = resolve_attachment_path(req_att)
        if found_path and os.path.exists(found_path):
            if found_path not in resolved_attachments:
                resolved_attachments.append(found_path)
        else:
            missing_attachments.append(req_att)
            print(f"[Email Service] Fichier joint introuvable ignoré: {req_att}")

    # Prise en compte de la capture d'écran
    screenshot_file = None
    if include_screenshot:
        screenshot_file = capture_current_screen()
        if screenshot_file and os.path.exists(screenshot_file):
            if screenshot_file not in resolved_attachments:
                resolved_attachments.append(screenshot_file)

    # GARDE-FOU ESSENTIEL : Si l'utilisateur ou l'agent a demandé des pièces jointes mais qu'aucune n'a pu être résolue
    if requested_attachments and not resolved_attachments:
        missing_str = ", ".join(missing_attachments)
        err_msg = (
            f"Échec de l'envoi : la pièce jointe demandée ('{missing_str}') est introuvable sur le disque et dans les dossiers de téléchargements. "
            f"L'e-mail n'a pas été envoyé pour éviter de transmettre un courriel sans pièce jointe."
        )
        print(f"[Email Service] {err_msg}")
        return {
            "status": "attachment_not_found",
            "recipient": recipient,
            "subject": subject,
            "attachments_count": 0,
            "missing_attachments": missing_attachments,
            "message": err_msg
        }

    # Noms de fichiers pour l'affichage
    att_basenames = [os.path.basename(p) for p in resolved_attachments]

    # Construction du message EmailMessage MIME
    msg = EmailMessage()
    msg["Subject"] = subject
    sender_name = EMAIL_SENDER_NAME or "J.A.R.V.I.S."
    sender_addr = SMTP_USER if (SMTP_USER and "@" in SMTP_USER) else "jarvis@stark.ai"
    msg["From"] = f"{sender_name} <{sender_addr}>"
    msg["To"] = recipient
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()

    # Distinction selon le destinataire :
    # Si le mail est adressé à Pierre Cassagnettes (pierrecassagnettes@gmail.com), on conserve le formatage officiel Stark Industries.
    # Pour tout autre destinataire, aucun template/habillage ni message de base n'est imposé : l'agent rédige le mail de A à Z (y compris corps vide).
    is_pierre_dest = (recipient.lower() == "pierrecassagnettes@gmail.com")

    # Corps alternatif texte brut
    if is_pierre_dest:
        plain_text = f"{subject}\n\n{body}\n\n---\nTransmis par J.A.R.V.I.S. à destination de {recipient}"
    else:
        plain_text = body or ""
    msg.set_content(plain_text)

    # Corps HTML enrichi Stark Industries (uniquement pour Pierre)
    html_content = ""
    if is_pierre_dest and is_html_report:
        html_content = build_stark_html_report(
            subject=subject,
            body=body,
            recipient=recipient,
            attachments_info=att_basenames,
            has_screenshot=(screenshot_file is not None)
        )
        msg.add_alternative(html_content, subtype="html")

    # Attachement des fichiers
    for file_path in resolved_attachments:
        try:
            filename = os.path.basename(file_path)
            ctype, encoding = mimetypes.guess_type(file_path)
            if ctype is None or encoding is not None:
                ctype = "application/octet-stream"
            maintype, subtype = ctype.split("/", 1)

            with open(file_path, "rb") as f:
                file_bytes = f.read()

            msg.add_attachment(
                file_bytes,
                maintype=maintype,
                subtype=subtype,
                filename=filename
            )
        except Exception as att_err:
            print(f"[Email Service] Erreur lors de l'attachement de {file_path}: {att_err}")

    # Archivage local systématique dans outbox_emails/
    email_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_filename = f"{timestamp}_{email_id}"
    
    archive_html_path = os.path.join(EMAIL_OUTBOX_DIR, f"{base_filename}.html")
    archive_meta_path = os.path.join(EMAIL_OUTBOX_DIR, f"{base_filename}_meta.json")

    try:
        if html_content:
            with open(archive_html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
        else:
            with open(archive_html_path, "w", encoding="utf-8") as f:
                f.write(f"<pre>{plain_text}</pre>")
    except Exception as e:
        print(f"[Email Service] Erreur lors de la sauvegarde HTML outbox: {e}")

    # Tentative d'envoi SMTP réel
    smtp_configured = bool(SMTP_USER and SMTP_PASSWORD and SMTP_PASSWORD.strip())
    
    if not smtp_configured:
        meta_info = {
            "id": email_id,
            "timestamp": timestamp,
            "status": "archived_in_outbox",
            "recipient": recipient,
            "subject": subject,
            "attachments": att_basenames,
            "html_path": archive_html_path,
            "note": "SMTP_PASSWORD non renseigné dans .env. L'email est archivé localement."
        }
        with open(archive_meta_path, "w", encoding="utf-8") as f:
            json.dump(meta_info, f, indent=2, ensure_ascii=False)
            
        print(f"[Email Service] E-mail archivé avec succès dans '{EMAIL_OUTBOX_DIR}' (SMTP non configuré).")
        return {
            "status": "archived_in_outbox",
            "email_id": email_id,
            "recipient": recipient,
            "subject": subject,
            "attachments_count": len(resolved_attachments),
            "attachments": att_basenames,
            "html_preview": archive_html_path,
            "message": (
                f"Le courriel '{subject}' a été composé et archivé avec succès dans l'outbox locale pour {recipient}. "
                f"Pour que l'envoi réel vers Gmail parte immédiatement, ajoutez votre mot de passe d'application Google dans le fichier .env (SMTP_PASSWORD)."
            )
        }

    # Connexion et envoi SMTP réel
    try:
        print(f"[Email Service] Connexion SMTP vers {SMTP_HOST}:{SMTP_PORT}...")
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15)
        server.ehlo()
        if SMTP_USE_TLS:
            server.starttls()
            server.ehlo()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()

        meta_info = {
            "id": email_id,
            "timestamp": timestamp,
            "status": "sent",
            "recipient": recipient,
            "subject": subject,
            "attachments": att_basenames,
            "html_path": archive_html_path
        }
        with open(archive_meta_path, "w", encoding="utf-8") as f:
            json.dump(meta_info, f, indent=2, ensure_ascii=False)

        print(f"[Email Service] E-mail envoyé avec succès à {recipient} !")
        return {
            "status": "sent",
            "email_id": email_id,
            "recipient": recipient,
            "subject": subject,
            "attachments_count": len(resolved_attachments),
            "attachments": att_basenames,
            "html_preview": archive_html_path,
            "message": f"Courriel '{subject}' expédié avec succès à {recipient} avec {len(resolved_attachments)} pièce(s) jointe(s)."
        }

    except Exception as smtp_err:
        error_msg = str(smtp_err)
        print(f"[Email Service] Erreur lors de l'envoi SMTP: {error_msg}")
        meta_info = {
            "id": email_id,
            "timestamp": timestamp,
            "status": "failed",
            "error": error_msg,
            "recipient": recipient,
            "subject": subject,
            "attachments": att_basenames,
            "html_path": archive_html_path
        }
        with open(archive_meta_path, "w", encoding="utf-8") as f:
            json.dump(meta_info, f, indent=2, ensure_ascii=False)

        return {
            "status": "smtp_error",
            "email_id": email_id,
            "recipient": recipient,
            "subject": subject,
            "error": error_msg,
            "html_preview": archive_html_path,
            "message": (
                f"L'e-mail a été composé et archivé localement dans l'outbox, mais l'envoi SMTP a rencontré une erreur ({error_msg}). "
                f"Vérifiez vos identifiants Gmail dans le fichier .env."
            )
        }


async def send_email_async(
    subject: str,
    body: str,
    to_email: Optional[str] = None,
    attachments: Optional[List[str]] = None,
    include_screenshot: bool = False,
    is_html_report: bool = True
) -> Dict[str, Any]:
    """Version asynchrone non-bloquante de send_email pour FastAPI et Gemini Live."""
    return await asyncio.to_thread(
        send_email,
        subject=subject,
        body=body,
        to_email=to_email,
        attachments=attachments,
        include_screenshot=include_screenshot,
        is_html_report=is_html_report
    )


def list_outbox_emails() -> List[Dict[str, Any]]:
    """Liste tous les e-mails archivés dans l'outbox locale."""
    results = []
    if not os.path.exists(EMAIL_OUTBOX_DIR):
        return results

    for fname in os.listdir(EMAIL_OUTBOX_DIR):
        if fname.endswith("_meta.json"):
            try:
                full_path = os.path.join(EMAIL_OUTBOX_DIR, fname)
                with open(full_path, "r", encoding="utf-8") as f:
                    results.append(json.load(f))
            except Exception:
                pass
                
    results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return results


def _decode_mime_header(header_value: Optional[str]) -> str:
    """Décode proprement un en-tête MIME (Sujet, Expéditeur, etc.)."""
    if not header_value:
        return ""
    try:
        decoded_fragments = decode_header(header_value)
        parts = []
        for piece, charset in decoded_fragments:
            if isinstance(piece, bytes):
                encoding = charset or "utf-8"
                try:
                    parts.append(piece.decode(encoding, errors="replace"))
                except Exception:
                    parts.append(piece.decode("utf-8", errors="replace"))
            else:
                parts.append(str(piece))
        return "".join(parts).strip()
    except Exception:
        return str(header_value)


def _extract_email_body_and_attachments(msg: email.message.Message) -> Dict[str, Any]:
    """Extrait le corps texte/html et la liste des pièces jointes d'un message email."""
    text_content = ""
    html_content = ""
    attachments = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))

            # Si c'est une pièce jointe
            if "attachment" in content_disposition.lower() or part.get_filename():
                filename = part.get_filename()
                if filename:
                    filename = _decode_mime_header(filename)
                attachments.append(filename or "pièce_jointe")
                continue

            # Sinon contenu texte
            if content_type == "text/plain" and not text_content:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                if payload:
                    try:
                        text_content = payload.decode(charset, errors="replace")
                    except Exception:
                        text_content = payload.decode("utf-8", errors="replace")
            elif content_type == "text/html" and not html_content:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                if payload:
                    try:
                        html_content = payload.decode(charset, errors="replace")
                    except Exception:
                        html_content = payload.decode("utf-8", errors="replace")
    else:
        content_type = msg.get_content_type()
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or "utf-8"
        if payload:
            decoded = ""
            try:
                decoded = payload.decode(charset, errors="replace")
            except Exception:
                decoded = payload.decode("utf-8", errors="replace")
            if content_type == "text/plain":
                text_content = decoded
            elif content_type == "text/html":
                html_content = decoded

    # Nettoyage sommaire HTML si seul HTML est dispo
    clean_body = text_content.strip()
    if not clean_body and html_content:
        import re
        clean_body = re.sub(r'<[^>]+>', ' ', html_content)
        clean_body = re.sub(r'\s+', ' ', clean_body).strip()

    return {
        "body_text": clean_body,
        "attachments": attachments
    }


def read_received_emails(
    max_count: int = 5,
    query: Optional[str] = None,
    unread_only: bool = False,
    folder: str = "INBOX"
) -> Dict[str, Any]:
    """Interroge la boîte de réception Gmail via IMAP pour récupérer les derniers e-mails reçus."""
    user = SMTP_USER or DEFAULT_RECIPIENT_EMAIL
    pwd = (SMTP_PASSWORD or "").replace(" ", "").strip()

    if not user or not pwd:
        return {
            "status": "error",
            "message": "Identifiants Gmail (SMTP_USER / SMTP_PASSWORD) non configurés dans le fichier .env.",
            "emails": []
        }

    try:
        if IMAP_SSL:
            mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, timeout=3.0)
        else:
            mail = imaplib.IMAP4(IMAP_HOST, IMAP_PORT, timeout=3.0)

        mail.login(user, pwd)
        status, _ = mail.select(folder, readonly=True)
        if status != "OK":
            mail.logout()
            return {
                "status": "error",
                "message": f"Impossible d'accéder au dossier '{folder}'.",
                "emails": []
            }

        # Construction du critère de recherche
        search_criteria = []
        if unread_only:
            search_criteria.append("UNSEEN")
        else:
            search_criteria.append("ALL")

        if query:
            # Recherche par sujet ou expéditeur
            q_clean = query.strip()
            # Sous IMAP : (OR SUBJECT "terme" FROM "terme") ou texte général
            search_criteria = [f'(OR SUBJECT "{q_clean}" FROM "{q_clean}")']

        status, search_data = mail.search(None, *search_criteria)
        if status != "OK":
            mail.logout()
            return {
                "status": "error",
                "message": "Erreur lors de la recherche des e-mails.",
                "emails": []
            }

        msg_ids = search_data[0].split()
        total_found = len(msg_ids)
        if total_found == 0:
            mail.logout()
            return {
                "status": "ok",
                "count": 0,
                "message": f"Aucun e-mail trouvé avec les critères demandés ({'non lus uniquement' if unread_only else 'tous'}).",
                "emails": []
            }

        # Récupérer les 'max_count' plus récents (ils sont en fin de liste)
        selected_ids = msg_ids[-max_count:]
        selected_ids.reverse()  # Le plus récent d'abord

        email_list = []
        for msg_id in selected_ids:
            try:
                res, data = mail.fetch(msg_id, "(RFC822)")
                if res != "OK" or not data or not data[0]:
                    continue

                raw_email = data[0][1]
                msg = email.message_from_bytes(raw_email)

                raw_subject = msg.get("Subject", "(Sans sujet)")
                subject = _decode_mime_header(raw_subject)

                raw_from = msg.get("From", "Inconnu")
                sender = _decode_mime_header(raw_from)

                date_str = msg.get("Date", "")
                formatted_date = date_str
                try:
                    dt = parsedate_to_datetime(date_str)
                    formatted_date = dt.strftime("%d/%m/%Y à %H:%M")
                except Exception:
                    pass

                content_info = _extract_email_body_and_attachments(msg)
                body_snippet = content_info["body_text"][:350]
                if len(content_info["body_text"]) > 350:
                    body_snippet += "..."

                email_list.append({
                    "id": msg_id.decode("utf-8", errors="ignore"),
                    "subject": subject or "(Sans sujet)",
                    "from": sender,
                    "date": formatted_date,
                    "snippet": body_snippet,
                    "body": content_info["body_text"],
                    "attachments": content_info["attachments"],
                    "has_attachments": len(content_info["attachments"]) > 0
                })
            except Exception as item_err:
                print(f"[Email Service] Erreur lors de la lecture d'un message : {item_err}")
                continue

        mail.logout()

        return {
            "status": "ok",
            "account": user,
            "folder": folder,
            "total_matches": total_found,
            "count": len(email_list),
            "emails": email_list
        }

    except Exception as exc:
        err_msg = str(exc)
        print(f"[Email Service] Erreur IMAP : {err_msg}")
        return {
            "status": "error",
            "message": f"Erreur lors de la connexion IMAP à Gmail : {err_msg}",
            "emails": []
        }


async def read_received_emails_async(
    max_count: int = 5,
    query: Optional[str] = None,
    unread_only: bool = False,
    folder: str = "INBOX"
) -> Dict[str, Any]:
    """Version asynchrone non-bloquante de read_received_emails pour FastAPI et Gemini Live."""
    return await asyncio.to_thread(
        read_received_emails,
        max_count=max_count,
        query=query,
        unread_only=unread_only,
        folder=folder
    )


async def analyser_et_preparer_brouillon_agent(
    email_data: Dict[str, Any],
    instructions_supplementaires: str = ""
) -> Dict[str, Any]:
    """Analyse un e-mail reçu complexe ou une pièce jointe PDF et prépare un projet de réponse
    via l'agent Antigravity CLI 'email_drafting' (Système 2), sauvegardé dans outbox_emails/.
    """
    from services.agentic_dispatcher import agentic_dispatcher

    sujet = email_data.get("subject", "Sans sujet")
    expediteur = email_data.get("from", "Inconnu")
    corps = email_data.get("body") or email_data.get("snippet", "")
    attachments = email_data.get("attachments", [])

    # Extraction du texte des pièces jointes PDF si disponibles
    pdf_texts = []
    for att_name in attachments:
        if att_name.lower().endswith(".pdf"):
            # Recherche du fichier sur le disque
            candidate_paths = [
                os.path.join(DOWNLOADS_DIR, att_name),
                os.path.join(WORKSPACE_DIR, att_name),
                os.path.join(BASE_DIR, att_name)
            ]
            for c_path in candidate_paths:
                if os.path.exists(c_path):
                    try:
                        from pypdf import PdfReader
                        reader = PdfReader(c_path)
                        text = "".join([page.extract_text() or "" for page in reader.pages[:10]])
                        if text:
                            pdf_texts.append(f"--- Contenu PDF ({att_name}) ---\n{text[:2000]}")
                        break
                    except Exception as pdf_err:
                        logger.warning(f"[EmailService] Erreur lecture PDF {att_name}: {pdf_err}")

    pdf_extra = "\n\n".join(pdf_texts)

    goal = f"Triage exécutif et rédaction de réponse pour l'e-mail de '{expediteur}' sur '{sujet}'"
    context = {
        "expediteur": expediteur,
        "sujet": sujet,
        "date": email_data.get("date", ""),
        "corps": corps[:3000],
        "pieces_jointes": attachments,
        "contenu_pieces_jointes": pdf_extra,
        "instructions_supplementaires": instructions_supplementaires
    }

    return await agentic_dispatcher.launch_agentic_mission(
        mission_type="email_drafting",
        goal=goal,
        context=context
    )


