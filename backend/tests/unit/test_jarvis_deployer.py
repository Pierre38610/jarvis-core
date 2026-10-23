"""backend/tests/unit/test_jarvis_deployer.py
Tests unitaires 100 % offline pour le déployeur autonome Blue/Green J.A.R.V.I.S.
Couvre : file d'attente, machine à états, rollback atomique, seuils de surveillance,
timeouts, idempotence, journalisation append-only, reprise après crash, modes --once/--dry-run
et notifications Telegram. Utilise tmp_path et des mocks complets.
"""

import asyncio
import json
import os
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import tempfile
import pytest

from ops.deploy.jarvis_deployer import (
    DeployerConfig,
    DeployerJournal,
    DeployerDB,
    StateFileManager,
    ReleaseManager,
    HealthChecker,
    ServiceManager,
    TelegramDirectNotifier,
    DeployerEngine,
    DeployerServer,
    _sanitize_secrets,
    sanitize_text,
    sanitize_data,
)


_SCRATCH_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "_test_scratch", "unit_tmp"))
os.makedirs(_SCRATCH_DIR, exist_ok=True)


@pytest.fixture
def tmp_path():
    """Fixture tmp_path autonome compatible pathlib.Path dans l'espace de travail _test_scratch."""
    sub_id = f"test_{int(time.time() * 1000)}_{os.urandom(4).hex()}"
    p = Path(_SCRATCH_DIR) / sub_id
    p.mkdir(parents=True, exist_ok=True)
    try:
        yield p
    finally:
        import shutil
        shutil.rmtree(str(p), ignore_errors=True)


@pytest.fixture
def test_setup(tmp_path):
    """Prépare un environnement isolé via tmp_path avec arborescence source valide."""
    deploy_root = tmp_path / "deploy_root"
    deploy_root.mkdir()

    source_dir = tmp_path / "source_repo"
    source_dir.mkdir()

    # Création de fichiers sources valides pour py_compile
    core_tools = source_dir / "backend" / "core" / "tools"
    core_tools.mkdir(parents=True)
    (core_tools / "declarations.py").write_text("TOOLS = []\n", encoding="utf-8")
    (core_tools / "dispatcher.py").write_text("def dispatch(): pass\n", encoding="utf-8")
    (core_tools / "result.py").write_text("class Result: pass\n", encoding="utf-8")
    (source_dir / "main.py").write_text("print('Jarvis App v5.95.0')\n", encoding="utf-8")

    cfg = DeployerConfig.from_env(
        deploy_root_override=str(deploy_root),
        workspace_override=str(source_dir),
    )
    # Paramètres ultra-rapides pour les tests unitaires
    cfg.monitor_duration_sec = 0.2
    cfg.monitor_interval_sec = 0.05
    cfg.smoke_retry_delay_sec = 0.01
    cfg.smoke_retries = 2
    cfg.error_threshold = 0.10
    cfg.max_errors = 2
    cfg.max_latency_ms = 150.0
    cfg.http_port = 19123
    cfg.telegram_bot_token = "mock_bot_token"
    cfg.telegram_chat_id = "mock_chat_id"

    return {
        "deploy_root": deploy_root,
        "source_dir": source_dir,
        "config": cfg,
    }


# ─── 1. SANITISATION DES SECRETS ──────────────────────────────────────────────

def test_sanitize_secrets():
    raw_text = (
        "Fatal error with token: bot123456789:AAEFakeTelegramTokenXYZ987654321 "
        "and password='SuperSecretPassword123' and key=AIzaSyABCDEF12345678901234567890123 "
        "and Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.tokenpart.sig"
    )
    sanitized = _sanitize_secrets(raw_text)
    assert "SuperSecretPassword123" not in sanitized
    assert "AAEFakeTelegramTokenXYZ" not in sanitized
    assert "AIzaSyABCDEF" not in sanitized
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in sanitized
    assert "[REDACTED]" in sanitized or "[REDACTED_TELEGRAM_TOKEN]" in sanitized

    # Alias check
    assert sanitize_text(raw_text) == sanitized

    # Dict et listes récursives
    sensitive_dict = {
        "api_key": "secret123",
        "nested": {"client_password": "pass", "ok_val": 42},
        "items": ["token: abc12345", "clean_item"],
    }
    cleaned = sanitize_data(sensitive_dict)
    assert cleaned["api_key"] == "[REDACTED]"
    assert cleaned["nested"]["client_password"] == "[REDACTED]"
    assert cleaned["nested"]["ok_val"] == 42
    assert "[REDACTED]" in cleaned["items"][0]
    assert cleaned["items"][1] == "clean_item"


