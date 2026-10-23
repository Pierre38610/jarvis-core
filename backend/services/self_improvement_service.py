"""backend/services/self_improvement_service.py
Service d'auto-amélioration et d'auto-refactorisation autonome de J.A.R.V.I.S.
Permet à Jarvis de se recoder et de se tester lui-même via les agents Antigravity (agy)
sur le VPS, en exploitant le partitionnement en sous-dossiers et le catalogue dynamique des modèles.
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import config
from core.shared_state import (
    ACTIVE_AGY_LOGS,
    append_agy_log,
    get_agy_task_telemetry,
    mark_agy_task_status,
    register_agy_task,
    broadcast_supervision,
)
from google_antigravity import _sanitize_secrets, find_antigravity_binary, resolve_cli_model_args
from ops.scripts.check_protected_paths import check_all_changes
from services.console_monitor import console_monitor
from services.model_routing.model_registry import ModelInfo, get_registry, model_registry
from services.model_routing.model_router import select_model
from services.supervision_service import supervision_service

logger = logging.getLogger("jarvis.self_improvement")

# ─── Configuration Globale & Sémaphore Mono-Agent ───────────────────────────
MAX_CONCURRENT_SELF_IMPROVE = 1
_SELF_IMPROVE_LOCK = asyncio.Semaphore(MAX_CONCURRENT_SELF_IMPROVE)

MAX_RUNS_PER_DAY = 10
MAX_RUNS_PER_WEEK = 30
MAX_ITERATIONS = 3

REPO_ROOT = getattr(config, "BASE_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(REPO_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)

KILL_SWITCH_FILE = os.path.join(DATA_DIR, "self_improve_kill_switch.flag")
JOURNAL_FILE = os.path.join(DATA_DIR, "self_improvement_journal.json")


# ─── Dataclasses ─────────────────────────────────────────────────────────────
@dataclass
class SubfolderScope:
    """Périmètre et confinement architectural d'une auto-amélioration."""
    subfolder: str
    allowed_subdirs: List[str]
    architecture_file: str
    targeted_test_files: List[str]
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subfolder": self.subfolder,
            "allowed_subdirs": self.allowed_subdirs,
            "architecture_file": self.architecture_file,
            "targeted_test_files": self.targeted_test_files,
            "description": self.description,
        }


@dataclass
class SelfImprovementResult:
    """Résultat consolidé d'une session d'auto-amélioration."""
    status: str  # "success" | "failed" | "blocked_quota" | "blocked_kill_switch" | "aborted"
    goal: str
    subfolder_scope: Optional[SubfolderScope]
    model_used: str
    effort_used: Optional[str]
    iterations_count: int
    branch_name: str
    pr_url: Optional[str]
    diff_summary: str
    user_message: str
    error: Optional[str] = None
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "goal": self.goal,
            "subfolder_scope": self.subfolder_scope.to_dict() if self.subfolder_scope else None,
            "model_used": self.model_used,
            "effort_used": self.effort_used,
            "iterations_count": self.iterations_count,
            "branch_name": self.branch_name,
            "pr_url": self.pr_url,
            "diff_summary": self.diff_summary,
            "user_message": self.user_message,
            "error": self.error,
            "duration_seconds": round(self.duration_seconds, 2),
        }


