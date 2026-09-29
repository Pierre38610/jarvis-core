"""tests/test_tool_metrics.py
Tests unitaires pour l'instrumentation des appels d'outils J.A.R.V.I.S.
Vérifie la table de métriques, l'écriture non bloquante, le calcul d'agrégats (24h/7j/30j),
l'encapsulation dans dispatcher.py et le bon fonctionnement de l'endpoint /api/supervision/metrics.
"""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from services.metrics_service import MetricsService, metrics_service
from core.tools.dispatcher import dispatch_tool, _infer_tool_tier_and_cost


@pytest.fixture
def fresh_metrics_service():
    """Crée une instance isolée de MetricsService pour les tests."""
    return MetricsService(buffer_size=100)


# ─── 1. Tests unitaires du MetricsService (Buffer mémoire & Synthèse) ──────────

def test_infer_tool_tier_and_cost():
    """Valide la déduction correcte du palier cognitif et du coût selon le nom d'outil et arguments."""
    # Tier 1 : Curation livre
    tier1, cost1 = _infer_tool_tier_and_cost("generate_book_summary", {"titre_livre": "Dune"}, is_paid_live=False)
    assert tier1 == 1

    # Tier 2 : Train
    tier2, cost2 = _infer_tool_tier_and_cost("rechercher_train", {"origine": "Paris", "destination": "Lyon"}, is_paid_live=False)
    assert tier2 == 2

    # Tier 3 : Auto-guérison SRE
    tier3, cost3 = _infer_tool_tier_and_cost("system_self_healing", {"motif": "Crash"}, is_paid_live=False)
    assert tier3 == 3

    # Browser-use payant
    tier_b, cost_b = _infer_tool_tier_and_cost("run_browser_task", {"goal": "Acheter billet"}, is_paid_live=False)
    assert cost_b == 0.02

    # ask_deep_reasoning avec modèle pro-high (Tier 3)
    tier_r3, cost_r3 = _infer_tool_tier_and_cost("ask_deep_reasoning", {"model": "gemini-3.1-pro-high"}, is_paid_live=False)
    assert tier_r3 == 3
    assert cost_r3 == 0.03


@pytest.mark.asyncio
async def test_metrics_service_in_memory_summary(fresh_metrics_service):
    """Vérifie l'agrégation statistique fidèle (top outils, échecs, latences p95, tiers, coûts)."""
    svc = fresh_metrics_service

    # Enregistrement de 4 appels :
    # 2x search_web (succès, 100ms et 200ms, cost 0.0)
    # 1x run_browser_task (échec, 500ms, cost 0.02)
    # 1x ask_deep_reasoning (succès, 1200ms, tier 3, cost 0.03)
    now = datetime.now(timezone.utc)
    await svc.record_tool_call("search_web", "success", 100.0, cognitive_tier=None, cost_est=0.0, created_at=now)
    await svc.record_tool_call("search_web", "success", 200.0, cognitive_tier=None, cost_est=0.0, created_at=now)
    await svc.record_tool_call("run_browser_task", "failure", 500.0, cognitive_tier=None, cost_est=0.02, created_at=now)
    await svc.record_tool_call("ask_deep_reasoning", "success", 1200.0, cognitive_tier=3, cost_est=0.03, created_at=now)

    summary = await svc.get_metrics_summary("24h")

    assert summary["total_calls"] == 4
    assert summary["total_failures"] == 1
    assert summary["total_timeouts"] == 0
    assert summary["global_failure_rate"] == 0.25
    assert summary["total_cost"] == 0.05

    # Top outils
    top_tool_names = [t["tool_name"] for t in summary["top_tools"]]
    assert top_tool_names[0] == "search_web"
    assert summary["top_tools"][0]["count"] == 2

    # Taux d'échec par outil
    browser_fail = next(f for f in summary["failure_rates"] if f["tool_name"] == "run_browser_task")
    assert browser_fail["failures"] == 1
    assert browser_fail["failure_rate"] == 1.0

    # Latences p95
    search_lat = next(l for l in summary["latencies"] if l["tool_name"] == "search_web")
    assert search_lat["avg_latency_ms"] == 150.0
    assert search_lat["p95_latency_ms"] > 0

    # Répartition Tiers
    assert summary["tier_usage"]["tier_3"] == 1
    assert summary["tier_usage"]["none"] == 3


