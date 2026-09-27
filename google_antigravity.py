"""Shim de compatibilité et exécuteur de tâches pour Antigravity CLI sur le VPS.
Suppression totale de l'API Antigravity IDE : seule la solution Antigravity CLI sur le VPS est active.
"""

import os
os.environ["NO_PROXY"] = "127.0.0.1,localhost,::1,0.0.0.0"
os.environ["no_proxy"] = "127.0.0.1,localhost,::1,0.0.0.0"
import asyncio
import shutil
from dataclasses import dataclass
from typing import Any, Optional, Literal, Tuple

from services.console_monitor import console_monitor
import config
from config import GEMINI_API_KEY_PAID, GEMINI_API_KEY_FREE


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
            is_override=is_override
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
        if "opus" in up or "sonnet" in up or "claude" in up:
            return CognitiveConfig(
                model="claude-3-opus" if "opus" in up else "claude-3-7-sonnet",
                thinking_level="high", timeout_seconds=600, tier=3,
                cli_model_arg="claude-opus-4-6-thinking" if "opus" in up else "claude-3-7-sonnet-thinking",
                voice_pitch=COGNITIVE_TIER_3.voice_pitch,
                description="Tier 3 — Délibération Système 2 & Haute Ingénierie (Claude Thinking)",
                reason=f"Override modèle Claude: {user_preference}", is_override=True
            )

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

    # 1. Claude Sonnet / Opus -> modélisé via le moteur Gemini 3.1 Pro haute réflexion
    if "opus" in key:
        target = ModelTarget(
            name="gemini-3.1-pro-preview",
            endpoint=GeminiAPIEndpoint(api_key=effective_key, options=GeminiModelOptions(thinking_level=ThinkingLevel.HIGH))
        )
        return target, "Claude 3 Opus (via Gemini 3.1 Pro)"
    if "sonnet" in key:
        target = ModelTarget(
            name="gemini-3.1-pro-preview",
            endpoint=GeminiAPIEndpoint(api_key=effective_key, options=GeminiModelOptions(thinking_level=ThinkingLevel.HIGH))
        )
        return target, "Claude 3.7 Sonnet (via Gemini 3.1 Pro)"

    # 2. Gemini 3.1 Pro (nom officiel API: gemini-3.1-pro-preview)
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


def resolve_cli_model_args(model_name: Any = None, thinking_level: str | None = None) -> list[str]:
    """Résout les arguments de modèle pour le binaire agy CLI (avec modèle et effort valides)."""
    if isinstance(model_name, CognitiveConfig):
        cfg = model_name
        model_name = cfg.cli_model_arg or cfg.model
        thinking_level = thinking_level or cfg.thinking_level

    if not model_name:
        return ["--model", "gemini-3.8-flash-high", "--thinking", "high"]
    
    m = model_name.lower().strip()
    
    # Claude models
    if "opus" in m:
        return ["--model", "claude-opus-4-6-thinking", "--thinking", "high"]
    if "sonnet" in m or "claude" in m:
        return ["--model", "claude-3-7-sonnet-thinking", "--thinking", "high"]
    
    # Gemini 3.1 Pro models
    if "3.1" in m or "pro" in m:
        th = thinking_level or ("low" if "low" in m else "medium" if ("med" in m or "medium" in m) else "high")
        return ["--model", f"gemini-3.1-pro-{th}", "--thinking", th]
    
    # Gemini 3.8 Flash models
    if "3.8" in m or "flash" in m:
        th = thinking_level or ("low" if "low" in m else "medium" if ("med" in m or "medium" in m) else "high")
        return ["--model", f"gemini-3.8-flash-{th}", "--thinking", th]
        
    # Fallback générique
    th = thinking_level or ("low" if "low" in m else "high")
    return ["--model", model_name, "--thinking", th]


class AntigravityAgent:
    """Agent Antigravity CLI exécutant les tâches via le binaire agy/antigravity-cli sur le VPS."""

    def __init__(self, workspace: str = "./my-project", model: str | None = None, api_key: str | None = None, thinking_level: str | None = None, **kwargs):
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
        self.thinking_level = thinking_level or ("low" if model and "low" in model.lower() else "medium" if model and ("med" in model.lower() or "medium" in model.lower()) else "high" if model and "high" in model.lower() else None)
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
                
            binary = None
            for cand in ["agy", "antigravity-cli", "/home/opc/.local/bin/agy", "/usr/local/bin/antigravity-cli", "/usr/bin/antigravity-cli"]:
                if shutil.which(cand) or (os.path.isabs(cand) and os.path.exists(cand) and os.access(cand, os.X_OK)):
                    binary = cand
                    break

            if not binary or not (shutil.which(binary) or (os.path.isabs(binary) and os.path.exists(binary))):
                print(f"[Antigravity CLI] Binaire agy non présent dans le PATH.")
                return TaskResult(
                    summary="Antigravity CLI n'est pas disponible dans l'environnement local (tourne sur le VPS Oracle).",
                    status="completed",
                    model_label=self.model_label
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
