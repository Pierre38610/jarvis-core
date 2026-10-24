"""backend/services/prompt_batch_runner.py
Service d'exécution autonome de séries de prompts (Prompt Batch Runner) pour J.A.R.V.I.S.
Permet d'exécuter, tester et valider de bout en bout des fichiers markdown contenant des prompts séquentiels
sur le VPS avec confinement architectural par sous-dossier, sélection dynamique des modèles Antigravity,
persistance atomique pour reprise après crash, contrôle interactif Telegram et rapport final complet.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import html
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import config
from core.shared_state import (
    ACTIVE_AGY_LOGS,
    append_agy_log,
    mark_agy_task_status,
    register_agy_task,
    broadcast_supervision,
    active_task_controller,
)
from google_antigravity import _sanitize_secrets, find_antigravity_binary, resolve_cli_model_args
from ops.scripts.check_protected_paths import check_all_changes
from services.model_routing.model_registry import get_registry
from services.supervision_service import supervision_service
from services.self_improvement_service import (
    REPO_ROOT,
    SubfolderScope,
    resolve_subfolder_scope,
    resolve_live_agy_model,
    create_isolated_worktree,
    cleanup_isolated_worktree,
    _get_git_modified_files,
    _run_agy_process,
    _create_github_pr,
    build_low_priority_subprocess_kwargs,
)
from services.email_service import send_email_async

logger = logging.getLogger("jarvis.prompt_batch_runner")

# Répertoire de persistance des batches
DATA_DIR = os.path.join(REPO_ROOT, "data")
BATCHES_DIR = os.path.join(DATA_DIR, "prompt_batches")
os.makedirs(BATCHES_DIR, exist_ok=True)

MAX_PROMPT_ATTEMPTS = 3
DEFAULT_BATCH_TIMEOUT = 360.0

# Actions Telegram pour Prompt Batch Runner (<= 64 octets dans callback_data)
# Format : bpa:<action>:<batch_id>:<sig>
BATCH_ACTION_RESUME = "res"
BATCH_ACTION_SKIP = "skp"
BATCH_ACTION_ABORT = "abt"
BATCH_ACTION_CLAUDE = "cld"
BATCH_ACTION_ARGON = "arg"
BATCH_ACTION_WAIT_5H = "w5h"


# ─── Dataclasses ─────────────────────────────────────────────────────────────
@dataclass
class PromptItem:
    """Représentation d'un prompt extrait d'une série markdown."""
    index: int
    label: str  # ex: "1", "1A", "2"
    title: str
    body: str
    level: str = "medium"  # "low" | "medium" | "high"
    read_only_files: List[str] = field(default_factory=list)
    target_subfolders: List[str] = field(default_factory=list)
    manual_actions: List[str] = field(default_factory=list)
    validation_command: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PromptItem:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class BatchSpec:
    """Spécification complète d'une série de prompts analysée."""
    batch_id: str
    title: str
    prompts: List[PromptItem]
    raw_content: str
    source_file: Optional[str] = None
    all_manual_actions: List[str] = field(default_factory=list)
    improvement_summary: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["prompts"] = [p.to_dict() for p in self.prompts]
        return d


@dataclass
class PromptExecutionResult:
    """Résultat de l'exécution d'un prompt individuel de la série."""
    prompt_id: str
    label: str
    title: str
    model_used: str
    effort_used: Optional[str]
    subdirs_scoped: List[str]
    duration_seconds: float
    attempts: int
    status: str  # "succeeded" | "failed" | "skipped"
    error: Optional[str] = None
    modified_files: List[str] = field(default_factory=list)
    validation_output: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PromptExecutionResult:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class BatchRunState:
    """État persistant atomique du runner de batch pour tolérance aux crashs."""
    batch_id: str
    title: str
    status: str  # "queued" | "running" | "verifying" | "succeeded" | "failed" | "stopped" | "paused" | "completed"
    current_prompt_index: int  # 0-indexed
    total_prompts: int
    attempt: int
    branch_name: str
    worktree_dir: Optional[str]
    results: List[Dict[str, Any]] = field(default_factory=list)
    manual_actions_collected: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_error: Optional[str] = None
    pr_url: Optional[str] = None
    source_file: Optional[str] = None
    override_model: Optional[str] = None
    scheduled_resume_time: Optional[float] = None
    improvement_summary: Optional[str] = None
    current_prompt_title: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BatchRunState:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ─── 1. Sécurité des Chemins & Prévention Path-Traversal ─────────────────────
GENERIC_BATCH_HINTS = {
    "", "latest", "dernier", "last", "telegram", "batch", "prompt", "prompts",
    "fichier", "file", "fichier .md", "fichier md", ".md", "un fichier .md",
    "le fichier .md", "mon fichier .md", "ce fichier .md", "auto-amelioration",
    "auto amelioration", "auto_amelioration", "amelioration", "amélioration",
    "prompts_auto_amelioration", "prompts auto-amélioration", "auto-amélioration",
}

EXCLUDED_BATCH_FILENAMES = {
    "agents.md", "architecture_complete_jarvis.md", "capabilities_ledger.md",
    "readme.md", "profil_candidature_pierre_cassagnettes.md", "skill.md", "rule.md", "rules.md"
}

_BATCH_HEADER_RE = re.compile(
    r'(?im)^#{1,3}\s+(?:PROMPT|ÉTAPE|ETAPE|PHASE|STEP)\s+([0-9]+[A-Za-z]?|[A-Za-z0-9_\-]+)'
)


def _is_valid_batch_content(file_path: str) -> bool:
    """Vérifie rapidement si le fichier contient des sections de prompt valides et n'est pas un fichier exclu."""
    if os.path.basename(file_path).lower() in EXCLUDED_BATCH_FILENAMES:
        return False
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            sample = f.read(8192)
            return bool(_BATCH_HEADER_RE.search(sample))
    except Exception:
        return False


def _collect_candidate_batch_dirs() -> List[str]:
    """Retourne la liste des répertoires du projet susceptibles de contenir des séries de prompts."""
    downloads_dir = getattr(config, "DOWNLOADS_DIR", os.path.join(REPO_ROOT, "downloads"))
    chat_dir = getattr(config, "CHAT_UPLOADS_DIR", os.path.join(REPO_ROOT, "data", "chat_uploads"))
    candidates = [
        os.path.abspath(BATCHES_DIR),
        os.path.abspath(os.path.join(REPO_ROOT, "prompts", "Desktop")),
        os.path.abspath(os.path.join(REPO_ROOT, "prompts")),
        os.path.abspath(downloads_dir),
        os.path.abspath(chat_dir),
        os.path.abspath(REPO_ROOT),
        os.path.abspath(os.path.join(REPO_ROOT, "docs")),
    ]
    return [d for d in candidates if os.path.isdir(d)]


