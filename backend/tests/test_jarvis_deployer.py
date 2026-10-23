"""backend/tests/test_jarvis_deployer.py
Tests unitaires et d'intégration offline pour le déployeur autonome J.A.R.V.I.S. (Prompt 1).
Couvre : file d'attente, machine à états, rollback atomique, seuils de surveillance,
timeouts, idempotence, journalisation append-only, reprise après crash et notifications Telegram.
"""

import asyncio
import json
import os
import shutil
import tempfile
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from ops.deploy.jarvis_deployer import (
    DeployerConfig,
    DeployerJournal,
    DeployerDB,
    ReleaseManager,
    HealthChecker,
    ServiceManager,
    TelegramDirectNotifier,
    DeployerEngine,
    DeployerServer,
    sanitize_text,
    sanitize_data,
)


_TEST_BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "_test_scratch", "deployer"))
os.makedirs(_TEST_BASE_DIR, exist_ok=True)


@pytest.fixture
def deployer_env():
    """Crée un environnement isolé pour tester le déployeur dans _test_scratch."""
    sub_id = f"test_{int(time.time() * 1000)}_{os.urandom(4).hex()}"
    tmp_str = os.path.join(_TEST_BASE_DIR, sub_id)
    os.makedirs(tmp_str, exist_ok=True)

    ws = os.path.join(tmp_str, "workspace")
    os.makedirs(ws, exist_ok=True)
    releases = os.path.join(tmp_str, "releases")
    os.makedirs(releases, exist_ok=True)
    current = os.path.join(ws, "current")
    db_file = os.path.join(tmp_str, "deployments.db")
    journal_file = os.path.join(tmp_str, "journal.jsonl")
    lock_file = os.path.join(tmp_str, "deployer.lock")

    # Création d'un mini-projet valide
    backend_dir = os.path.join(ws, "backend", "core", "tools")
    os.makedirs(backend_dir, exist_ok=True)
    with open(os.path.join(backend_dir, "declarations.py"), "w", encoding="utf-8") as f:
        f.write("TOOLS = []\n")
    with open(os.path.join(backend_dir, "dispatcher.py"), "w", encoding="utf-8") as f:
        f.write("def dispatch(): pass\n")
    with open(os.path.join(backend_dir, "result.py"), "w", encoding="utf-8") as f:
        f.write("class Result: pass\n")
    with open(os.path.join(ws, "main.py"), "w", encoding="utf-8") as f:
        f.write("print('Jarvis Core Test')\n")

    cfg = DeployerConfig(
        workspace_dir=ws,
        releases_dir=releases,
        current_symlink=current,
        db_path=db_file,
        journal_path=journal_file,
        lock_file=lock_file,
        service_name="jarvis-test",
        http_host="127.0.0.1",
        http_port=18001,
        jarvis_port=18000,
        jarvis_http_url="http://127.0.0.1:18000",
        jarvis_ws_url="ws://127.0.0.1:18000/ws",
        cdp_url="http://127.0.0.1:19222",
        monitor_duration_sec=0.2,
        monitor_interval_sec=0.05,
        error_threshold=0.10,
        max_latency_ms=200.0,
        smoke_retries=2,
        smoke_retry_delay_sec=0.01,
        telegram_bot_token="test_bot_token",
        telegram_chat_id="test_chat_id",
    )
    try:
        yield cfg
    finally:
        shutil.rmtree(tmp_str, ignore_errors=True)


# ─── 1. Tests Configuration & Sanitisation des Secrets ────────────────────────

