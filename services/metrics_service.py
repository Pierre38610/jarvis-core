"""services/metrics_service.py
Service d'instrumentation et de métriques pour les appels d'outils J.A.R.V.I.S.
Gère l'enregistrement asynchrone non-bloquant (PostgreSQL 16 + buffer mémoire de secours)
et fournit les agrégats de performance (top outils, taux d'échec, latence moy/p95, tiers, coûts).
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.metrics")

# Fenêtres temporelles supportées
WINDOW_DURATIONS = {
    "24h": timedelta(hours=24),
    "7j": timedelta(days=7),
    "7d": timedelta(days=7),
    "30j": timedelta(days=30),
    "30d": timedelta(days=30),
}


class MetricsService:
    """Service central d'observabilité pour les appels d'outils."""

    def __init__(self, buffer_size: int = 2000):
        # Buffer mémoire circulaire ultra-rapide pour fallback hors-ligne et calculs instantanés
        self._memory_buffer: deque = deque(maxlen=buffer_size)
        self._schema_ensured: bool = False
        self._claimed_success_without_verification: int = 0

    def record_claimed_success_without_verification(self, tool_name: str = "") -> None:
        """Incrémente le compteur d'alerte lorsqu'un succès est affirmé sans vérification indépendante."""
        self._claimed_success_without_verification += 1
        logger.warning(
            f"[MetricsService] Succès sans vérification pour '{tool_name}' (total: {self._claimed_success_without_verification})"
        )

    def increment_claimed_success_without_verification(self) -> None:
        self.record_claimed_success_without_verification()

    def get_claimed_success_without_verification_count(self) -> int:
        return self._claimed_success_without_verification

    @property
    def claimed_success_without_verification(self) -> int:
        return self._claimed_success_without_verification

    async def _get_pg_pool(self):
        """Récupère le pool PostgreSQL depuis vector_memory."""
        try:
            from services.memory import vector_memory
            return vector_memory._pg_pool
        except Exception:
            return None

    async def ensure_schema(self) -> bool:
        """Vérifie ou applique la création de la table tool_call_metrics."""
        if self._schema_ensured:
            return True

        pool = await self._get_pg_pool()
        if not pool:
            return False

        try:
            sql = """
            CREATE TABLE IF NOT EXISTS tool_call_metrics (
                id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
                created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
                tool_name           TEXT            NOT NULL,
                status              TEXT            NOT NULL,
                latency_ms          DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                cognitive_tier      SMALLINT,
                cost_est            DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                is_paid_key         BOOLEAN         NOT NULL DEFAULT FALSE,
                metadata            JSONB           NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_tool_call_metrics_created_at ON tool_call_metrics (created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_tool_call_metrics_tool_name ON tool_call_metrics (tool_name);
            CREATE INDEX IF NOT EXISTS idx_tool_call_metrics_status ON tool_call_metrics (status);
            CREATE INDEX IF NOT EXISTS idx_tool_call_metrics_tier ON tool_call_metrics (cognitive_tier);
            """
            async with pool.acquire() as conn:
                await conn.execute(sql)
            self._schema_ensured = True
            logger.info("[MetricsService] Schéma PostgreSQL tool_call_metrics vérifié")
            return True
        except Exception as e:
            logger.warning(f"[MetricsService] Impossible d'appliquer le schéma metrics : {e}")
            return False

    def record_to_memory(
        self,
        tool_name: str,
        status: str,
        latency_ms: float,
        cognitive_tier: Optional[int] = None,
        cost_est: float = 0.0,
        is_paid_key: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
        created_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Ajoute immédiatement un enregistrement dans le buffer circulaire mémoire O(1)."""
        ts = created_at or datetime.now(timezone.utc)
        meta = metadata or {}
        if str(status).lower() in ("done", "success", "completed") and not meta.get("verified", False):
            self._claimed_success_without_verification += 1

        record = {
            "created_at": ts,
            "tool_name": tool_name,
            "status": status,
            "latency_ms": float(latency_ms),
            "cognitive_tier": cognitive_tier,
            "cost_est": float(cost_est),
            "is_paid_key": bool(is_paid_key),
            "metadata": meta,
        }
        self._memory_buffer.append(record)
        return record

    def record_tool_call_background(
        self,
        tool_name: str,
        status: str,
        latency_ms: float,
        cognitive_tier: Optional[int] = None,
        cost_est: float = 0.0,
        is_paid_key: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Enregistrement non-bloquant en arrière-plan.
        Stocke immédiatement dans le buffer mémoire (O(1)) et délègue
        l'écriture PostgreSQL à une tâche asynchrone pour ne jamais ralentir Jarvis.
        """
        record = self.record_to_memory(
            tool_name=tool_name,
            status=status,
            latency_ms=latency_ms,
            cognitive_tier=cognitive_tier,
            cost_est=cost_est,
            is_paid_key=is_paid_key,
            metadata=metadata,
        )

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                self.record_tool_call(
                    tool_name=tool_name,
                    status=status,
                    latency_ms=latency_ms,
                    cognitive_tier=cognitive_tier,
                    cost_est=cost_est,
                    is_paid_key=is_paid_key,
                    metadata=metadata,
                    created_at=record["created_at"],
                    store_in_memory=False,
                )
            )
        except RuntimeError:
            # Pas de boucle en cours d'exécution dans ce thread (ex. test synchrone)
            pass

    async def record_tool_call(
        self,
        tool_name: str,
        status: str,
        latency_ms: float,
        cognitive_tier: Optional[int] = None,
        cost_est: float = 0.0,
        is_paid_key: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
        created_at: Optional[datetime] = None,
        store_in_memory: bool = True,
    ) -> bool:
        """Insère une métrique d'outil dans PostgreSQL de manière robuste."""
        ts = created_at or datetime.now(timezone.utc)
        if store_in_memory:
            self.record_to_memory(
                tool_name=tool_name,
                status=status,
                latency_ms=latency_ms,
                cognitive_tier=cognitive_tier,
                cost_est=cost_est,
                is_paid_key=is_paid_key,
                metadata=metadata,
                created_at=ts,
            )

        pool = await self._get_pg_pool()
        if not pool:
            return False

        if not self._schema_ensured:
            await self.ensure_schema()

        ts = created_at or datetime.now(timezone.utc)
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)

        try:
            sql = """
                INSERT INTO tool_call_metrics (
                    created_at, tool_name, status, latency_ms,
                    cognitive_tier, cost_est, is_paid_key, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """
            async with pool.acquire() as conn:
                await conn.execute(
                    sql,
                    ts,
                    str(tool_name),
                    str(status),
                    float(latency_ms),
                    int(cognitive_tier) if cognitive_tier in (1, 2, 3) else None,
                    float(cost_est),
                    bool(is_paid_key),
                    meta_json,
                )
            return True
        except Exception as e:
            logger.debug(f"[MetricsService] Échec insertion métrique Postgres : {e}")
            return False

    async def get_metrics_summary(self, window_str: str = "24h") -> Dict[str, Any]:
        """Retourne la synthèse complète des métriques sur la fenêtre choisie (24h, 7j, 30j)."""
        w_key = (window_str or "24h").lower().strip()
        duration = WINDOW_DURATIONS.get(w_key, timedelta(hours=24))
        now = datetime.now(timezone.utc)
        cutoff = now - duration

        pool = await self._get_pg_pool()
        if pool:
            try:
                summary = await self._query_pg_summary(cutoff, w_key, duration)
                if summary["total_calls"] > 0:
                    return summary
            except Exception as e:
                logger.warning(f"[MetricsService] Erreur lors de la requête Postgres, repli mémoire : {e}")

        # Repli sur le buffer mémoire (local ou PostgreSQL vide/non connecté)
        return self._compute_memory_summary(cutoff, w_key, duration)

    async def _query_pg_summary(
        self, cutoff: datetime, window_str: str, duration: timedelta
    ) -> Dict[str, Any]:
        """Calcule l'agrégation statistique directement dans PostgreSQL 16."""
        pool = await self._get_pg_pool()
        async with pool.acquire() as conn:
            # 1. Totaux globaux
            row_totals = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS total_calls,
                    COUNT(*) FILTER (WHERE status IN ('failure', 'error', 'échec')) AS total_failures,
                    COUNT(*) FILTER (WHERE status = 'timeout') AS total_timeouts,
                    COALESCE(SUM(cost_est), 0.0) AS total_cost
                FROM tool_call_metrics
                WHERE created_at >= $1
                """,
                cutoff,
            )

            total_calls = int(row_totals["total_calls"] or 0)
            total_failures = int(row_totals["total_failures"] or 0)
            total_timeouts = int(row_totals["total_timeouts"] or 0)
            total_cost = round(float(row_totals["total_cost"] or 0.0), 4)
            global_failure_rate = round(total_failures / total_calls, 4) if total_calls > 0 else 0.0

            # 2. Répartition par outil
            rows_tools = await conn.fetch(
                """
                SELECT
                    tool_name,
                    COUNT(*) AS call_count,
                    COUNT(*) FILTER (WHERE status IN ('failure', 'error', 'échec')) AS failure_count,
                    COUNT(*) FILTER (WHERE status = 'timeout') AS timeout_count,
                    COALESCE(AVG(latency_ms), 0.0) AS avg_latency,
                    COALESCE(percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms), AVG(latency_ms), 0.0) AS p95_latency,
                    COALESCE(SUM(cost_est), 0.0) AS tool_cost
                FROM tool_call_metrics
                WHERE created_at >= $1
                GROUP BY tool_name
                ORDER BY call_count DESC
                """,
                cutoff,
            )

            top_tools = []
            failure_rates = []
            latencies = []
            tools_summary = []

            for r in rows_tools:
                t_name = r["tool_name"]
                c_cnt = int(r["call_count"])
                f_cnt = int(r["failure_count"])
                to_cnt = int(r["timeout_count"])
                avg_lat = round(float(r["avg_latency"]), 1)
                p95_lat = round(float(r["p95_latency"]), 1)
                c_cost = round(float(r["tool_cost"]), 4)
                f_rate = round(f_cnt / c_cnt, 4) if c_cnt > 0 else 0.0
                pct = round((c_cnt / total_calls) * 100.0, 1) if total_calls > 0 else 0.0

                top_tools.append({
                    "tool_name": t_name,
                    "count": c_cnt,
                    "percentage": pct
                })
                failure_rates.append({
                    "tool_name": t_name,
                    "total": c_cnt,
                    "failures": f_cnt,
                    "timeouts": to_cnt,
                    "failure_rate": f_rate
                })
                latencies.append({
                    "tool_name": t_name,
                    "avg_latency_ms": avg_lat,
                    "p95_latency_ms": p95_lat
                })
                tools_summary.append({
                    "tool_name": t_name,
                    "count": c_cnt,
                    "failures": f_cnt,
                    "timeouts": to_cnt,
                    "failure_rate": f_rate,
                    "avg_latency_ms": avg_lat,
                    "p95_latency_ms": p95_lat,
                    "cost_est": c_cost
                })

            # 3. Répartition des Tiers Cognitifs (1, 2, 3, None)
            rows_tiers = await conn.fetch(
                """
                SELECT
                    COALESCE(cognitive_tier, 0) AS tier,
                    COUNT(*) AS count
                FROM tool_call_metrics
                WHERE created_at >= $1
                GROUP BY COALESCE(cognitive_tier, 0)
                """,
                cutoff,
            )
            tier_usage = {"tier_1": 0, "tier_2": 0, "tier_3": 0, "none": 0}
            for tr in rows_tiers:
                t_val = int(tr["tier"])
                cnt = int(tr["count"])
                if t_val == 1:
                    tier_usage["tier_1"] = cnt
                elif t_val == 2:
                    tier_usage["tier_2"] = cnt
                elif t_val == 3:
                    tier_usage["tier_3"] = cnt
                else:
                    tier_usage["none"] = cnt

            return {
                "window": window_str,
                "window_seconds": int(duration.total_seconds()),
                "total_calls": total_calls,
                "total_failures": total_failures,
                "total_timeouts": total_timeouts,
                "claimed_success_without_verification": self._claimed_success_without_verification,
                "global_failure_rate": global_failure_rate,
                "total_cost": total_cost,
                "top_tools": top_tools,
                "failure_rates": failure_rates,
                "latencies": latencies,
                "tier_usage": tier_usage,
                "tools_summary": tools_summary,
                "source": "postgresql",
            }

    def _compute_memory_summary(
        self, cutoff: datetime, window_str: str, duration: timedelta
    ) -> Dict[str, Any]:
        """Calcul de secours à partir du buffer mémoire de l'instance."""
        records = [r for r in self._memory_buffer if r["created_at"] >= cutoff]
        total_calls = len(records)
        total_failures = 0
        total_timeouts = 0
        total_cost = 0.0

        tools_data: Dict[str, Dict[str, Any]] = {}
        tier_usage = {"tier_1": 0, "tier_2": 0, "tier_3": 0, "none": 0}

        for r in records:
            t_name = r["tool_name"]
            st = str(r["status"]).lower()
            lat = float(r["latency_ms"])
            cost = float(r.get("cost_est", 0.0))
            tier = r.get("cognitive_tier")

            total_cost += cost
            if st in ("failure", "error", "échec"):
                total_failures += 1
            elif st == "timeout":
                total_timeouts += 1

            if tier == 1:
                tier_usage["tier_1"] += 1
            elif tier == 2:
                tier_usage["tier_2"] += 1
            elif tier == 3:
                tier_usage["tier_3"] += 1
            else:
                tier_usage["none"] += 1

            if t_name not in tools_data:
                tools_data[t_name] = {
                    "count": 0,
                    "failures": 0,
                    "timeouts": 0,
                    "latencies": [],
                    "cost_est": 0.0,
                }
            t_entry = tools_data[t_name]
            t_entry["count"] += 1
            if st in ("failure", "error", "échec"):
                t_entry["failures"] += 1
            elif st == "timeout":
                t_entry["timeouts"] += 1
            t_entry["latencies"].append(lat)
            t_entry["cost_est"] += cost

        # Tri par nombre d'appels décroissant
        sorted_tools = sorted(tools_data.items(), key=lambda x: x[1]["count"], reverse=True)

        top_tools = []
        failure_rates = []
        latencies = []
        tools_summary = []

        for t_name, stats in sorted_tools:
            c_cnt = stats["count"]
            f_cnt = stats["failures"]
            to_cnt = stats["timeouts"]
            lats = stats["latencies"]
            avg_lat = round(sum(lats) / len(lats), 1) if lats else 0.0
            
            # Calcul du p95
            if lats:
                sorted_lats = sorted(lats)
                p95_idx = min(len(sorted_lats) - 1, math.ceil(0.95 * len(sorted_lats)) - 1)
                p95_lat = round(sorted_lats[p95_idx], 1)
            else:
                p95_lat = 0.0

            c_cost = round(stats["cost_est"], 4)
            f_rate = round(f_cnt / c_cnt, 4) if c_cnt > 0 else 0.0
            pct = round((c_cnt / total_calls) * 100.0, 1) if total_calls > 0 else 0.0

            top_tools.append({
                "tool_name": t_name,
                "count": c_cnt,
                "percentage": pct
            })
            failure_rates.append({
                "tool_name": t_name,
                "total": c_cnt,
                "failures": f_cnt,
                "timeouts": to_cnt,
                "failure_rate": f_rate
            })
            latencies.append({
                "tool_name": t_name,
                "avg_latency_ms": avg_lat,
                "p95_latency_ms": p95_lat
            })
            tools_summary.append({
                "tool_name": t_name,
                "count": c_cnt,
                "failures": f_cnt,
                "timeouts": to_cnt,
                "failure_rate": f_rate,
                "avg_latency_ms": avg_lat,
                "p95_latency_ms": p95_lat,
                "cost_est": c_cost
            })

        global_failure_rate = round(total_failures / total_calls, 4) if total_calls > 0 else 0.0

        return {
            "window": window_str,
            "window_seconds": int(duration.total_seconds()),
            "total_calls": total_calls,
            "total_failures": total_failures,
            "total_timeouts": total_timeouts,
            "claimed_success_without_verification": self._claimed_success_without_verification,
            "global_failure_rate": global_failure_rate,
            "total_cost": round(total_cost, 4),
            "top_tools": top_tools,
            "failure_rates": failure_rates,
            "latencies": latencies,
            "tier_usage": tier_usage,
            "tools_summary": tools_summary,
            "source": "memory_buffer",
        }


# Instance globale singleton
metrics_service = MetricsService()