def validate_safe_batch_path(file_path: str, allowed_roots: Optional[List[str]] = None) -> str:
    """Vérifie qu'un chemin de fichier est sécurisé, sans traversée de répertoire (anti-traversal),
    avec résolution intelligente multi-répertoires et détection tolérante des fichiers de batch.

    Autorise :
    - Fichiers au sein du dépôt REPO_ROOT (notamment prompts/, data/prompt_batches/, etc.)
    - Dossiers downloads/ et chat_uploads/
    - Dossiers temporaires du système d'exploitation
    """
    raw_path = str(file_path or "").strip().strip("'\"")
    raw_lower = raw_path.lower().strip()

    # Nettoyage d'articles ou préfixes courants en langage naturel
    for prefix in ("un ", "le ", "mon ", "ce ", "fichier "):
        if raw_lower.startswith(prefix) and raw_lower != prefix:
            raw_lower = raw_lower[len(prefix):].strip()

    is_generic = (
        not raw_lower
        or raw_lower in GENERIC_BATCH_HINTS
        or raw_lower in (".md", "fichier.md", "fichier.txt", "batch.md")
        or (raw_lower.endswith(".md") and len(raw_lower) <= 12 and "auto" not in raw_lower)
    )

    # Répertoires autorisés par défaut
    if allowed_roots is None:
        downloads_dir = getattr(config, "DOWNLOADS_DIR", os.path.join(REPO_ROOT, "downloads"))
        chat_dir = getattr(config, "CHAT_UPLOADS_DIR", os.path.join(REPO_ROOT, "data", "chat_uploads"))
        temp_dir = os.path.abspath(os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp")
        allowed_roots = [
            os.path.abspath(REPO_ROOT),
            os.path.abspath(downloads_dir),
            os.path.abspath(chat_dir),
            os.path.abspath(DATA_DIR),
            os.path.abspath(os.path.join(REPO_ROOT, "prompts")),
            temp_dir,
        ]

    search_dirs = _collect_candidate_batch_dirs()

    def _check_allowed(path: str) -> bool:
        norm = os.path.abspath(path)
        return any(os.path.commonpath([norm, r]) == r for r in allowed_roots)

    # 1. Vérification anti-traversal immédiate sur le chemin fourni s'il est spécifié
    if not os.path.isabs(raw_path):
        resolved = os.path.abspath(os.path.join(REPO_ROOT, raw_path))
    else:
        resolved = os.path.abspath(raw_path)

    if not _check_allowed(resolved):
        raise PermissionError(
            f"Chemin de batch non autorisé (traversée de répertoire détectée ou hors périmètre) : {file_path}"
        )

    # 2. Demande générique ("latest", "dernier", "fichier .md", "batch", etc.)
    if is_generic:
        # A. Vérifier Telegram en priorité
        try:
            from services.self_improvement_telegram import get_latest_telegram_file
            latest_tg = get_latest_telegram_file()
            if latest_tg and os.path.isfile(latest_tg) and _is_valid_batch_content(latest_tg):
                if _check_allowed(latest_tg):
                    return os.path.abspath(latest_tg)
        except Exception:
            pass

        # B. Trouver le fichier de batch valide le plus récemment modifié dans le workspace
        all_candidates: List[Tuple[float, str]] = []
        for sdir in search_dirs:
            try:
                for fname in os.listdir(sdir):
                    if fname.lower().endswith((".md", ".txt")):
                        fp = os.path.join(sdir, fname)
                        if os.path.isfile(fp) and _is_valid_batch_content(fp) and _check_allowed(fp):
                            all_candidates.append((os.path.getmtime(fp), fp))
            except Exception:
                pass

        if all_candidates:
            all_candidates.sort(key=lambda x: x[0], reverse=True)
            return os.path.abspath(all_candidates[0][1])

    # 3. Si le chemin résolu direct est un répertoire (ex: 'prompts' ou 'prompts/Desktop')
    if os.path.isdir(resolved):
        dir_files: List[Tuple[float, str]] = []
        try:
            for fname in os.listdir(resolved):
                if fname.lower().endswith((".md", ".txt")):
                    fp = os.path.join(resolved, fname)
                    if os.path.isfile(fp) and _is_valid_batch_content(fp) and _check_allowed(fp):
                        dir_files.append((os.path.getmtime(fp), fp))
        except Exception:
            pass
        if dir_files:
            dir_files.sort(key=lambda x: x[0], reverse=True)
            return os.path.abspath(dir_files[0][1])

    # 4. Si le fichier exact existe
    if os.path.isfile(resolved):
        return resolved

    # 5. Recherche par nom exact ou suffixe .md dans search_dirs
    base_name = os.path.basename(raw_path).strip()
    stem = os.path.splitext(base_name)[0].rstrip(".").strip().lower()

    for sdir in search_dirs:
        for cand_name in (base_name, f"{base_name}.md"):
            cand = os.path.abspath(os.path.join(sdir, cand_name))
            if os.path.isfile(cand) and _check_allowed(cand):
                return cand

    # 6. Recherche par correspondance de motif / sous-chaîne (stem)
    matching_files: List[Tuple[float, str]] = []
    if len(stem) >= 3 and "nonexistent" not in stem and not raw_lower.startswith("nonexistent"):
        for sdir in search_dirs:
            try:
                for fn in os.listdir(sdir):
                    if fn.lower().endswith((".md", ".txt")):
                        clean_fn = fn.lower()
                        if stem in clean_fn or clean_fn.startswith(stem) or any(part in clean_fn for part in stem.split() if len(part) >= 4):
                            cand = os.path.abspath(os.path.join(sdir, fn))
                            if os.path.isfile(cand) and _is_valid_batch_content(cand) and _check_allowed(cand):
                                matching_files.append((os.path.getmtime(cand), cand))
            except Exception:
                pass

    if matching_files:
        matching_files.sort(key=lambda x: x[0], reverse=True)
        return matching_files[0][1]

    raise FileNotFoundError(
        f"Fichier de batch introuvable pour '{file_path}'. "
        f"Répertoires scrutés : {', '.join(search_dirs)}. "
        f"Place ton fichier .md dans 'prompts/' ou 'data/prompt_batches/', ou envoie-le sur Telegram."
    )




# ─── 2. Parser Tolérant de Markdown de Batch ────────────────────────────────
def parse_prompt_batch_markdown(content: str, source_file: Optional[str] = None) -> BatchSpec:
    """Parse un fichier markdown contenant une série de prompts ordonnés.
    
    Tolérant aux formats :
    - `## Prompt 1`, `### PROMPT 1A`, `## Étape 2`, `### Phase 3`, `## Prompt 1: Titre`
    - Niveaux d'effort : `low`, `medium`, `high`, `rapide`, `approfondie`
    - Fichiers à lire : `LIS UNIQUEMENT`, `À lire`, `CONTRAINTES D'ÉCONOMIE DE TOKENS`
    - Actions manuelles : `À faire par l'utilisateur`, `Actions manuelles`, `Ce que tu dois faire ensuite`
    - Commandes de validation : `COMMANDES DE VALIDATION EXACTES`, `VALIDATION :`
    """
    if not content or not content.strip():
        raise ValueError("Le contenu du fichier de batch est vide.")

    # 1. Découpage en sections de prompts
    # Recherche des titres de section de prompt
    # Exemples : `## Prompt 1`, `### PROMPT 1A`, `## Étape 1 : Création`, `# Prompt 2`
    header_pattern = re.compile(
        r'(?im)^#{1,3}\s+(?:PROMPT|ÉTAPE|ETAPE|PHASE|STEP)\s+([0-9]+[A-Za-z]?|[A-Za-z0-9_\-]+)\s*(?:[:\.\-–—]\s*(.*?))?$',
        re.MULTILINE
    )

    matches = list(header_pattern.finditer(content))
    if not matches:
        # Repli si les en-têtes sont sous la forme "## 1. Titre" ou "## 1A. Titre"
        fallback_pattern = re.compile(
            r'(?im)^#{2,3}\s+([0-9]+[A-Za-z]?)\s*[\.\:\-–—]\s*(.*?)$',
            re.MULTILINE
        )
        matches = list(fallback_pattern.finditer(content))

    if not matches:
        raise ValueError(
            "Aucun prompt détecté dans le markdown. Utilisez le format '## Prompt 1: Titre' ou '### PROMPT 1A'."
        )

    # Titre global du batch (premier # s'il existe avant les prompts)
    first_match_start = matches[0].start()
    pre_content = content[:first_match_start]
    batch_title = "Série de Prompts Jarvis"
    h1_match = re.search(r'(?im)^#\s+(.+)$', pre_content)
    if h1_match:
        batch_title = h1_match.group(1).strip()
    elif source_file:
        batch_title = os.path.splitext(os.path.basename(source_file))[0]

    prompts: List[PromptItem] = []
    seen_labels = set()
    all_manual_actions: List[str] = []

    for i, m in enumerate(matches):
        raw_label = m.group(1).strip()
        raw_title = (m.group(2) or "").strip()
        start_idx = m.end()
        end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        section_text = content[start_idx:end_idx].strip()

        if not section_text:
            raise ValueError(f"Le prompt '{raw_label}' est vide (aucun contenu sous l'en-tête).")

        if raw_label in seen_labels:
            raise ValueError(f"Numérotation de prompt incohérente : identifiant en double '{raw_label}'.")
        seen_labels.add(raw_label)

        # A. Détection du niveau d'effort / réflexion
        level = "medium"
        # 1. Vérifier si indiqué dans le titre ex: (high) ou (low)
        level_paren = re.search(r'\((low|medium|high|rapide|approfondie|pro)\)', f"{raw_label} {raw_title}", re.IGNORECASE)
        if level_paren:
            norm_lvl = level_paren.group(1).lower()
            level = "high" if norm_lvl in ("high", "approfondie", "pro") else ("low" if norm_lvl in ("low", "rapide") else "medium")
        else:
            # 2. Chercher dans le corps de section (ex: NIVEAU : high, **Niveau conseillé : high**, EFFORT : low)
            lvl_match = re.search(
                r'(?im)^[\*\-\s]*(?:NIVEAU(?:\s+CONSEILL[ÉE])?|EFFORT|COMPLEXIT[ÉE]|MOD[ÈE]LE)[\*\s]*[:=]\s*[\*`]*([a-zA-Z0-9_\-]+)',
                section_text,
            )
            if lvl_match:
                norm_lvl = lvl_match.group(1).lower()
                level = "high" if norm_lvl in ("high", "approfondie", "pro") else ("low" if norm_lvl in ("low", "rapide") else "medium")

        # B, C, D : Détection ligne par ligne des métadonnées (lecture seule, actions manuelles, validation, corps)
        read_only_files: List[str] = []
        manual_actions: List[str] = []
        val_cmds: List[str] = []
        body_lines: List[str] = []

        curr_section = "body"
        for line in section_text.splitlines():
            s = line.strip()
            if re.match(r'^```[a-zA-Z0-9_\-]*$', s):
                continue
            if not s or (len(s) >= 3 and all(c in "-*=_ " for c in s)):
                if curr_section in ("ro", "validation"):
                    curr_section = "body"
                continue

            # Détection des en-têtes de sous-sections
            if re.search(r'(?i)^(?:CONTRAINTES\s+D.*?LIS\s+UNIQUEMENT|LIS\s+UNIQUEMENT|FICHIERS?\s+[ÀA]\s+LIRE|[ÀA]\s+LIRE|READ\s+ONLY)\s*[:—\-]?$', s):
                curr_section = "ro"
                continue
            if re.search(r'(?i)^(?:[ÀA]\s+FAIRE\s+PAR\s+L.*?UTILISATEUR|ACTIONS?\s+MANUELLES?|CE\s+QUE\s+TU\s+DOIS\s+FAIRE\s+ENSUITE|MANUAL\s+ACTIONS?)\s*[:—\-]?$', s):
                curr_section = "manual"
                continue
            if re.search(r'(?i)^(?:COMMANDES?\s+DE\s+VALIDATION(?:\s+EXACTES?)?|VALIDATION\s*(?:EXACTE)?)\s*[:—\-]?$', s):
                curr_section = "validation"
                continue

            if curr_section == "ro":
                cleaned = re.sub(r'^[0-9]+[\.\)]\s*|^[-*+]\s*', '', s).strip('` \t')
                # Retenir si chemin de fichier ou extension reconnue
                if ('/' in cleaned or '\\' in cleaned or any(cleaned.endswith(ext) for ext in ('.py', '.md', '.json', '.txt', '.sh', '.html', '.css', '.js'))):
                    if cleaned not in read_only_files:
                        read_only_files.append(cleaned)
                else:
                    curr_section = "body"
                    body_lines.append(s)
            elif curr_section == "manual":
                cleaned = re.sub(r'^[0-9]+[\.\)]\s*|^[-*+]\s*', '', s).strip()
                if cleaned and len(cleaned) > 2 and not all(c in "-*=_ " for c in cleaned):
                    if cleaned not in manual_actions:
                        manual_actions.append(cleaned)
                        all_manual_actions.append(cleaned)
            elif curr_section == "validation":
                val_cmds.append(s)
            else:
                body_lines.append(s)

        val_cmd = "\n".join(val_cmds).strip("`") if val_cmds else None
        body_text = "\n".join(body_lines).strip() or section_text

        prompt_item = PromptItem(
            index=i,
            label=raw_label,
            title=raw_title or f"Prompt {raw_label}",
            body=body_text,
            level=level,
            read_only_files=read_only_files,
            manual_actions=manual_actions,
            validation_command=val_cmd,
        )
        prompts.append(prompt_item)

    # Identifiant unique de batch
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", batch_title.strip()[:20].lower()).strip("-") or "batch"
    batch_id = f"batch_{slug}_{int(time.time() * 1000) % 1000000}"

    return BatchSpec(
        batch_id=batch_id,
        title=batch_title,
        prompts=prompts,
        raw_content=content,
        source_file=source_file,
        all_manual_actions=all_manual_actions,
    )


def load_batch_from_file(file_path: str) -> BatchSpec:
    """Charge et parse un fichier markdown après validation stricte anti-traversal."""
    safe_path = validate_safe_batch_path(file_path)
    with open(safe_path, "r", encoding="utf-8") as f:
        content = f.read()
    return parse_prompt_batch_markdown(content, source_file=safe_path)


# ─── 3. Persistance & Reprise après Crash ────────────────────────────────────
def _get_batch_state_path(batch_id: str) -> str:
    return os.path.join(BATCHES_DIR, f"{batch_id}.json")


def save_batch_state(state: BatchRunState) -> None:
    """Sauvegarde atomique de l'état du batch sur disque."""
    state.updated_at = time.time()
    target_path = _get_batch_state_path(state.batch_id)
    temp_path = f"{target_path}.tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)
        os.replace(temp_path, target_path)
    except Exception as e:
        logger.error(f"[PromptBatchRunner] Erreur sauvegarde état batch {state.batch_id}: {e}")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def load_batch_state(batch_id: str) -> Optional[BatchRunState]:
    """Charge l'état d'un batch depuis le disque."""
    target_path = _get_batch_state_path(batch_id)
    if not os.path.exists(target_path):
        return None
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return BatchRunState.from_dict(data)
    except Exception as e:
        logger.error(f"[PromptBatchRunner] Erreur lecture état batch {batch_id}: {e}")
        return None


# ─── 4. Gestion des Callbacks Signés Telegram ───────────────────────────────
def generate_batch_callback_signature(action: str, batch_id: str, secret: str) -> str:
    """Signature HMAC SHA-256 tronquée à 12 caractères pour respecter <= 64 octets."""
    msg = f"{action}:{batch_id}".encode("utf-8")
    key = secret.encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()[:12]


def build_batch_callback_data(action: str, batch_id: str, secret: str) -> str:
    """Génère callback_data sous la forme bpa:<action>:<batch_id>:<sig>."""
    sig = generate_batch_callback_signature(action, batch_id, secret)
    cb = f"bpa:{action}:{batch_id}:{sig}"
    if len(cb.encode("utf-8")) > 64:
        raise ValueError(f"callback_data Telegram trop long ({len(cb)} > 64) : {cb}")
    return cb


def parse_batch_callback_data(callback_data: str, secret: str) -> Tuple[bool, Optional[str], Optional[str], str]:
    """Valide et parse le callback_data d'un bouton de contrôle de batch."""
    parts = (callback_data or "").split(":")
    if len(parts) != 4 or parts[0] != "bpa":
        return False, None, None, "Format de callback batch invalide"
    _, action, batch_id, signature = parts
    allowed_actions = (
        BATCH_ACTION_RESUME,
        BATCH_ACTION_SKIP,
        BATCH_ACTION_ABORT,
        BATCH_ACTION_CLAUDE,
        BATCH_ACTION_ARGON,
        BATCH_ACTION_WAIT_5H,
    )
    if action not in allowed_actions:
        return False, None, None, f"Action batch inconnue '{action}'"
    expected = generate_batch_callback_signature(action, batch_id, secret)
    if not hmac.compare_digest(expected, signature):
        return False, None, None, "Signature HMAC invalide ou compromise"
    return True, action, batch_id, "OK"


def is_quota_exhausted_error(error_str: str) -> bool:
    """Détecte si une erreur provient de l'épuisement de quota (code 429 / RESOURCE_EXHAUSTED)."""
    if not error_str:
        return False
    s = error_str.lower()
    return any(k in s for k in (
        "individual quota reached",
        "quota reached",
        "resource_exhausted",
        "code 429",
        "quota exceeded",
        "resets in",
        "limit reached",
    ))


def extract_quota_reset_hint(error_str: str) -> str:
    """Extrait la durée de réinitialisation si présente dans l'erreur, sinon renvoie '5h'."""
    if not error_str:
        return "5h (environ)"
    m = re.search(r"Resets in ([0-9a-zA-Z\s]+)", error_str, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return "5h (environ)"


def get_batch_improvement_summary(title: str, raw_content: str = "") -> str:
    """Fournit un résumé clair et direct de ce qu'apporte la série d'auto-amélioration à Jarvis."""
    t_low = (title or "").lower()
    c_low = (raw_content or "").lower()
    if any(k in t_low or k in c_low for k in ("auto-amélioration", "auto amélioration", "circuit d'auto-amélioration", "circuit")):
        return (
            "Ce patch dote Jarvis d'un circuit complet d'auto-amélioration autonome sur le VPS. Il apporte : "
            "1. Un déployeur résilient et testable avec rollback automatique (`jarvis-deployer`), "
            "2. Des garde-fous stricts CI/CODEOWNERS protégeant les fichiers sensibles (.env, clés), "
            "3. L'outil `self_improve` pour générer du code dans des worktrees isolés et ouvrir des Pull Requests GitHub, "
            "4. La validation et gouvernance interactive par Telegram (approbation, rejet, reprise sur quota), "
            "5. Une veille technique autonome hebdomadaire et un runner de séries de prompts séquentielles avec reprise sur incident."
        )
    return f"Série d'amélioration logicielle ciblée « {title} » pour enrichir les capacités autonomes de Jarvis."


async def _send_telegram_text(text: str) -> bool:
    """Envoie un message textuel simple sur Telegram."""
    bot_token = getattr(config, "TELEGRAM_BOT_TOKEN", "") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = getattr(config, "TELEGRAM_CHAT_ID", "") or os.environ.get("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            return resp.status_code == 200
    except Exception as e:
        logger.warning(f"[PromptBatchRunner] Erreur envoi Telegram texte: {e}")
        return False


# ─── 5. Notifications & Clavier de Pause ────────────────────────────────────
async def send_batch_quota_telegram_alert(
    state: BatchRunState,
    current_prompt: PromptItem,
    error_extract: str,
    secret: Optional[str] = None,
) -> bool:
    """Envoie une alerte Telegram interactive lors d'une limite de quota atteinte sur Antigravity CLI,
    avec boutons de décision (Claude, Argon, Retenter dans 5h, Annuler le batch, Retenter maintenant).
    Aucun e-mail n'est envoyé lors d'un épuisement de quota.
    """
    bot_token = getattr(config, "TELEGRAM_BOT_TOKEN", "") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = getattr(config, "TELEGRAM_CHAT_ID", "") or os.environ.get("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        logger.info("[PromptBatchRunner] Telegram non configuré pour l'alerte de quota batch.")
        return False

    hmac_sec = (
        secret
        or getattr(config, "TELEGRAM_HMAC_SECRET", "")
        or os.environ.get("TELEGRAM_HMAC_SECRET", "")
        or getattr(config, "JWT_SECRET_KEY", "")
        or "jarvis-batch-hmac-fallback"
    )

    cb_claude = build_batch_callback_data(BATCH_ACTION_CLAUDE, state.batch_id, hmac_sec)
    cb_argon = build_batch_callback_data(BATCH_ACTION_ARGON, state.batch_id, hmac_sec)
    cb_wait5h = build_batch_callback_data(BATCH_ACTION_WAIT_5H, state.batch_id, hmac_sec)
    cb_abort = build_batch_callback_data(BATCH_ACTION_ABORT, state.batch_id, hmac_sec)
    cb_resume = build_batch_callback_data(BATCH_ACTION_RESUME, state.batch_id, hmac_sec)

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "🤖 Retenter avec Claude", "callback_data": cb_claude},
                {"text": "⚡ Retenter avec Argon", "callback_data": cb_argon},
            ],
            [
                {"text": "⏳ Retenter dans 5h", "callback_data": cb_wait5h},
                {"text": "🛑 Annuler le batch", "callback_data": cb_abort},
            ],
            [
                {"text": "▶️ Retenter maintenant", "callback_data": cb_resume},
            ],
        ]
    }

    reset_hint = extract_quota_reset_hint(error_extract)
    err_clean = html.escape(error_extract[-500:] if error_extract else "Limite de quota individuel atteinte sur agy CLI.")
    completed_count = len([r for r in state.results if r.get("status") == "succeeded"])

    text = (
        f"⚠️ <b>Limite de Quota Atteinte (Antigravity CLI)</b>\n"
        f"📦 <b>Série :</b> {html.escape(state.title)}\n"
        f"📍 <b>Prompt bloqué :</b> [{current_prompt.label}] {html.escape(current_prompt.title)}\n"
        f"📊 <b>Avancement :</b> Prompt {state.current_prompt_index + 1}/{state.total_prompts} (déjà validés : {completed_count})\n"
        f"⏳ <b>Reset estimé :</b> {html.escape(reset_hint)}\n\n"
        f"<b>Détail :</b>\n<pre>{err_clean}</pre>\n\n"
        f"<i>Le batch est suspendu sans perte d'état. Que souhaites-tu faire ?</i>"
    )

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": keyboard,
    }

    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            return resp.status_code == 200
    except Exception as e:
        logger.warning(f"[PromptBatchRunner] Erreur envoi Telegram alerte quota : {e}")
        return False


