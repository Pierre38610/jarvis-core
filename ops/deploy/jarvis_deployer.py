"""ops/deploy/jarvis_deployer.py
Service autonome et indépendant de déploiement VPS Blue/Green pour J.A.R.V.I.S. - Stark Industries.

Architecture & Contrat :
- Processus dédié distinct de `jarvis.service` (exécuté sous `jarvis-deployer.service`).
- Cycle de vie Blue/Green sécurisé avec releases/<id> et symlink atomique 'current'.
- Machine à états persistante : queued -> running -> smoke -> monitoring -> succeeded | rolled_back | failed.
- Idempotence stricte et verrou mono-déploiement.
- Injections complètes : racine de déploiement (JARVIS_DEPLOY_ROOT), command runner, probes health (HTTP /api/verify, WS, CDP 9222, adaptateur Telegram).
- Surveillance active pendant DEPLOY_MONITOR_SECONDS avec seuils de taux d'erreur et de latence -> Auto-rollback atomique.
- Journalisation append-only JSONL + SQLite sans aucun secret (_sanitize_secrets).
- Reprise automatique après crash / redémarrage du VPS.
- Modes CLI --once et --dry-run qui se terminent toujours d'eux-mêmes.
- API loopback HTTP (127.0.0.1:8001) et fichier d'état persistant.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import dataclasses
from datetime import datetime, timezone
import json
import logging
import os
import py_compile
import re
import shutil
import sqlite3
import sys
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("jarvis.deployer")


# ─── 1. CONFIGURATION & SANITISATION DES SECRETS ──────────────────────────────

def _sanitize_secrets(text: str) -> str:
    """Masque tout secret, jeton d'API, mot de passe ou clé privée dans les textes ou logs."""
    if not text:
        return ""
    sanitized = str(text)
    # Remplacement des motifs clés/valeurs sensibles
    key_val_pattern = re.compile(
        r'(?i)\b(token|key|secret|password|passwd|auth|jwt|bearer)\s*[:=]\s*["\']?([^"\'\s]+)["\']?'
    )
    sanitized = key_val_pattern.sub(r'\1=[REDACTED]', sanitized)
    # Jetons de bots Telegram
    sanitized = re.sub(r'bot[0-9]{8,12}:[a-zA-Z0-9_-]{30,}', '[REDACTED_TELEGRAM_TOKEN]', sanitized)
    # Clés Google AI / Gemini
    sanitized = re.sub(r'AIzaSy[a-zA-Z0-9_-]{33}', '[REDACTED_API_KEY]', sanitized)
    # Headers Bearer
    sanitized = re.sub(r'(?i)bearer\s+[a-zA-Z0-9_\-\.]{15,}', 'Bearer [REDACTED]', sanitized)
    return sanitized


# Alias de compatibilité
sanitize_text = _sanitize_secrets


def sanitize_data(data: Any) -> Any:
    """Nettoie récursivement les dictionnaires et listes pour les journaux."""
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            if any(s in str(k).lower() for s in ("token", "secret", "password", "passwd", "key", "jwt", "auth", "cert")):
                cleaned[k] = "[REDACTED]"
            else:
                cleaned[k] = sanitize_data(v)
        return cleaned
    elif isinstance(data, list):
        return [sanitize_data(item) for item in data]
    elif isinstance(data, str):
        return _sanitize_secrets(data)
    return data


@dataclasses.dataclass
class DeployerConfig:
    deploy_root: str = ""
    workspace_dir: str = ""
    releases_dir: str = ""
    current_symlink: str = ""
    state_file: str = ""
    db_path: str = ""
    journal_path: str = ""
    lock_file: str = ""
    service_name: str = "jarvis"
    http_host: str = "127.0.0.1"
    http_port: int = 8001
    jarvis_port: int = 8000
    jarvis_http_url: str = "http://127.0.0.1:8000"
    http_verify_path: str = "/api/verify"
    jarvis_ws_url: str = "ws://127.0.0.1:8000/ws"
    cdp_url: str = "http://127.0.0.1:9222"
    monitor_duration_sec: float = 10.0    # Pilotable par DEPLOY_MONITOR_SECONDS (1–3s en tests, 15–30min en prod)
    monitor_interval_sec: float = 1.0     # Intervalle de sonde pendant le monitoring
    error_threshold: float = 0.05         # Seuil d'erreur (5% max)
    max_errors: int = 3                   # Nombre absolu maximal d'erreurs tolérées en monitoring
    max_latency_ms: float = 2500.0        # Max latence moyenne tolérée
    smoke_retries: int = 5
    smoke_retry_delay_sec: float = 1.0
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    dry_run: bool = False

    @classmethod
    def from_env(
        cls,
        deploy_root_override: Optional[str] = None,
        workspace_override: Optional[str] = None,
        dry_run: bool = False,
    ) -> DeployerConfig:
        """Instancie la configuration en privilégiant JARVIS_DEPLOY_ROOT et les variables SRE standard."""
        # 1. Racine de déploiement (priorité absolue à l'injection ou à JARVIS_DEPLOY_ROOT)
        root = (
            deploy_root_override
            or os.environ.get("JARVIS_DEPLOY_ROOT")
            or workspace_override
            or os.environ.get("JARVIS_WORKSPACE_DIR")
        )
        if not root:
            cur = os.path.dirname(os.path.abspath(__file__))
            repo_root = os.path.abspath(os.path.join(cur, "..", ".."))
            root = repo_root

        root = os.path.abspath(root)
        ws = os.path.abspath(workspace_override or os.environ.get("JARVIS_WORKSPACE_DIR") or root)

        # 2. Sous-dossiers et fichiers dérivés
        releases = os.environ.get("JARVIS_RELEASES_DIR") or os.path.join(root, "releases")
        current = os.environ.get("JARVIS_CURRENT_SYMLINK") or os.path.join(root, "current")
        state = os.environ.get("JARVIS_DEPLOY_STATE") or os.path.join(root, "deployer_state.json")
        db = os.environ.get("JARVIS_DEPLOY_DB") or os.path.join(root, "deployments.db")
        journal = os.environ.get("JARVIS_DEPLOY_JOURNAL") or os.path.join(root, "deployer_journal.jsonl")
        lock = os.environ.get("JARVIS_DEPLOY_LOCK") or os.path.join(root, "deployer.lock")

        # 3. Durée de surveillance
        mon_sec_str = (
            os.environ.get("DEPLOY_MONITOR_SECONDS")
            or os.environ.get("JARVIS_DEPLOY_MONITOR_SECONDS")
            or "10.0"
        )
        try:
            mon_sec = float(mon_sec_str)
        except Exception:
            mon_sec = 10.0

        return cls(
            deploy_root=root,
            workspace_dir=ws,
            releases_dir=releases,
            current_symlink=current,
            state_file=state,
            db_path=db,
            journal_path=journal,
            lock_file=lock,
            service_name=os.environ.get("JARVIS_SERVICE_NAME", "jarvis"),
            http_host=os.environ.get("JARVIS_DEPLOY_HOST", "127.0.0.1"),
            http_port=int(os.environ.get("JARVIS_DEPLOY_PORT", "8001")),
            jarvis_port=int(os.environ.get("JARVIS_PORT", "8000")),
            jarvis_http_url=os.environ.get("JARVIS_HTTP_URL", "http://127.0.0.1:8000"),
            http_verify_path=os.environ.get("JARVIS_HTTP_VERIFY_PATH", "/api/verify"),
            jarvis_ws_url=os.environ.get("JARVIS_WS_URL", "ws://127.0.0.1:8000/ws"),
            cdp_url=os.environ.get("JARVIS_CDP_URL", "http://127.0.0.1:9222"),
            monitor_duration_sec=mon_sec,
            monitor_interval_sec=float(os.environ.get("JARVIS_DEPLOY_MONITOR_INTERVAL", "1.0")),
            error_threshold=float(os.environ.get("JARVIS_DEPLOY_ERROR_THRESHOLD", "0.05")),
            max_errors=int(os.environ.get("JARVIS_DEPLOY_MAX_ERRORS", "3")),
            max_latency_ms=float(os.environ.get("JARVIS_DEPLOY_MAX_LATENCY_MS", "2500.0")),
            smoke_retries=int(os.environ.get("JARVIS_DEPLOY_SMOKE_RETRIES", "5")),
            smoke_retry_delay_sec=float(os.environ.get("JARVIS_DEPLOY_SMOKE_DELAY", "1.0")),
            telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", "").strip(),
            dry_run=dry_run,
        )