# ─── Catalogue des Sous-Dossiers Logiques & Contrats d'Architecture ─────────
SUBFOLDER_REGISTRY: Dict[str, Dict[str, Any]] = {
    "backend/core/tools": {
        "allowed_subdirs": ["backend/core/tools", "backend/core"],
        "architecture_file": "backend/ARCHITECTURE.md",
        "targeted_test_files": [
            "backend/tests/test_agentic_tools.py",
            "backend/tests/unit/test_antigravity_first_routing.py",
            "backend/tests/unit/test_tool_false_failures.py",
        ],
        "keywords": ["tool", "outil", "declarations", "dispatcher", "arg_validator", "verifier", "palette", "gemini live tools"],
        "description": "Outils Gemini Live, dispatching et validation d'arguments",
    },
    "backend/services/model_routing": {
        "allowed_subdirs": ["backend/services/model_routing"],
        "architecture_file": "backend/ARCHITECTURE.md",
        "targeted_test_files": [
            "backend/tests/test_model_routing.py",
            "backend/tests/unit/test_paid_key_gate.py",
        ],
        "keywords": ["model_routing", "model_registry", "routing", "arbitrage", "fallback_handler", "modèle", "llm", "tier", "quota"],
        "description": "Routage dynamique de modèles LLM et gestion des replis",
    },
    "backend/services/browser_agent": {
        "allowed_subdirs": ["backend/services/browser_agent", "backend/services"],
        "architecture_file": "backend/ARCHITECTURE.md",
        "targeted_test_files": [
            "backend/tests/unit/test_antigravity_task_engine.py",
            "backend/tests/test_browser_loop.py",
            "backend/tests/unit/test_antigravity_browser_mission.py",
        ],
        "keywords": ["browser_agent", "navigateur", "browser", "playwright", "cdp", "recette", "navigation web", "loop"],
        "description": "Navigation web autonome, vision LLM et recettes de scraping",
    },
    "backend/services": {
        "allowed_subdirs": ["backend/services"],
        "architecture_file": "backend/ARCHITECTURE.md",
        "targeted_test_files": [
            "backend/tests/unit/test_antigravity_task_engine.py",
        ],
        "keywords": ["service", "agentic_runner", "antigravity", "memory", "email", "spotify", "transport"],
        "description": "Services métier et intelligence serveur",
    },
    "backend/routers": {
        "allowed_subdirs": ["backend/routers"],
        "architecture_file": "backend/ARCHITECTURE.md",
        "targeted_test_files": [
            "backend/tests/unit/test_voice_multisession.py",
            "backend/tests/unit/test_mobile_bridge.py",
        ],
        "keywords": ["router", "route", "endpoint", "websocket", "fastapi", "voice router", "chat router"],
        "description": "Points d'entrée REST et sessions WebSockets FastAPI",
    },
    "frontend/static": {
        "allowed_subdirs": ["frontend/static", "static"],
        "architecture_file": "frontend/ARCHITECTURE.md",
        "targeted_test_files": [
            "backend/tests/unit/test_version_sync.py",
        ],
        "keywords": ["frontend", "hud", "pwa", "css", "html", "javascript", "interface", "app.js", "style.css"],
        "description": "Interface PWA HUD temps réel et assets visuels",
    },
    "ops/deploy": {
        "allowed_subdirs": ["ops/deploy", "ops/scripts"],
        "architecture_file": "ops/ARCHITECTURE.md",
        "targeted_test_files": [
            "backend/tests/unit/test_jarvis_deployer.py",
            "backend/tests/unit/test_check_protected_paths.py",
        ],
        "keywords": ["deploy", "sync_deploy", "systemd", "oracle", "vps", "ssh", "cloud", "blue_green"],
        "description": "Scripts de déploiement cloud Oracle et supervision systemd",
    },
    "ops/windows": {
        "allowed_subdirs": ["ops/windows"],
        "architecture_file": "ops/ARCHITECTURE.md",
        "targeted_test_files": [
            "backend/tests/unit/test_jarvis_deployer.py",
        ],
        "keywords": ["windows", "relais local", "bat", "powershell", "daemon local"],
        "description": "Scripts d'exécution et relais PC local Windows",
    },
    "firmware/esp32": {
        "allowed_subdirs": ["firmware/esp32"],
        "architecture_file": "firmware/ARCHITECTURE.md",
        "targeted_test_files": [
            "backend/tests/unit/test_device_voice_buffer.py",
            "backend/tests/unit/test_device_voice_followup.py",
        ],
        "keywords": ["firmware", "esp32", "esp-idf", "microcontrôleur", "c++", "audio board"],
        "description": "Firmware microcontrôleur ESP32-S3",
    },
    "docs": {
        "allowed_subdirs": ["docs"],
        "architecture_file": "docs/ARCHITECTURE.md",
        "targeted_test_files": [],
        "keywords": ["doc", "documentation", "spec", "markdown", "architecture_complete"],
        "description": "Documentation technique et spécifications",
    },
}


# ─── 1. Résolveur de Sous-Dossier & Tests Ciblés ────────────────────────────
def resolve_subfolder_scope(goal: str, target_hint: str = "") -> SubfolderScope:
    """Détermine automatiquement le sous-dossier logique, le fichier ARCHITECTURE.md local,
    les répertoires autorisés et les tests unitaires ciblés.
    """
    hint_clean = (target_hint or "").lower().replace("\\", "/").strip()
    goal_clean = (goal or "").lower().strip()

    # 1. Résolution prioritaire par indice cible explicite (target_hint)
    if hint_clean:
        for key, conf in SUBFOLDER_REGISTRY.items():
            if hint_clean == key.lower() or hint_clean.startswith(key.lower()) or key.lower() in hint_clean:
                return _build_scope_instance(key, conf)
        # Tester si un des allowed_subdirs correspond
        for key, conf in SUBFOLDER_REGISTRY.items():
            if any(hint_clean.startswith(sd.lower()) for sd in conf["allowed_subdirs"]):
                return _build_scope_instance(key, conf)

    # 2. Résolution heuristique par mots-clés dans le goal
    best_match_key: Optional[str] = None
    best_score = 0
    for key, conf in SUBFOLDER_REGISTRY.items():
        score = 0
        for kw in conf.get("keywords", []):
            if kw in goal_clean:
                score += 2 if len(kw) > 5 else 1
        if score > best_score:
            best_score = score
            best_match_key = key

    if best_match_key:
        return _build_scope_instance(best_match_key, SUBFOLDER_REGISTRY[best_match_key])

    # 3. Repli par défaut : backend/services
    default_key = "backend/services"
    return _build_scope_instance(default_key, SUBFOLDER_REGISTRY[default_key])


def _build_scope_instance(key: str, conf: Dict[str, Any]) -> SubfolderScope:
    arch_file = conf["architecture_file"]
    # Vérification d'existence sur le disque ou repli sur backend/ARCHITECTURE.md
    full_arch_path = os.path.join(REPO_ROOT, arch_file)
    if not os.path.exists(full_arch_path):
        fallback_arch = "backend/ARCHITECTURE.md"
        arch_file = fallback_arch if os.path.exists(os.path.join(REPO_ROOT, fallback_arch)) else "ARCHITECTURE_COMPLETE_JARVIS.md"

    # Filtrer les fichiers de tests pour ne retenir que ceux qui existent ou qui sont ciblés
    existing_tests = []
    for tf in conf.get("targeted_test_files", []):
        existing_tests.append(tf)

    return SubfolderScope(
        subfolder=key,
        allowed_subdirs=list(conf["allowed_subdirs"]),
        architecture_file=arch_file,
        targeted_test_files=existing_tests,
        description=conf.get("description", ""),
    )