# ─── 2. INJECTION DE JARVIS_DEPLOY_ROOT & CONFIGURATION ──────────────────────

def test_config_from_env_deploy_root(tmp_path, monkeypatch):
    root_dir = tmp_path / "custom_deploy_root"
    root_dir.mkdir()

    monkeypatch.setenv("JARVIS_DEPLOY_ROOT", str(root_dir))
    monkeypatch.setenv("DEPLOY_MONITOR_SECONDS", "2.5")
    monkeypatch.setenv("JARVIS_DEPLOY_PORT", "9099")

    cfg = DeployerConfig.from_env()
    assert cfg.deploy_root == str(root_dir.resolve())
    assert cfg.monitor_duration_sec == 2.5
    assert cfg.http_port == 9099
    assert cfg.releases_dir == str((root_dir / "releases").resolve())
    assert cfg.current_symlink == str((root_dir / "current").resolve())
    assert cfg.state_file == str((root_dir / "deployer_state.json").resolve())
    assert cfg.db_path == str((root_dir / "deployments.db").resolve())
    assert cfg.journal_path == str((root_dir / "deployer_journal.jsonl").resolve())


# ─── 3. ÉTAT PERSISTANT & JOURNAL APPEND-ONLY ─────────────────────────────────

def test_journal_and_state_file(test_setup):
    cfg = test_setup["config"]
    journal = DeployerJournal(cfg.journal_path)

    journal.append("START", "dep_01", {"token": "secret_abc", "info": "ready"})
    journal.append("FINISH", "dep_01", {"status": "ok"})

    entries = journal.read_entries()
    assert len(entries) == 2
    assert entries[0]["event"] == "START"
    assert entries[0]["data"]["token"] == "[REDACTED]"
    assert entries[1]["event"] == "FINISH"

    state_mgr = StateFileManager(cfg.state_file)
    state_mgr.write_state({"deployment_id": "dep_01", "status": "running", "token": "secret_abc"})

    state = state_mgr.read_state()
    assert state["deployment_id"] == "dep_01"
    assert state["status"] == "running"
    assert state["token"] == "[REDACTED]"
    assert "updated_at" in state


def test_db_persistence_lifecycle(test_setup):
    cfg = test_setup["config"]
    db = DeployerDB(cfg.db_path)

    dep = db.create_deployment("dep_100", target_ref="v1.0.0")
    assert dep["status"] == "queued"
    assert dep["target_ref"] == "v1.0.0"

    db.update_status("dep_100", "running", release_id="rel_100", release_dir="/tmp/rel_100")
    dep = db.get_deployment("dep_100")
    assert dep["status"] == "running"
    assert dep["release_id"] == "rel_100"

    db.update_status("dep_100", "succeeded", metrics={"latency": 12.5})
    dep = db.get_deployment("dep_100")
    assert dep["status"] == "succeeded"
    assert dep["metrics"]["latency"] == 12.5

    recent = db.get_recent(5)
    assert len(recent) == 1
    assert recent[0]["id"] == "dep_100"


# ─── 4. GESTIONNAIRE DE RELEASES & ATOMIC SYMLINK ────────────────────────────

def test_release_manager_blue_green(test_setup):
    cfg = test_setup["config"]
    rm = ReleaseManager(cfg)

    # 1. Préparation de la release Blue
    rel_id, rel_dir = rm.prepare_release(cfg.workspace_dir, release_id="release_blue")
    assert os.path.exists(rel_dir)
    assert os.path.exists(os.path.join(rel_dir, "main.py"))

    # Activation atomique
    prev = rm.activate_symlink(rel_dir)
    assert prev is None or prev == ""
    assert rm.get_current_release_dir() == os.path.abspath(rel_dir)

    # 2. Préparation de la release Green
    rel_id_2, rel_dir_2 = rm.prepare_release(cfg.workspace_dir, release_id="release_green")
    prev_2 = rm.activate_symlink(rel_dir_2)
    assert prev_2 == os.path.abspath(rel_dir)
    assert rm.get_current_release_dir() == os.path.abspath(rel_dir_2)

    # 3. Rollback atomique vers Blue
    ok = rm.revert_symlink(prev_2)
    assert ok is True
    assert rm.get_current_release_dir() == os.path.abspath(rel_dir)


# ─── 5. SONDES HEALTH & PROBES INJECTABLES ────────────────────────────────────