# ─── 2. JOURNAL APPEND-ONLY & BASE DE DONNÉES ─────────────────────────────────

class DeployerJournal:
    """Journal append-only au format JSON Lines garantissant la traçabilité des événements sans fuite de secrets."""

    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def append(self, event_type: str, deployment_id: str, data: Optional[Dict[str, Any]] = None):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            "deployment_id": deployment_id,
            "data": sanitize_data(data or {}),
        }
        line = json.dumps(entry, ensure_ascii=False)
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as e:
            logger.error(f"[DeployerJournal] Échec écriture journal : {e}")

    def read_entries(self, limit: int = 100) -> List[Dict[str, Any]]:
        if not os.path.exists(self.path):
            return []
        entries = []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except Exception:
                            continue
        except Exception as e:
            logger.error(f"[DeployerJournal] Échec lecture journal : {e}")
        return entries[-limit:]


class DeployerDB:
    """Gestionnaire SQLite de l'état persistant des déploiements."""

    def __init__(self, db_path: str):
        self.db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS deployments (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                target_ref TEXT,
                release_id TEXT,
                release_dir TEXT,
                previous_release_dir TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                error_message TEXT,
                rollback_reason TEXT,
                metrics_json TEXT,
                metadata_json TEXT
            );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_deployments_created ON deployments (created_at DESC);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_deployments_status ON deployments (status);")
            conn.commit()

    def create_deployment(self, deployment_id: str, target_ref: str = "", metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO deployments (id, status, target_ref, created_at, metadata_json)
                VALUES (?, 'queued', ?, ?, ?)
                """,
                (deployment_id, target_ref, now, json.dumps(metadata or {}))
            )
            conn.commit()
        return self.get_deployment(deployment_id) or {}

    def update_status(
        self,
        deployment_id: str,
        status: str,
        release_id: Optional[str] = None,
        release_dir: Optional[str] = None,
        previous_release_dir: Optional[str] = None,
        error_message: Optional[str] = None,
        rollback_reason: Optional[str] = None,
        metrics: Optional[Dict[str, Any]] = None,
    ):
        now = datetime.now(timezone.utc).isoformat()
        updates = ["status = ?"]
        params: List[Any] = [status]

        if status == "running":
            updates.append("started_at = ?")
            params.append(now)
        elif status in ("succeeded", "rolled_back", "failed"):
            updates.append("finished_at = ?")
            params.append(now)

        if release_id is not None:
            updates.append("release_id = ?")
            params.append(release_id)
        if release_dir is not None:
            updates.append("release_dir = ?")
            params.append(release_dir)
        if previous_release_dir is not None:
            updates.append("previous_release_dir = ?")
            params.append(previous_release_dir)
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(_sanitize_secrets(error_message))
        if rollback_reason is not None:
            updates.append("rollback_reason = ?")
            params.append(_sanitize_secrets(rollback_reason))
        if metrics is not None:
            updates.append("metrics_json = ?")
            params.append(json.dumps(sanitize_data(metrics)))

        params.append(deployment_id)
        sql = f"UPDATE deployments SET {', '.join(updates)} WHERE id = ?"
        with self._get_connection() as conn:
            conn.execute(sql, params)
            conn.commit()

    def get_deployment(self, deployment_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM deployments WHERE id = ?", (deployment_id,))
            row = cur.fetchone()
            if not row:
                return None
            d = dict(row)
            if d.get("metrics_json"):
                try:
                    d["metrics"] = json.loads(d["metrics_json"])
                except Exception:
                    pass
            if d.get("metadata_json"):
                try:
                    d["metadata"] = json.loads(d["metadata_json"])
                except Exception:
                    pass
            return d

    def get_active_or_queued(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM deployments WHERE status IN ('queued', 'running', 'smoke', 'monitoring') ORDER BY created_at ASC"
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows]

    def get_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM deployments ORDER BY created_at DESC LIMIT ?", (limit,))
            return [dict(r) for r in cur.fetchall()]


class StateFileManager:
    """Gère un fichier d'état JSON atomique pour consultation rapide ou inter-processus."""

    def __init__(self, state_file: str):
        self.state_file = os.path.abspath(state_file)
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)

    def write_state(self, state_data: Dict[str, Any]):
        tmp_file = f"{self.state_file}.tmp"
        payload = sanitize_data(copy.deepcopy(state_data)) if hasattr(copy, "deepcopy") else sanitize_data(dict(state_data))
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            os.replace(tmp_file, self.state_file)
        except Exception as e:
            logger.warning(f"[StateFileManager] Échec écriture fichier état : {e}")

    def read_state(self) -> Dict[str, Any]:
        if not os.path.exists(self.state_file):
            return {}
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"[StateFileManager] Échec lecture état : {e}")
            return {}