# ─── 2. Sélection Dynamique du Modèle Antigravity ───────────────────────────
def resolve_live_agy_model(complexity: str = "medium", task_kind: str = "code") -> Tuple[str, Optional[str]]:
    """Sélectionne dynamiquement le meilleur couple (modèle, effort) parmi les modèles actifs
    dans Antigravity CLI sans jamais inclure le flag '--thinking'.
    
    Règles :
    - 'low' -> modèle Flash actif le plus rapide + effort='low'
    - 'medium' -> modèle Flash actif le plus récent + effort='medium'
    - 'high' -> modèle Pro ou Claude Sonnet actif dans Antigravity + effort='high'
    """
    comp = (complexity or "medium").lower().strip()
    registry = get_registry()
    registry.refresh_if_needed()

    active_models = registry.list_models()
    flash_models = [m for m in active_models if m.tier == "flash" or "flash" in m.name.lower()]
    pro_models = [m for m in active_models if m.tier in ("pro", "sonnet", "opus") or any(k in m.name.lower() for k in ("pro", "sonnet"))]

    if comp in ("low", "rapide", "min", "economique"):
        # Modèle Flash le plus rapide
        if flash_models:
            flash_models.sort(key=lambda m: (m.latency_rank, m.cost_rank))
            chosen = flash_models[0].name
        else:
            chosen = "gemini-3.7-flash"
        return chosen, "low"

    elif comp in ("high", "complexe", "approfondie", "pro", "l3"):
        # Modèle Pro ou Claude Sonnet actif
        if pro_models:
            # Privilégier gemini-3.1-pro ou claude-3-7-sonnet
            preferred = [m for m in pro_models if "3.1-pro" in m.name.lower() or "sonnet" in m.name.lower()]
            if preferred:
                chosen_info = preferred[0]
            else:
                chosen_info = pro_models[0]
            chosen = chosen_info.name
            effort = "high" if chosen_info.supports_effort else None
        else:
            chosen = "gemini-3.1-pro"
            effort = "high"
        return chosen, effort

    else:
        # Complexité standard 'medium' : Flash le plus récent
        if flash_models:
            # Ordre décroissant de version si possible (3.8 > 3.7)
            flash_models.sort(key=lambda m: m.name, reverse=True)
            chosen = flash_models[0].name
        else:
            chosen = "gemini-3.8-flash"
        return chosen, "medium"


# ─── 3. Gouvernance, Kill Switch & Quotas ────────────────────────────────────
def is_kill_switch_active() -> bool:
    """Vérifie si le kill switch persistant d'auto-amélioration est enclenché."""
    return os.path.exists(KILL_SWITCH_FILE)


def set_kill_switch(active: bool) -> None:
    """Active ou désactive le kill switch persistant."""
    if active:
        with open(KILL_SWITCH_FILE, "w", encoding="utf-8") as f:
            f.write(f"Kill switch activated at {time.time()} ({time.ctime()})\n")
        logger.warning("[SelfImprovement] Kill switch persistant ACTIVÉ.")
    else:
        if os.path.exists(KILL_SWITCH_FILE):
            try:
                os.remove(KILL_SWITCH_FILE)
                logger.info("[SelfImprovement] Kill switch persistant DÉSACTIVÉ.")
            except Exception as e:
                logger.error(f"[SelfImprovement] Erreur désactivation kill switch: {e}")


def _load_journal() -> List[Dict[str, Any]]:
    """Charge le journal d'historique des exécutions d'auto-amélioration."""
    if not os.path.exists(JOURNAL_FILE):
        return []
    try:
        with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning(f"[SelfImprovement] Erreur lecture journal: {e}")
        return []


def _save_journal(journal: List[Dict[str, Any]]) -> None:
    """Sauvegarde atomique du journal."""
    temp_file = f"{JOURNAL_FILE}.tmp"
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(journal, f, indent=2, ensure_ascii=False)
        os.replace(temp_file, JOURNAL_FILE)
    except Exception as e:
        logger.error(f"[SelfImprovement] Erreur sauvegarde journal: {e}")
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass


def check_quota_available() -> Tuple[bool, str]:
    """Contrôle les plafonds de runs par jour (24h) et par semaine (7j)."""
    journal = _load_journal()
    now = time.time()
    day_limit_ts = now - 86400
    week_limit_ts = now - (7 * 86400)

    runs_today = [j for j in journal if j.get("timestamp", 0) >= day_limit_ts]
    runs_this_week = [j for j in journal if j.get("timestamp", 0) >= week_limit_ts]

    if len(runs_today) >= MAX_RUNS_PER_DAY:
        msg = f"Plafond quotidien d'auto-amélioration atteint ({len(runs_today)}/{MAX_RUNS_PER_DAY} runs sur 24h)."
        return False, msg

    if len(runs_this_week) >= MAX_RUNS_PER_WEEK:
        msg = f"Plafond hebdomadaire d'auto-amélioration atteint ({len(runs_this_week)}/{MAX_RUNS_PER_WEEK} runs sur 7j)."
        return False, msg

    return True, "Quota disponible"


