"""Shim de compatibilité et sélecteur de modèles pour le SDK officiel Google Antigravity."""

import os
os.environ["NO_PROXY"] = "127.0.0.1,localhost,::1,0.0.0.0"
os.environ["no_proxy"] = "127.0.0.1,localhost,::1,0.0.0.0"
import asyncio
from typing import Any
from google.antigravity import Agent, LocalAgentConfig, CapabilitiesConfig
from google.antigravity.hooks import policy
from google.antigravity.models import ModelTarget, GeminiAPIEndpoint, GeminiModelOptions, ThinkingLevel
from google.antigravity.types import ToolCall, Thought, RetryConfig, ModelAPIRetryConfig

from services.console_monitor import console_monitor
import config
from config import GEMINI_API_KEY_PAID, GEMINI_API_KEY_FREE

class AntigravityQuotaExhaustedError(Exception):
    """Levée quand le quota 5h est atteint sur l'API Antigravity CLI."""
    pass


class TaskResult:
    def __init__(self, summary: str = "", status: str = "completed", model_label: str = "Gemini 3.8 Flash (Medium)", error_type: str | None = None):
        self.summary = summary
        self.status = status
        self.model_label = model_label
        self.error_type = error_type

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
        # Pour les modèles Flash : par défaut LOW pour équilibre optimal réactivité / charge / quotas
        # Pour Pro / Claude : HIGH par défaut
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

