"""backend/services/weekly_improvement_watch.py
Moteur de propositions régulières d'auto-améliorations J.A.R.V.I.S.

Fonctionnement :
1. Collecte les signaux internes :
   - Exceptions et avertissements fréquents capturés par console_monitor.py.
   - Outils lents (latence moy/p95), en échec ou 'claimed_success_without_verification' dans metrics_service.py.
   - Tâches Antigravity bloquées ('stalled'/'timeout') dans ACTIVE_AGY_LOGS.
   - Structure des sous-dossiers et contrats de confinement ARCHITECTURE.md.
2. Formule 1 à 3 propositions d'améliorations à fort impact via une mission parallèle L2 sur le VPS
   (run_l2_parallel_agents + cross_check_l2_results, 100% headless, interdiction stricte de Chrome local ou UI Gemini Web).
3. Chaque proposition contient :
   - title, target_subfolder, recommended_complexity (low|medium|high),
     rationale, ready_to_run_prompt, targeted_tests.
4. Persistance avec déduplication et transmission à Pierre sur Telegram via self_improvement_telegram.py.
5. Déclenchement automatique en 1 clic de self_improve sur le sous-dossier ciblé dès que Pierre clique '✅ Approuver'.
6. Scheduler asynchrone serveur (idempotent, intervalle configurable, 100% headless).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import secrets
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple

import config
from services.agentic_runner import (
    AgentOutput,
    CrossCheckResult,
    L2WorkerMission,
    cross_check_l2_results,
    run_l2_parallel_agents,
)
from services.console_monitor import console_monitor
from services.metrics_service import metrics_service
from services.architecture_service import (
    get_capabilities_ledger_summary,
    verify_capability_not_already_implemented,
    _load_declared_tool_names,
)
from services.self_improvement_telegram import (
    ImprovementProposal,
    SelfImprovementTelegramAdapter,
    telegram_proposal_adapter,
)

try:
    from core.shared_state import ACTIVE_AGY_LOGS
except ImportError:
    ACTIVE_AGY_LOGS: Dict[str, Dict[str, Any]] = {}

logger = logging.getLogger("jarvis.weekly_improvement_watch")

# Sous-dossiers connus et leurs contrats d'architecture
KNOWN_SUBFOLDERS = {
    "backend": "backend/ARCHITECTURE.md",
    "frontend": "frontend/ARCHITECTURE.md",
    "firmware": "firmware/ARCHITECTURE.md",
    "ops": "ops/ARCHITECTURE.md",
    "docs": "docs/ARCHITECTURE.md",
}

VALID_SUBFOLDER_PREFIXES = (
    "backend",
    "frontend",
    "firmware",
    "ops",
    "docs",
)

# Lexique strictement banni (anti-coaching personnel / sport / bien-être hors-sujet)
BANNED_LIFESTYLE_KEYWORDS = (
    "faire du sport",
    "faire plus de sport",
    "séance de sport",
    "seance de sport",
    "hydratation",
    "boire de l'eau",
    "sommeil",
    "mieux dormir",
    "méditation",
    "meditation",
    "régime alimentaire",
    "regime alimentaire",
    "musculation",
    "cardio",
    "course à pied",
    "étirement",
    "etirement",
    "bien-être personnel",
    "developpement personnel",
    "développement personnel",
    "nutrition",
    "calories",
    "yoga",
    "pompes",
    "abdos",
    "marche quotidienne",
)


def validate_technical_proposal(proposal: "ImprovementWatchProposal") -> Tuple[bool, str]:
    """Vérifie qu'une proposition d'auto-amélioration est :
    1. Strictement logicielle/architecturale (aucun conseil personnel, sportif ou lifestyle).
    2. Ciblée sur un vrai sous-dossier du dépôt (backend, frontend, ops, firmware, docs).
    3. Non redondante avec les outils déjà implémentés dans CAPABILITIES_LEDGER.md et declarations.py.
    """
    combined_text = f"{proposal.title} {proposal.rationale} {proposal.ready_to_run_prompt}".lower()
    for banned in BANNED_LIFESTYLE_KEYWORDS:
        if banned in combined_text:
            return False, f"Rejet anti-coaching : mot-clé personnel/lifestyle hors-sujet détecté ('{banned}')."

    # Rejet si le mot 'sport' apparaît isolément comme conseil de vie (hors itinéraire GPS 'salle de sport')
    if re.search(r"\bsport\b", combined_text) and "salle de sport" not in combined_text:
        return False, "Rejet anti-coaching : proposition orientée sport/lifestyle au lieu du code de Jarvis."

    sub = (proposal.target_subfolder or "").strip().replace("\\", "/").lstrip("./")
    if not sub or not any(sub == p or sub.startswith(f"{p}/") for p in VALID_SUBFOLDER_PREFIXES):
        return False, f"Sous-dossier cible invalide ou hors du dépôt : '{proposal.target_subfolder}'."

    is_not_dup, reason = verify_capability_not_already_implemented(
        proposal.title,
        proposal.targeted_tests,
    )
    if not is_not_dup:
        return False, f"Capacité déjà implémentée : {reason}"

    return True, "Proposition technique validée."


# ─── Dataclass de Proposition de Veille ───────────────────────────────────────
@dataclass
class ImprovementWatchProposal:
    """Représentation d'une opportunité d'auto-amélioration identifiée par la veille."""

    proposal_id: str
    title: str
    target_subfolder: str
    recommended_complexity: str  # "low" | "medium" | "high"
    rationale: str
    ready_to_run_prompt: str
    targeted_tests: List[str] = field(default_factory=list)
    fingerprint: str = ""
    status: str = "proposed"  # proposed | approved | rejected | running | completed | failed
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.fingerprint:
            self.fingerprint = self.compute_fingerprint(self.target_subfolder, self.title)

    @staticmethod
    def compute_fingerprint(subfolder: str, title: str) -> str:
        """Calcule une empreinte déterministe pour éviter les propositions redondantes."""
        normalized = f"{subfolder.strip().lower()}:{title.strip().lower()}"
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ImprovementWatchProposal:
        d = dict(data)
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_telegram_proposal(self) -> ImprovementProposal:
        """Convertit en ImprovementProposal pour l'adaptateur Telegram interactif."""
        clean_sub = self.target_subfolder.replace("/", "-").replace("\\", "-")
        branch_name = f"watch/{clean_sub}-{self.proposal_id}"
        test_summary = f"Tests ciblés : {', '.join(self.targeted_tests)}" if self.targeted_tests else "Tests unitaires du sous-dossier"
        diff_text = f"💡 Rationale :\n{self.rationale}\n\n🎯 Prompt prêt à l'exécution :\n{self.ready_to_run_prompt}"

        return ImprovementProposal(
            proposal_id=self.proposal_id,
            goal=self.title,
            subfolder=self.target_subfolder,
            model_used=f"gemini-2.5-flash (L2 Watch - {self.recommended_complexity})",
            diff_summary=diff_text,
            diff_line_count=0,
            pytest_results=test_summary,
            tests_passed=True,
            branch_name=branch_name,
            modified_files=self.targeted_tests,
            status=self.status,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


# ─── Persistance & Déduplication ─────────────────────────────────────────────
class WeeklyImprovementWatchStore:
    """Gestionnaire de persistance et de déduplication des propositions de veille."""

    def __init__(self, storage_path: Optional[str] = None):
        if storage_path is None:
            base_dir = getattr(
                config,
                "BASE_DIR",
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            )
            data_dir = os.path.join(base_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            self.storage_path = os.path.join(data_dir, "weekly_improvement_watch.json")
        else:
            self.storage_path = storage_path
            parent = os.path.dirname(os.path.abspath(storage_path))
            if parent:
                os.makedirs(parent, exist_ok=True)

        self._proposals: Dict[str, ImprovementWatchProposal] = {}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.storage_path):
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                prop = ImprovementWatchProposal.from_dict(item)
                self._proposals[prop.proposal_id] = prop
        except Exception as e:
            logger.warning(f"[WeeklyImprovementWatchStore] Échec lecture storage : {e}")

    def _save(self) -> None:
        try:
            tmp_path = f"{self.storage_path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump([p.to_dict() for p in self._proposals.values()], f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.storage_path)
        except Exception as e:
            logger.error(f"[WeeklyImprovementWatchStore] Échec sauvegarde storage : {e}")

    def save(self, proposal: ImprovementWatchProposal) -> None:
        proposal.updated_at = time.time()
        self._proposals[proposal.proposal_id] = proposal
        self._save()

    def get(self, proposal_id: str) -> Optional[ImprovementWatchProposal]:
        return self._proposals.get(proposal_id)

    def list_all(self) -> List[ImprovementWatchProposal]:
        return list(self._proposals.values())

    def list_active(self) -> List[ImprovementWatchProposal]:
        return [p for p in self._proposals.values() if p.status in ("proposed", "approved", "running")]

    def is_duplicate(self, fingerprint: str, cooldown_days: float = 7.0) -> bool:
        """Vérifie si une proposition similaire existe déjà dans la fenêtre de cooldown."""
        cutoff = time.time() - (cooldown_days * 86400)
        for p in self._proposals.values():
            if p.fingerprint == fingerprint and p.created_at >= cutoff and p.status != "rejected":
                return True
        return False


# ─── Collecteur de Signaux Internes ──────────────────────────────────────────
class InternalSignalsCollector:
    """Collecte et qualifie les métriques, erreurs et contrats du workspace."""

    def __init__(self, repo_root: Optional[str] = None):
        self.repo_root = repo_root or getattr(
            config,
            "BASE_DIR",
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        )

    def collect_console_signals(self) -> Dict[str, Any]:
        """Capture les exceptions et warnings fréquents depuis console_monitor."""
        errors = console_monitor.get_recent_errors(limit=80)
        source_counts: Dict[str, int] = {}
        patterns: List[str] = []

        for e in errors:
            src = e.get("source", "unknown")
            source_counts[src] = source_counts.get(src, 0) + 1
            msg = e.get("message", "")
            if msg and msg not in patterns and len(patterns) < 5:
                patterns.append(f"[{src}] {msg[:90]}")

        return {
            "total_recent_errors": len(errors),
            "errors_by_source": source_counts,
            "sample_patterns": patterns,
        }

    async def collect_telemetry_signals(self, window_str: str = "7d") -> Dict[str, Any]:
        """Collecte les latences, taux d'échec et anomalies de metrics_service."""
        try:
            summary = await metrics_service.get_metrics_summary(window_str)
        except Exception as e:
            logger.debug(f"[InternalSignalsCollector] metrics fallback memory : {e}")
            summary = metrics_service._compute_memory_summary(
                cutoff=time.time() - (7 * 86400), window_str="7d", duration=None  # type: ignore
            ) if hasattr(metrics_service, "_compute_memory_summary") else {}

        tools_summary = summary.get("tools_summary", [])
        slow_tools = [
            t for t in tools_summary
            if t.get("p95_latency_ms", 0) >= 2000 or t.get("avg_latency_ms", 0) >= 1200
        ]
        failing_tools = [
            t for t in tools_summary
            if t.get("failure_rate", 0) > 0.05 or t.get("failures", 0) > 0 or t.get("timeouts", 0) > 0
        ]

        claimed_success_count = getattr(
            metrics_service, "claimed_success_without_verification", 0
        )
        if callable(claimed_success_count):
            claimed_success_count = claimed_success_count()

        # Analyse des tâches Antigravity bloquées ou en timeout dans ACTIVE_AGY_LOGS
        stalled_tasks = []
        timeout_tasks = []
        now = time.monotonic()
        for tid, entry in list(ACTIVE_AGY_LOGS.items()):
            st = str(entry.get("status", "")).lower()
            last_out = entry.get("last_output_at", 0)
            if st == "timeout":
                timeout_tasks.append(tid)
            elif st == "stalled" or (last_out and (now - last_out) > 120 and st == "running"):
                stalled_tasks.append(tid)

        return {
            "window": window_str,
            "total_calls": summary.get("total_calls", 0),
            "global_failure_rate": summary.get("global_failure_rate", 0.0),
            "slow_tools": slow_tools,
            "failing_tools": failing_tools,
            "claimed_success_without_verification": claimed_success_count,
            "stalled_tasks_count": len(stalled_tasks),
            "timeout_tasks_count": len(timeout_tasks),
        }

    def collect_architecture_contracts(self) -> Dict[str, Any]:
        """Inspecte les sous-dossiers et l'existence des contrats ARCHITECTURE.md."""
        contracts_found = {}
        for sub, rel_path in KNOWN_SUBFOLDERS.items():
            full_path = os.path.join(self.repo_root, rel_path)
            contracts_found[sub] = {
                "contract_file": rel_path,
                "exists": os.path.exists(full_path),
            }

        return {
            "repo_root": self.repo_root,
            "subfolders": contracts_found,
        }

    async def collect_all_signals(self) -> Dict[str, Any]:
        """Agrège l'ensemble des signaux internes, du code réel et de CAPABILITIES_LEDGER.md pour la synthèse L2."""
        console_sig = self.collect_console_signals()
        telemetry_sig = await self.collect_telemetry_signals()
        arch_sig = self.collect_architecture_contracts()
        ledger_summary = get_capabilities_ledger_summary()
        declared_tools = _load_declared_tool_names()

        services_dir = os.path.join(self.repo_root, "backend", "services")
        routers_dir = os.path.join(self.repo_root, "backend", "routers")
        tools_dir = os.path.join(self.repo_root, "backend", "core", "tools")

        code_inventory = {
            "declared_tools_count": len(declared_tools),
            "declared_tools": declared_tools,
            "services_files": sorted([f for f in os.listdir(services_dir) if f.endswith(".py")]) if os.path.isdir(services_dir) else [],
            "routers_files": sorted([f for f in os.listdir(routers_dir) if f.endswith(".py")]) if os.path.isdir(routers_dir) else [],
            "tools_files": sorted([f for f in os.listdir(tools_dir) if f.endswith(".py")]) if os.path.isdir(tools_dir) else [],
        }

        return {
            "timestamp": time.time(),
            "console": console_sig,
            "telemetry": telemetry_sig,
            "architecture": arch_sig,
            "code_inventory": code_inventory,
            "capabilities_ledger_excerpt": ledger_summary[:3500] if ledger_summary else "",
        }


# ─── Moteur de Formulation L2 Parallèle ──────────────────────────────────────
class L2ImprovementFormulator:
    """Orchestre la mission L2 Flash/Pro parallèle sur le VPS pour formuler 1 à 3 propositions."""

    def __init__(
        self,
        custom_exec_fn: Optional[Callable] = None,
        agent_timeout: float = 60.0,
    ):
        self.custom_exec_fn = custom_exec_fn
        self.agent_timeout = agent_timeout

    def _build_l2_missions(self, signals_summary: str) -> List[L2WorkerMission]:
        """Définit les missions spécialisées L2 (100% headless, interdiction de Chrome local/UI Gemini)."""
        return [
            L2WorkerMission(
                worker_id="telemetry_analyst",
                role="critic",
                mission=(
                    "Analyse les signaux de télémétrie de Jarvis (erreurs console, latences d'outils, "
                    "claimed_success_without_verification, tâches stalled/timeout). Identifie les 2 anomalies "
                    f"les plus critiques : {signals_summary}"
                ),
                effort="medium",
                timeout=self.agent_timeout,
            ),
            L2WorkerMission(
                worker_id="architecture_critic",
                role="critic",
                mission=(
                    "Examine les sous-dossiers de Jarvis (backend, frontend, ops, firmware, docs) et leurs contrats "
                    "ARCHITECTURE.md. Détermine quel sous-dossier présente le risque le plus élevé ou la plus forte "
                    f"opportunité de simplification sans régression : {signals_summary}"
                ),
                effort="medium",
                timeout=self.agent_timeout,
            ),
            L2WorkerMission(
                worker_id="proposal_synthesizer",
                role="architect",
                mission=(
                    "RÈGLE STRICTE : L'auto-amélioration désigne EXCLUSIVEMENT l'amélioration logicielle et "
                    "architecturale du code source Python/JS/Firmware de J.A.R.V.I.S. INTERDICTION ABSOLUE de "
                    "proposer des conseils personnels, sportifs, santé ou lifestyle à l'utilisateur, et INTERDICTION "
                    "de reproposer un outil déjà listé dans CAPABILITIES_LEDGER.md. "
                    "Synthétise 1 à 3 propositions concrètes d'améliorations techniques sous forme d'un tableau JSON strict. "
                    "Chaque élément doit comporter : title, target_subfolder, recommended_complexity (low|medium|high), "
                    "rationale (ou technical_rationale), expected_benefit, files_to_modify_or_create, ready_to_run_prompt, targeted_tests. "
                    f"Signaux d'entrée : {signals_summary}"
                ),
                effort="high",
                timeout=self.agent_timeout,
            ),
        ]

    def _parse_proposals_from_text(self, text: str) -> List[Dict[str, Any]]:
        """Extrait résilientement la liste JSON des propositions depuis la sortie LLM."""
        if not text:
            return []

        # 1. Recherche d'un bloc de code json
        code_block = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
        candidate = code_block.group(1) if code_block else None

        # 2. Recherche directe d'un tableau JSON
        if not candidate:
            array_match = re.search(r"(\[\s*\{.*?\}\s*\])", text, re.DOTALL)
            if array_match:
                candidate = array_match.group(1)

        if candidate:
            try:
                # Nettoyage des virgules pendantes
                cleaned = re.sub(r",\s*([\]}])", r"\1", candidate)
                data = json.loads(cleaned)
                if isinstance(data, list):
                    return data
            except Exception as e:
                logger.debug(f"[L2ImprovementFormulator] Échec parsing JSON extrait : {e}")

        return []

    def _generate_rule_based_fallback(self, signals: Dict[str, Any]) -> List[ImprovementWatchProposal]:
        """Génère 1 à 3 propositions déterministes si L2 est offline ou sans JSON valide."""
        proposals: List[ImprovementWatchProposal] = []
        telemetry = signals.get("telemetry", {})
        console = signals.get("console", {})

        # Règle 1 : Outils lents ou en échec
        slow_tools = telemetry.get("slow_tools", [])
        failing_tools = telemetry.get("failing_tools", [])
        if slow_tools or failing_tools:
            tool_entry = (failing_tools or slow_tools)[0]
            t_name = tool_entry.get("tool_name", "tool_service")
            lat = tool_entry.get("p95_latency_ms", tool_entry.get("avg_latency_ms", 0))
            fails = tool_entry.get("failures", 0)
            pid = f"watch_prop_{secrets.token_hex(4)}"
            proposals.append(
                ImprovementWatchProposal(
                    proposal_id=pid,
                    title=f"Optimisation de la résilience et des performances de {t_name}",
                    target_subfolder="backend/core/tools",
                    recommended_complexity="low",
                    rationale=f"Télémétrie : {t_name} présente une latence p95 de {lat:.0f}ms et {fails} échec(s) récent(s).",
                    ready_to_run_prompt=(
                        f"Refactoriser l'outil '{t_name}' dans backend/core/tools pour intégrer un timeout adaptatif, "
                        "un cache de résultats et une gestion d'erreur robuste sans bloquer le loop asyncio."
                    ),
                    targeted_tests=["backend/tests/unit/test_tools_resilience.py"],
                )
            )

        # Règle 2 : Succès sans vérification indépendante
        claimed_success = telemetry.get("claimed_success_without_verification", 0)
        if claimed_success > 0 and len(proposals) < 3:
            pid = f"watch_prop_{secrets.token_hex(4)}"
            proposals.append(
                ImprovementWatchProposal(
                    proposal_id=pid,
                    title="Renforcement du protocole de vérification des outils (anti faux-succès)",
                    target_subfolder="backend/services",
                    recommended_complexity="medium",
                    rationale=f"{claimed_success} appel(s) d'outils ont affirmé un succès sans validation indépendante.",
                    ready_to_run_prompt=(
                        "Améliorer metrics_service.py et tool_dispatcher pour imposer une vérification "
                        "systématique des effets de bord avant d'affirmer le statut 'success'."
                    ),
                    targeted_tests=["backend/tests/unit/test_metrics_service.py"],
                )
            )

        # Règle 3 : Exceptions récurrentes console
        errors_by_src = console.get("errors_by_source", {})
        if errors_by_src and len(proposals) < 3:
            top_src = max(errors_by_src.items(), key=lambda x: x[1])
            pid = f"watch_prop_{secrets.token_hex(4)}"
            subfolder = "backend/services" if "service" in top_src[0] else "backend"
            proposals.append(
                ImprovementWatchProposal(
                    proposal_id=pid,
                    title=f"Élimination des avertissements récurrents dans {top_src[0]}",
                    target_subfolder=subfolder,
                    recommended_complexity="low",
                    rationale=f"Le moniteur de console rapporte {top_src[1]} occurrence(s) d'anomalies dans la source '{top_src[0]}'.",
                    ready_to_run_prompt=(
                        f"Stabiliser le module '{top_src[0]}' en ajoutant des gardes-fous et une journalisation "
                        "propre pour éviter toute cascade d'exceptions dans la console."
                    ),
                    targeted_tests=["backend/tests/unit/test_console_monitor.py"],
                )
            )

        # Règle de repli absolu si aucun signal d'erreur
        if not proposals:
            pid = f"watch_prop_{secrets.token_hex(4)}"
            proposals.append(
                ImprovementWatchProposal(
                    proposal_id=pid,
                    title="Revue de robustesse et couverture de tests du moteur d'auto-amélioration",
                    target_subfolder="backend/services",
                    recommended_complexity="low",
                    rationale="Tous les systèmes sont nominaux ; optimisation proactive de la suite de tests.",
                    ready_to_run_prompt=(
                        "Ajouter des tests unitaires de cas limites sur self_improvement_service.py et "
                        "weekly_improvement_watch.py pour garantir la fiabilité continue."
                    ),
                    targeted_tests=["backend/tests/unit/test_weekly_improvement_watch.py"],
                )
            )

        return proposals[:3]

    async def formulate_proposals(self, signals: Dict[str, Any]) -> List[ImprovementWatchProposal]:
        """Formule 1 à 3 propositions via L2 avec bascule propre sur heuristiques de repli."""
        signals_summary = json.dumps(
            {
                "console": signals.get("console"),
                "telemetry": signals.get("telemetry"),
                "subfolders": list(signals.get("architecture", {}).get("subfolders", {}).keys()),
            },
            ensure_ascii=False,
        )

        missions = self._build_l2_missions(signals_summary)
        goal = "Veille hebdomadaire d'auto-amélioration continue J.A.R.V.I.S."

        raw_parsed: List[Dict[str, Any]] = []

        try:
            l2_res = await run_l2_parallel_agents(
                goal=goal,
                worker_missions=missions,
                max_workers=3,
                max_iterations=1,
                agent_timeout=self.agent_timeout,
                global_timeout=self.agent_timeout * 2,
                custom_exec_fn=self.custom_exec_fn,
            )

            # Audit croisé entre les agents L2
            all_outputs = list(l2_res.successful_agents)
            if l2_res.synthesis:
                all_outputs.append(l2_res.synthesis)
            cross_check = cross_check_l2_results(all_outputs)
            logger.info(f"[WeeklyWatch L2] Cross-check score: {cross_check.agreement_score} (passed={cross_check.passed})")

            # Récupération de la sortie du synthétiseur
            synth_text = l2_res.synthesis.conclusion if l2_res.synthesis else ""
            if not synth_text:
                for a in l2_res.successful_agents:
                    if a.worker_id == "proposal_synthesizer" or "title" in a.conclusion:
                        synth_text = a.conclusion
                        break

            raw_parsed = self._parse_proposals_from_text(synth_text)
        except Exception as e:
            logger.warning(f"[L2ImprovementFormulator] Exécution L2 impossible ou échouée : {e}. Utilisation du fallback.")

        proposals: List[ImprovementWatchProposal] = []
        for item in raw_parsed:
            if not isinstance(item, dict) or "title" not in item:
                continue
            pid = f"watch_prop_{secrets.token_hex(4)}"
            complexity = str(item.get("recommended_complexity") or item.get("complexity") or "medium").lower()
            rationale = str(item.get("rationale") or item.get("technical_rationale") or "Détecté par analyse L2")
            expected_benefit = str(item.get("expected_benefit") or "")
            files_to_mod = item.get("files_to_modify_or_create") or item.get("targeted_tests") or []
            if isinstance(files_to_mod, str):
                files_to_mod = [files_to_mod]
            prop = ImprovementWatchProposal(
                proposal_id=pid,
                title=str(item.get("title", "Amélioration recommandée")),
                target_subfolder=str(item.get("target_subfolder", "backend/services")),
                recommended_complexity=complexity,
                rationale=f"{rationale} — Bénéfice attendu : {expected_benefit}" if expected_benefit else rationale,
                ready_to_run_prompt=str(item.get("ready_to_run_prompt", "")),
                targeted_tests=list(item.get("targeted_tests") or files_to_mod),
                metadata={
                    "files_to_modify_or_create": list(files_to_mod),
                    "expected_benefit": expected_benefit,
                    "technical_rationale": rationale,
                },
            )
            valid_prop, reject_reason = validate_technical_proposal(prop)
            if not valid_prop:
                logger.info(f"[L2ImprovementFormulator] Proposition rejetée ('{prop.title}') : {reject_reason}")
                continue
            proposals.append(prop)

        if not proposals:
            fallback_candidates = self._generate_rule_based_fallback(signals)
            for fc in fallback_candidates:
                ok_fc, _ = validate_technical_proposal(fc)
                if ok_fc:
                    proposals.append(fc)

        return proposals[:3]


# ─── Service Central de Veille & Scheduler Asynchrone ────────────────────────
class WeeklyImprovementWatchService:
    """Service central et scheduler asynchrone pour la veille régulière d'améliorations."""

    def __init__(
        self,
        store: Optional[WeeklyImprovementWatchStore] = None,
        telegram_adapter_instance: Optional[SelfImprovementTelegramAdapter] = None,
        collector: Optional[InternalSignalsCollector] = None,
        formulator: Optional[L2ImprovementFormulator] = None,
        self_improve_runner: Optional[Callable[..., Coroutine[Any, Any, Any]]] = None,
        interval_seconds: float = 7 * 86400.0,
    ):
        self.store = store or WeeklyImprovementWatchStore()
        self.telegram_adapter = telegram_adapter_instance or telegram_proposal_adapter
        self.collector = collector or InternalSignalsCollector()
        self.formulator = formulator or L2ImprovementFormulator()
        self.self_improve_runner = self_improve_runner
        self.interval_seconds = interval_seconds

        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._lock = asyncio.Lock()

        # Enregistrement du hook sur l'adaptateur Telegram pour déclencher l'auto-amélioration en 1 clic
        if hasattr(self.telegram_adapter, "on_approved_hook"):
            self.telegram_adapter.on_approved_hook = self.on_telegram_proposal_approved

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    async def run_scan(self) -> List[ImprovementWatchProposal]:
        """Exécute un cycle complet de veille d'auto-amélioration."""
        async with self._lock:
            logger.info("[WeeklyImprovementWatch] Démarrage du scan d'améliorations...")

            # 1. Collecte des signaux internes
            signals = await self.collector.collect_all_signals()

            # 2. Formulation via L2 (ou heuristiques de repli)
            proposals = await self.formulator.formulate_proposals(signals)

            # 3. Filtrage anti-coaching, anti-doublon ledger et déduplication
            retained: List[ImprovementWatchProposal] = []
            for p in proposals:
                valid_tech, reason = validate_technical_proposal(p)
                if not valid_tech:
                    logger.info(f"[WeeklyImprovementWatch] Proposition invalide rejetée ('{p.title}') : {reason}")
                    continue
                if self.store.is_duplicate(p.fingerprint, cooldown_days=7.0):
                    logger.info(f"[WeeklyImprovementWatch] Proposition dédupliquée ignorée : '{p.title}'")
                    continue
                retained.append(p)
                self.store.save(p)

            # 4. Envoi des propositions retenues à Pierre sur Telegram
            for p in retained:
                ip = p.to_telegram_proposal()
                sent, mid, msg = await self.telegram_adapter.send_proposal(ip)
                if sent:
                    logger.info(f"[WeeklyImprovementWatch] Proposition '{p.proposal_id}' envoyée sur Telegram (msg_id={mid})")
                else:
                    logger.debug(f"[WeeklyImprovementWatch] Proposition '{p.proposal_id}' non envoyée : {msg}")

            logger.info(f"[WeeklyImprovementWatch] Scan terminé : {len(retained)} proposition(s) transmise(s).")
            return retained

    async def on_telegram_proposal_approved(self, proposal: ImprovementProposal) -> None:
        """Déclenche automatiquement self_improve dès que Pierre clique '✅ Approuver'."""
        watch_prop = self.store.get(proposal.proposal_id)
        target_subfolder = watch_prop.target_subfolder if watch_prop else proposal.subfolder
        prompt_to_run = watch_prop.ready_to_run_prompt if watch_prop else proposal.goal
        complexity = watch_prop.recommended_complexity if watch_prop else "medium"

        logger.info(
            f"[WeeklyImprovementWatch] Proposition '{proposal.proposal_id}' APPROUVÉE ! "
            f"Lancement de self_improve sur '{target_subfolder}' (complexité: {complexity})."
        )

        if watch_prop:
            watch_prop.status = "approved"
            self.store.save(watch_prop)

        runner = self.self_improve_runner
        if runner is None:
            try:
                from services.self_improvement_service import run_self_improvement
                runner = run_self_improvement
            except Exception as e:
                logger.error(f"[WeeklyImprovementWatch] Impossible d'importer run_self_improvement : {e}")
                return

        # Lancement asynchrone non-bloquant pour ne pas figer le webhook Telegram
        async def _exec():
            try:
                if watch_prop:
                    watch_prop.status = "running"
                    self.store.save(watch_prop)
                await runner(
                    goal=prompt_to_run,
                    target_subfolder=target_subfolder,
                    complexity=complexity,
                    create_pr=True,
                )
                if watch_prop:
                    watch_prop.status = "completed"
                    self.store.save(watch_prop)
            except Exception as ex:
                logger.error(f"[WeeklyImprovementWatch] Erreur exécution self_improve : {ex}")
                if watch_prop:
                    watch_prop.status = "failed"
                    self.store.save(watch_prop)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_exec(), name=f"self_improve_watch_{proposal.proposal_id}")
        except RuntimeError:
            pass

    async def _loop(self) -> None:
        """Boucle périodique du scheduler de veille."""
        while self._running:
            try:
                await self.run_scan()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[WeeklyImprovementWatch] Erreur lors du cycle de veille : {e}")

            try:
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                break

    def start(self, interval_seconds: Optional[float] = None) -> bool:
        """Démarre le scheduler asynchrone de manière idempotente."""
        if interval_seconds:
            self.interval_seconds = interval_seconds

        if self.is_running:
            logger.info("[WeeklyImprovementWatch] Scheduler déjà actif.")
            return False

        self._running = True
        try:
            loop = asyncio.get_running_loop()
            self._task = loop.create_task(self._loop(), name="weekly_improvement_watch_scheduler")
            logger.info(f"[WeeklyImprovementWatch] Scheduler démarré (intervalle: {self.interval_seconds}s).")
            return True
        except RuntimeError:
            logger.warning("[WeeklyImprovementWatch] Pas de loop asyncio en cours.")
            return False

    def stop(self) -> bool:
        """Arrête proprement le scheduler."""
        if not self._running:
            return False

        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("[WeeklyImprovementWatch] Scheduler arrêté.")
            return True
        return False


