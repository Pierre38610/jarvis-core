"""Shim de compatibilité et exécuteur de tâches pour Antigravity CLI sur le VPS.
Suppression totale de l'API Antigravity IDE : seule la solution Antigravity CLI sur le VPS est active.
"""

import os
os.environ["NO_PROXY"] = "127.0.0.1,localhost,::1,0.0.0.0"
os.environ["no_proxy"] = "127.0.0.1,localhost,::1,0.0.0.0"
import asyncio
import shutil
import time
from dataclasses import dataclass
from typing import Any, Optional, Literal, Tuple

from services.console_monitor import console_monitor
import config
from config import GEMINI_API_KEY_FREE, GEMINI_API_KEY_PAID


class AntigravityQuotaExhaustedError(Exception):
    """Levée quand le quota 5h est atteint sur Antigravity CLI."""
    pass


@dataclass
class CognitiveConfig:
    """Structure de configuration cognitive pour le routage dynamique en 3 paliers (Tiers)."""
    model: str
    thinking_level: str
    timeout_seconds: int
    tier: int = 2
    cli_model_arg: str = ""
    voice_pitch: str = ""
    description: str = ""
    reason: str = ""
    is_override: bool = False
    estimated_duration: float = 0.0

    def __post_init__(self):
        if not self.cli_model_arg:
            if self.thinking_level:
                self.cli_model_arg = f"{self.model}-{self.thinking_level}"
            else:
                self.cli_model_arg = self.model
        if self.tier == 2:
            if "flash" in self.model and self.thinking_level in ("low", "minimal"):
                self.tier = 1
            elif any(k in self.model for k in ["pro", "opus", "sonnet"]):
                self.tier = 3
        if not self.estimated_duration and self.timeout_seconds:
            self.estimated_duration = float(self.timeout_seconds)

    def with_details(self, reason: str = "", is_override: bool = False) -> "CognitiveConfig":
        return CognitiveConfig(
            model=self.model,
            thinking_level=self.thinking_level,
            timeout_seconds=self.timeout_seconds,
            tier=self.tier,
            cli_model_arg=self.cli_model_arg,
            voice_pitch=self.voice_pitch,
            description=self.description,
            reason=reason,
            is_override=is_override,
            estimated_duration=self.estimated_duration
        )


# ─── PALIERS COGNITIFS OFFICIELS (TIERS 1, 2, 3) ───
COGNITIVE_TIER_1 = CognitiveConfig(
    model="gemini-3.8-flash",
    thinking_level="low",
    timeout_seconds=120,
    tier=1,
    cli_model_arg="gemini-3.8-flash-low",
    voice_pitch="Je te règle ça en un instant Pierre.",
    description="Tier 1 — Rapidité & Économie (gemini-3.8-flash | réflexion: low)"
)

COGNITIVE_TIER_2 = CognitiveConfig(
    model="gemini-3.8-flash",
    thinking_level="high",
    timeout_seconds=300,
    tier=2,
    cli_model_arg="gemini-3.8-flash-high",
    voice_pitch="Je lance une passe d'analyse tactique, j'en ai pour quelques secondes.",
    description="Tier 2 — Raisonnement Tactique (gemini-3.8-flash | réflexion: high)"
)

COGNITIVE_TIER_3 = CognitiveConfig(
    model="gemini-3.1-pro",
    thinking_level="high",
    timeout_seconds=600,
    tier=3,
    cli_model_arg="gemini-3.1-pro-high",
    voice_pitch="C'est une analyse de fond, je mobilise notre réflexion approfondie 3.1 Pro en arrière-plan.",
    description="Tier 3 — Délibération Système 2 & Haute Ingénierie (gemini-3.1-pro | réflexion: high)"
)