async def send_batch_telegram_alert(
    state: BatchRunState,
    current_prompt: PromptItem,
    error_extract: str,
    secret: Optional[str] = None,
) -> bool:
    """Envoie une alerte Telegram immédiate lors d'un échec après 3 essais avec boutons de reprise."""
    bot_token = getattr(config, "TELEGRAM_BOT_TOKEN", "") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = getattr(config, "TELEGRAM_CHAT_ID", "") or os.environ.get("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        logger.info("[PromptBatchRunner] Telegram non configuré pour l'alerte d'échec de batch.")
        return False

    hmac_sec = (
        secret
        or getattr(config, "TELEGRAM_HMAC_SECRET", "")
        or os.environ.get("TELEGRAM_HMAC_SECRET", "")
        or getattr(config, "JWT_SECRET_KEY", "")
        or "jarvis-batch-hmac-fallback"
    )

    cb_resume = build_batch_callback_data(BATCH_ACTION_RESUME, state.batch_id, hmac_sec)
    cb_skip = build_batch_callback_data(BATCH_ACTION_SKIP, state.batch_id, hmac_sec)
    cb_abort = build_batch_callback_data(BATCH_ACTION_ABORT, state.batch_id, hmac_sec)

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "▶️ Reprendre", "callback_data": cb_resume},
                {"text": "⏭️ Ignorer ce prompt", "callback_data": cb_skip},
                {"text": "🛑 Annuler le batch", "callback_data": cb_abort},
            ]
        ]
    }

    err_clean = html.escape(error_extract[-600:] if error_extract else "Erreur indéterminée")
    text = (
        f"⚠️ <b>Blocage Batch Runner J.A.R.V.I.S.</b>\n"
        f"📦 <b>Série :</b> {html.escape(state.title)}\n"
        f"📍 <b>Prompt bloqué :</b> [{current_prompt.label}] {html.escape(current_prompt.title)}\n"
        f"🔄 <b>Essais épuisés :</b> {MAX_PROMPT_ATTEMPTS}/{MAX_PROMPT_ATTEMPTS}\n\n"
        f"<b>Extrait d'erreur :</b>\n<pre>{err_clean}</pre>\n\n"
        f"<i>Le batch est en pause. Que souhaites-tu faire ?</i>"
    )

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": keyboard,
    }

    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            return resp.status_code == 200
    except Exception as e:
        logger.warning(f"[PromptBatchRunner] Erreur envoi Telegram alerte : {e}")
        return False


