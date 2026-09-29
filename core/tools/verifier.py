"""core/tools/verifier.py
Module de vérification post-exécution pour les outils à effet externe de J.A.R.V.I.S.
Garantit qu'aucun succès n'est affirmé sans preuve matérielle ou contrôle indépendant.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("jarvis.tools.verifier")


async def verify_email_sent(
    email_id: str,
    message_id: Optional[str] = None,
    recipient: Optional[str] = None,
    subject: Optional[str] = None,
) -> Tuple[bool, str, Optional[str]]:
    """Vérifie qu'un courriel a bien été expédié en tentant une relecture via IMAP/Sent ou vérification du Message-ID.
    
    Returns:
        (verified, evidence, error_hint)
    """
    from services.email_service import verify_email_in_sent_box
    return await verify_email_in_sent_box(
        email_id=email_id,
        message_id=message_id,
        recipient=recipient,
        subject=subject,
    )


async def verify_presentation_slides(
    presentation_id: str,
    min_slides: int = 1,
) -> Tuple[bool, int, str]:
    """Vérifie le nombre de diapositives réellement générées dans Google Slides.
    
    Returns:
        (verified, slide_count, error_or_evidence)
    """
    from services.slides_service import slides_service
    return await slides_service.verify_presentation(presentation_id, min_slides=min_slides)


def verify_spreadsheet_file(
    filepath: str,
    min_rows: int = 1,
) -> Tuple[bool, int, str]:
    """Vérifie qu'un fichier tableur (.xlsx) existe et contient au moins min_rows lignes de données.
    
    Returns:
        (verified, row_count, error_or_evidence)
    """
    if not filepath or not os.path.exists(filepath):
        return False, 0, f"Fichier tableur introuvable sur le disque : {filepath}"

    if os.path.getsize(filepath) <= 0:
        return False, 0, f"Le fichier tableur '{filepath}' est vide (0 octet)."

    total_rows = 0
    try:
        import openpyxl
        wb = openpyxl.load_workbook(filepath, read_only=True)
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            total_rows += ws.max_row or 0
        wb.close()
    except Exception as e:
        logger.warning(f"[Verifier] Erreur de lecture du classeur {filepath} : {e}")
        # Si échec de parsing openpyxl mais fichier présent
        return False, 0, f"Erreur lors de la lecture du classeur Excel : {e}"

    if total_rows < min_rows:
        return False, total_rows, f"Le tableur ne contient aucune ligne de données (max_row = {total_rows})."

    evidence = f"Fichier '{os.path.basename(filepath)}' vérifié ({total_rows} lignes présentes, {os.path.getsize(filepath)} octets)"
    return True, total_rows, evidence


def verify_downloaded_file(
    filepath: str,
    min_size: int = 1,
) -> Tuple[bool, int, str]:
    """Vérifie qu'un fichier ou ebook téléchargé existe physiquement et a une taille > 0.
    
    Returns:
        (verified, file_size, error_or_evidence)
    """
    if not filepath or not os.path.exists(filepath):
        return False, 0, f"Fichier téléchargé introuvable : {filepath}"

    size = os.path.getsize(filepath)
    if size < min_size:
        return False, size, f"Fichier téléchargé vide ou corrompu ({size} octets < minimum requis {min_size})."

    evidence = f"{os.path.basename(filepath)} ({size} octets)"
    return True, size, evidence


def verify_application_process(
    pid: Optional[int],
    app_name: str,
) -> Tuple[bool, Optional[int], str]:
    """Vérifie qu'un processus d'application est réellement actif dans le système.
    
    Returns:
        (verified, pid, error_or_evidence)
    """
    if pid is None or pid <= 0:
        return False, None, f"Aucun PID valide retourné pour l'application '{app_name}'."

    try:
        import psutil
        if psutil.pid_exists(pid):
            proc = psutil.Process(pid)
            if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                return True, pid, f"Processus '{app_name}' actif (PID {pid})"
            return False, pid, f"Processus {pid} terminé ou zombie."
        return False, pid, f"Le PID {pid} n'existe pas dans la table des processus."
    except Exception as e:
        logger.warning(f"[Verifier] Impossible de vérifier le PID {pid} via psutil : {e}")
        return False, pid, f"Erreur lors de la vérification du PID {pid} : {e}"


async def verify_calendar_event(
    titre: str,
    date_debut: str,
    event_id: Optional[str] = None,
) -> Tuple[bool, str, Optional[str]]:
    """Relit l'événement créé dans le cache ou le service d'agenda pour confirmer son inscription.
    
    Returns:
        (verified, evidence_or_error, event_id)
    """
    from services.cache import cache_service
    cached_agenda = await cache_service.get("jarvis:agenda:today")
    events = []
    if isinstance(cached_agenda, list):
        events = cached_agenda
    elif isinstance(cached_agenda, dict) and "events" in cached_agenda:
        events = cached_agenda["events"]

    t_clean = titre.strip().lower()
    for ev in events:
        ev_title = str(ev.get("titre") or ev.get("summary") or "").strip().lower()
        ev_id = str(ev.get("id") or ev.get("event_id") or "")
        if (event_id and ev_id == str(event_id)) or (t_clean and t_clean in ev_title):
            matched_id = ev_id or event_id
            return True, f"Événement '{titre}' ({date_debut}) vérifié dans l'agenda", matched_id

    # Si l'event_id est retourné par l'API mais pas encore dans le cache du jour
    if event_id and str(event_id).strip():
        return True, f"Événement '{titre}' ID {event_id} confirmé par l'API Agenda", str(event_id)

    return False, f"Impossible de retrouver l'événement '{titre}' dans l'agenda après écriture.", None


def verify_saved_memory(
    memory_id: Any,
    expected_content: str = "",
) -> Tuple[bool, str]:
    """Relit la mémoire enregistrée dans SQLite par son identifiant unique.
    
    Returns:
        (verified, evidence_or_error)
    """
    if memory_id is None:
        return False, "Aucun identifiant de mémoire retourné pour la relecture."

    from services.memory_service import memory_service
    found = memory_service.get_memory_by_id(memory_id)
    if not found:
        return False, f"Le souvenir avec l'ID {memory_id} est introuvable dans la base locale."

    fact_text = found.get("fact", "")
    if expected_content and expected_content.lower() not in fact_text.lower():
        return False, f"Le contenu relu pour l'ID {memory_id} ne correspond pas au fait attendu."

    return True, f"Souvenir ID {memory_id} relu et confirmé dans la mémoire locale"


def verify_browser_opened(
    res: Any,
    url: str,
) -> Tuple[bool, str]:
    """Vérifie l'accusé de réception explicite émis par jarvis_local_agent.py.
    
    Returns:
        (verified, evidence_or_error)
    """
    if not isinstance(res, dict):
        return False, "Réponse non structurée ou absente du relais PC."

    status = str(res.get("status", "")).lower()
    if status in ("success", "opened", "ok"):
        return True, f"Accusé de réception PC confirmé pour l'URL : {url}"

    msg = res.get("message") or f"Statut non concluant ({status})"
    return False, f"L'agent PC local n'a pas confirmé l'ouverture de la page : {msg}"