def resolve_cognitive_tier_sync(
    mission_type: Optional[str] = None,
    query: str = "",
    user_preference: Optional[str] = None,
    intensite_reflexion: Optional[str] = None
) -> CognitiveConfig:
    """Version synchrone de résolution cognitive (priorité overrides, missions statiques et repli Tier 2)."""
    # ─── MODE 1 : Surcharge explicite (Overriding) ───
    if intensite_reflexion:
        ir = intensite_reflexion.lower().strip()
        if any(k in ir for k in ["rapide", "tier1", "tier 1", "flash-low", "flash_low", "economique"]):
            return COGNITIVE_TIER_1.with_details(reason=f"Override explicite intensite_reflexion: {intensite_reflexion}", is_override=True)
        elif any(k in ir for k in ["tactique", "tier2", "tier 2", "flash-high", "flash_high"]):
            return COGNITIVE_TIER_2.with_details(reason=f"Override explicite intensite_reflexion: {intensite_reflexion}", is_override=True)
        elif any(k in ir for k in ["approfondie", "tier3", "tier 3", "pro-high", "pro_high", "fond", "ingenierie"]):
            return COGNITIVE_TIER_3.with_details(reason=f"Override explicite intensite_reflexion: {intensite_reflexion}", is_override=True)

    if user_preference:
        up = user_preference.lower().strip()
        if any(k in up for k in ["tier1", "tier 1", "flash-low", "flash_low"]):
            return COGNITIVE_TIER_1.with_details(reason=f"Override explicite user_preference: {user_preference}", is_override=True)
        if any(k in up for k in ["tier2", "tier 2", "tactique", "flash-high", "flash_high"]):
            return COGNITIVE_TIER_2.with_details(reason=f"Override explicite user_preference: {user_preference}", is_override=True)
        if any(k in up for k in ["tier3", "tier 3", "approfondie", "pro-high", "pro_high"]):
            return COGNITIVE_TIER_3.with_details(reason=f"Override explicite user_preference: {user_preference}", is_override=True)
        if "flash" in up:
            if any(k in up for k in ["low", "min", "rapide"]):
                return COGNITIVE_TIER_1.with_details(reason=f"Override modèle: {user_preference}", is_override=True)
            return COGNITIVE_TIER_2.with_details(reason=f"Override modèle: {user_preference}", is_override=True)
        if "pro" in up or "3.1" in up:
            if "low" in up:
                return CognitiveConfig(
                    model="gemini-3.1-pro", thinking_level="low", timeout_seconds=300, tier=2,
                    cli_model_arg="gemini-3.1-pro-low", voice_pitch=COGNITIVE_TIER_2.voice_pitch,
                    description="Tier 2 — Raisonnement Tactique (gemini-3.1-pro | réflexion: low)",
                    reason=f"Override modèle pro-low: {user_preference}", is_override=True
                )
            if any(k in up for k in ["med", "medium"]):
                return CognitiveConfig(
                    model="gemini-3.1-pro", thinking_level="medium", timeout_seconds=300, tier=2,
                    cli_model_arg="gemini-3.1-pro-medium", voice_pitch=COGNITIVE_TIER_2.voice_pitch,
                    description="Tier 2 — Raisonnement Tactique (gemini-3.1-pro | réflexion: medium)",
                    reason=f"Override modèle pro-medium: {user_preference}", is_override=True
                )
            return COGNITIVE_TIER_3.with_details(reason=f"Override modèle pro: {user_preference}", is_override=True)

    if query:
        q_lower = query.lower()
        tier1_signals = [
            "passe rapide", "mode rapide", "en rapide", "fais une passe rapide",
            "réponse rapide", "rapide avec flash", "flash rapide", "ultra rapide",
            "sans réfléchir", "juste un résumé court", "brouillon rapide", "check rapide"
        ]
        if any(sig in q_lower for sig in tier1_signals):
            return COGNITIVE_TIER_1.with_details(reason="Override vocal explicite: passe rapide demandée", is_override=True)

        tier3_signals = [
            "prends tout ton temps", "réfléchis au maximum", "réflexion maximale",
            "analyse approfondie", "réflexion approfondie", "analyse de fond",
            "haute ingénierie", "délibération complète", "mode pro", "avec pro"
        ]
        if any(sig in q_lower for sig in tier3_signals):
            return COGNITIVE_TIER_3.with_details(reason="Override vocal explicite: réflexion maximale demandée", is_override=True)

        tier2_signals = [
            "analyse tactique", "passe tactique", "tactique", "intermédiaire",
            "flash high", "réflexion tactique", "analyse équilibrée"
        ]
        if any(sig in q_lower for sig in tier2_signals):
            return COGNITIVE_TIER_2.with_details(reason="Override vocal explicite: analyse tactique demandée", is_override=True)

    # ─── MODE 2 : Table de correspondance statique par mission_type ───
    if mission_type:
        mt = mission_type.lower().strip()
        tier1_missions = {"doc_sync", "book_curation", "email_simple", "log_check", "curation_livre_synthese", "documentation"}
        tier2_missions = {"transport_optimizer", "spreadsheet_modeler", "email_analysis", "email_drafting", "memory_consolidation", "morning_briefing"}
        tier3_missions = {"deep_research", "system_healing", "code_refactoring", "software_refactoring", "auto_guerison_systeme", "healing"}

        if mt in tier1_missions:
            return COGNITIVE_TIER_1.with_details(reason=f"Mission statique {mission_type}", is_override=False)
        if mt in tier2_missions:
            return COGNITIVE_TIER_2.with_details(reason=f"Mission statique {mission_type}", is_override=False)
        if mt in tier3_missions:
            return COGNITIVE_TIER_3.with_details(reason=f"Mission statique {mission_type}", is_override=False)

    return COGNITIVE_TIER_2.with_details(reason="Défaut tactique Tier 2 (mode synchrone)", is_override=False)