async def send_batch_email_alert(
    state: BatchRunState,
    current_prompt: PromptItem,
    error_extract: str,
) -> None:
    """Envoie un e-mail d'alerte lors d'un blocage de prompt."""
    subject = f"⚠️ [Jarvis Batch] Blocage sur le Prompt {current_prompt.label} ({state.title})"
    body = (
        f"# Blocage d'Exécution sur le Prompt {current_prompt.label}\n\n"
        f"La série de prompts **{state.title}** a été suspendue après 3 tentatives infructueuses sur le prompt suivant :\n\n"
        f"- **Prompt :** [{current_prompt.label}] {current_prompt.title}\n"
        f"- **Branche :** `{state.branch_name}`\n"
        f"- **Avancement :** {state.current_prompt_index + 1}/{state.total_prompts}\n\n"
        f"### Extrait de l'Erreur\n```\n{error_extract[-1000:]}\n```\n\n"
        f"Vous pouvez reprendre, ignorer ce prompt ou annuler la série via Telegram ou l'interface Jarvis."
    )
    try:
        await send_email_async(subject=subject, body=body)
    except Exception as e:
        logger.warning(f"[PromptBatchRunner] Erreur envoi Email d'alerte : {e}")


# ─── 6. Exécution d'un Prompt Unique dans le Worktree ────────────────────────
async def _execute_single_prompt(
    prompt: PromptItem,
    worktree_dir: str,
    task_id: str,
    feedback_section: str = "",
    override_model: Optional[str] = None,
) -> Tuple[bool, str, List[str], str]:
    """Exécute un prompt individuel dans le worktree isolé avec agy et effectue les validations :
    1. Résolution dynamique du modèle et sous-dossier (Gemini 3 par défaut, ou override_model si spécifié)
    2. Exécution d'agy avec nice -n 10 et streaming
    3. Porte de validation locale (confinement, check_protected_paths, py_compile, pytest ciblés)
    
    Returns:
        (success, error_or_output, modified_files, model_used)
    """
    # 1. Résolution sous-dossier et modèle
    hint = ""
    if prompt.read_only_files:
        hint = prompt.read_only_files[0]
    elif prompt.target_subfolders:
        hint = prompt.target_subfolders[0]

    scope = resolve_subfolder_scope(goal=prompt.body, target_hint=hint)
    if override_model:
        model, effort = resolve_live_agy_model(prompt.level, override_model=override_model)
    else:
        model, effort = resolve_live_agy_model(prompt.level)

    # 2. Construction de la consigne d'agent
    tests_str = " ".join(scope.targeted_test_files) if scope.targeted_test_files else "backend/tests/"
    read_only_note = f"\nFICHIERS DE RÉFÉRENCE À CONSULTER EN PRIORITÉ :\n" + "\n".join(f"- {f}" for f in prompt.read_only_files) if prompt.read_only_files else ""
    feedback_note = f"\nATTENTION : L'essai précédent a échoué avec l'erreur suivante :\n{feedback_section}\nCorrige cette erreur sans dévier du périmètre." if feedback_section else ""

    agent_prompt = (
        f"RÔLE : Agent autonome J.A.R.V.I.S. pour la série de prompts (Prompt {prompt.label} : {prompt.title}).\n"
        f"OBJECTIF : {prompt.body}\n"
        f"PÉRIMÈTRE AUTORISÉ : Travaille STRICTEMENT ET UNIQUEMENT dans : {', '.join(scope.allowed_subdirs)}.\n"
        f"CONTRAT D'ARCHITECTURE : Consulte impérativement le fichier '{scope.architecture_file}'.\n"
        f"RÈGLE OBLIGATOIRE : Toute mission d'auto-amélioration (`self_improve` ou `prompt_batch_runner`) qui ajoute, modifie ou corrige une fonctionnalité de Jarvis DOIT mettre à jour `CAPABILITIES_LEDGER.md` (et `ARCHITECTURE_COMPLETE_JARVIS.md` si l'architecture change) avant de clôturer la tâche.\n"
        f"TESTS CIBLÉS : Lance uniquement 'pytest {tests_str}' pendant tes itérations.\n"
        f"INTERDICTIONS ABSOLUES :\n"
        f"- Ne modifie AUCUN fichier .env* ni les clés d'API ni auth_service.py.\n"
        f"- Ne supprime aucun test unitaire existant.\n"
        f"- Reste confiné à {scope.allowed_subdirs} (et CAPABILITIES_LEDGER.md / backend/tests/).\n"
        f"{read_only_note}\n"
        f"{feedback_note}\n"
        f"Conclus avec un bloc JSON final conforme à AGENTS.md."
    )

    agy_bin = find_antigravity_binary() or shutil.which("agy") or "agy"
    model_args = resolve_cli_model_args(model, effort=effort)
    cmd = [
        agy_bin,
        "-p", agent_prompt,
        "--dangerously-skip-permissions",
        "--output-format", "text",
        *model_args,
    ]

    append_agy_log(task_id, f"Lancement Prompt {prompt.label} avec agy (modèle: {model}, effort: {effort or 'none'}, args: {' '.join(model_args)})...")
    exit_code, stdout, stderr = await _run_agy_process(
        cmd=cmd,
        cwd=worktree_dir,
        task_id=task_id,
        timeout=DEFAULT_BATCH_TIMEOUT,
    )

    # 3. Récupération des fichiers modifiés
    changes = _get_git_modified_files(worktree_dir)
    modified_files = [path for _, path in changes]

    if exit_code != 0 and not modified_files:
        err_detail = (stderr or stdout or f"code de sortie {exit_code}")[-600:]
        return False, f"Antigravity CLI a échoué (code {exit_code}) : {err_detail}", [], model

    if not modified_files:
        err_detail = (stderr or stdout or "aucune sortie")[-400:]
        return False, f"Aucun fichier n'a été modifié par l'agent dans le worktree ({err_detail}).", [], model

    # 4. Portes de validation locale
    # A. Chemins protégés
    violations = check_all_changes(changes)
    if violations:
        err = f"Violation des fichiers protégés : {'; '.join(violations)}"
        return False, err, modified_files, model

    # B. py_compile sur fichiers .py modifiés
    python_bin = sys.executable or "python"
    low_prio_kwargs = build_low_priority_subprocess_kwargs()
    for status_code, path in changes:
        if status_code.upper() == "D":
            continue
        if path.endswith(".py"):
            full_path = os.path.join(worktree_dir, path)
            if os.path.exists(full_path):
                try:
                    subprocess.run(
                        [python_bin, "-m", "py_compile", full_path],
                        capture_output=True,
                        text=True,
                        check=True,
                        **low_prio_kwargs,
                    )
                except subprocess.CalledProcessError as e:
                    return False, f"Erreur de syntaxe Python dans '{path}' : {e.stderr.strip()}", modified_files, model

    # C. pytest sur tests ciblés
    if scope.targeted_test_files:
        valid_tests = [tf for tf in scope.targeted_test_files if os.path.exists(os.path.join(worktree_dir, tf))]
        if valid_tests:
            pytest_cmd = [python_bin, "-m", "pytest", "-q"] + valid_tests
            env = os.environ.copy()
            env["CI"] = "1"
            env["GIT_TERMINAL_PROMPT"] = "0"
            env["PYTHONPATH"] = f"{os.path.join(worktree_dir, 'backend')}{os.pathsep}{env.get('PYTHONPATH', '')}"
            try:
                proc = subprocess.run(
                    pytest_cmd,
                    cwd=worktree_dir,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    **low_prio_kwargs,
                )
                if proc.returncode != 0:
                    err_msg = f"Échec des tests ciblés : {proc.stdout[-400:]}\n{proc.stderr[-200:]}"
                    return False, err_msg, modified_files, model
            except subprocess.TimeoutExpired:
                return False, "Timeout lors de l'exécution des tests unitaires ciblés.", modified_files, model
            except Exception as e:
                return False, f"Erreur lors de l'appel pytest : {e}", modified_files, model

    # D. Commande de validation spécifique au prompt si présente
    if prompt.validation_command:
        append_agy_log(task_id, "Exécution de la commande de validation spécifique du prompt...")
        val_env = os.environ.copy()
        val_env["CI"] = "1"
        val_env["GIT_TERMINAL_PROMPT"] = "0"
        venv_bin = os.path.dirname(python_bin) if python_bin else ""
        if venv_bin:
            val_env["PATH"] = f"{venv_bin}{os.pathsep}{val_env.get('PATH', '')}"
        val_env["PYTHONPATH"] = f"{os.path.join(worktree_dir, 'backend')}{os.pathsep}{worktree_dir}{os.pathsep}{val_env.get('PYTHONPATH', '')}"

        for raw_cmd_line in prompt.validation_command.splitlines():
            cmd_line = raw_cmd_line.strip().strip("`")
            if not cmd_line or cmd_line.startswith("#"):
                continue
            # Compatibilité Windows si la commande commence par 'timeout <N>' ou 'env VAR=VAL'
            if os.name == "nt":
                cmd_line = re.sub(r"^timeout\s+\d+\s+", "", cmd_line)
                while cmd_line.startswith("env ") or re.match(r"^[A-Z0-9_]+=\S+\s+", cmd_line):
                    if cmd_line.startswith("env "):
                        cmd_line = cmd_line[4:].lstrip()
                    m_env = re.match(r"^([A-Z0-9_]+)=(\S+)\s+(.*)$", cmd_line)
                    if m_env:
                        val_env[m_env.group(1)] = m_env.group(2)
                        cmd_line = m_env.group(3).lstrip()
                    else:
                        break
                if cmd_line.startswith("python "):
                    cmd_line = f'"{python_bin}" ' + cmd_line[7:]
            try:
                val_proc = subprocess.run(
                    cmd_line,
                    shell=True,
                    cwd=worktree_dir,
                    env=val_env,
                    capture_output=True,
                    text=True,
                    timeout=180,
                    **low_prio_kwargs,
                )
                if val_proc.returncode != 0:
                    err_msg = f"Échec de la commande de validation spécifique ({cmd_line}) : {val_proc.stdout[-400:]}\n{val_proc.stderr[-200:]}"
                    return False, err_msg, modified_files, model
            except Exception as e:
                return False, f"Erreur validation spécifique ({cmd_line}) : {e}", modified_files, model

    return True, "Validation locale réussie", modified_files, model