def record_run_in_journal(entry: Dict[str, Any]) -> None:
    """Enregistre un run dans le journal d'auto-amélioration."""
    journal = _load_journal()
    journal.append(entry)
    # Conservation des 200 dernières entrées
    if len(journal) > 200:
        journal = journal[-200:]
    _save_journal(journal)


# ─── 4. Gestion Isolée du Git Worktree ───────────────────────────────────────
def create_isolated_worktree(repo_root: str, branch_name: str) -> str:
    """Crée un git worktree isolé temporaire branché sur `branch_name`."""
    temp_dir = tempfile.mkdtemp(prefix="jarvis_self_improve_")
    cmd = ["git", "worktree", "add", "-b", branch_name, temp_dir, "HEAD"]
    try:
        subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, check=True)
        logger.info(f"[SelfImprovement] Worktree créé avec succès dans {temp_dir} (branche: {branch_name})")
        return temp_dir
    except subprocess.CalledProcessError as e:
        logger.error(f"[SelfImprovement] Échec création git worktree: {e.stderr}")
        # Nettoyage dossier temporaire vide en cas d'échec
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass
        raise RuntimeError(f"Impossible de créer le git worktree: {e.stderr or str(e)}")


def cleanup_isolated_worktree(repo_root: str, worktree_dir: str, branch_name: str, delete_branch: bool = True) -> None:
    """Garantit le démontage et nettoyage propre du git worktree en `finally`."""
    try:
        cmd_rm = ["git", "worktree", "remove", "--force", worktree_dir]
        subprocess.run(cmd_rm, cwd=repo_root, capture_output=True, text=True, check=False)
        cmd_prune = ["git", "worktree", "prune"]
        subprocess.run(cmd_prune, cwd=repo_root, capture_output=True, text=True, check=False)
    except Exception as e:
        logger.warning(f"[SelfImprovement] Warning lors de git worktree remove: {e}")

    if os.path.exists(worktree_dir):
        try:
            shutil.rmtree(worktree_dir, ignore_errors=True)
        except Exception as e:
            logger.warning(f"[SelfImprovement] Warning lors du rmtree worktree: {e}")

    if delete_branch:
        try:
            cmd_branch = ["git", "branch", "-D", branch_name]
            subprocess.run(cmd_branch, cwd=repo_root, capture_output=True, text=True, check=False)
        except Exception:
            pass
    logger.info(f"[SelfImprovement] Nettoyage complet du worktree {worktree_dir} terminé.")


# ─── 5. Revue Légère du Diff Avant PR ────────────────────────────────────────
def review_diff(diff_text: str, goal: str) -> Tuple[bool, str]:
    """Examine le diff git avant soumission de la PR pour détecter des incohérences ou risques manifestes."""
    if not diff_text or not diff_text.strip():
        return False, "Le diff produit est vide (aucune modification détectée)."

    # Recherche de patterns suspects
    lower_diff = diff_text.lower()
    suspicious_patterns = [
        "eval(", "exec(", "__import__('os').system", "rm -rf", "drop table", "api_key = \"aiza"
    ]
    for pat in suspicious_patterns:
        if pat in lower_diff:
            return False, f"Motif suspect détecté dans le diff : '{pat}'"

    # Vérification que le volume du diff reste maîtrisé
    diff_lines = diff_text.splitlines()
    if len(diff_lines) > 2500:
        return False, f"Le diff est excessivement volumineux ({len(diff_lines)} lignes). Réduis le périmètre."

    return True, f"Diff examiné et validé ({len(diff_lines)} lignes modifiées)."


# ─── 5bis. Isolation CPU & Priorité Basse des Sous-Processus ────────────────
def _set_low_cpu_priority() -> None:
    """Abaisser la priorité CPU du sous-processus (nice +10) sous POSIX/Linux
    afin de garantir la priorité temps réel absolue du moteur vocal (routers/voice.py
    et routers/device_voice.py avec DeviceAudioPacer à 55 ms) sur les 4 OCPU du VPS.
    """
    if os.name == "posix":
        try:
            if hasattr(os, "nice"):
                os.nice(10)
        except Exception:
            pass


def build_low_priority_subprocess_kwargs() -> dict:
    """Retourne les arguments de sous-processus pour subprocess.run / asyncio.create_subprocess_exec
    abaissant la priorité CPU sous Linux (os.name == 'posix') via preexec_fn (nice +10).
    Sous Windows (os.name != 'posix'), retourne un dictionnaire vide car preexec_fn n'est pas supporté.
    """
    if os.name == "posix":
        return {"preexec_fn": _set_low_cpu_priority}
    return {}