# ─── 3. ADAPTATEUR TELEGRAM MOCKABLE ──────────────────────────────────────────

class TelegramDirectNotifier:
    """Expédie les notifications directement via l'API Telegram Bot depuis ce processus dédié."""

    def __init__(self, bot_token: str = "", chat_id: str = "", http_client: Optional[Any] = None):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._http_client = http_client

    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        if not self.bot_token or not self.chat_id:
            logger.debug(f"[TelegramDirect] Notification ignorée (non configuré) : {_sanitize_secrets(text[:80])}")
            return False

        clean_text = _sanitize_secrets(text)
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": clean_text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        try:
            if self._http_client:
                res = await self._http_client.post(url, json=payload, timeout=10.0)
                return getattr(res, "status_code", 200) == 200

            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload)
                return res.status_code == 200
        except Exception as e:
            logger.warning(f"[TelegramDirect] Échec envoi Telegram : {e}")
            return False

    async def notify_status(self, deployment_id: str, status: str, details: Optional[Dict[str, Any]] = None):
        icons = {
            "queued": "⏳",
            "running": "🚀",
            "smoke": "🧪",
            "monitoring": "👀",
            "succeeded": "🎉",
            "rolled_back": "⚠️",
            "failed": "❌",
        }
        icon = icons.get(status, "ℹ️")
        details = details or {}
        release_id = details.get("release_id", "-")
        reason = details.get("rollback_reason") or details.get("error_message") or ""

        msg_lines = [
            f"<b>{icon} Jarvis Deployer [{status.upper()}]</b>",
            f"• <b>Déploiement :</b> <code>{deployment_id}</code>",
            f"• <b>Release :</b> <code>{release_id}</code>",
        ]
        if reason:
            msg_lines.append(f"• <b>Motif/Erreur :</b> {_sanitize_secrets(reason)}")
        if "metrics" in details:
            m = details["metrics"]
            lat = m.get("avg_latency_ms", 0)
            err_r = m.get("error_rate", 0) * 100
            msg_lines.append(f"• <b>Métriques :</b> Latence ~{lat:.1f}ms | Erreurs ~{err_r:.1f}%")

        await self.send_message("\n".join(msg_lines))


# ─── 4. GESTIONNAIRE DE COMMANDES & SYSTEMCTL ─────────────────────────────────

class ServiceManager:
    """Pilote le redémarrage et le statut du service avec runner injectable."""

    def __init__(
        self,
        service_name: str = "jarvis",
        runner: Optional[Callable[..., Union[Tuple[int, str, str], Awaitable[Tuple[int, str, str]]]]] = None,
        dry_run: bool = False,
    ):
        self.service_name = service_name
        self.runner = runner or self._default_runner
        self.dry_run = dry_run

    def _default_runner(self, cmd: List[str]) -> Tuple[int, str, str]:
        # En mode dry-run ou hors Linux, ne jamais exécuter systemctl
        if self.dry_run:
            return 0, "DRY_RUN: execution simulee", ""
        if sys.platform != "linux":
            return 0, f"Simulated non-linux ({sys.platform}) execution", ""

        import subprocess
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return res.returncode, res.stdout, res.stderr
        except Exception as e:
            return 1, "", str(e)

    def restart(self) -> Tuple[bool, str]:
        if self.dry_run:
            logger.info(f"[ServiceManager] [DRY_RUN] Simulation redémarrage service '{self.service_name}'")
            return True, "DRY_RUN: Service redémarré en simulation"

        logger.info(f"[ServiceManager] Redémarrage de l'unité '{self.service_name}'...")
        res = self.runner(["sudo", "systemctl", "restart", self.service_name])
        # Support synchrone ou coroutine
        if asyncio.iscoroutine(res):
            raise RuntimeError("Le runner fourni doit être appelé de façon compatible")
        code, stdout, stderr = res
        if code != 0:
            err = stderr.strip() or stdout.strip() or f"Code sortie {code}"
            return False, f"Échec redémarrage service {self.service_name} : {err}"
        return True, "Service redémarré avec succès"

    def is_active(self) -> bool:
        if self.dry_run:
            return True
        res = self.runner(["sudo", "systemctl", "is-active", self.service_name])
        code, stdout, _ = res
        return code == 0 and "active" in stdout.lower()


# ─── 5. SONDES HEALTH & SMOKE TESTS INJECTABLES ───────────────────────────────