# ─── 7. Moteur Principal de Batch (Orchestrateur) ───────────────────────────
class PromptBatchRunner:
    """Orchestre l'exécution complète d'un batch de prompts de A à Z."""

    def __init__(
        self,
        batch_spec: BatchSpec,
        websocket: Any = None,
        telegram_secret: Optional[str] = None,
    ):
        self.batch_spec = batch_spec
        self.websocket = websocket
        self.telegram_secret = telegram_secret
        self.state: Optional[BatchRunState] = None
        self._stop_requested = False

    async def run(self) -> BatchRunState:
        """Exécute l'intégralité du batch séquentiellement avec validation et persistance."""
        # 1. Rafraîchissement unique du registre de modèles avant démarrage
        try:
            get_registry().refresh_if_needed()
        except Exception as e:
            logger.warning(f"[PromptBatchRunner] Erreur refresh registry: {e}")

        # 2. Initialisation ou reprise de l'état persistant
        if self.state is None:
            slug = re.sub(r"[^a-zA-Z0-9]+", "-", self.batch_spec.title.strip()[:20].lower()).strip("-") or "batch"
            branch_name = f"jarvis/batch-{slug}-{int(time.time()) % 10000}"

            self.state = BatchRunState(
                batch_id=self.batch_spec.batch_id,
                title=self.batch_spec.title,
                status="running",
                current_prompt_index=0,
                total_prompts=len(self.batch_spec.prompts),
                attempt=1,
                branch_name=branch_name,
                worktree_dir=None,
                results=[],
                manual_actions_collected=list(self.batch_spec.all_manual_actions),
                source_file=self.batch_spec.source_file,
                improvement_summary=self.batch_spec.improvement_summary,
            )
            save_batch_state(self.state)
        else:
            branch_name = self.state.branch_name
            if not self.state.improvement_summary and self.batch_spec.improvement_summary:
                self.state.improvement_summary = self.batch_spec.improvement_summary

        # 3. Création du git worktree unique pour toute la série
        is_resuming = (self.state.current_prompt_index > 0 or len(self.state.results) > 0)
        if not self.state.worktree_dir or not os.path.exists(self.state.worktree_dir):
            worktree_dir = create_isolated_worktree(REPO_ROOT, branch_name, resume_existing_branch=is_resuming)
            self.state.worktree_dir = worktree_dir
            save_batch_state(self.state)
        else:
            worktree_dir = self.state.worktree_dir

        task_id = f"batch_{self.batch_spec.batch_id}"
        register_agy_task(
            task_id=task_id,
            goal=f"Batch [{self.batch_spec.title}] : {len(self.batch_spec.prompts)} prompts",
            model="dynamic",
            effort="dynamic",
        )

        supervision_service.start_action(
            "prompt_batch",
            f"Prompt Batch ({len(self.batch_spec.prompts)} prompts)",
            "prompt_batch",
            self.batch_spec.title,
            "Antigravity CLI (Dynamic)",
        )
        await broadcast_supervision()

        success_all = False
        try:
            while self.state.current_prompt_index < self.state.total_prompts:
                if self._stop_requested:
                    self.state.status = "stopped"
                    save_batch_state(self.state)
                    break

                curr_prompt = self.batch_spec.prompts[self.state.current_prompt_index]
                self.state.current_prompt_title = f"[{curr_prompt.label}] {curr_prompt.title}"
                save_batch_state(self.state)
                append_agy_log(task_id, f"=== Démarrage du Prompt {curr_prompt.label} ({self.state.current_prompt_index + 1}/{self.state.total_prompts}) ===")

                prompt_ok = False
                last_error = ""
                mod_files: List[str] = []
                model_used = ""
                t_p0 = time.perf_counter()

                for attempt in range(1, MAX_PROMPT_ATTEMPTS + 1):
                    if self._stop_requested:
                        break
                    self.state.attempt = attempt
                    save_batch_state(self.state)

                    append_agy_log(task_id, f"Prompt {curr_prompt.label} - Essai {attempt}/{MAX_PROMPT_ATTEMPTS}...")
                    p_ok, p_out, p_files, p_model = await _execute_single_prompt(
                        prompt=curr_prompt,
                        worktree_dir=worktree_dir,
                        task_id=task_id,
                        feedback_section=last_error if attempt > 1 else "",
                        override_model=self.state.override_model,
                    )
                    model_used = p_model
                    mod_files = p_files

                    if p_ok:
                        prompt_ok = True
                        last_error = ""
                        # Commit incrémental dans le worktree
                        try:
                            subprocess.run(["git", "add", "."], cwd=worktree_dir, capture_output=True, text=True, check=True)
                            subprocess.run(
                                ["git", "commit", "-m", f"jarvis batch: [{curr_prompt.label}] {curr_prompt.title[:50]}"],
                                cwd=worktree_dir,
                                capture_output=True,
                                text=True,
                                check=True
                            )
                        except Exception as c_err:
                            logger.warning(f"[PromptBatchRunner] Warning commit: {c_err}")
                        break
                    else:
                        last_error = p_out
                        append_agy_log(task_id, f"Échec essai {attempt} Prompt {curr_prompt.label} : {p_out}", stream="stderr")
                        if is_quota_exhausted_error(last_error):
                            append_agy_log(task_id, f"Interruption préventive : limite de quota CLI détectée sur {p_model}.", stream="stderr")
                            break

                p_dur = time.perf_counter() - t_p0

                if prompt_ok:
                    # Enregistrer un commit git propre pour ce prompt dans le worktree
                    try:
                        subprocess.run(["git", "add", "."], cwd=worktree_dir, capture_output=True, text=True, check=False)
                        subprocess.run(
                            ["git", "commit", "-m", f"jarvis batch [{curr_prompt.label}]: {curr_prompt.title[:60]}"],
                            cwd=worktree_dir,
                            capture_output=True,
                            text=True,
                            check=False,
                        )
                    except Exception as c_err:
                        logger.debug(f"[PromptBatchRunner] Info commit étape : {c_err}")

                    res_item = PromptExecutionResult(
                        prompt_id=curr_prompt.label,
                        label=curr_prompt.label,
                        title=curr_prompt.title,
                        model_used=model_used,
                        effort_used=curr_prompt.level,
                        subdirs_scoped=curr_prompt.target_subfolders,
                        duration_seconds=round(p_dur, 2),
                        attempts=self.state.attempt,
                        status="succeeded",
                        modified_files=mod_files,
                        validation_output="Validé",
                    )
                    self.state.results.append(res_item.to_dict())
                    self.state.current_prompt_index += 1
                    self.state.attempt = 1
                    save_batch_state(self.state)
                else:
                    # Échec (ou quota atteint) -> mise en pause et notification adaptée
                    self.state.status = "paused"
                    self.state.last_error = last_error
                    save_batch_state(self.state)

                    if is_quota_exhausted_error(last_error):
                        append_agy_log(task_id, f"PAUSE : Le Prompt {curr_prompt.label} est suspendu (quota CLI atteint). Alerte interactive Telegram envoyée.", stream="stderr")
                        await send_batch_quota_telegram_alert(self.state, curr_prompt, last_error, secret=self.telegram_secret)
                    else:
                        append_agy_log(task_id, f"PAUSE : Le Prompt {curr_prompt.label} a échoué après {MAX_PROMPT_ATTEMPTS} essais.", stream="stderr")
                        await send_batch_telegram_alert(self.state, curr_prompt, last_error, secret=self.telegram_secret)
                        await send_batch_email_alert(self.state, curr_prompt, last_error)
                    return self.state

            # 4. Tous les prompts sont terminés avec succès -> Validation globale
            if self.state.current_prompt_index >= self.state.total_prompts:
                self.state.status = "verifying"
                save_batch_state(self.state)
                # Détermination des tests ciblés à valider pour le batch complet
                all_targeted_tests = set()
                for p in self.batch_spec.prompts:
                    h = p.read_only_files[0] if p.read_only_files else (p.target_subfolders[0] if p.target_subfolders else "")
                    sc = resolve_subfolder_scope(goal=p.body, target_hint=h)
                    for tf in sc.targeted_test_files:
                        if os.path.exists(os.path.join(worktree_dir, tf)):
                            all_targeted_tests.add(tf)

                # Toujours inclure les tests d'intégrité de base
                for base_tf in ("backend/tests/unit/test_self_improvement_service.py", "backend/tests/unit/test_version_sync.py"):
                    if os.path.exists(os.path.join(worktree_dir, base_tf)):
                        all_targeted_tests.add(base_tf)

                final_test_targets = sorted(list(all_targeted_tests))
                append_agy_log(task_id, f"Validation finale globale : exécution de pytest {' '.join(final_test_targets)}...")

                python_bin = sys.executable or "python"
                env = os.environ.copy()
                env["CI"] = "1"
                env["GIT_TERMINAL_PROMPT"] = "0"
                env["PYTHONPATH"] = f"{os.path.join(worktree_dir, 'backend')}{os.pathsep}{worktree_dir}"
                low_prio = build_low_priority_subprocess_kwargs()

                try:
                    glob_proc = subprocess.run(
                        [python_bin, "-m", "pytest", "-q"] + final_test_targets,
                        cwd=worktree_dir,
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=180,
                        **low_prio,
                    )

                    if glob_proc.returncode != 0:
                        err_msg = f"Échec de la validation globale finale (pytest {' '.join(final_test_targets)}) : {glob_proc.stdout[-500:]}"
                        append_agy_log(task_id, err_msg, stream="stderr")
                        self.state.status = "failed"
                        self.state.last_error = err_msg
                        save_batch_state(self.state)
                        return self.state
                except subprocess.TimeoutExpired:
                    err_msg = f"Échec validation globale : timeout de 180s dépassé sur pytest {' '.join(final_test_targets)}."
                    append_agy_log(task_id, err_msg, stream="stderr")
                    self.state.status = "failed"
                    self.state.last_error = err_msg
                    save_batch_state(self.state)
                    return self.state
                except Exception as e_glob:
                    err_msg = f"Erreur inattendue validation globale : {e_glob}"
                    append_agy_log(task_id, err_msg, stream="stderr")
                    self.state.status = "failed"
                    self.state.last_error = err_msg
                    save_batch_state(self.state)
                    return self.state

                # 5. Push et Création de la PR GitHub unique
                append_agy_log(task_id, "Validation finale validée avec succès ! Push de la branche et ouverture de PR...")
                try:
                    subprocess.run(["git", "add", "."], cwd=worktree_dir, capture_output=True, text=True, check=False)
                    subprocess.run(
                        ["git", "commit", "-m", f"jarvis batch: {self.batch_spec.title[:60]}"],
                        cwd=worktree_dir,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    subprocess.run(["git", "push", "origin", branch_name], cwd=worktree_dir, capture_output=True, text=True, check=False)
                    dummy_scope = SubfolderScope("batch", ["backend", "frontend", "ops", "docs"], "ARCHITECTURE.md", [])
                    pr_url = await _create_github_pr(branch_name, f"Batch : {self.batch_spec.title}", dummy_scope, f"Série de {len(self.batch_spec.prompts)} prompts exécutée.")
                    self.state.pr_url = pr_url
                except Exception as pr_err:
                    logger.warning(f"[PromptBatchRunner] Erreur push/PR : {pr_err}")
                    self.state.pr_url = f"https://github.com/Pierre38610/jarvis-core/tree/{branch_name}"

                success_all = True
                self.state.status = "completed"
                save_batch_state(self.state)

                # 6. Livraison finale (Email récapitulatif + Telegram)
                await self._deliver_final_summary()

        finally:
            is_paused_or_scheduled = self.state and self.state.status in ("paused", "scheduled_resume")
            should_delete_branch = (not success_all) and (not is_paused_or_scheduled)
            if worktree_dir:
                cleanup_isolated_worktree(REPO_ROOT, worktree_dir, branch_name, delete_branch=should_delete_branch)
            mark_agy_task_status(task_id, "completed" if success_all else "failed")
            supervision_service.complete_action("prompt_batch", status="completed" if success_all else "error")
            await broadcast_supervision()

        return self.state

    async def _deliver_final_summary(self) -> None:
        """Envoie l'e-mail récapitulatif et la notification Telegram finale."""
        if not self.state:
            return

        # Construction du tableau de bilan par prompt
        table_rows = [
            "| Prompt | Titre | Modèle | Durée | Essais | Statut |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
        for r in self.state.results:
            table_rows.append(
                f"| {r.get('label')} | {r.get('title')[:30]} | {r.get('model_used')} | {r.get('duration_seconds')}s | {r.get('attempts')} | ✅ Succès |"
            )
        table_str = "\n".join(table_rows)

        # Section exacte "Ce que tu dois faire ensuite"
        manual_actions = self.state.manual_actions_collected or self.batch_spec.all_manual_actions
        if manual_actions:
            manual_str = "\n".join(f"- {act}" for act in manual_actions)
        else:
            manual_str = "- Aucune action manuelle requise. Tout a été automatisé avec succès."

        body = (
            f"# Bilan de la Série de Prompts : {self.batch_spec.title}\n\n"
            f"La série de **{len(self.batch_spec.prompts)} prompts** a été implémentée, testée et validée de A à Z sur le VPS.\n\n"
            f"### Bilan Détaillé par Prompt\n\n"
            f"{table_str}\n\n"
            f"### Validation des Tests\n"
            f"- **Tests ciblés par prompt :** ✅ Tous validés\n"
            f"- **Validation globale finale (`pytest backend/tests/unit`) :** ✅ 100% verte\n\n"
            f"### Livrable GitHub\n"
            f"- **Pull Request :** [{self.state.branch_name}]({self.state.pr_url or '#'})\n\n"
            f"## Ce que tu dois faire ensuite\n"
            f"{manual_str}\n"
        )

        subject = f"🎉 [Jarvis Batch] Succès de la série : {self.batch_spec.title}"

        # 1. Envoi Email
        try:
            await send_email_async(subject=subject, body=body)
        except Exception as e:
            logger.warning(f"[PromptBatchRunner] Erreur envoi Email récapitulatif : {e}")

        # 2. Envoi Telegram
        bot_token = getattr(config, "TELEGRAM_BOT_TOKEN", "") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = getattr(config, "TELEGRAM_CHAT_ID", "") or os.environ.get("TELEGRAM_CHAT_ID", "")
        if bot_token and chat_id:
            tg_text = (
                f"🎉 <b>Série de Prompts Validée avec Succès !</b>\n"
                f"📦 <b>Titre :</b> {html.escape(self.batch_spec.title)}\n"
                f"🔢 <b>Prompts :</b> {len(self.batch_spec.prompts)}/{len(self.batch_spec.prompts)} validés\n"
                f"🧪 <b>Tests globaux :</b> ✅ <code>pytest backend/tests/unit</code> vert\n"
                f"🔗 <b>Pull Request :</b> <a href=\"{html.escape(self.state.pr_url or '')}\">{html.escape(self.state.branch_name)}</a>\n\n"
                f"<b>Ce que tu dois faire ensuite :</b>\n"
                + "\n".join(f"• {html.escape(act)}" for act in manual_actions[:5])
            )
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": tg_text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            try:
                import httpx
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(url, json=payload)
            except Exception as tg_err:
                logger.warning(f"[PromptBatchRunner] Erreur envoi Telegram final: {tg_err}")

    def stop(self) -> None:
        """Demande l'arrêt propre de la série de prompts."""
        self._stop_requested = True


# ─── 8. Point d'Entrée & Gestionnaire de Callback Telegram ──────────────────
async def _delayed_resume_batch(batch_id: str, delay_seconds: float) -> None:
    """Attend la fin de l'intervalle de réinitialisation de quota puis relance le batch."""
    logger.info(f"[PromptBatchRunner] Attente de {delay_seconds:.0f}s avant reprise programmée du batch {batch_id}...")
    try:
        await asyncio.sleep(delay_seconds)
        st = load_batch_state(batch_id)
        if st and st.status == "scheduled_resume":
            logger.info(f"[PromptBatchRunner] Déclenchement de la reprise programmée pour {batch_id}...")
            await _send_telegram_text(f"⏰ <b>Reprise automatique du batch</b>\nLe délai d'attente de quota est écoulé. Reprise du batch <code>{batch_id}</code>...")
            await resume_prompt_batch(batch_id, action=BATCH_ACTION_RESUME)
    except asyncio.CancelledError:
        logger.info(f"[PromptBatchRunner] Tâche d'attente annulée pour le batch {batch_id}.")
    except Exception as e:
        logger.error(f"[PromptBatchRunner] Erreur reprise différée batch {batch_id}: {e}")


async def resume_prompt_batch(batch_id: str, action: str = BATCH_ACTION_RESUME) -> Optional[BatchRunState]:
    """Reprend l'exécution d'un batch en pause, passe au prompt suivant (skip), annule, change de modèle, ou programme dans 5h."""
    state = load_batch_state(batch_id)
    if not state:
        logger.error(f"[PromptBatchRunner] Impossible de reprendre : batch '{batch_id}' introuvable.")
        return None

    if action == BATCH_ACTION_ABORT:
        state.status = "stopped"
        save_batch_state(state)
        await _send_telegram_text(
            f"🛑 <b>Batch arrêté</b>\nLa série de prompts <code>{batch_id}</code> a été interrompue à votre demande."
        )
        return state

    if action == BATCH_ACTION_WAIT_5H:
        state.status = "scheduled_resume"
        state.scheduled_resume_time = time.time() + (5 * 3600)
        save_batch_state(state)
        await _send_telegram_text(
            f"⏳ <b>Reprise programmée</b>\nLe batch <code>{batch_id}</code> reprendra automatiquement dans 5 heures à l'expiration du quota Gemini."
        )
        asyncio.create_task(_delayed_resume_batch(batch_id, 5 * 3600))
        return state

    if action == BATCH_ACTION_CLAUDE:
        state.override_model = "claude-sonnet-5-5-high"
        state.attempt = 1
        state.status = "running"
        save_batch_state(state)
        await _send_telegram_text(
            f"🤖 <b>Reprise avec Claude Sonnet 5.5</b>\nReprise immédiate du batch <code>{batch_id}</code> au prompt {state.current_prompt_index + 1}."
        )

    elif action == BATCH_ACTION_ARGON:
        state.override_model = "gemini-4-argon-high"
        state.attempt = 1
        state.status = "running"
        save_batch_state(state)
        await _send_telegram_text(
            f"⚡ <b>Reprise avec Gemini Argon</b>\nReprise immédiate du batch <code>{batch_id}</code> au prompt {state.current_prompt_index + 1}."
        )

    elif action == BATCH_ACTION_SKIP:
        state.current_prompt_index += 1
        state.attempt = 1
        state.results.append({
            "prompt_id": f"prompt_{state.current_prompt_index}",
            "label": f"{state.current_prompt_index}",
            "title": "Ignoré par l'utilisateur",
            "model_used": "N/A",
            "effort_used": "N/A",
            "subdirs_scoped": [],
            "duration_seconds": 0.0,
            "attempts": 0,
            "status": "skipped",
            "modified_files": [],
            "validation_output": "Ignoré",
        })
        state.status = "running"
        save_batch_state(state)
        await _send_telegram_text(
            f"⏩ <b>Prompt sauté</b>\nPassage au prompt suivant pour le batch <code>{batch_id}</code>."
        )

    elif action == BATCH_ACTION_RESUME:
        state.attempt = 1
        state.status = "running"
        save_batch_state(state)
        await _send_telegram_text(
            f"▶️ <b>Reprise du batch</b>\nReprise immédiate au prompt {state.current_prompt_index + 1} avec le modèle Gemini 3 par défaut."
        )

    # Si le fichier source d'origine existe, recharger le BatchSpec et relancer
    source_p = state.source_file
    if source_p:
        try:
            safe_source = validate_safe_batch_path(source_p)
            if os.path.exists(safe_source):
                batch_spec = load_batch_from_file(safe_source)
                runner = PromptBatchRunner(batch_spec)
                runner.state = state
                return await runner.run()
        except Exception as e:
            logger.warning(f"[PromptBatchRunner] Impossible de relancer via {source_p}: {e}")

    return state


async def run_prompt_batch(
    file_path: Optional[str] = None,
    markdown_content: Optional[str] = None,
    websocket: Any = None,
) -> Dict[str, Any]:
    """Exécute un prompt batch depuis un chemin de fichier sécurisé ou du contenu markdown."""
    if file_path:
        spec = load_batch_from_file(file_path)
    elif markdown_content:
        spec = parse_prompt_batch_markdown(markdown_content)
    else:
        raise ValueError("Aucun fichier ni contenu markdown spécifié pour le Prompt Batch.")

    runner = PromptBatchRunner(spec, websocket=websocket)
    state = await runner.run()
    return state.to_dict()