async def resolve_cognitive_tier(
    mission_type: Optional[str] = None,
    query: str = "",
    user_preference: Optional[str] = None,
    intensite_reflexion: Optional[str] = None
) -> CognitiveConfig:
    """Résout dynamiquement le palier cognitif (Tier 1, 2 ou 3) :
    1. Surcharge explicite prioritaire (vitesse, modèle forcé, intensité)
    2. Table de correspondance statique par mission_type
    3. Classification légère via modèle Tier 1 (gemini-3.8-flash) renvoyant {"tier": 1|2|3, "reason": "..."}
    """
    from services.reasoning_service import resolve_cognitive_tier as _rct
    return await _rct(
        mission_type=mission_type,
        query=query,
        user_preference=user_preference,
        intensite_reflexion=intensite_reflexion
    )


class TaskResult:
    def __init__(self, summary: str = "", status: str = "completed", model_label: str = "Gemini 3.8 Flash (Medium)", error_type: str | None = None):
        self.summary = summary
        self.status = status
        self.model_label = model_label
        self.error_type = error_type


class ThinkingLevel:
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class GeminiModelOptions:
    def __init__(self, thinking_level: str = ThinkingLevel.LOW):
        self.thinking_level = thinking_level


class GeminiAPIEndpoint:
    def __init__(self, api_key: str | None = None, options: GeminiModelOptions | None = None):
        self.api_key = api_key
        self.options = options or GeminiModelOptions()


class ModelTarget:
    def __init__(self, name: str = "", endpoint: GeminiAPIEndpoint | None = None):
        self.name = name
        self.endpoint = endpoint or GeminiAPIEndpoint()