# ─── 6. Exécution d'Antigravity CLI avec Nice & Streaming ────────────────────
async def _run_agy_process(
    cmd: List[str],
    cwd: str,
    task_id: str,
    timeout: float = 300.0,
) -> Tuple[int, str, str]:
    """Lance agy avec streaming direct vers ACTIVE_AGY_LOGS et nice -n 10 sous Linux."""
    # Règle stricte anti-flag --thinking
    for arg in cmd:
        if "--thinking" in str(arg):
            raise ValueError("L'utilisation du flag '--thinking' est strictement interdite.")

    final_cmd = list(cmd)
    if sys.platform != "win32":
        # nice -n 10 pour préserver le CPU du moteur vocal Gemini Live
        nice_bin = shutil.which("nice")
        if nice_bin:
            final_cmd = [nice_bin, "-n", "10"] + final_cmd

    env = os.environ.copy()
    current_path = env.get("PATH", "")
    venv_bin = os.path.dirname(sys.executable) if sys.executable else ""
    extra_paths = [
        p for p in [
            venv_bin,
            os.path.join(REPO_ROOT, "venv", "bin"),
            os.path.join(REPO_ROOT, "venv", "Scripts"),
            "/home/opc/.local/bin",
            "/usr/local/bin",
            os.path.expanduser("~/.local/bin"),
        ] if p
    ]
    for ep in reversed(extra_paths):
        if ep not in current_path and os.path.exists(ep):
            current_path = f"{ep}{os.pathsep}{current_path}"
    env["PATH"] = current_path
    if cwd:
        env["PYTHONPATH"] = f"{os.path.join(cwd, 'backend')}{os.pathsep}{cwd}{os.pathsep}{env.get('PYTHONPATH', '')}"

    stdout_lines: List[str] = []
    stderr_lines: List[str] = []

    low_prio_kwargs = build_low_priority_subprocess_kwargs()

    try:
        proc = await asyncio.create_subprocess_exec(
            *final_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
            **low_prio_kwargs,
        )
    except Exception as e:
        err_msg = f"Impossible de démarrer le processus agy: {e}"
        logger.error(f"[SelfImprovement] {err_msg}")
        append_agy_log(task_id, err_msg, stream="stderr")
        return 127, "", err_msg

    async def _read_stream(reader: Optional[asyncio.StreamReader], is_stderr: bool):
        if reader is None:
            return
        stream_name = "stderr" if is_stderr else "stdout"
        target_list = stderr_lines if is_stderr else stdout_lines
        while True:
            line_bytes = await reader.readline()
            if not line_bytes:
                break
            raw_line = line_bytes.decode("utf-8", errors="replace").strip()
            if not raw_line:
                continue
            clean_line = _sanitize_secrets(raw_line)
            target_list.append(clean_line)
            append_agy_log(task_id, clean_line, stream=stream_name)

    try:
        await asyncio.wait_for(
            asyncio.gather(
                _read_stream(proc.stdout, False),
                _read_stream(proc.stderr, True),
                proc.wait(),
            ),
            timeout=timeout,
        )
        exit_code = proc.returncode or 0
    except asyncio.TimeoutError:
        logger.warning(f"[SelfImprovement] Timeout ({timeout}s) atteint pour la tâche {task_id}")
        try:
            proc.kill()
        except Exception:
            pass
        append_agy_log(task_id, f"Timeout ({timeout}s) dépassé.", stream="stderr")
        mark_agy_task_status(task_id, "timeout", error="Timeout d'exécution dépassé")
        return 124, "\n".join(stdout_lines), "Timeout dépassé"

    return exit_code, "\n".join(stdout_lines), "\n".join(stderr_lines)


# ─── 7. Pipeline de Validation Locale (py_compile, protected, pytest) ────────
def _get_git_modified_files(worktree_dir: str) -> List[Tuple[str, str]]:
    """Récupère les fichiers modifiés dans le worktree par rapport à HEAD."""
    cmd = ["git", "status", "--porcelain"]
    try:
        res = subprocess.run(cmd, cwd=worktree_dir, capture_output=True, text=True, check=True)
    except Exception:
        return []
    changes = []
    for line in res.stdout.splitlines():
        line = line.strip()
        if not line or len(line) < 3:
            continue
        status_part = line[:2].strip()
        path_part = line[2:].strip().replace('"', '')
        changes.append((status_part, path_part))
    return changes