def test_sanitize_secrets():
    raw = "Erreur avec token: bot123456789:AAEFakeTelegramTokenXYZ987654321 et password='SuperSecretPassword123'"
    sanitized = sanitize_text(raw)
    assert "SuperSecretPassword123" not in sanitized
    assert "AAEFakeTelegramToken" not in sanitized
    assert "[REDACTED]" in sanitized

    dict_data = {
        "api_key": "AIzaSyABCDEF12345678901234567890123",
        "username": "opc",
        "nested": {"client_secret": "my-secret-val", "metric": 42}
    }
    cleaned = sanitize_data(dict_data)
    assert cleaned["api_key"] == "[REDACTED]"
    assert cleaned["username"] == "opc"
    assert cleaned["nested"]["client_secret"] == "[REDACTED]"
    assert cleaned["nested"]["metric"] == 42


def test_deployer_config_from_env(monkeypatch):
    sub_id = f"test_cfg_{int(time.time() * 1000)}_{os.urandom(4).hex()}"
    tmp_str = os.path.join(_TEST_BASE_DIR, sub_id)
    os.makedirs(tmp_str, exist_ok=True)
    try:
        monkeypatch.setenv("JARVIS_WORKSPACE_DIR", tmp_str)
        monkeypatch.setenv("JARVIS_DEPLOY_PORT", "9999")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "mock_tok")

        cfg = DeployerConfig.from_env()
        assert cfg.workspace_dir == os.path.abspath(tmp_str)
        assert cfg.http_port == 9999
        assert cfg.telegram_bot_token == "mock_tok"
    finally:
        shutil.rmtree(tmp_str, ignore_errors=True)


# ─── 2. Tests Journal Append-Only & Base de Données ───────────────────────────

def test_journal_append_and_read(deployer_env):
    journal = DeployerJournal(deployer_env.journal_path)
    journal.append("TEST_EVENT", "dep_123", {"secret_token": "shhh", "status": "ok"})
    journal.append("TEST_EVENT_2", "dep_123", {"status": "done"})

    entries = journal.read_entries()
    assert len(entries) == 2
    assert entries[0]["event"] == "TEST_EVENT"
    assert entries[0]["data"]["secret_token"] == "[REDACTED]"
    assert entries[1]["event"] == "TEST_EVENT_2"


def test_db_persistence_and_transitions(deployer_env):
    db = DeployerDB(deployer_env.db_path)
    dep = db.create_deployment("dep_001", target_ref="v1.0.0", metadata={"author": "Pierre"})
    assert dep["status"] == "queued"
    assert dep["target_ref"] == "v1.0.0"

    db.update_status("dep_001", "running", release_id="rel_001", release_dir="/tmp/rel_001")
    dep = db.get_deployment("dep_001")
    assert dep["status"] == "running"
    assert dep["release_id"] == "rel_001"
    assert dep["started_at"] is not None

    db.update_status("dep_001", "succeeded", metrics={"latency": 15.2})
    dep = db.get_deployment("dep_001")
    assert dep["status"] == "succeeded"
    assert dep["finished_at"] is not None
    assert dep["metrics"]["latency"] == 15.2

    recent = db.get_recent(5)
    assert len(recent) == 1
    assert recent[0]["id"] == "dep_001"


# ─── 3. Tests Release Manager & Symlink Blue/Green ────────────────────────────

def test_release_manager_prepare_and_activate(deployer_env):
    rm = ReleaseManager(deployer_env)
    rel_id, target_dir = rm.prepare_release(deployer_env.workspace_dir)

    assert os.path.exists(target_dir)
    assert os.path.exists(os.path.join(target_dir, "main.py"))
    assert os.path.exists(os.path.join(target_dir, "backend", "core", "tools", "declarations.py"))

    # Bascule atomique du symlink
    prev = rm.activate_symlink(target_dir)
    current_active = rm.get_current_release_dir()
    assert current_active == os.path.abspath(target_dir)

    # Création d'une seconde release et vérification du pointeur précédent
    rel_id_2, target_dir_2 = rm.prepare_release(deployer_env.workspace_dir, release_id="rel_second")
    prev_2 = rm.activate_symlink(target_dir_2)
    assert prev_2 == os.path.abspath(target_dir)
    assert rm.get_current_release_dir() == os.path.abspath(target_dir_2)

    # Rollback vers la précédente
    ok = rm.revert_symlink(prev_2)
    assert ok is True
    assert rm.get_current_release_dir() == os.path.abspath(target_dir)