class HealthChecker:
    """Exécute les smoke tests et le polling de santé (HTTP /api/verify, WebSocket, CDP 9222, Contrats)."""

    def __init__(
        self,
        config: DeployerConfig,
        http_client: Optional[Any] = None,
        http_probe: Optional[Callable[[], Awaitable[Tuple[bool, float, str]]]] = None,
        ws_probe: Optional[Callable[[], Awaitable[Tuple[bool, str]]]] = None,
        cdp_probe: Optional[Callable[[], Awaitable[Tuple[bool, str]]]] = None,
        tools_probe: Optional[Callable[[str], Awaitable[Tuple[bool, str]]]] = None,
    ):
        self.config = config
        self._http_client = http_client
        self._custom_http_probe = http_probe
        self._custom_ws_probe = ws_probe
        self._custom_cdp_probe = cdp_probe
        self._custom_tools_probe = tools_probe

    async def check_http(self) -> Tuple[bool, float, str]:
        """Vérifie l'accessibilité de l'endpoint HTTP (/api/verify par défaut, avec fallback racine)."""
        if self._custom_http_probe:
            return await self._custom_http_probe()

        start = time.time()
        base_url = self.config.jarvis_http_url.rstrip("/")
        verify_path = self.config.http_verify_path or "/api/verify"
        url = f"{base_url}{verify_path}"

        try:
            if self._http_client:
                res = await self._http_client.get(url, timeout=5.0)
                lat = (time.time() - start) * 1000.0
                status_code = getattr(res, "status_code", 500)
                if status_code == 404:
                    # Fallback sur / si /api/verify n'est pas encore routé
                    res_root = await self._http_client.get(f"{base_url}/", timeout=5.0)
                    status_code = getattr(res_root, "status_code", 500)
                ok = (status_code < 500)
                return ok, lat, f"HTTP {status_code}"

            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(url)
                lat = (time.time() - start) * 1000.0
                if res.status_code == 404:
                    res_root = await client.get(f"{base_url}/")
                    status_code = res_root.status_code
                else:
                    status_code = res.status_code
                ok = (status_code < 500)
                return ok, lat, f"HTTP {status_code}"
        except Exception as e:
            lat = (time.time() - start) * 1000.0
            return False, lat, str(e)

    async def check_cdp(self) -> Tuple[bool, str]:
        """Vérifie l'endpoint /json/version du Chrome CDP Headless (port 9222)."""
        if self._custom_cdp_probe:
            return await self._custom_cdp_probe()

        url = self.config.cdp_url.rstrip("/") + "/json/version"
        try:
            if self._http_client:
                res = await self._http_client.get(url, timeout=3.0)
                code = getattr(res, "status_code", 500)
                return code == 200, f"CDP HTTP {code}"

            import httpx
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(url)
                return res.status_code == 200, f"CDP HTTP {res.status_code}"
        except Exception as e:
            return False, f"CDP Inaccessible ({e})"

    async def check_websocket(self) -> Tuple[bool, str]:
        """Vérifie l'établissement ou l'écoute du port WebSocket."""
        if self._custom_ws_probe:
            return await self._custom_ws_probe()

        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            host = self.config.http_host
            port = self.config.jarvis_port
            res = sock.connect_ex((host, port))
            sock.close()
            if res == 0:
                return True, "Port WebSocket accessible"
            return False, f"Port {port} non joignable (code {res})"
        except Exception as e:
            return False, f"Erreur WebSocket probe : {e}"

    async def check_tool_contracts(self, release_dir: str) -> Tuple[bool, str]:
        """Vérifie l'intégrité syntaxique des déclarations et contrats d'outils."""
        if self._custom_tools_probe:
            return await self._custom_tools_probe(release_dir)

        try:
            tools_dir = os.path.join(release_dir, "backend", "core", "tools")
            if not os.path.exists(tools_dir):
                tools_dir = os.path.join(release_dir, "core", "tools")
            if os.path.exists(tools_dir):
                for f in ("declarations.py", "dispatcher.py", "result.py"):
                    fp = os.path.join(tools_dir, f)
                    if os.path.exists(fp):
                        py_compile.compile(fp, doraise=True)
            return True, "Contrats d'outils intègres"
        except Exception as e:
            return False, f"Erreur validation contrats outils : {e}"

    async def run_full_smoke_check(self, release_dir: str) -> Tuple[bool, Dict[str, Any]]:
        """Exécute l'ensemble des sondes smoke avec politique de retry."""
        results: Dict[str, Any] = {}
        ok_http = False
        last_http_msg = ""
        lat = 0.0

        for _ in range(1, self.config.smoke_retries + 1):
            ok_http, lat, last_http_msg = await self.check_http()
            if ok_http:
                break
            await asyncio.sleep(self.config.smoke_retry_delay_sec)

        results["http"] = {"ok": ok_http, "latency_ms": lat, "message": last_http_msg}

        ok_ws, ws_msg = await self.check_websocket()
        results["websocket"] = {"ok": ok_ws, "message": ws_msg}

        ok_cdp, cdp_msg = await self.check_cdp()
        results["cdp"] = {"ok": ok_cdp, "message": cdp_msg}

        ok_tools, tools_msg = await self.check_tool_contracts(release_dir)
        results["tool_contracts"] = {"ok": ok_tools, "message": tools_msg}

        overall_ok = ok_http and ok_ws and ok_tools
        return overall_ok, results


# ─── 6. GESTIONNAIRE DE RELEASES & SYMLINK BLUE/GREEN ────────────────────────

EXCLUDE_DIRS = {
    "venv", ".venv", ".git", ".jarvis_chrome_profile", ".jarvis_shopping_profile",
    ".browseruse", ".antigravity_save", "downloads", "__pycache__", "clés ssh", "cles ssh",
    "releases", "current", ".cache", ".pytest_cache", "build", "managed_components",
    "firmware", "_archive", "scratch_healing", "_test_scratch", ".healing_sandboxes"
}
EXCLUDE_FILES = {
    "cloudflared.exe", "jarvis_memory.db", ".env", "deployments.db", "deployer.lock",
    "deployer_state.json", "deployer_journal.jsonl"
}