@pytest.mark.asyncio
async def test_metrics_service_window_filtering(fresh_metrics_service):
    """Valide que les événements antérieurs à la fenêtre demandée sont ignorés."""
    svc = fresh_metrics_service
    now = datetime.now(timezone.utc)

    # Événement récent (il y a 1h)
    await svc.record_tool_call("recent_tool", "success", 50.0, created_at=now - timedelta(hours=1))
    # Événement vieux de 3 jours
    await svc.record_tool_call("old_tool_3d", "success", 80.0, created_at=now - timedelta(days=3))
    # Événement vieux de 15 jours
    await svc.record_tool_call("ancient_tool_15d", "success", 120.0, created_at=now - timedelta(days=15))

    # Fenêtre 24h : seul recent_tool
    sum_24h = await svc.get_metrics_summary("24h")
    assert sum_24h["total_calls"] == 1
    assert sum_24h["top_tools"][0]["tool_name"] == "recent_tool"

    # Fenêtre 7j : recent_tool + old_tool_3d
    sum_7j = await svc.get_metrics_summary("7j")
    assert sum_7j["total_calls"] == 2

    # Fenêtre 30j : les 3 événements
    sum_30j = await svc.get_metrics_summary("30j")
    assert sum_30j["total_calls"] == 3


# ─── 2. Tests de l'instrumentation dans dispatcher.py ─────────────────────────

@pytest.mark.asyncio
async def test_dispatch_tool_records_metrics_on_success():
    """Valide que chaque appel réussi de dispatch_tool est instrumenté et enregistré."""
    mock_ws = AsyncMock()
    initial_count = len(metrics_service._memory_buffer)

    # Appel d'un outil local rapide
    res = await dispatch_tool(
        name="get_system_status",
        args={},
        websocket=mock_ws,
        session=MagicMock(),
        is_paid_live=False,
        live_display_label="Gemini Flash"
    )

    assert isinstance(res, dict)
    assert len(metrics_service._memory_buffer) == initial_count + 1

    last_record = metrics_service._memory_buffer[-1]
    assert last_record["tool_name"] == "get_system_status"
    assert last_record["status"] == "success"
    assert last_record["latency_ms"] >= 0.0


@pytest.mark.asyncio
async def test_dispatch_tool_records_metrics_on_error_status():
    """Valide qu'un outil retournant un statut d'erreur est comptabilisé en statut 'failure'."""
    mock_ws = AsyncMock()

    # Outil inconnu retournant {"status": "error"}
    res = await dispatch_tool(
        name="outil_inexistant_xyz",
        args={},
        websocket=mock_ws,
        session=MagicMock(),
        is_paid_live=False,
        live_display_label="Gemini Flash"
    )

    assert res.get("status") in ("error", "failed")
    last_record = metrics_service._memory_buffer[-1]
    assert last_record["tool_name"] == "outil_inexistant_xyz"
    assert last_record["status"] == "failure"


@pytest.mark.asyncio
async def test_dispatch_tool_records_timeout_status():
    """Valide que si un outil lève TimeoutError, le statut 'timeout' est consigné."""
    mock_ws = AsyncMock()

    with patch("core.tools.dispatcher._execute_dispatch_tool", side_effect=asyncio.TimeoutError("Timeout test")):
        with pytest.raises(asyncio.TimeoutError):
            await dispatch_tool(
                name="timeout_tool_test",
                args={},
                websocket=mock_ws,
                session=MagicMock(),
                is_paid_live=False,
                live_display_label="Gemini Flash"
            )

    last_record = metrics_service._memory_buffer[-1]
    assert last_record["tool_name"] == "timeout_tool_test"
    assert last_record["status"] == "timeout"


# ─── 3. Tests de l'endpoint FastAPI /api/supervision/metrics ───────────────────

def test_api_supervision_metrics_unauthorized(test_client):
    """Valide le rejet 401 si aucun jeton d'authentification valide n'est transmis."""
    res = test_client.get("/api/supervision/metrics")
    assert res.status_code == 401
    assert res.json().get("authorized") is False


def test_api_supervision_metrics_authorized(authenticated_client):
    """Valide le format et le contenu retourné par /api/supervision/metrics."""
    # Enregistrer un appel d'outil pour s'assurer que la réponse contient des données
    metrics_service.record_tool_call_background(
        tool_name="test_api_tool",
        status="success",
        latency_ms=120.5,
        cognitive_tier=2,
        cost_est=0.015
    )

    res = authenticated_client.get("/api/supervision/metrics?window=24h")
    assert res.status_code == 200
    data = res.json()

    assert "window" in data
    assert data["window"] == "24h"
    assert "total_calls" in data
    assert "global_failure_rate" in data
    assert "top_tools" in data
    assert "failure_rates" in data
    assert "latencies" in data
    assert "tier_usage" in data
    assert "total_cost" in data
    assert "tools_summary" in data

    # Vérification des sous-structures
    assert "tier_1" in data["tier_usage"]
    assert "tier_2" in data["tier_usage"]
    assert "tier_3" in data["tier_usage"]
