"""Shim de compatibilité et exécuteur de tâches pour Antigravity CLI sur le VPS.
Suppression totale de l'API Antigravity IDE : seule la solution Antigravity CLI sur le VPS est active.
"""

import os
os.environ["NO_PROXY"] = "127.0.0.1,localhost,::1,0.0.0.0"
os.environ["no_proxy"] = "127.0.0.1,localhost,::1,0.0.0.0"
import asyncio
import shutil
from typing import Any

from services.console_monitor import console_monitor
import config
from config import GEMINI_API_KEY_PAID, GEMINI_API_KEY_FREE


class AntigravityQuotaExhaustedError(Exception):
    """Levée quand le quota 5h est atteint sur Antigravity CLI."""
    pass


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


def resolve_cli_model_args(model_name: str | None) -> list[str]:
    """Résout les arguments de modèle pour le binaire agy CLI (avec modèle et effort valides)."""
    if not model_name:
        return ["--model", "gemini-3.1-pro-high"]
    
    m = model_name.lower().strip()
    
    # Claude models
    if "opus" in m:
        return ["--model", "claude-opus-4-6-thinking"]
    if "sonnet" in m or "claude" in m:
        return ["--model", "claude-3-7-sonnet-thinking"]
    
    # Gemini 3.1 Pro models
    if "3.1" in m or "pro" in m:
        if "low" in m:
            return ["--model", "gemini-3.1-pro-low"]
        if "medium" in m or "med" in m:
            return ["--model", "gemini-3.1-pro-medium"]
        return ["--model", "gemini-3.1-pro-high"]
    
    # Gemini 3.8 Flash models
    if "3.8" in m or "flash" in m:
        if "low" in m:
            return ["--model", "gemini-3.8-flash-low"]
        if "medium" in m or "med" in m:
            return ["--model", "gemini-3.8-flash-medium"]
        return ["--model", "gemini-3.8-flash-high"]
        
    # Fallback générique
    return ["--model", "gemini-3.1-pro-high"]


class AntigravityAgent:
    """Agent Antigravity CLI exécutant les tâches via le binaire agy/antigravity-cli sur le VPS."""

    def __init__(self, workspace: str = "./my-project", model: str | None = None, api_key: str | None = None, **kwargs):
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
            cmd.extend(resolve_cli_model_args(self.requested_model))

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
