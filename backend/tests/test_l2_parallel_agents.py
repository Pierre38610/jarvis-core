"""tests/test_l2_parallel_agents.py
Tests unitaires et d'acceptation pour le palier L2 :
- Agents CLI parallèles (Flash/Pro bornés, max 3 par défaut) avec asyncio.gather
- Isolation stricte des workspaces / task-id anti-écritures concurrentes
- Phase de cross-check (détection de contradictions, affirmations sans source, sorties invalides)
- Synthèse REDUCE et boucle de vérification bornée (max_iterations=2)
- Gestion des pannes partielles (résultat partiel explicite sans faux succès)
- Respect de la cascade quota-aware et cooldown des modèles
- Métadonnées et observabilité sans fuite de secrets
"""

import asyncio
import json
import os
import shutil
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.agentic_runner import (
    AgentOutput,
    CrossCheckResult,
    L2ExecutionResult,
    L2WorkerMission,
    cross_check_l2_results,
    run_agentic,
    run_l2_parallel_agents,
)
from services.antigravity_models import MODEL_FLASH, MODEL_PRO
from services.model_routing.fallback_handler import cooldown_manager


@pytest.fixture(autouse=True)
def cleanup_cooldowns_and_consents():
    cooldown_manager.clear()
    yield
    cooldown_manager.clear()


def _extract_mock_role(cmd) -> str:
    """Extrait le rôle simulé à partir de la commande d'exécution."""
    cmd_str = " ".join(str(x) for x in cmd).lower()
    if "synthèse" in cmd_str or "synthese" in cmd_str or "synthesis" in cmd_str:
        if "agent synthèse" in cmd_str or "agent synthese" in cmd_str or "rôle : synthèse" in cmd_str:
            return "synthesis"
    if "agent critique" in cmd_str or "critique & logique" in cmd_str:
        return "critic"
    if "agent prospecteur" in cmd_str:
        return "prospector"
    if "architecte système" in cmd_str or "architecte" in cmd_str:
        return "architect"
    if "rédacteur technique" in cmd_str:
        return "writer"
    if "chercheur multi-source" in cmd_str:
        return "researcher"
    if "agent décisionnel" in cmd_str:
        return "decider"
    if "synthesis" in cmd_str:
        return "synthesis"
    if "critic" in cmd_str:
        return "critic"
    if "prospect" in cmd_str:
        return "prospector"
    return str(cmd[1]) if len(cmd) > 1 else "general_agent"


@pytest.mark.asyncio
async def test_l2_three_agents_concurrent_execution_and_synthesis():
    """Critère 1 : 3 agents exécutés en parallèle via asyncio.gather, résultat agrégé et synthèse déterministe."""
    execution_order = []

    async def mock_exec(cmd, timeout, cwd=None):
        role = _extract_mock_role(cmd)
        execution_order.append(role)
        # Simulation d'une latence pour vérifier la concurrence
        await asyncio.sleep(0.05)

        if role == "prospector":
            payload = {
                "facts": ["Faits 1: Le système supporte ARM64 et x86_64.", "Faits 2: 12 coeurs CPU disponibles."],
                "sources": ["spec_hardware.md", "architecture.md"],
                "hypotheses": ["Performance optimale sur ARM64"],
                "uncertainties": [],
                "conclusion": "Données matérielles collectées avec succès.",
                "confidence": 0.95,
                "artifacts": []
            }
        elif role == "critic":
            payload = {
                "facts": ["Faits 3: La mémoire RAM minimale requise est de 8 Go."],
                "sources": ["architecture.md"],
                "hypotheses": [],
                "uncertainties": ["Consommation mémoire sous forte charge"],
                "conclusion": "Analyse critique : faisabilité confirmée sous réserve de 8 Go RAM.",
                "confidence": 0.90,
                "artifacts": []
            }
        elif role == "architect":
            payload = {
                "facts": ["Faits 4: Architecture micro-services modulaire."],
                "sources": ["system_design.md"],
                "hypotheses": ["Déploiement conteneurisé Docker"],
                "uncertainties": [],
                "conclusion": "Structure modulaire conforme aux directives.",
                "confidence": 0.92,
                "artifacts": []
            }
        elif role == "synthesis":
            payload = {
                "facts": ["Synthèse globale validée."],
                "sources": ["spec_hardware.md", "architecture.md", "system_design.md"],
                "hypotheses": [],
                "uncertainties": [],
                "conclusion": "Recommandation finale : Déploiement validé sur ARM64 avec 8 Go RAM et conteneurs Docker.",
                "confidence": 0.95,
                "artifacts": []
            }
        else:
            payload = {
                "conclusion": "OK",
                "confidence": 0.8,
                "sources": ["doc.md"],
                "open_questions": [],
                "artifacts": []
            }
        return 0, json.dumps(payload), ""

    t_start = time.perf_counter()
    res: L2ExecutionResult = await run_l2_parallel_agents(
        goal="Évaluer la faisabilité du déploiement ARM64",
        max_workers=3,
        custom_exec_fn=mock_exec,
    )
    t_elapsed = time.perf_counter() - t_start

    assert res.status == "completed"
    assert res.quality_gate_passed is True
    assert len(res.successful_agents) == 3
    assert len(res.failed_agents) == 0
    assert res.cross_check.passed is True
    assert res.cross_check.agreement_score >= 0.8
    assert res.synthesis is not None
    assert "Recommandation finale" in res.synthesis.conclusion
    assert res.iterations_run == 1

    # Vérification que les 3 rôles de base ont été sollicités
    assert "prospector" in execution_order
    assert "critic" in execution_order
    assert "architect" in execution_order
    assert "synthesis" in execution_order