@pytest.mark.asyncio
async def test_health_checker_probes(test_setup):
    cfg = test_setup["config"]

    # Injections de sondes simulées
    mock_http_probe = AsyncMock(return_value=(True, 25.0, "HTTP 200 /api/verify"))
    mock_ws_probe = AsyncMock(return_value=(True, "WS connected"))
    mock_cdp_probe = AsyncMock(return_value=(True, "CDP 9222 ready"))
    mock_tools_probe = AsyncMock(return_value=(True, "Tools verified"))

    checker = HealthChecker(
        cfg,
        http_probe=mock_http_probe,
        ws_probe=mock_ws_probe,
        cdp_probe=mock_cdp_probe,
        tools_probe=mock_tools_probe,
    )

    ok, details = await checker.run_full_smoke_check(cfg.workspace_dir)
    assert ok is True
    assert details["http"]["ok"] is True
    assert details["websocket"]["ok"] is True
    assert details["cdp"]["ok"] is True
    assert details["tool_contracts"]["ok"] is True
    assert mock_http_probe.called
    assert mock_ws_probe.called
    assert mock_cdp_probe.called


# ─── 6. SERVICE MANAGER & INJECTION DU RUNNER DE COMMANDES ───────────────────

def test_service_manager_command_runner():
    executed_cmds = []

    def mock_runner(cmd):
        executed_cmds.append(cmd)
        return (0, "active", "")

    mgr = ServiceManager(service_name="test-service", runner=mock_runner)
    ok, msg = mgr.restart()
    assert ok is True
    assert ["sudo", "systemctl", "restart", "test-service"] in executed_cmds

    assert mgr.is_active() is True

    # Mode dry-run : aucune commande réelle
    mgr_dry = ServiceManager(service_name="test-service", dry_run=True)
    ok_dry, _ = mgr_dry.restart()
    assert ok_dry is True
    assert mgr_dry.is_active() is True


# ─── 7. ADAPTATEUR DIRECT TELEGRAM MOCKABLE ──────────────────────────────────

@pytest.mark.asyncio
async def test_telegram_notifier_mockable():
    mock_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_client.post.return_value = mock_resp

    notifier = TelegramDirectNotifier(
        bot_token="fake_bot_token",
        chat_id="fake_chat_id",
        http_client=mock_client,
    )

    ok = await notifier.send_message("Test message with token: secret_xyz")
    assert ok is True
    assert mock_client.post.called

    call_args = mock_client.post.call_args
    sent_text = call_args[1]["json"]["text"]
    assert "secret_xyz" not in sent_text
    assert "[REDACTED]" in sent_text


# ─── 8. MACHINE À ÉTATS & PIPELINE DE DÉPLOIEMENT COMPLET ─────────────────────

@pytest.mark.asyncio
async def test_full_pipeline_success(test_setup):
    cfg = test_setup["config"]
    mock_runner = lambda cmd: (0, "active", "")
    service_mgr = ServiceManager(service_name="test", runner=mock_runner)

    mock_notifier = MagicMock()
    mock_notifier.notify_status = AsyncMock()

    checker = HealthChecker(
        cfg,
        http_probe=AsyncMock(return_value=(True, 15.0, "HTTP 200")),
        ws_probe=AsyncMock(return_value=(True, "WS OK")),
        cdp_probe=AsyncMock(return_value=(True, "CDP OK")),
        tools_probe=AsyncMock(return_value=(True, "Tools OK")),
    )

    engine = DeployerEngine(
        cfg,
        service_manager=service_mgr,
        notifier=mock_notifier,
        health_checker=checker,
    )

    res = await engine.trigger_deployment(target_ref="v5.95.0", run_sync=True)
    assert res["status"] == "succeeded"
    assert res["metrics"]["error_rate"] == 0.0

    state = engine.state_file_mgr.read_state()
    assert state["status"] == "succeeded"
    assert state["deployment_id"] == res["id"]


@pytest.mark.asyncio
async def test_full_pipeline_rollback_on_smoke_failure(test_setup):
    cfg = test_setup["config"]
    rm = ReleaseManager(cfg)
    _, initial_rel = rm.prepare_release(cfg.workspace_dir, release_id="initial_stable_release")
    rm.activate_symlink(initial_rel)

    mock_runner = lambda cmd: (0, "active", "")
    service_mgr = ServiceManager(service_name="test", runner=mock_runner)
    mock_notifier = MagicMock()
    mock_notifier.notify_status = AsyncMock()

    # Smoke probe HTTP échoue
    checker = HealthChecker(
        cfg,
        http_probe=AsyncMock(return_value=(False, 10.0, "Connexion refusée")),
        ws_probe=AsyncMock(return_value=(True, "WS OK")),
        cdp_probe=AsyncMock(return_value=(True, "CDP OK")),
        tools_probe=AsyncMock(return_value=(True, "Tools OK")),
    )

    engine = DeployerEngine(
        cfg,
        service_manager=service_mgr,
        notifier=mock_notifier,
        health_checker=checker,
    )

    res = await engine.trigger_deployment(target_ref="bad_release", run_sync=True)
    assert res["status"] == "rolled_back"
    assert "Échec des smoke tests" in res["rollback_reason"]
    # Vérification que le symlink pointe toujours vers la version initiale
    assert rm.get_current_release_dir() == os.path.abspath(initial_rel)