class ReleaseManager:
    """Gère l'arborescence releases/<id> et la bascule atomique Blue/Green de 'current' strictement dans deploy_root."""

    def __init__(self, config: DeployerConfig):
        self.config = config
        os.makedirs(self.config.releases_dir, exist_ok=True)

    def prepare_release(self, source_dir: str, release_id: Optional[str] = None) -> Tuple[str, str]:
        """Crée un dossier de release immuté et valide la syntaxe Python."""
        rel_id = release_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        target_dir = os.path.join(self.config.releases_dir, rel_id)
        os.makedirs(target_dir, exist_ok=True)

        def _ignore_filter(src, names):
            ignored = set()
            for name in names:
                if name in EXCLUDE_DIRS or name in EXCLUDE_FILES or name.startswith(".antigravity"):
                    ignored.add(name)
                elif any(name.endswith(ext) for ext in (".pyc", ".tmp", ".log", ".key")):
                    ignored.add(name)
            return ignored

        # Copie récursive sécurisée
        for item in os.listdir(source_dir):
            if item in EXCLUDE_DIRS or item in EXCLUDE_FILES or item.startswith("."):
                continue
            src_path = os.path.join(source_dir, item)
            dst_path = os.path.join(target_dir, item)
            if os.path.isdir(src_path):
                shutil.copytree(src_path, dst_path, ignore=_ignore_filter, symlinks=False if sys.platform == "win32" else True)
            elif os.path.isfile(src_path) and not item.endswith((".key", ".tmp", ".log")):
                shutil.copy2(src_path, dst_path)

        # Contrôle strict py_compile
        for root, _, files in os.walk(target_dir):
            for f in files:
                if f.endswith(".py"):
                    full_p = os.path.join(root, f)
                    try:
                        py_compile.compile(full_p, doraise=True)
                    except Exception as e:
                        shutil.rmtree(target_dir, ignore_errors=True)
                        raise RuntimeError(f"Erreur py_compile sur {full_p} : {e}")

        return rel_id, target_dir

    def get_current_release_dir(self) -> Optional[str]:
        sym = self.config.current_symlink
        if os.path.islink(sym):
            try:
                target = os.readlink(sym)
                if not os.path.isabs(target):
                    target = os.path.join(os.path.dirname(sym), target)
                return os.path.abspath(target)
            except Exception:
                return None
        elif os.path.exists(sym) and os.path.isdir(sym):
            return os.path.abspath(sym)

        # Fallback fichier pointeur
        ptr = os.path.join(self.config.deploy_root, "current_release.txt")
        if os.path.exists(ptr):
            try:
                with open(ptr, "r", encoding="utf-8") as f:
                    p = f.read().strip()
                    if os.path.isdir(p):
                        return os.path.abspath(p)
            except Exception:
                pass
        return None

    def activate_symlink(self, target_dir: str) -> Optional[str]:
        """Bascule atomique du symlink 'current' vers target_dir. Retourne l'ancienne cible."""
        sym = self.config.current_symlink
        prev = self.get_current_release_dir()

        if self.config.dry_run:
            logger.info(f"[ReleaseManager] [DRY_RUN] Simulation bascule symlink current -> {target_dir}")
            return prev

        tmp_link = sym + "_tmp"
        if os.path.islink(tmp_link) or os.path.exists(tmp_link):
            try:
                if os.path.islink(tmp_link):
                    os.remove(tmp_link)
                else:
                    shutil.rmtree(tmp_link, ignore_errors=True)
            except Exception:
                pass

        try:
            os.symlink(target_dir, tmp_link, target_is_directory=True)
            os.replace(tmp_link, sym)
            logger.info(f"[ReleaseManager] Symlink 'current' basculé vers {target_dir}")
        except (OSError, NotImplementedError) as e:
            # Fallback Windows sans permissions symlink
            ptr = os.path.join(self.config.deploy_root, "current_release.txt")
            with open(ptr, "w", encoding="utf-8") as f:
                f.write(target_dir)
            logger.info(f"[ReleaseManager] Pointeur alternatif current_release.txt mis à jour ({e})")

        return prev

    def revert_symlink(self, previous_dir: str) -> bool:
        """Restaure le symlink vers la release précédente."""
        if not previous_dir or not os.path.exists(previous_dir):
            logger.warning(f"[ReleaseManager] Impossible de restaurer : dossier précédent inexistant ({previous_dir})")
            return False
        self.activate_symlink(previous_dir)
        return True


# ─── 7. MOTEUR CENTRAL D'ORCHESTRATION ────────────────────────────────────────