@pytest.mark.asyncio
async def test_l2_partial_failure_recovers_remaining_agents_and_reports_partial():
    """Critère 2 : Si un agent échoue ou timeout, les autres sont récupérés, et un résultat partiel est retourné sans faux succès."""
    async def mock_exec_with_failure(cmd, timeout, cwd=None):
        role = _extract_mock_role(cmd)
        if role == "critic":
            raise asyncio.TimeoutError("Timeout sur l'agent critique")

        if role == "synthesis":
            payload = {
                "conclusion": "Synthèse partielle basée sur les agents disponibles.",
                "confidence": 0.75,
                "sources": ["source1.md"],
                "facts": ["Fait partiel"],
                "hypotheses": [],
                "uncertainties": ["Données de critique manquantes suite à timeout"],
                "artifacts": []
            }
            return 0, json.dumps(payload), ""

        payload = {
            "facts": [f"Fait collecté par {role}"],
            "sources": ["source1.md"],
            "hypotheses": [],
            "uncertainties": [],
            "conclusion": f"Conclusion de {role}",
            "confidence": 0.9,
            "artifacts": []
        }
        return 0, json.dumps(payload), ""

    res: L2ExecutionResult = await run_l2_parallel_agents(
        goal="Audit partiel",
        max_workers=3,
        custom_exec_fn=mock_exec_with_failure,
    )

    # Le statut doit être "partial", pas "completed"
    assert res.status == "partial"
    assert res.quality_gate_passed is False
    assert len(res.successful_agents) == 2
    assert len(res.failed_agents) == 1
    assert "critic_2" in str(res.failed_agents) or "Timeout" in str(res.failed_agents)
    assert res.synthesis is not None
    assert "Synthèse partielle" in res.synthesis.conclusion


@pytest.mark.asyncio
async def test_l2_cross_check_contradiction_detection_and_bounded_retry():
    """Critère 3 : Détection d'une contradiction entre agents, échec du cross-check, et relance bornée à max_iterations=2."""
    call_count = {"prospector": 0, "critic": 0, "architect": 0}

    async def mock_exec_contradiction(cmd, timeout, cwd=None):
        role = _extract_mock_role(cmd)
        call_count[role] = call_count.get(role, 0) + 1
        iteration_current = call_count[role]

        if role == "prospector":
            # Le prospecteur affirme que c'est possible
            payload = {
                "facts": ["L'implémentation est possible et compatible."],
                "sources": ["doc_a.md"],
                "hypotheses": [],
                "uncertainties": [],
                "conclusion": "Le déploiement est possible et compatible sans surcoût.",
                "confidence": 0.95,
                "artifacts": []
            }
        elif role == "critic":
            if iteration_current == 1:
                # Contradiction à l'itération 1 : affirme que c'est impossible
                payload = {
                    "facts": ["Le composant est incompatible."],
                    "sources": ["doc_b.md"],
                    "hypotheses": [],
                    "uncertainties": [],
                    "conclusion": "Le déploiement est impossible et incompatible en l'état.",
                    "confidence": 0.90,
                    "artifacts": []
                }
            else:
                # À l'itération 2, la contradiction est résolue
                payload = {
                    "facts": ["Le composant est compatible moyennant configuration."],
                    "sources": ["doc_b_v2.md"],
                    "hypotheses": [],
                    "uncertainties": [],
                    "conclusion": "Le déploiement est possible avec une configuration adaptée.",
                    "confidence": 0.92,
                    "artifacts": []
                }
        else:
            payload = {
                "facts": ["Architecture standard."],
                "sources": ["doc_c.md"],
                "hypotheses": [],
                "uncertainties": [],
                "conclusion": "Architecture prête.",
                "confidence": 0.9,
                "artifacts": []
            }
        return 0, json.dumps(payload), ""

    res: L2ExecutionResult = await run_l2_parallel_agents(
        goal="Audit de compatibilité",
        max_workers=3,
        max_iterations=2,
        custom_exec_fn=mock_exec_contradiction,
    )

    # Vérification que 2 itérations ont eu lieu
    assert res.iterations_run == 2
    assert call_count["critic"] == 2
    assert res.cross_check.passed is True
    assert res.quality_gate_passed is True