def resolve_antigravity_model(model_name: str | None = None, api_key: str | None = None) -> tuple[ModelTarget, str]:
    """Résout le choix de modèle Antigravity vers un ModelTarget avec options de réflexion (Thinking Level),
    et retourne le libellé propre destiné à l'affichage dans le HUD mobile.
    """
    key = (model_name or "gemini-3.8-flash").lower().strip()
    effective_key = api_key or config.get_effective_paid_key() or GEMINI_API_KEY_FREE

    # Détermination intelligente du niveau de réflexion (Thinking Level)
    if "high" in key:
        level = ThinkingLevel.HIGH
        label_level = "High"
    elif "medium" in key or "med" in key:
        level = ThinkingLevel.MEDIUM
        label_level = "Medium"
    elif "low" in key:
        level = ThinkingLevel.LOW
        label_level = "Low"
    else:
        if any(p in key for p in ["pro", "opus", "sonnet"]):
            level = ThinkingLevel.HIGH
            label_level = "High"
        elif "high" in key:
            level = ThinkingLevel.HIGH
            label_level = "High"
        elif "med" in key:
            level = ThinkingLevel.MEDIUM
            label_level = "Medium"
        else:
            level = ThinkingLevel.LOW
            label_level = "Low"

    # 0. Claude 3.7 Sonnet / Opus
    if "claude" in key or "sonnet" in key:
        target = ModelTarget(
            name="claude-3-7-sonnet",
            endpoint=GeminiAPIEndpoint(api_key=effective_key, options=GeminiModelOptions(thinking_level=level))
        )
        return target, "Claude 3.7 Sonnet"

    # 1. Gemini 3.1 Pro (nom officiel API: gemini-3.1-pro-preview)
    if "3.1" in key or "pro" in key:
        target = ModelTarget(
            name="gemini-3.1-pro-preview",
            endpoint=GeminiAPIEndpoint(api_key=effective_key, options=GeminiModelOptions(thinking_level=level))
        )
        return target, f"Gemini 3.1 Pro ({label_level})"

    # 2b. Gemini 3.5 Flash
    if "3.5" in key:
        target = ModelTarget(
            name="gemini-3.5-flash",
            endpoint=GeminiAPIEndpoint(api_key=effective_key, options=GeminiModelOptions(thinking_level=level))
        )
        return target, f"Gemini 3.5 Flash ({label_level})"

    # 3. Gemini 3.6 Flash
    if "3.6" in key:
        target = ModelTarget(
            name="gemini-3.6-flash",
            endpoint=GeminiAPIEndpoint(api_key=effective_key, options=GeminiModelOptions(thinking_level=level))
        )
        return target, f"Gemini 3.6 Flash ({label_level})"

    # 4. Gemini 3.7 Flash
    if "3.7" in key:
        target = ModelTarget(
            name="gemini-3.7-flash",
            endpoint=GeminiAPIEndpoint(api_key=effective_key, options=GeminiModelOptions(thinking_level=level))
        )
        return target, f"Gemini 3.7 Flash ({label_level})"

    # 5. Gemini Flash Latest
    if "latest" in key:
        target = ModelTarget(
            name="gemini-flash-latest",
            endpoint=GeminiAPIEndpoint(api_key=effective_key, options=GeminiModelOptions(thinking_level=level))
        )
        return target, f"Gemini Flash Latest ({label_level})"

    # 6. Gemini 3.8 Flash (par défaut) avec Thinking Level
    target = ModelTarget(
        name="gemini-3.8-flash",
        endpoint=GeminiAPIEndpoint(api_key=effective_key, options=GeminiModelOptions(thinking_level=level))
    )
    return target, f"Gemini 3.8 Flash ({label_level})"


def is_stop_directive(text: str) -> bool:
    """Détecte les ordres explicites d'interruption et d'arrêt de l'utilisateur."""
    if not text:
        return False
    t = text.lower().strip()
    stop_words = [
        "arrête", "arrete", "stop", "annule", "annuler", "interromps", "interrompre",
        "abandonne", "abandonner", "stoppe", "stopper", "pause", "arrête-toi", "arrete-toi",
        "arrête tout", "arrete tout", "arrête de coder", "arrete de coder",
        "tais-toi et arrête", "cancel", "quitte", "halt", "abort", "__stop__"
    ]
    if t in stop_words:
        return True
    for sw in stop_words:
        if t == sw or t.startswith(sw + " ") or t.endswith(" " + sw) or f" {sw} " in t:
            return True
    return False


def find_antigravity_binary() -> Optional[str]:
    """Recherche déterministe du binaire Antigravity CLI (agy).
    Vérifie le PATH ainsi que les emplacements standards connus sur le VPS Oracle et localement.
    """
    candidates = [
        "agy",
        "antigravity-cli",
        os.path.expanduser("~/.local/bin/agy"),
        "/home/opc/.local/bin/agy",
        "/usr/local/bin/antigravity-cli",
        "/usr/local/bin/agy",
        "/usr/bin/antigravity-cli",
        "/usr/bin/agy"
    ]
    if os.name == "nt":
        candidates.extend(["agy.cmd", "agy.exe", "antigravity-cli.cmd", "antigravity-cli.exe"])

    for cand in candidates:
        if not cand:
            continue
        which_path = shutil.which(cand)
        if which_path and os.path.exists(which_path) and (os.access(which_path, os.X_OK) or os.name == "nt"):
            return which_path
        if os.path.isabs(cand) and os.path.exists(cand) and (os.access(cand, os.X_OK) or os.name == "nt"):
            return cand

    return None