# ─── 4. Tests Sondes de Santé & Smoke Tests ───────────────────────────────────

@pytest.mark.asyncio
async def test_smoke_check_success_and_failure(deployer_env):
    mock_http_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_http_client.get.return_value = mock_resp

    checker = HealthChecker(deployer_env, http_client=mock_http_client)

    with patch.object(checker, "check_websocket", AsyncMock(return_value=(True, "OK"))), \
         patch.object(checker, "check_cdp", AsyncMock(return_value=(True, "CDP OK"))), \
         patch.object(checker, "check_tool_contracts", AsyncMock(return_value=(True, "Tools OK"))):

        ok, details = await checker.run_full_smoke_check(deployer_env.workspace_dir)
        assert ok is True
        assert details["http"]["ok"] is True
        assert details["websocket"]["ok"] is True
        assert details["cdp"]["ok"] is True
        assert details["tool_contracts"]["ok"] is True

    # Cas d'échec HTTP
    mock_fail_resp = MagicMock()
    mock_fail_resp.status_code = 503
    mock_http_client.get.return_value = mock_fail_resp

    with patch.object(checker, "check_websocket", AsyncMock(return_value=(True, "OK"))), \
         patch.object(checker, "check_cdp", AsyncMock(return_value=(True, "CDP OK"))), \
         patch.object(checker, "check_tool_contracts", AsyncMock(return_value=(True, "Tools OK"))):

        ok, details = await checker.run_full_smoke_check(deployer_env.workspace_dir)
        assert ok is False
        assert details["http"]["ok"] is False


# ─── 5. Tests Boucle de Surveillance & Seuils d'Erreur / Latence ──────────────

@pytest.mark.asyncio
async def test_monitoring_loop_threshold_auto_rollback(deployer_env):
    checker = HealthChecker(deployer_env)
    # Simuler des erreurs répétées (50% d'erreurs)
    call_count = 0

    async def mock_err_http():
        nonlocal call_count
        call_count += 1
        return (False, 30.0, "HTTP 500") if call_count % 2 == 0 else (True, 30.0, "HTTP 200")

    checker.check_http = AsyncMock(side_effect=mock_err_http)

    engine = DeployerEngine(deployer_env, health_checker=checker)
    ok, metrics, reason = await engine._run_monitoring_loop("dep_test")
    assert ok is False
    assert "Taux d'erreur trop élevé" in reason
    assert metrics["error_rate"] >= deployer_env.error_threshold


@pytest.mark.asyncio
async def test_monitoring_loop_latency_threshold_auto_rollback(deployer_env):
    checker = HealthChecker(deployer_env)
    # Simuler une latence excessive (> 200ms)
    checker.check_http = AsyncMock(return_value=(True, 350.0, "HTTP 200"))

    engine = DeployerEngine(deployer_env, health_checker=checker)
    ok, metrics, reason = await engine._run_monitoring_loop("dep_test")
    assert ok is False
    assert "Latence moyenne excessive" in reason


@pytest.mark.asyncio
async def test_monitoring_loop_success(deployer_env):
    checker = HealthChecker(deployer_env)
    # Tout est normal (latence 20ms, zéro erreur)
    checker.check_http = AsyncMock(return_value=(True, 20.0, "HTTP 200"))

    engine = DeployerEngine(deployer_env, health_checker=checker)
    ok, metrics, reason = await engine._run_monitoring_loop("dep_test")
    assert ok is True
    assert metrics["error_rate"] == 0.0
    assert metrics["avg_latency_ms"] <= 50.0


# ─── 6. Test du Pipeline Complet de Déploiement & Rollback Atomique ───────────