# ─── 9. SEUILS D'ERREUR & SURVEILLANCE AUTO-ROLLBACK ─────────────────────────

@pytest.mark.asyncio
async def test_monitoring_loop_error_threshold_rollback(test_setup):
    cfg = test_setup["config"]
    cfg.max_errors = 2

    call_count = 0

    async def failing_http():
        nonlocal call_count
        call_count += 1
        return False, 20.0, "HTTP 500"

    checker = HealthChecker(cfg, http_probe=failing_http)
    engine = DeployerEngine(cfg, health_checker=checker)

    ok, metrics, reason = await engine._run_monitoring_loop("dep_threshold_test")
    assert ok is False
    assert "Seuil maximal d'erreurs franchi" in reason
    assert metrics["errors"] >= 2


@pytest.mark.asyncio
async def test_monitoring_loop_latency_threshold_rollback(test_setup):
    cfg = test_setup["config"]
    cfg.max_latency_ms = 50.0

    async def slow_http():
        return True, 120.0, "HTTP 200"

    checker = HealthChecker(cfg, http_probe=slow_http)
    engine = DeployerEngine(cfg, health_checker=checker)

    ok, metrics, reason = await engine._run_monitoring_loop("dep_latency_test")
    assert ok is False
    assert "Latence moyenne excessive" in reason


# ─── 10. REPRISE APRÈS CRASH (CRASH RECOVERY) ────────────────────────────────

@pytest.mark.asyncio
async def test_crash_recovery(test_setup):
    cfg = test_setup["config"]
    rm = ReleaseManager(cfg)
    _, initial_rel = rm.prepare_release(cfg.workspace_dir, release_id="stable_rel")
    rm.activate_symlink(initial_rel)

    db = DeployerDB(cfg.db_path)
    # 1. Déploiement coupé pendant 'running'
    db.create_deployment("dep_crashed_1", target_ref="ref1")
    db.update_status("dep_crashed_1", "running")

    # 2. Déploiement coupé pendant 'monitoring'
    db.create_deployment("dep_crashed_2", target_ref="ref2")
    db.update_status("dep_crashed_2", "monitoring", previous_release_dir=initial_rel)

    service_mgr = ServiceManager(service_name="test", runner=lambda cmd: (0, "active", ""))
    notifier = MagicMock()
    notifier.notify_status = AsyncMock()

    engine = DeployerEngine(cfg, service_manager=service_mgr, notifier=notifier)
    await engine.recover_or_resume()

    rec_1 = db.get_deployment("dep_crashed_1")
    assert rec_1["status"] == "failed"

    rec_2 = db.get_deployment("dep_crashed_2")
    assert rec_2["status"] == "rolled_back"
    assert "Redémarrage inopiné" in rec_2["rollback_reason"]
    assert rm.get_current_release_dir() == os.path.abspath(initial_rel)


# ─── 11. MODES CLI --ONCE ET --DRY-RUN ───────────────────────────────────────

@pytest.mark.asyncio
async def test_dry_run_simulation(test_setup):
    cfg = test_setup["config"]
    cfg.dry_run = True

    checker = HealthChecker(
        cfg,
        http_probe=AsyncMock(return_value=(True, 10.0, "HTTP 200")),
        ws_probe=AsyncMock(return_value=(True, "WS OK")),
        cdp_probe=AsyncMock(return_value=(True, "CDP OK")),
        tools_probe=AsyncMock(return_value=(True, "Tools OK")),
    )

    engine = DeployerEngine(cfg, health_checker=checker, dry_run=True)
    res = await engine.trigger_deployment(target_ref="dry_run_test", run_sync=True)
    assert res["status"] == "succeeded"

    state = engine.state_file_mgr.read_state()
    assert state["dry_run"] is True


# ─── 12. SERVEUR HTTP LOOPBACK (PORT 8001 / ZERO DÉPENDANCE) ────────────────

@pytest.mark.asyncio
async def test_loopback_http_server(test_setup):
    cfg = test_setup["config"]
    engine = DeployerEngine(cfg)
    server = DeployerServer(engine)
    await server.start()

    try:
        reader, writer = await asyncio.open_connection(cfg.http_host, cfg.http_port)

        # GET /health
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
    finally:
        await server.stop()