_CLI_READY_CACHE: tuple[float, bool, str, Optional[str]] = (0.0, False, "", None)

async def verify_antigravity_cli_ready(force_refresh: bool = False) -> tuple[bool, str, Optional[str]]:
    """Vérifie de manière concrète si le binaire Antigravity CLI (agy) est présent, exécutable
    et capable de répondre à une commande basique (--version).
    Renvoie (is_ready: bool, message: str, binary_path: Optional[str]).
    Utilise un cache court (30s si succès, 5s si échec) pour concilier vélocité et réactivité.
    """
    global _CLI_READY_CACHE
    now = time.time()
    cache_ttl = 30.0 if _CLI_READY_CACHE[1] else 5.0

    if not force_refresh and (now - _CLI_READY_CACHE[0] < cache_ttl):
        return _CLI_READY_CACHE[1], _CLI_READY_CACHE[2], _CLI_READY_CACHE[3]

    binary = find_antigravity_binary()
    if not binary:
        msg = "Binaire Antigravity CLI ('agy') introuvable sur le système (vérifié dans le PATH et ~/.local/bin/agy)."
        _CLI_READY_CACHE = (now, False, msg, None)
        return False, msg, None

    try:
        proc = await asyncio.create_subprocess_exec(
            binary, "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=3.0)
        if proc.returncode == 0:
            version_str = stdout.decode('utf-8', errors='replace').strip() or "OK"
            msg = f"Antigravity CLI opérationnel ({binary}, version: {version_str})"
            _CLI_READY_CACHE = (now, True, msg, binary)
            return True, msg, binary
        else:
            err_str = stderr.decode('utf-8', errors='replace').strip() or f"Code sortie {proc.returncode}"
            msg = f"Antigravity CLI a renvoyé une erreur lors du test de version : {err_str}"
            _CLI_READY_CACHE = (now, False, msg, binary)
            return False, msg, binary
    except asyncio.TimeoutError:
        msg = f"Timeout lors de l'exécution de '{binary} --version' (> 3s)."
        _CLI_READY_CACHE = (now, False, msg, binary)
        return False, msg, binary
    except Exception as e:
        msg = f"Exception lors du pré-test de '{binary}' : {str(e)}"
        _CLI_READY_CACHE = (now, False, msg, binary)
        return False, msg, binary


def resolve_cli_model_args(model_name: Any = None, thinking_level: str | None = None, effort: str | None = None) -> list[str]:
    """Résout les arguments de modèle pour le binaire agy CLI (avec modèle et effort valides).
    RÈGLE ABSOLUE : agy supporte uniquement --model et optionnellement --effort (low|medium|high|max).
    Le drapeau --thinking est INEXISTANT dans agy et cause une erreur fatale code 2.
    """
    effective_effort = effort or thinking_level

    if isinstance(model_name, CognitiveConfig):
        cfg = model_name
        model_name = cfg.cli_model_arg or cfg.model
        effective_effort = effective_effort or cfg.thinking_level

    if not model_name:
        return ["--model", "gemini-3.7-flash-high", "--effort", "high"]

    m = str(model_name).lower().strip()

    # Modèles Claude : pas d'argument --effort
    if "claude" in m or "sonnet" in m:
        return ["--model", str(model_name)]

    # Gemini 3.1 Pro models
    if "3.1" in m or "pro" in m:
        th = effective_effort or ("low" if "low" in m else "high")
        eff = "low" if th == "low" else "high"
        base_name = str(model_name) if ("-" in str(model_name) and not str(model_name).endswith("-pro")) else f"gemini-3.1-pro-{eff}"
        return ["--model", base_name, "--effort", eff]

    # Gemini 3.7 Flash models
    if "3.7" in m:
        th = effective_effort or ("low" if "low" in m else "medium" if ("med" in m or "medium" in m) else "high")
        eff = "low" if th == "low" else "medium" if th == "medium" else "high"
        base_name = str(model_name) if ("-" in str(model_name) and not str(model_name).endswith("-flash")) else f"gemini-3.7-flash-{eff}"
        return ["--model", base_name, "--effort", eff]

    # Gemini 3.8 Flash models
    if "3.8" in m or "flash" in m:
        th = effective_effort or ("low" if "low" in m else "medium" if ("med" in m or "medium" in m) else "high")
        eff = "low" if th == "low" else "medium" if th == "medium" else "high"
        base_name = str(model_name) if ("-" in str(model_name) and not str(model_name).endswith("-flash")) else f"gemini-3.8-flash-{eff}"
        return ["--model", base_name, "--effort", eff]

    # Fallback générique
    th = effective_effort or ("low" if "low" in m else "high")
    eff = "low" if th == "low" else "high"
    return ["--model", str(model_name), "--effort", eff]


class AntigravityAgent:
    """Agent Antigravity CLI exécutant les tâches via le binaire agy/antigravity-cli sur le VPS."""

    def __init__(self, workspace: str = "./my-project", model: str | None = None, api_key: str | None = None, thinking_level: str | None = None, effort: str | None = None, **kwargs):
        self.workspace = os.path.abspath(workspace)
        os.makedirs(self.workspace, exist_ok=True)
        # Règle d'impossibilité physique : si la clé payante n'est pas cochée/autorisée dans l'application,
        # l'agent refuse catégoriquement toute clé payante et bascule sur la clé gratuite.
        if not config.is_paid_key_authorized():
            self.api_key = GEMINI_API_KEY_FREE
        else:
            self.api_key = api_key or config.get_effective_paid_key() or GEMINI_API_KEY_FREE
        self.is_cancelled = False
        self.cli_process = None
        self.requested_model = model
        self.effort = effort or thinking_level or ("low" if model and "low" in str(model).lower() else "medium" if model and ("med" in str(model).lower() or "medium" in str(model).lower()) else "high" if model and "high" in str(model).lower() else None)
        self.thinking_level = self.effort
        self.target_model, self.model_label = resolve_antigravity_model(model, api_key=self.api_key)

    def cancel(self):
        """Déclenche l'interruption immédiate de l'agent Antigravity CLI."""
        self.is_cancelled = True
        if self.cli_process:
            try:
                self.cli_process.terminate()
            except Exception:
                try:
                    self.cli_process.kill()
                except Exception:
                    pass
        print(f"[Antigravity CLI] Ordre de cancellation transmis à l'agent ({self.model_label}).")

    async def run_task(self, instruction: str) -> TaskResult:
        return await self.run_cli_task_stream(instruction)

    async def run_task_stream(
        self,
        instruction: str,
        on_progress: Any = None,
        directive_queue: asyncio.Queue | None = None
    ) -> TaskResult:
        """Délègue directement à Antigravity CLI."""
        return await self.run_cli_task_stream(instruction, on_progress=on_progress, directive_queue=directive_queue)

    async def run_cli_task_stream(
        self,
        instruction: str,
        on_progress: Any = None,
        directive_queue: asyncio.Queue | None = None
    ) -> TaskResult:
        """Exécute la tâche en appelant directement le binaire antigravity-cli sur le système via subprocess."""
        if self.is_cancelled:
            return TaskResult(summary="Développement arrêté à la demande de l'utilisateur.", status="cancelled", model_label=self.model_label)

        try:
            print(f"[Antigravity CLI] Lancement de antigravity-cli pour {self.model_label} : {instruction[:60]}...")
            if on_progress:
                await on_progress({"step": "start", "text": f"Lancement de la réflexion approfondie via Antigravity CLI avec {self.model_label}."})

            env = os.environ.copy()
            if self.api_key:
                env["GEMINI_API_KEY"] = self.api_key
                env["GOOGLE_API_KEY"] = self.api_key
            if self.thinking_level:
                env["ANTIGRAVITY_THINKING"] = self.thinking_level
                env["GEMINI_THINKING_LEVEL"] = self.thinking_level
            if self.requested_model:
                env["ANTIGRAVITY_MODEL"] = self.requested_model

            # Enrichir PATH pour garantir l'accès à ~/.local/bin et /usr/local/bin
            current_path = env.get("PATH", "")
            extra_paths = ["/home/opc/.local/bin", "/usr/local/bin", os.path.expanduser("~/.local/bin")]
            for ep in extra_paths:
                if ep not in current_path and os.path.exists(ep):
                    current_path = f"{ep}:{current_path}"
            env["PATH"] = current_path

            binary = find_antigravity_binary()
            if not binary:
                msg = "Antigravity CLI n'est pas disponible sur le serveur (binaire 'agy' introuvable)."
                print(f"[Antigravity CLI] {msg}")
                return TaskResult(
                    summary=msg,
                    status="error",
                    model_label=self.model_label,
                    error_type="binary_not_found"
                )

            cmd = [
                binary,
                "-p", instruction,
                "--dangerously-skip-permissions",
                "--output-format", "text"
            ]
            cmd.extend(resolve_cli_model_args(self.requested_model, self.thinking_level))

            try:
                self.cli_process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                    cwd=self.workspace
                )
            except FileNotFoundError:
                print(f"[Antigravity CLI] Fichier binaire introuvable à l'exécution.")
                return TaskResult(
                    summary="Binaire Antigravity CLI introuvable à l'exécution.",
                    status="error",
                    model_label=self.model_label,
                    error_type="binary_not_found"
                )
            
            stdout_output = []
            stderr_output = []
            
            async def read_stream(stream, is_stderr=False):
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    line_str = line.decode('utf-8', errors='replace').strip()
                    if line_str:
                        if is_stderr:
                            stderr_output.append(line_str)
                            # Détection de quota 429
                            if any(k in line_str.lower() for k in ["429", "quota", "resource_exhausted", "quotaexceeded"]):
                                if self.cli_process:
                                    try:
                                        self.cli_process.terminate()
                                    except Exception:
                                        pass
                                raise AntigravityQuotaExhaustedError("Quota 5h épuisé sur Antigravity CLI.")
                        else:
                            stdout_output.append(line_str)
                            if on_progress:
                                await on_progress({"step": "thought", "text": line_str[:120]})
                                
            await asyncio.gather(
                read_stream(self.cli_process.stdout, False),
                read_stream(self.cli_process.stderr, True)
            )
            
            await self.cli_process.wait()
            
            if self.is_cancelled:
                raise asyncio.CancelledError("Arrêt demandé par l'utilisateur.")
                
            if self.cli_process.returncode != 0:
                err_text = "\n".join(stderr_output)
                if "429" in err_text or "quota" in err_text.lower():
                    raise AntigravityQuotaExhaustedError("Quota 5h épuisé sur Antigravity CLI.")
                raise RuntimeError(f"Erreur Antigravity CLI (code {self.cli_process.returncode}): {err_text}")
                
            summary = "\n".join(stdout_output)
            if not summary:
                summary = "Tâche Antigravity CLI terminée."
                
            if on_progress:
                await on_progress({"step": "complete", "text": "Le raisonnement est achevé avec succès."})
                
            return TaskResult(summary=summary, status="completed", model_label=self.model_label)
            
        except AntigravityQuotaExhaustedError:
            raise
        except asyncio.CancelledError:
            print(f"[Antigravity CLI] Tâche annulée avec succès ({self.model_label}).")
            return TaskResult(summary="Développement interrompu à la demande de l'utilisateur.", status="cancelled", model_label=self.model_label)
        except Exception as e:
            if isinstance(e, AntigravityQuotaExhaustedError):
                raise
            err_msg = str(e)
            print(f"[Antigravity CLI] Exception d'exécution ({self.model_label}): {err_msg}")
            console_monitor.record_error(source=f"Antigravity CLI ({self.model_label})", message=err_msg, level="ERROR")
            if any(k in err_msg.lower() for k in ["429", "quota", "resource_exhausted"]):
                raise AntigravityQuotaExhaustedError("Quota 5h épuisé sur Antigravity CLI.")
            
            return TaskResult(summary=f"Erreur d'exécution Antigravity CLI ({self.model_label}): {err_msg}", status="error", model_label=self.model_label, error_type="error")