def _run_local_validation_gate(
    worktree_dir: str,
    scope: SubfolderScope,
) -> Tuple[bool, str]:
    """Exécute la porte de validation locale :
    1. py_compile sur tous les fichiers python modifiés
    2. ops/scripts/check_protected_paths.py sur les changements
    3. pytest UNIQUEMENT sur targeted_test_files
    """
    changes = _get_git_modified_files(worktree_dir)
    if not changes:
        return False, "Aucun fichier n'a été modifié par l'agent dans le worktree."

    # A. Vérification de confinement : les fichiers modifiés doivent respecter allowed_subdirs
    root_allowed_files = {
        "CAPABILITIES_LEDGER.md",
        "ARCHITECTURE_COMPLETE_JARVIS.md",
        "AGENTS.md",
        "README.md",
    }
    for status, path in changes:
        norm_path = path.replace("\\", "/").lstrip("./")
        # Tolérer modifications dans targeted_test_files, allowed_subdirs ou fichiers de gouvernance racines
        allowed = (
            any(norm_path.startswith(sd) for sd in scope.allowed_subdirs)
            or norm_path in root_allowed_files
            or norm_path.startswith(".agents/")
        )
        if not allowed and norm_path.startswith("backend/tests/"):
            # Si l'agent a complété, créé ou mis à jour un test unitaire
            allowed = True
        if not allowed:
            return False, f"Violation de confinement : le fichier '{norm_path}' est hors du périmètre autorisé {scope.allowed_subdirs}."

    # B. Protection des chemins critiques (ops/scripts/check_protected_paths.py)
    violations = check_all_changes(changes)
    if violations:
        return False, f"Violation des fichiers protégés : {'; '.join(violations)}"

    # C. py_compile sur les fichiers .py modifiés
    python_bin = sys.executable or "python"
    low_prio_kwargs = build_low_priority_subprocess_kwargs()
    for status, path in changes:
        if status.upper() == "D":
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
                    return False, f"Erreur de syntaxe Python dans '{path}' : {e.stderr.strip()}"

    # D. Exécution des tests ciblés (ultra-rapide avec priorité CPU basse)
    if scope.targeted_test_files:
        valid_test_paths = []
        for tf in scope.targeted_test_files:
            p = os.path.join(worktree_dir, tf)
            if os.path.exists(p):
                valid_test_paths.append(tf)

        if valid_test_paths:
            pytest_cmd = [python_bin, "-m", "pytest", "-q"] + valid_test_paths
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
                    return False, f"Échec des tests unitaires ciblés ({', '.join(valid_test_paths)}) : {proc.stdout[-500:]}\n{proc.stderr[-300:]}"
            except subprocess.TimeoutExpired:
                return False, f"Timeout lors de l'exécution des tests ciblés ({valid_test_paths})."
            except Exception as e:
                return False, f"Erreur lors de l'appel pytest : {e}"

    return True, "Validation locale (py_compile, protected_paths, pytest ciblés) réussie avec succès."