class DeployerEngine:
    """Orchestre la machine à états de déploiement Blue/Green, le verrou mono-instance, la surveillance et l'auto-rollback."""

    def __init__(
        self,
        config: Optional[DeployerConfig] = None,
        deploy_root: Optional[str] = None,
        command_runner: Optional[Callable] = None,
        service_manager: Optional[ServiceManager] = None,
        notifier: Optional[Any] = None,
        health_checker: Optional[HealthChecker] = None,
        dry_run: bool = False,
    ):
        if config is None:
            self.config = DeployerConfig.from_env(deploy_root_override=deploy_root, dry_run=dry_run)
        else:
            self.config = config
            if deploy_root:
                self.config.deploy_root = deploy_root
            if dry_run:
                self.config.dry_run = dry_run

        self.db = DeployerDB(self.config.db_path)
        self.journal = DeployerJournal(self.config.journal_path)
        self.state_file_mgr = StateFileManager(self.config.state_file)

        self.service_manager = service_manager or ServiceManager(
            service_name=self.config.service_name,
            runner=command_runner,
            dry_run=self.config.dry_run,
        )
        self.notifier = notifier or TelegramDirectNotifier(
            bot_token=self.config.telegram_bot_token,
            chat_id=self.config.telegram_chat_id,
        )
        self.health_checker = health_checker or HealthChecker(self.config)
        self.release_manager = ReleaseManager(self.config)

        self._lock = asyncio.Lock()
        self._current_task: Optional[asyncio.Task] = None
        self._active_deployment_id: Optional[str] = None
        self._is_recovering = False

    def acquire_file_lock(self) -> bool:
        """Tente d'acquérir le verrou exclusif mono-déploiement."""
        pid = str(os.getpid())
        lock_file = self.config.lock_file
        if os.path.exists(lock_file):
            try:
                with open(lock_file, "r") as f:
                    old_pid = f.read().strip()
                if old_pid and old_pid.isdigit():
                    try:
                        os.kill(int(old_pid), 0)
                        return False
                    except (OSError, ProcessLookupError, AttributeError):
                        pass
            except Exception:
                pass
        try:
            with open(lock_file, "w") as f:
                f.write(pid)
            return True
        except Exception:
            return False

    def release_file_lock(self):
        try:
            if os.path.exists(self.config.lock_file):
                os.remove(self.config.lock_file)
        except Exception:
            pass

    def _sync_state(self, deployment_id: str, status: str, extra: Optional[Dict[str, Any]] = None):
        """Met à jour l'état persistant dans la DB SQLite, le fichier d'état et le journal."""
        extra = extra or {}
        self.state_file_mgr.write_state({
            "deployment_id": deployment_id,
            "status": status,
            "release_id": extra.get("release_id"),
            "release_dir": extra.get("release_dir"),
            "previous_release_dir": extra.get("previous_release_dir"),
            "current_release": self.release_manager.get_current_release_dir(),
            "dry_run": self.config.dry_run,
            "metrics": extra.get("metrics"),
            "error_message": extra.get("error_message"),
            "rollback_reason": extra.get("rollback_reason"),
        })

    async def recover_or_resume(self):
        """Au démarrage : réconcilie et nettoie les déploiements interrompus lors d'un crash ou redémarrage."""
        self._is_recovering = True
        try:
            dangling = self.db.get_active_or_queued()
            for dep in dangling:
                dep_id = dep["id"]
                st = dep["status"]
                logger.warning(f"[DeployerEngine] Détection d'un déploiement interrompu ({dep_id}) au statut '{st}'")
                self.journal.append("CRASH_RECOVERY_DETECTED", dep_id, {"previous_status": st})

                if st in ("queued", "running"):
                    self.db.update_status(dep_id, "failed", error_message="Interrompu par arrêt inopiné du processus")
                    self._sync_state(dep_id, "failed", {"error_message": "Interruption inopinée"})
                    self.journal.append("CRASH_RECOVERY_FAILED", dep_id)
                elif st in ("smoke", "monitoring"):
                    prev_dir = dep.get("previous_release_dir")
                    reason = f"Redémarrage inopiné pendant l'étape critique '{st}'"
                    if prev_dir and os.path.exists(prev_dir):
                        logger.info(f"[DeployerEngine] Déclenchement rollback de sécurité vers {prev_dir}")
                        self.release_manager.revert_symlink(prev_dir)
                        self.service_manager.restart()
                        self.db.update_status(dep_id, "rolled_back", rollback_reason=reason)
                        self._sync_state(dep_id, "rolled_back", {"rollback_reason": reason, "previous_release_dir": prev_dir})
                        self.journal.append("CRASH_RECOVERY_ROLLED_BACK", dep_id, {"target": prev_dir})
                        if hasattr(self.notifier, "notify_status"):
                            await self.notifier.notify_status(dep_id, "rolled_back", {"rollback_reason": reason})
                    else:
                        self.db.update_status(dep_id, "failed", error_message=reason)
                        self._sync_state(dep_id, "failed", {"error_message": reason})
                        self.journal.append("CRASH_RECOVERY_FAILED", dep_id, {"error": reason})
        finally:
            self.release_file_lock()
            self._is_recovering = False

    async def trigger_deployment(
        self,
        source_dir: Optional[str] = None,
        target_ref: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        run_sync: bool = False,
    ) -> Dict[str, Any]:
        """Point d'entrée idempotent de soumission d'une demande de déploiement."""
        src = source_dir or self.config.workspace_dir

        # Idempotence : si un déploiement avec le même target_ref est déjà en cours
        active = self.db.get_active_or_queued()
        for a in active:
            if target_ref and a.get("target_ref") == target_ref:
                logger.info(f"[DeployerEngine] Requête idempotente : déploiement {a['id']} déjà actif pour {target_ref}")
                return a

        if self._lock.locked() or not self.acquire_file_lock():
            dep_id = f"dep_{int(time.time())}_{os.urandom(2).hex()}"
            record = self.db.create_deployment(dep_id, target_ref=target_ref, metadata=metadata)
            self._sync_state(dep_id, "queued")
            self.journal.append("QUEUED_WAITING_LOCK", dep_id)
            return {"status": "queued", "id": dep_id, "message": "Déploiement mis en file d'attente"}

        dep_id = f"dep_{int(time.time())}_{os.urandom(2).hex()}"
        record = self.db.create_deployment(dep_id, target_ref=target_ref, metadata=metadata)
        self._sync_state(dep_id, "queued")
        self.journal.append("QUEUED", dep_id, {"source": src, "ref": target_ref, "dry_run": self.config.dry_run})

        self._active_deployment_id = dep_id

        if run_sync:
            await self._run_deployment_pipeline(dep_id, src, target_ref)
            return self.db.get_deployment(dep_id) or record
        else:
            self._current_task = asyncio.create_task(self._run_deployment_pipeline(dep_id, src, target_ref))
            return record

    async def _run_deployment_pipeline(self, deployment_id: str, source_dir: str, target_ref: str):
        async with self._lock:
            release_dir = ""
            prev_dir = ""
            try:
                # ── ÉTAPE 1 : RUNNING (Préparation & Validation syntaxique)
                self.db.update_status(deployment_id, "running")
                self._sync_state(deployment_id, "running")
                self.journal.append("RUNNING_START", deployment_id)
                if hasattr(self.notifier, "notify_status"):
                    await self.notifier.notify_status(deployment_id, "running")

                rel_id, release_dir = self.release_manager.prepare_release(source_dir)
                self.db.update_status(deployment_id, "running", release_id=rel_id, release_dir=release_dir)
                self._sync_state(deployment_id, "running", {"release_id": rel_id, "release_dir": release_dir})
                self.journal.append("RELEASE_PREPARED", deployment_id, {"release_dir": release_dir})

                # ── ÉTAPE 2 : SMOKE (Bascule symlink & Redémarrage & Probes)
                prev_dir = self.release_manager.activate_symlink(release_dir) or ""
                self.db.update_status(deployment_id, "smoke", previous_release_dir=prev_dir)
                self._sync_state(deployment_id, "smoke", {"previous_release_dir": prev_dir, "release_id": rel_id})
                self.journal.append("SYMLINK_ACTIVATED", deployment_id, {"new": release_dir, "prev": prev_dir})

                restart_ok, restart_msg = self.service_manager.restart()
                if not restart_ok:
                    raise RuntimeError(f"Échec redémarrage service systemd : {restart_msg}")

                smoke_ok, smoke_details = await self.health_checker.run_full_smoke_check(release_dir)
                self.journal.append("SMOKE_CHECK_COMPLETED", deployment_id, smoke_details)

                if not smoke_ok:
                    raise RuntimeError(f"Échec des smoke tests : {smoke_details}")

                if hasattr(self.notifier, "notify_status"):
                    await self.notifier.notify_status(deployment_id, "smoke", {"release_id": rel_id})

                # ── ÉTAPE 3 : MONITORING (Surveillance active)
                self.db.update_status(deployment_id, "monitoring")
                self._sync_state(deployment_id, "monitoring", {"release_id": rel_id})
                self.journal.append("MONITORING_START", deployment_id, {"duration_sec": self.config.monitor_duration_sec})
                if hasattr(self.notifier, "notify_status"):
                    await self.notifier.notify_status(deployment_id, "monitoring", {"release_id": rel_id})

                mon_ok, mon_metrics, mon_reason = await self._run_monitoring_loop(deployment_id)

                if not mon_ok:
                    logger.warning(f"[DeployerEngine] Déclenchement automatique de rollback : {mon_reason}")
                    self.journal.append("AUTO_ROLLBACK_TRIGGERED", deployment_id, {"reason": mon_reason, "metrics": mon_metrics})
                    self._execute_rollback(prev_dir)
                    self.db.update_status(deployment_id, "rolled_back", rollback_reason=mon_reason, metrics=mon_metrics)
                    self._sync_state(deployment_id, "rolled_back", {"rollback_reason": mon_reason, "metrics": mon_metrics})
                    self.journal.append("ROLLED_BACK", deployment_id)
                    if hasattr(self.notifier, "notify_status"):
                        await self.notifier.notify_status(deployment_id, "rolled_back", {
                            "release_id": rel_id,
                            "rollback_reason": mon_reason,
                            "metrics": mon_metrics
                        })
                    return

                # ── ÉTAPE 4 : SUCCEEDED
                self.db.update_status(deployment_id, "succeeded", metrics=mon_metrics)
                self._sync_state(deployment_id, "succeeded", {"release_id": rel_id, "metrics": mon_metrics})
                self.journal.append("SUCCEEDED", deployment_id, mon_metrics)
                if hasattr(self.notifier, "notify_status"):
                    await self.notifier.notify_status(deployment_id, "succeeded", {"release_id": rel_id, "metrics": mon_metrics})

            except Exception as e:
                err_text = str(e)
                logger.error(f"[DeployerEngine] Incident déploiement {deployment_id} : {err_text}")
                self.journal.append("DEPLOYMENT_FAILED", deployment_id, {"error": err_text})

                if prev_dir and os.path.exists(prev_dir):
                    logger.info(f"[DeployerEngine] Rollback de secours vers {prev_dir}")
                    self._execute_rollback(prev_dir)
                    self.db.update_status(deployment_id, "rolled_back", rollback_reason=f"Erreur d'étape : {err_text}")
                    self._sync_state(deployment_id, "rolled_back", {"rollback_reason": err_text})
                    if hasattr(self.notifier, "notify_status"):
                        await self.notifier.notify_status(deployment_id, "rolled_back", {
                            "rollback_reason": f"Erreur critique : {err_text}"
                        })
                else:
                    self.db.update_status(deployment_id, "failed", error_message=err_text)
                    self._sync_state(deployment_id, "failed", {"error_message": err_text})
                    if hasattr(self.notifier, "notify_status"):
                        await self.notifier.notify_status(deployment_id, "failed", {"error_message": err_text})

            finally:
                self.release_file_lock()
                self._active_deployment_id = None

    async def _run_monitoring_loop(self, deployment_id: str) -> Tuple[bool, Dict[str, Any], str]:
        """Boucle de surveillance analysant le taux d'erreur, le nombre d'erreurs et la latence moyenne."""
        start_t = time.time()
        end_t = start_t + self.config.monitor_duration_sec
        checks = 0
        errors = 0
        latencies: List[float] = []

        while time.time() < end_t:
            checks += 1
            ok, lat, msg = await self.health_checker.check_http()
            if not ok:
                errors += 1
            latencies.append(lat)

            err_rate = (errors / checks) if checks > 0 else 0.0
            avg_lat = (sum(latencies) / len(latencies)) if latencies else 0.0

            # Détection dépassement de seuil d'erreurs absolu ou relatif
            if errors >= self.config.max_errors:
                reason = f"Seuil maximal d'erreurs franchi ({errors} erreurs >= max {self.config.max_errors})"
                metrics = {"checks": checks, "errors": errors, "error_rate": err_rate, "avg_latency_ms": avg_lat}
                return False, metrics, reason

            if checks >= 3 and err_rate > self.config.error_threshold:
                reason = f"Taux d'erreur trop élevé ({err_rate*100:.1f}% > seuil {self.config.error_threshold*100:.1f}%)"
                metrics = {"checks": checks, "errors": errors, "error_rate": err_rate, "avg_latency_ms": avg_lat}
                return False, metrics, reason

            if checks >= 3 and avg_lat > self.config.max_latency_ms:
                reason = f"Latence moyenne excessive ({avg_lat:.1f}ms > max {self.config.max_latency_ms:.1f}ms)"
                metrics = {"checks": checks, "errors": errors, "error_rate": err_rate, "avg_latency_ms": avg_lat}
                return False, metrics, reason

            rem = end_t - time.time()
            if rem <= 0:
                break
            sleep_t = min(self.config.monitor_interval_sec, rem)
            await asyncio.sleep(sleep_t)

        final_err_rate = (errors / checks) if checks > 0 else 0.0
        final_avg_lat = (sum(latencies) / len(latencies)) if latencies else 0.0
        metrics = {
            "checks": checks,
            "errors": errors,
            "error_rate": final_err_rate,
            "avg_latency_ms": round(final_avg_lat, 2),
            "duration_monitored_sec": round(time.time() - start_t, 2)
        }
        return True, metrics, ""

    def _execute_rollback(self, previous_dir: str):
        """Action physique atomique de rollback."""
        if previous_dir and os.path.exists(previous_dir):
            self.release_manager.revert_symlink(previous_dir)
            self.service_manager.restart()
            logger.info(f"[DeployerEngine] Rollback physique complété vers {previous_dir}")

    async def manual_rollback(self) -> Dict[str, Any]:
        """Déclenche un rollback manuel immédiat vers la release précédente."""
        recent = self.db.get_recent(10)
        target_dir = ""
        for r in recent:
            if r.get("previous_release_dir") and os.path.exists(r["previous_release_dir"]):
                target_dir = r["previous_release_dir"]
                break

        if not target_dir:
            return {"status": "error", "message": "Aucune release précédente valide trouvée"}

        self._execute_rollback(target_dir)
        dep_id = f"dep_rollback_{int(time.time())}"
        self.db.create_deployment(dep_id, target_ref="manual_rollback")
        self.db.update_status(dep_id, "rolled_back", rollback_reason="Déclenché manuellement par l'opérateur")
        self._sync_state(dep_id, "rolled_back", {"rollback_reason": "Rollback manuel exécuté", "restored_dir": target_dir})
        self.journal.append("MANUAL_ROLLBACK", dep_id, {"target": target_dir})
        if hasattr(self.notifier, "notify_status"):
            await self.notifier.notify_status(dep_id, "rolled_back", {"rollback_reason": "Rollback manuel exécuté"})
        return {"status": "rolled_back", "id": dep_id, "restored_dir": target_dir}