# Alias pour compatibilité
WeeklyImprovementWatchScheduler = WeeklyImprovementWatchService

# Singleton global
weekly_improvement_watch_service = WeeklyImprovementWatchService()


async def generate_and_send_technical_improvements(
    focus_area: str = "",
    count: int = 3,
    trigger_source: str = "manual",
    service_instance: Optional[WeeklyImprovementWatchService] = None,
) -> Dict[str, Any]:
    """Fonction maîtresse en 4 étapes :
    1. Audit interne du code réel et de CAPABILITIES_LEDGER.md + télémétrie/erreurs.
    2. Vraie recherche technique L2 via agents Antigravity (agy) sur le VPS (zéro coaching personnel).
    3. Vérification anti-doublon (verify_capability_not_already_implemented) & validation lexicale anti-coaching.
    4. Envoi sur Telegram avec boutons d'action directe (✅ Approuver, ❌ Rejeter, ✏️ Modifier).
    """
    svc = service_instance or weekly_improvement_watch_service

    # Étape 1 : Audit interne du code, de CAPABILITIES_LEDGER.md et de la télémétrie
    signals = await svc.collector.collect_all_signals()
    if focus_area:
        signals["focus_area"] = focus_area
    signals["trigger_source"] = trigger_source

    # Étape 2 : Recherche technique L2 via agents Antigravity (ou repli déterministe si hors-ligne)
    raw_proposals = await svc.formulator.formulate_proposals(signals)

    # Étape 3 : Filtrage strict (anti-coaching + anti-doublon CAPABILITIES_LEDGER.md + sous-dossier valide)
    validated: List[ImprovementWatchProposal] = []
    rejected: List[Dict[str, str]] = []

    for prop in raw_proposals:
        if focus_area and focus_area.strip():
            norm_focus = focus_area.strip().replace("\\", "/").lstrip("./")
            if any(norm_focus.startswith(p) for p in VALID_SUBFOLDER_PREFIXES):
                prop.target_subfolder = norm_focus

        ok_tech, reason = validate_technical_proposal(prop)
        if not ok_tech:
            rejected.append({"title": prop.title, "reason": reason})
            continue

        # En mode manuel ('propose'), on évite de bloquer si Pierre redemande explicitement des idées,
        # mais en mode automatique ('scheduler') on applique le cooldown de 7 jours.
        if trigger_source != "manual" and svc.store.is_duplicate(prop.fingerprint, cooldown_days=7.0):
            rejected.append({"title": prop.title, "reason": "Déjà proposée au cours des 7 derniers jours."})
            continue

        validated.append(prop)
        svc.store.save(prop)
        if len(validated) >= max(1, count):
            break

    # Si toutes les propositions L2 ont été filtrées, compléter avec les propositions techniques de repli
    if not validated:
        for fb in svc.formulator._generate_rule_based_fallback(signals):
            ok_fb, _ = validate_technical_proposal(fb)
            if ok_fb:
                validated.append(fb)
                svc.store.save(fb)
                if len(validated) >= max(1, count):
                    break

    # Étape 4 : Envoi sur Telegram avec boutons inline (✅ Approuver, ❌ Rejeter, ✏️ Modifier)
    sent_message_ids: List[int] = []
    telegram_errors: List[str] = []
    for p in validated:
        tg_prop = p.to_telegram_proposal()
        sent, mid, msg = await svc.telegram_adapter.send_proposal(tg_prop)
        if sent and mid is not None:
            sent_message_ids.append(mid)
        else:
            telegram_errors.append(msg)

    return {
        "status": "ok",
        "trigger_source": trigger_source,
        "focus_area": focus_area,
        "count": len(validated),
        "sent_count": len(sent_message_ids),
        "sent_message_ids": sent_message_ids,
        "proposals": [p.to_dict() for p in validated],
        "rejected_proposals": rejected,
        "telegram_errors": telegram_errors,
    }