class AntigravityAgent:
    """Agent Antigravity prêt pour l'exécution asynchrone de tâches avec choix dynamique du modèle."""

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

        if "policies" not in kwargs:
            kwargs["policies"] = [policy.allow_all()]

        # Répertoire de session sécurisé dans le workspace pour éviter les conflits d'accès temp
        if "save_dir" not in kwargs:
            save_dir = os.path.join(self.workspace, ".antigravity_session")
            os.makedirs(save_dir, exist_ok=True)
            kwargs["save_dir"] = save_dir

        # Configuration de réessais robuste avec backoff exponentiel pour absorber les pics 503 / 429
        if "retry_config" not in kwargs:
            kwargs["retry_config"] = RetryConfig(
                api_retry=ModelAPIRetryConfig(
                    max_retries=5,
                    initial_sleep_duration_ms=2500,
                    exponential_multiplier=2.0,
                    jitter_range=0.2
                )
            )

        self.requested_model = model

        # Résolution du modèle et de son niveau de réflexion avec la clé payante
        self.target_model, self.model_label = resolve_antigravity_model(model, api_key=self.api_key)

        subproc_env = kwargs.pop("env", {}) or {}
        if self.api_key:
            subproc_env["GEMINI_API_KEY"] = self.api_key
            subproc_env["GOOGLE_API_KEY"] = self.api_key

        self.config = LocalAgentConfig(
            workspaces=[self.workspace],
            model=self.target_model,
            api_key=self.api_key,
            env=subproc_env,
            capabilities=kwargs.pop("capabilities", CapabilitiesConfig()),
            **kwargs,
        )

    def cancel(self):
        """Déclenche l'interruption immédiate de l'agent Antigravity."""
        self.is_cancelled = True
        if self.cli_process:
            try:
                self.cli_process.terminate()
            except Exception:
                try:
                    self.cli_process.kill()
                except Exception:
                    pass
        print(f"[Antigravity] Ordre de cancellation transmis à l'agent ({self.model_label}).")

    async def run_task(self, instruction: str) -> TaskResult:
        return await self.run_task_stream(instruction)

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
                
            import shutil
            binary = None
            for cand in ["agy", "antigravity-cli", "/home/opc/.local/bin/agy", "/usr/local/bin/antigravity-cli", "/usr/bin/antigravity-cli"]:
                if shutil.which(cand) or (os.path.isabs(cand) and os.path.exists(cand) and os.access(cand, os.X_OK)):
                    binary = cand
                    break
            if not binary:
                binary = "agy"

            cmd = [
                binary,
                "-p", instruction,
                "--dangerously-skip-permissions",
                "--output-format", "text"
            ]
            if self.requested_model:
                cmd.extend(["--model", self.requested_model])

            self.cli_process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=self.workspace
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

    async def run_task_stream(
        self,
        instruction: str,
        on_progress: Any = None,
        directive_queue: asyncio.Queue | None = None
    ) -> TaskResult:
        """Exécute la tâche en streaming avec émission d'étapes et gestion de consignes en direct."""
        if self.is_cancelled:
            return TaskResult(summary="Développement immédiatement arrêté à la demande de l'utilisateur.", status="cancelled", model_label=self.model_label)
        try:
            print(f"[Antigravity] Exécution de la tâche avec {self.model_label} : {instruction[:60]}...")
            if on_progress:
                await on_progress({
                    "step": "start",
                    "text": f"J'engage les protocoles de développement avec {self.model_label}."
                })

            async with Agent(self.config) as agent:
                if self.is_cancelled:
                    raise asyncio.CancelledError("Arrêt demandé par l'utilisateur.")

                if on_progress:
                    await on_progress({
                        "step": "planning",
                        "text": "Analyse de la structure et préparation de l'implémentation..."
                    })

                response = await agent.chat(instruction)
                collected_chunks = []
                pending_directives = []
                last_oral_time = asyncio.get_event_loop().time()

                async def process_turn_chunks(active_response):
                    nonlocal last_oral_time
                    async for chunk in active_response.chunks:
                        if self.is_cancelled:
                            raise asyncio.CancelledError("Arrêt demandé par l'utilisateur.")

                        collected_chunks.append(chunk)

                        # 1. Prise en compte immédiate d'une consigne en direct (ou ordre d'arrêt)
                        if directive_queue and not directive_queue.empty():
                            try:
                                d = directive_queue.get_nowait()
                                if is_stop_directive(d):
                                    self.is_cancelled = True
                                    print(f"[Antigravity] ORDRE D'ARRÊT REÇU : '{d}'. Interruption immédiate !")
                                    if on_progress:
                                        await on_progress({
                                            "step": "cancelled",
                                            "text": "Développement immédiatement interrompu à votre demande."
                                        })
                                    raise asyncio.CancelledError("Arrêt demandé par l'utilisateur.")

                                print(f"[Antigravity] Consigne reçue en direct : {d}")
                                pending_directives.append(d)
                                if on_progress:
                                    await on_progress({
                                        "step": "adaptation",
                                        "text": f"Consigne en direct prise en compte : {d}."
                                    })
                                conn = getattr(getattr(agent, "conversation", None), "connection", None)
                                if conn and hasattr(conn, "send_trigger_notification"):
                                    await conn.send_trigger_notification(f"Consigne urgente de l'utilisateur : {d}")
                            except asyncio.CancelledError:
                                raise
                            except Exception as d_err:
                                print(f"[Antigravity] Notice injection directive: {d_err}")

                        # 2. Détection des outils exécutés
                        if isinstance(chunk, ToolCall):
                            if self.is_cancelled:
                                raise asyncio.CancelledError("Arrêt demandé par l'utilisateur.")

                            tool_name = getattr(chunk, "name", "outil")
                            args = getattr(chunk, "args", {})
                            oral_text = None
                            if "write" in tool_name or "create" in tool_name:
                                target = args.get("TargetFile") or args.get("path") or "un fichier"
                                fname = os.path.basename(str(target))
                                oral_text = f"Implémentation du code dans {fname}..."
                            elif "replace" in tool_name or "edit" in tool_name:
                                target = args.get("TargetFile") or args.get("path") or "le code"
                                fname = os.path.basename(str(target))
                                oral_text = f"Mise à jour du code dans {fname}..."
                            elif "command" in tool_name or "terminal" in tool_name:
                                oral_text = "Exécution des vérifications et tests..."
                            elif "view" in tool_name or "read" in tool_name:
                                target = args.get("AbsolutePath") or args.get("path") or ""
                                fname = os.path.basename(str(target)) if target else "les fichiers"
                                oral_text = f"Inspection de {fname}..."

                            if oral_text and on_progress:
                                now = asyncio.get_event_loop().time()
                                if now - last_oral_time >= 3.0:
                                    last_oral_time = now
                                    await on_progress({"step": "tool", "text": oral_text})

                        # 3. Détection de pensées/choix architecturaux
                        elif isinstance(chunk, Thought):
                            if self.is_cancelled:
                                raise asyncio.CancelledError("Arrêt demandé par l'utilisateur.")

                            thought_txt = (getattr(chunk, "text", "") or "").lower()
                            now = asyncio.get_event_loop().time()
                            if now - last_oral_time >= 6.0:
                                if any(k in thought_txt for k in ["choix", "opté", "décide", "architecture", "structure"]):
                                    last_oral_time = now
                                    if on_progress:
                                        await on_progress({
                                            "step": "thought",
                                            "text": "Conception de l'architecture logicielle..."
                                        })
                                elif any(k in thought_txt for k in ["erreur", "error", "problème", "issue", "corrige"]):
                                    last_oral_time = now
                                    if on_progress:
                                        await on_progress({
                                            "step": "fix",
                                            "text": "Ajustement technique et correction..."
                                        })

                # Traitement du premier tour de réponse
                await process_turn_chunks(response)

                # Si des consignes ont été reçues pendant le streaming ou restent en attente,
                # elles sont appliquées proprement sur la session devenue idle
                while pending_directives or (directive_queue and not directive_queue.empty()):
                    if self.is_cancelled:
                        raise asyncio.CancelledError("Arrêt demandé par l'utilisateur.")

                    if directive_queue and not directive_queue.empty():
                        d_next = directive_queue.get_nowait()
                        if is_stop_directive(d_next):
                            self.is_cancelled = True
                            print(f"[Antigravity] ORDRE D'ARRÊT REÇU : '{d_next}'. Interruption immédiate !")
                            if on_progress:
                                await on_progress({
                                    "step": "cancelled",
                                    "text": "Développement immédiatement interrompu à votre demande."
                                })
                            raise asyncio.CancelledError("Arrêt demandé par l'utilisateur.")
                        pending_directives.append(d_next)

                    directive_to_apply = pending_directives.pop(0)
                    print(f"[Antigravity] Application de la consigne complémentaire : {directive_to_apply}")
                    if on_progress:
                        await on_progress({
                            "step": "adaptation",
                            "text": f"Application de la consigne : {directive_to_apply}."
                        })
                    followup_resp = await agent.chat(
                        f"Consigne utilisateur supplémentaire reçue en direct : {directive_to_apply}. "
                        f"Applique immédiatement et valide les modifications nécessaires selon cette consigne."
                    )
                    await process_turn_chunks(followup_resp)
                    response = followup_resp

                if self.is_cancelled:
                    raise asyncio.CancelledError("Arrêt demandé par l'utilisateur.")

                summary = await response.text()
                if not summary:
                    summary = "Tâche Antigravity exécutée avec succès dans le projet."

                if on_progress:
                    await on_progress({
                        "step": "complete",
                        "text": "Le développement est achevé avec succès. Tous les fichiers sont prêts."
                    })

                return TaskResult(summary=summary, status="completed", model_label=self.model_label)

        except asyncio.CancelledError:
            print(f"[Antigravity] Tâche annulée avec succès ({self.model_label}).")
            return TaskResult(
                summary="Développement immédiatement arrêté à la demande de l'utilisateur.",
                status="cancelled",
                model_label=self.model_label
            )
        except Exception as e:
            err_msg = str(e)
            print(f"[Antigravity] Exception d'exécution ({self.model_label}): {err_msg}")
            console_monitor.record_error(
                source=f"Antigravity ({self.model_label})",
                message=err_msg,
                level="ERROR"
            )

            # Détection d'erreurs transitoires (surcharge serveur 503, 429, indisponibilité temporaire, forte demande)
            is_transient = any(k in err_msg.lower() for k in [
                "429", "503", "unavailable", "high demand", "resource_exhausted", "not found", "satur"
            ])

            if is_transient:
                # Chaîne de modèles de secours classés du plus performant au moins sollicité
                # avec niveau de réflexion bas (LOW) pour minimiser la consommation de calcul et contourner les 503
                fallback_chain = [
                    "gemini-3.8-flash-low",
                    "gemini-3.7-flash-low",
                    "gemini-3.6-flash-low",
                    "gemini-3.5-flash-low",
                    "gemini-flash-latest-low"
                ]

                # Éviter de retenter exactement le même modèle que celui qui vient d'échouer
                current_key = (self.requested_model or "gemini-3.8-flash").lower()
                candidates = [m for m in fallback_chain if m != current_key]

                for fb_model_name in candidates:
                    try:
                        fb_target, fb_label = resolve_antigravity_model(fb_model_name, api_key=self.api_key)
                        print(f"[Antigravity] Tentative de bascule vers le modèle moins sollicité : {fb_label}...")
                        if on_progress:
                            await on_progress({
                                "step": "fallback",
                                "text": f"Bascule vers {fb_label} pour contourner la forte demande..."
                            })

                        fb_env = {"GEMINI_API_KEY": self.api_key, "GOOGLE_API_KEY": self.api_key} if self.api_key else None
                        fb_config = LocalAgentConfig(
                            workspaces=[self.workspace],
                            model=fb_target,
                            api_key=self.api_key,
                            env=fb_env,
                            policies=[policy.allow_all()],
                            save_dir=os.path.join(self.workspace, ".antigravity_session"),
                            retry_config=RetryConfig(
                                api_retry=ModelAPIRetryConfig(
                                    max_retries=2,
                                    initial_sleep_duration_ms=1200,
                                    exponential_multiplier=1.8
                                )
                            )
                        )
                        async with Agent(fb_config) as fb_agent:
                            resp = await fb_agent.chat(instruction)
                            fb_summary = await resp.text()
                            if not fb_summary:
                                fb_summary = "Tâche Antigravity exécutée avec succès."
                            if on_progress:
                                await on_progress({
                                    "step": "complete",
                                    "text": f"Développement achevé avec succès via {fb_label}."
                                })
                            return TaskResult(
                                summary=fb_summary,
                                status="completed",
                                model_label=fb_label
                            )
                    except Exception as fb_err:
                        fb_err_str = str(fb_err)
                        print(f"[Antigravity] Modèle {fb_model_name} également indisponible : {fb_err_str[:120]}")
                        console_monitor.record_error(
                            source=f"Antigravity Fallback ({fb_model_name})",
                            message=fb_err_str,
                            level="WARNING"
                        )
                        continue

                # Si tous les modèles de repli ont échoué en raison de la forte demande
                print(f"[Antigravity] Tous les modèles sont saturés par la forte demande actuelle.")
                if on_progress:
                    await on_progress({
                        "step": "error",
                        "text": "Forte demande sur tous les serveurs de modèles disponibles. Interruption sécurisée."
                    })
                return TaskResult(
                    summary="Forte demande générale sur les serveurs Google Antigravity (erreur 503). Tous les modèles testés sont temporairement saturés.",
                    status="overloaded",
                    model_label=self.model_label,
                    error_type="high_demand"
                )

            if on_progress:
                await on_progress({
                    "step": "error",
                    "text": "Une anomalie s'est produite lors de l'exécution. Enregistrement des détails techniques."
                })
            return TaskResult(
                summary=f"Erreur d'exécution Antigravity ({self.model_label}): {err_msg}",
                status="error",
                model_label=self.model_label,
                error_type="error"
            )