# ─── 8. API LOOPBACK HTTP (ZERO DÉPENDANCE EXTERNE) ───────────────────────────

class DeployerServer:
    """Serveur HTTP loopback léger asynchrone pour piloter le déployeur en local."""

    def __init__(self, engine: DeployerEngine):
        self.engine = engine
        self.config = engine.config
        self._server: Optional[asyncio.AbstractServer] = None

    async def start(self):
        await self.engine.recover_or_resume()
        host = self.config.http_host
        port = self.config.http_port
        self._server = await asyncio.start_server(self._handle_client, host, port)
        logger.info(f"[DeployerServer] API HTTP Loopback active sur http://{host}:{port}")

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            line = await reader.readline()
            if not line:
                writer.close()
                return

            req_line = line.decode().strip()
            parts = req_line.split(" ")
            if len(parts) < 2:
                writer.close()
                return
            method, path = parts[0], parts[1]

            content_length = 0
            while True:
                h_line = await reader.readline()
                if not h_line or h_line == b"\r\n" or h_line == b"\n":
                    break
                h_str = h_line.decode().strip().lower()
                if h_str.startswith("content-length:"):
                    content_length = int(h_str.split(":")[1].strip())

            body = b""
            if content_length > 0:
                body = await reader.readexactly(content_length)

            res_status, res_data = await self._route_request(method, path, body)

            body_bytes = json.dumps(res_data, ensure_ascii=False).encode("utf-8")
            resp_lines = [
                f"HTTP/1.1 {res_status} OK" if res_status == 200 else f"HTTP/1.1 {res_status} Error",
                "Content-Type: application/json; charset=utf-8",
                f"Content-Length: {len(body_bytes)}",
                "Connection: close",
                "",
                ""
            ]
            writer.write("\r\n".join(resp_lines).encode("latin-1") + body_bytes)
            await writer.drain()
        except Exception as e:
            logger.error(f"[DeployerServer] Erreur traitement requête : {e}")
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def _route_request(self, method: str, path: str, body: bytes) -> Tuple[int, Dict[str, Any]]:
        clean_path = path.split("?")[0].rstrip("/")

        if method == "GET" and clean_path in ("", "/health"):
            return 200, {
                "status": "ok",
                "service": "jarvis-deployer",
                "active_deployment": self.engine._active_deployment_id,
                "current_release": self.engine.release_manager.get_current_release_dir(),
            }

        elif method == "GET" and clean_path == "/status":
            recent = self.engine.db.get_recent(5)
            active = self.engine.db.get_active_or_queued()
            state = self.engine.state_file_mgr.read_state()
            return 200, {
                "service": "jarvis-deployer",
                "active": active,
                "recent": recent,
                "state_file": state,
                "current_symlink": self.engine.release_manager.get_current_release_dir(),
            }

        elif method == "GET" and clean_path in ("/deployments", "/history"):
            return 200, {"deployments": self.engine.db.get_recent(50)}

        elif method == "POST" and clean_path == "/deploy":
            payload = {}
            if body:
                try:
                    payload = json.loads(body.decode("utf-8"))
                except Exception:
                    pass
            source_dir = payload.get("source_dir")
            target_ref = payload.get("target_ref", "")
            meta = payload.get("metadata", {})
            res = await self.engine.trigger_deployment(source_dir=source_dir, target_ref=target_ref, metadata=meta)
            return 200, res

        elif method == "POST" and clean_path == "/rollback":
            res = await self.engine.manual_rollback()
            return (200 if res.get("status") != "error" else 400), res

        return 404, {"error": "Not Found", "path": clean_path}