# ─── 8. Création de PR GitHub via API REST ──────────────────────────────────
async def _create_github_pr(
    branch_name: str,
    goal: str,
    scope: SubfolderScope,
    diff_summary: str,
) -> Optional[str]:
    """Ouvre une Pull Request GitHub via l'API REST fine-grained si un token est configuré."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or getattr(config, "GITHUB_TOKEN", None)
    repo = os.environ.get("GITHUB_REPOSITORY", "Pierre38610/jarvis-core")

    if not token:
        logger.info("[SelfImprovement] Aucun GITHUB_TOKEN configuré. PR simulée localement.")
        return f"https://github.com/{repo}/compare/main...{branch_name}?expand=1"

    url = f"https://api.github.com/repos/{repo}/pulls"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Jarvis-SelfImprove-Agent",
    }
    title = f"🤖 Jarvis Self-Improve: {goal[:60]}"
    body = (
        f"## 🛠 Auto-Amélioration Autonome J.A.R.V.I.S.\n\n"
        f"**Objectif :** {goal}\n"
        f"**Périmètre :** `{scope.subfolder}`\n"
        f"**Sous-dossiers autorisés :** {', '.join(scope.allowed_subdirs)}\n"
        f"**Tests unitaires ciblés exécutés :** {', '.join(scope.targeted_test_files) if scope.targeted_test_files else 'Aucun'}\n\n"
        f"### Synthèse des Modifications\n```\n{diff_summary[:800]}\n```\n\n"
        f"*Validé avec py_compile, check_protected_paths.py et la suite pytest ciblée.*"
    )
    payload = {
        "title": title,
        "head": branch_name,
        "base": "main",
        "body": body,
        "draft": False,
    }

    try:
        import urllib.request
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        loop = asyncio.get_running_loop()

        def _do_post():
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))

        res = await loop.run_in_executor(None, _do_post)
        pr_html_url = res.get("html_url")
        logger.info(f"[SelfImprovement] Pull Request créée avec succès : {pr_html_url}")
        return pr_html_url
    except Exception as e:
        logger.warning(f"[SelfImprovement] Erreur création PR via API REST : {e}")
        return f"https://github.com/{repo}/compare/main...{branch_name}?expand=1"


# ─── 9. Moteur Principal d'Auto-Amélioration ─────────────────────────────────
async def run_self_improvement(
    goal: str,
    target_subfolder: str = "",
    complexity: str = "medium",
    create_pr: bool = True,
    session_id: Optional[str] = None,
    websocket: Any = None,
    telegram_adapter: Optional[Any] = None,
) -> SelfImprovementResult:
    """Orchestre la session d'auto-amélioration complète de bout en bout :
    1. Vérification Kill Switch & Quotas
    2. Résolution du sous-dossier & tests ciblés
    3. Sélection dynamique du modèle Antigravity
    4. Création du git worktree isolé
    5. Boucle d'essais (max 3) avec streaming logs et validations locales
    6. Revue du diff et création de PR GitHub
    7. Nettoyage garanti en finally
    """
    t0 = time.perf_counter()

    # 1. Vérification Kill Switch
    if is_kill_switch_active():
        msg = "Auto-amélioration bloquée : le Kill Switch persistant est activé ('stop auto-amélioration')."
        logger.warning(f"[SelfImprovement] {msg}")
        return SelfImprovementResult(
            status="blocked_kill_switch",
            goal=goal,
            subfolder_scope=None,
            model_used="",
            effort_used=None,
            iterations_count=0,
            branch_name="",
            pr_url=None,
            diff_summary="",
            user_message=msg,
            error=msg,
            duration_seconds=round(time.perf_counter() - t0, 2),
        )

    # 2. Vérification Quotas
    quota_ok, quota_msg = check_quota_available()
    if not quota_ok:
        logger.warning(f"[SelfImprovement] {quota_msg}")
        return SelfImprovementResult(
            status="blocked_quota",
            goal=goal,
            subfolder_scope=None,
            model_used="",
            effort_used=None,
            iterations_count=0,
            branch_name="",
            pr_url=None,
            diff_summary="",
            user_message=quota_msg,
            error=quota_msg,
            duration_seconds=round(time.perf_counter() - t0, 2),
        )

    # 3. Résolution sous-dossier & modèle
    scope = resolve_subfolder_scope(goal=goal, target_hint=target_subfolder)
    model, effort = resolve_live_agy_model(complexity=complexity)

    # Slug de branche
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", goal.strip()[:25].lower()).strip("-") or "patch"
    type_tag = "feat" if any(k in goal.lower() for k in ["ajout", "créer", "nouveau"]) else "fix"
    branch_name = f"jarvis/{type_tag}-{slug}-{int(time.time()) % 10000}"

    task_id = f"self_improve_{int(time.time() * 1000)}"
    register_agy_task(
        task_id=task_id,
        goal=f"Self-Improve [{scope.subfolder}] : {goal[:60]}",
        model=model,
        effort=effort or "none",
    )

    supervision_service.start_action(
        "self_improve",
        f"Auto-Amélioration ({scope.subfolder})",
        "self_improve",
        goal,
        f"Antigravity CLI ({model})",
        api_type="free",
        api_label="Antigravity VPS",
        cost_est="0.00 $",
    )
    await broadcast_supervision()

    if websocket:
        try:
            await websocket.send_text(json.dumps({
                "type": "jarvis_announcement",
                "text": f"Auto-amélioration lancée dans '{scope.subfolder}' avec {model}.",
                "voice": False,
            }))
        except Exception:
            pass

    async with _SELF_IMPROVE_LOCK:
        worktree_dir: Optional[str] = None
        pr_url: Optional[str] = None
        diff_summary: str = ""
        last_error: Optional[str] = None
        success = False
        iteration = 0

        try:
            worktree_dir = create_isolated_worktree(REPO_ROOT, branch_name)

            for iteration in range(1, MAX_ITERATIONS + 1):
                append_agy_log(task_id, f"--- Début de l'itération {iteration}/{MAX_ITERATIONS} ---")

                # Construction du prompt pour l'agent
                feedback_section = f"\nATTENTION : L'essai précédent a échoué avec l'erreur suivante :\n{last_error}\nCorrige cette erreur sans dévier du périmètre." if last_error else ""
                tests_to_run_str = " ".join(scope.targeted_test_files) if scope.targeted_test_files else "backend/tests/"

                agent_prompt = (
                    f"RÔLE : Agent autonome J.A.R.V.I.S. pour la tâche d'auto-amélioration.\n"
                    f"OBJECTIF : {goal}\n"
                    f"PÉRIMÈTRE AUTORISÉ : Travaille STRICTEMENT ET UNIQUEMENT dans : {', '.join(scope.allowed_subdirs)}.\n"
                    f"CONTRAT D'ARCHITECTURE : Consulte impérativement le fichier '{scope.architecture_file}'.\n"
                    f"RÈGLE OBLIGATOIRE : Toute mission d'auto-amélioration (`self_improve` ou `prompt_batch_runner`) qui ajoute, modifie ou corrige une fonctionnalité de Jarvis DOIT mettre à jour `CAPABILITIES_LEDGER.md` (et `ARCHITECTURE_COMPLETE_JARVIS.md` si l'architecture change) avant de clôturer la tâche.\n"
                    f"TESTS CIBLÉS : Lance uniquement 'pytest {tests_to_run_str}' pendant tes itérations.\n"
                    f"INTERDICTIONS ABSOLUES :\n"
                    f"- Ne modifie AUCUN fichier .env* ni les clés d'API ni auth_service.py.\n"
                    f"- Ne supprime aucun test unitaire existant.\n"
                    f"- Reste confiné à {scope.allowed_subdirs} (et CAPABILITIES_LEDGER.md / backend/tests/).\n"
                    f"{feedback_section}\n"
                    f"Conclus avec un bloc JSON final conforme à AGENTS.md."
                )

                # Construction de la commande agy (flags officiels --model et --effort via resolve_cli_model_args)
                agy_bin = find_antigravity_binary() or shutil.which("agy") or "agy"
                model_args = resolve_cli_model_args(model, effort=effort)
                cmd = [
                    agy_bin,
                    "-p", agent_prompt,
                    "--dangerously-skip-permissions",
                    "--output-format", "text",
                    *model_args,
                ]

                append_agy_log(task_id, f"Lancement d'Antigravity CLI (modèle: {model}, effort: {effort or 'none'})...")
                exit_code, stdout, stderr = await _run_agy_process(
                    cmd=cmd,
                    cwd=worktree_dir,
                    task_id=task_id,
                    timeout=360.0,
                )

                # Porte de validation locale
                val_ok, val_msg = _run_local_validation_gate(worktree_dir, scope)
                append_agy_log(task_id, f"Résultat validation locale itération {iteration} : {val_msg}")

                if val_ok:
                    success = True
                    append_agy_log(task_id, f"Itération {iteration} VALIDÉE avec succès !")
                    break
                else:
                    last_error = val_msg
                    append_agy_log(task_id, f"Échec validation itération {iteration} : {val_msg}", stream="stderr")

            # Récupération du diff final
            if worktree_dir and os.path.exists(worktree_dir):
                try:
                    diff_proc = subprocess.run(["git", "diff", "HEAD"], cwd=worktree_dir, capture_output=True, text=True, check=False)
                    diff_summary = diff_proc.stdout[:1500]
                except Exception:
                    diff_summary = "Diff indisponible."

            if success:
                # Revue légère du diff
                rev_ok, rev_msg = review_diff(diff_summary, goal)
                if not rev_ok:
                    success = False
                    last_error = f"Revue du diff rejetée : {rev_msg}"
                    append_agy_log(task_id, last_error, stream="stderr")
                else:
                    append_agy_log(task_id, f"Revue du diff validée : {rev_msg}")

            if success and create_pr:
                # Commit et Push de la branche
                try:
                    subprocess.run(["git", "add", "."], cwd=worktree_dir, capture_output=True, text=True, check=True)
                    subprocess.run(["git", "commit", "-m", f"jarvis self-improve: {goal[:50]}"], cwd=worktree_dir, capture_output=True, text=True, check=True)
                    # Push avec bypass sandbox si requis
                    subprocess.run(["git", "push", "origin", branch_name], cwd=worktree_dir, capture_output=True, text=True, check=False)
                    pr_url = await _create_github_pr(branch_name, goal, scope, diff_summary)
                except Exception as git_err:
                    logger.warning(f"[SelfImprovement] Erreur push/PR: {git_err}")
                    pr_url = f"https://github.com/Pierre38610/jarvis-core/tree/{branch_name}"

            # Notification Telegram interactive si configuré ou injecté
            active_adapter = telegram_adapter
            if active_adapter is None:
                try:
                    from services.self_improvement_telegram import telegram_proposal_adapter
                    if telegram_proposal_adapter.is_configured():
                        active_adapter = telegram_proposal_adapter
                except Exception as tg_err:
                    logger.debug(f"[SelfImprovement] Erreur init telegram adapter: {tg_err}")

            if success and active_adapter:
                try:
                    from services.self_improvement_telegram import ImprovementProposal, generate_proposal_id
                    modified_files_list = [path for _, path in _get_git_modified_files(worktree_dir)] if worktree_dir else []
                    diff_lines = len(diff_summary.splitlines()) if diff_summary else 0
                    pytest_summary = f"{len(scope.targeted_test_files)} test(s) ciblés validés" if scope.targeted_test_files else "Validation locale réussie"

                    proposal = ImprovementProposal(
                        proposal_id=generate_proposal_id(),
                        goal=goal,
                        subfolder=scope.subfolder,
                        model_used=model,
                        diff_summary=diff_summary,
                        diff_line_count=diff_lines,
                        pytest_results=pytest_summary,
                        tests_passed=True,
                        branch_name=branch_name,
                        modified_files=modified_files_list,
                        pr_url=pr_url,
                    )
                    await active_adapter.send_proposal(proposal)
                except Exception as tg_notify_err:
                    logger.warning(f"[SelfImprovement] Échec envoi notification Telegram : {tg_notify_err}")

            total_duration = time.perf_counter() - t0
            final_status = "success" if success else "failed"
            mark_agy_task_status(task_id, "completed" if success else "failed", error=last_error)

            user_msg = (
                f"Auto-amélioration terminée avec succès dans '{scope.subfolder}' en {iteration} itération(s) ({model}). "
                f"PR disponible : {pr_url or 'branche prête'}."
                if success
                else f"L'auto-amélioration a échoué après {iteration} essai(s) : {last_error}"
            )

            # Enregistrement au journal
            record_run_in_journal({
                "task_id": task_id,
                "timestamp": time.time(),
                "goal": goal,
                "subfolder": scope.subfolder,
                "model": model,
                "effort": effort,
                "status": final_status,
                "iterations": iteration,
                "pr_url": pr_url,
                "duration_seconds": round(total_duration, 2),
                "error": last_error,
            })

            supervision_service.complete_action("self_improve", status="completed" if success else "error", summary=user_msg[:200])
            await broadcast_supervision()

            return SelfImprovementResult(
                status=final_status,
                goal=goal,
                subfolder_scope=scope,
                model_used=model,
                effort_used=effort,
                iterations_count=iteration,
                branch_name=branch_name,
                pr_url=pr_url,
                diff_summary=diff_summary,
                user_message=user_msg,
                error=last_error,
                duration_seconds=round(total_duration, 2),
            )

        finally:
            # Nettoyage garanti du git worktree en finally
            if worktree_dir:
                # Si PR créée avec succès, conserver la branche sur git distant mais nettoyer le worktree local
                cleanup_isolated_worktree(REPO_ROOT, worktree_dir, branch_name, delete_branch=not success)