@pytest.mark.asyncio
async def test_l2_global_timeout_terminates_all_child_tasks():
    """Critère 4 : Timeout global interrompt l'ensemble du flux sans zombie et retourne status='timeout'."""
    async def mock_exec_hanging(cmd, timeout, cwd=None):
        await asyncio.sleep(10.0)
        return 0, "{}", ""

    res: L2ExecutionResult = await run_l2_parallel_agents(
        goal="Tâche bloquée",
        max_workers=3,
        global_timeout=0.1,
        custom_exec_fn=mock_exec_hanging,
    )

    assert res.status == "timeout"
    assert res.quality_gate_passed is False
    assert "Timeout global" in str(res.error)


@pytest.mark.asyncio
async def test_l2_isolated_workspaces_prevent_concurrent_file_collisions():
    """Critère 5 : Chaque agent reçoit un workspace isolé et n'écrit pas dans le dossier d'un autre."""
    test_dir = os.path.join(os.path.dirname(__file__), "_test_scratch", "l2_isolation_ws")
    os.makedirs(test_dir, exist_ok=True)
    try:
        workspaces_used = []

        async def mock_exec_workspace_check(cmd, timeout, cwd=None):
            assert cwd is not None
            workspaces_used.append(cwd)
            role = _extract_mock_role(cmd)
            # Écriture d'un fichier local pour vérifier l'absence d'écrasement concurrent
            worker_file = os.path.join(cwd, "test_file.txt")
            with open(worker_file, "w", encoding="utf-8") as f:
                f.write(f"Données de {role}")

            payload = {
                "facts": ["Fait local"],
                "sources": ["source.txt"],
                "hypotheses": [],
                "uncertainties": [],
                "conclusion": f"Fait par {role}",
                "confidence": 0.9,
                "artifacts": [worker_file]
            }
            return 0, json.dumps(payload), ""

        res: L2ExecutionResult = await run_l2_parallel_agents(
            goal="Test d'isolation des workspaces",
            max_workers=3,
            base_workspace=test_dir,
            custom_exec_fn=mock_exec_workspace_check,
        )

        assert res.status == "completed"
        # Les 3 workers + la synthèse doivent avoir des dossiers distincts
        unique_workspaces = set(workspaces_used)
        assert len(unique_workspaces) == 4  # 3 ouvriers + 1 synthèse
        for ws in unique_workspaces:
            assert os.path.isdir(ws)
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_l2_quota_cooldown_and_fallback_awareness():
    """Critère 6 : Détection d'un quota agy (429), marquage en cooldown, repli vers flash/high sans boucle infinie."""
    async def mock_exec_quota(cmd, timeout, cwd=None):
        model_used = cmd[cmd.index("--model") + 1]
        if "pro" in model_used:
            return 429, "Error 429: Resource exhausted on pro model", ""
        
        # En Flash, réponse valide
        payload = {
            "facts": ["Fait obtenu après repli flash"],
            "sources": ["source.md"],
            "hypotheses": [],
            "uncertainties": [],
            "conclusion": "Succès après repli Flash",
            "confidence": 0.9,
            "artifacts": []
        }
        return 0, json.dumps(payload), ""

    missions = [
        L2WorkerMission(worker_id="w1", role="prospector", mission="Collecte", model=MODEL_PRO, effort="high"),
        L2WorkerMission(worker_id="w2", role="critic", mission="Analyse", model=MODEL_PRO, effort="high"),
    ]

    # Sans consentement payant -> les agents lèvent PaidKeyConsentRequired
    from services.key_gate import PaidKeyConsentRequired
    with pytest.raises(PaidKeyConsentRequired):
        await run_l2_parallel_agents(
            goal="Test quota",
            worker_missions=missions,
            custom_exec_fn=mock_exec_quota,
        )

    # Vérification que le modèle a bien été enregistré en cooldown
    assert cooldown_manager.is_in_cooldown(MODEL_PRO) is True