# ─── 9. POINT D'ENTRÉE CLI & GESTION TERMINAISON ──────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="J.A.R.V.I.S. Déployeur Indépendant VPS Blue/Green")
    parser.add_argument("--server", action="store_true", help="Lance le démon serveur HTTP loopback")
    parser.add_argument("--deploy", action="store_true", help="Déclenche immédiatement un déploiement")
    parser.add_argument("--once", action="store_true", help="Exécute un cycle de déploiement unique synchrone puis se termine")
    parser.add_argument("--dry-run", action="store_true", help="Simule le cycle de déploiement sans basculer la production puis se termine")
    parser.add_argument("--rollback", action="store_true", help="Déclenche un rollback immédiat")
    parser.add_argument("--status", action="store_true", help="Affiche le statut courant des déploiements")
    parser.add_argument("--source", type=str, default="", help="Dossier source du code à déployer")
    parser.add_argument("--ref", type=str, default="", help="Référence Git ou identifiant cible")
    parser.add_argument("--root", type=str, default="", help="Racine de déploiement (override JARVIS_DEPLOY_ROOT)")
    return parser.parse_args()


async def main_async():
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s : %(message)s")

    cfg = DeployerConfig.from_env(
        deploy_root_override=args.root or None,
        workspace_override=args.source or None,
        dry_run=args.dry_run,
    )
    engine = DeployerEngine(cfg, dry_run=args.dry_run)

    if args.server:
        server = DeployerServer(engine)
        await server.start()
        print(f"✦ J.A.R.V.I.S. Deployer démarré sur http://{cfg.http_host}:{cfg.http_port} (PID {os.getpid()})")
        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\nArrêt propre du Deployer...")
            await server.stop()
            return

    elif args.rollback:
        res = await engine.manual_rollback()
        print(json.dumps(res, indent=2))
        return

    elif args.status:
        recent = engine.db.get_recent(5)
        active = engine.db.get_active_or_queued()
        state = engine.state_file_mgr.read_state()
        print(json.dumps({"active": active, "recent": recent, "state": state}, indent=2))
        return

    elif args.once or args.dry_run or args.deploy or not sys.argv[1:]:
        # Modes CLI qui se terminent toujours d'eux-mêmes
        res = await engine.trigger_deployment(
            source_dir=args.source or None,
            target_ref=args.ref or "cli_trigger",
            run_sync=True,
        )
        print(json.dumps(res, indent=2))
        st = res.get("status")
        if st in ("succeeded", "queued"):
            sys.exit(0)
        else:
            sys.exit(1 if not args.dry_run else 0)


def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