@pytest.mark.asyncio
async def test_full_deployment_pipeline_success(deployer_env):
    service_mgr = ServiceManager(service_name="test", runner=lambda cmd: (0, "active", ""))
    notifier = TelegramDirectNotifier(deployer_env.telegram_bot_token, deployer_env.telegram_chat_id)
    notifier.send_message = AsyncMock(return_value=True)

    checker = HealthChecker(deployer_env)
    checker.check_http = AsyncMock(return_value=(True, 15.0, "HTTP 200"))
    checker.check_websocket = AsyncMock(return_value=(True, "WS OK"))
    checker.check_cdp = AsyncMock(return_value=(True, "CDP OK"))
    checker.check_tool_contracts = AsyncMock(return_value=(True, "Tools OK"))

    engine = DeployerEngine(
        deployer_env,
        service_manager=service_mgr,
        notifier=notifier,
        health_checker=checker,
    )

    dep = await engine.trigger_deployment(target_ref="v5.95.0")
    dep_id = dep["id"]

    # Attente fin de tâche
    for _ in range(50):
        await asyncio.sleep(0.05)
        st = engine.db.get_deployment(dep_id)["status"]
        if st in ("succeeded", "failed", "rolled_back"):
            break

    final = engine.db.get_deployment(dep_id)
    assert final["status"] == "succeeded"
    assert final["release_dir"] is not None
    assert final["metrics"] is not None
    assert notifier.send_message.called


@pytest.mark.asyncio
async def test_full_deployment_pipeline_rollback_on_smoke_failure(deployer_env):
    # Préparer une release initiale pour simuler la release antérieure
    rm = ReleaseManager(deployer_env)
    _, initial_rel = rm.prepare_release(deployer_env.workspace_dir, release_id="initial_rel")
    rm.activate_symlink(initial_rel)

    service_mgr = ServiceManager(service_name="test", runner=lambda cmd: (0, "active", ""))
    notifier = TelegramDirectNotifier(deployer_env.telegram_bot_token, deployer_env.telegram_chat_id)
    notifier.send_message = AsyncMock(return_value=True)

    checker = HealthChecker(deployer_env)
    # Échec immédiat du HTTP probe
    checker.check_http = AsyncMock(return_value=(False, 10.0, "Connexion refusée"))
    checker.check_websocket = AsyncMock(return_value=(True, "WS OK"))
    checker.check_cdp = AsyncMock(return_value=(True, "CDP OK"))
    checker.check_tool_contracts = AsyncMock(return_value=(True, "Tools OK"))

    engine = DeployerEngine(
        deployer_env,
        service_manager=service_mgr,
        notifier=notifier,
        health_checker=checker,
    )

    dep = await engine.trigger_deployment(target_ref="bad_build")
    dep_id = dep["id"]

    for _ in range(50):
        await asyncio.sleep(0.05)
        st = engine.db.get_deployment(dep_id)["status"]
        if st in ("succeeded", "failed", "rolled_back"):
            break

    final = engine.db.get_deployment(dep_id)
    assert final["status"] == "rolled_back"
    # Vérification que le symlink pointe bien à nouveau vers la release initiale saine
    assert rm.get_current_release_dir() == os.path.abspath(initial_rel)


# ─── 7. Tests Idempotence & Verrou Mono-Déploiement ───────────────────────────

@pytest.mark.asyncio
async def test_idempotence_and_lock(deployer_env):
    engine = DeployerEngine(deployer_env)

    # 1. Verrou physique
    assert engine.acquire_file_lock() is True
    # Second essai sans libérer
    assert engine.acquire_file_lock() is False
    engine.release_file_lock()
    assert engine.acquire_file_lock() is True
    engine.release_file_lock()

    # 2. Requête idempotente : enregistrer un déploiement actif
    engine.db.create_deployment("dep_active", target_ref="commit_abc123")
    res = await engine.trigger_deployment(target_ref="commit_abc123")
    assert res["id"] == "dep_active"
    assert res["status"] == "queued"


# ─── 8. Tests Reprise après Crash (Crash Recovery) ────────────────────────────

@pytest.mark.asyncio
async def test_crash_recovery_resumes_and_cleans(deployer_env):
    rm = ReleaseManager(deployer_env)
    _, initial_rel = rm.prepare_release(deployer_env.workspace_dir, release_id="base_rel")
    rm.activate_symlink(initial_rel)

    db = DeployerDB(deployer_env.db_path)
    # 1. Déploiement coupé pendant 'running'
    db.create_deployment("dep_crashed_run", target_ref="ref1")
    db.update_status("dep_crashed_run", "running")

    # 2. Déploiement coupé pendant 'monitoring'
    db.create_deployment("dep_crashed_mon", target_ref="ref2")
    db.update_status("dep_crashed_mon", "monitoring", previous_release_dir=initial_rel)

    notifier = TelegramDirectNotifier(deployer_env.telegram_bot_token, deployer_env.telegram_chat_id)
    notifier.send_message = AsyncMock(return_value=True)
    service_mgr = ServiceManager(service_name="test", runner=lambda cmd: (0, "active", ""))

    engine = DeployerEngine(deployer_env, service_manager=service_mgr, notifier=notifier)
    await engine.recover_or_resume()

    # Vérification des statuts post-réconciliation
    rec_run = db.get_deployment("dep_crashed_run")
    assert rec_run["status"] == "failed"

    rec_mon = db.get_deployment("dep_crashed_mon")
    assert rec_mon["status"] == "rolled_back"
    assert "Redémarrage du VPS" in rec_mon["rollback_reason"]
    assert rm.get_current_release_dir() == os.path.abspath(initial_rel)


# ─── 9. Tests Notificateur Direct Telegram ────────────────────────────────────

@pytest.mark.asyncio
async def test_telegram_direct_notifier(deployer_env):
    mock_http = AsyncMock()
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_http.post.return_value = mock_res

    notifier = TelegramDirectNotifier(
        bot_token="fake_bot_token",
        chat_id="fake_chat_123",
        http_client=mock_http
    )

    ok = await notifier.send_message("<b>Test message</b>")
    assert ok is True
    assert mock_http.post.called
    call_args = mock_http.post.call_args
    assert "https://api.telegram.org/botfake_bot_token/sendMessage" in call_args[0][0]
    assert call_args[1]["json"]["chat_id"] == "fake_chat_123"

    await notifier.notify_status("dep_999", "rolled_back", {"rollback_reason": "Seuil latence"})
    assert mock_http.post.call_count == 2


# ─── 10. Tests Serveur HTTP Loopback (Port 8001 / Zero Dépendance) ────────────

@pytest.mark.asyncio
async def test_deployer_http_server(deployer_env):
    engine = DeployerEngine(deployer_env)
    server = DeployerServer(engine)
    await server.start()

    try:
        reader, writer = await asyncio.open_connection(deployer_env.http_host, deployer_env.http_port)

        # 1. GET /health
        writer.write(b"GET /health HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
        await writer.drain()

        resp_lines = []
        while True:
            line = await reader.readline()
            if not line or line == b"\r\n":
                break
            resp_lines.append(line.decode().strip())

        raw_body = await reader.read()
        body = json.loads(raw_body.decode())
        assert body["status"] == "ok"
        assert body["service"] == "jarvis-deployer"
        writer.close()
        await writer.wait_closed()

        # 2. POST /rollback
        reader2, writer2 = await asyncio.open_connection(deployer_env.http_host, deployer_env.http_port)
        writer2.write(b"POST /rollback HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 0\r\n\r\n")
        await writer2.drain()

        while True:
            line = await reader2.readline()
            if not line or line == b"\r\n":
                break

        raw_body2 = await reader2.read()
        body2 = json.loads(raw_body2.decode())
        assert "status" in body2
        writer2.close()
        await writer2.wait_closed()

    finally:
        await server.stop()
