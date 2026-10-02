"""Registre et découverte dynamique des modèles pour Antigravity CLI et J.A.R.V.I.S.
Gère le catalogue de modèles (Gemini et Claude), leur découverte via CLI, la configuration locale
et la liste de secours en dur, avec mise en cache TTL.
"""

import json
import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.model_registry")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_JSON_PATH = os.path.join(BASE_DIR, "config", "models.json")
CONFIG_YAML_PATH = os.path.join(BASE_DIR, "config", "models.yaml")


@dataclass
class ModelInfo:
    """Métadonnées complètes d'un modèle d'IA."""
    name: str
    provider: str  # "gemini" | "claude"
    tier: str      # "flash" | "pro" | "opus" | "sonnet"
    supports_effort: bool = False
    context_window: int = 1048576
    cost_rank: int = 1       # 1=économique, 2=modéré, 3=élevé
    latency_rank: int = 1    # 1=ultra-rapide, 2=modéré, 3=lent
    strengths: List[str] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)

    def matches(self, query_name: str) -> bool:
        """Vérifie si le nom recherché correspond au nom officiel ou à un alias."""
        q = query_name.lower().strip()
        if self.name.lower() == q:
            return True
        return any(a.lower() == q for a in self.aliases)


DEFAULT_MODELS: List[ModelInfo] = [
    ModelInfo(
        name="gemini-3.7-flash",
        provider="gemini",
        tier="flash",
        supports_effort=True,
        context_window=1048576,
        cost_rank=1,
        latency_rank=1,
        strengths=["simple", "diagnostic", "doc_sync", "email_simple", "quick_answer", "transport", "spreadsheet"],
        aliases=["3.7-flash", "flash-3.7", "gemini-flash"]
    ),
    ModelInfo(
        name="gemini-3.8-flash",
        provider="gemini",
        tier="flash",
        supports_effort=True,
        context_window=1048576,
        cost_rank=1,
        latency_rank=1,
        strengths=["simple", "tactical", "intermediate", "transport", "spreadsheet", "morning_briefing"],
        aliases=["3.8-flash", "flash-3.8"]
    ),
    ModelInfo(
        name="gemini-3.1-pro",
        provider="gemini",
        tier="pro",
        supports_effort=True,
        context_window=2097152,
        cost_rank=2,
        latency_rank=2,
        strengths=["complex", "deep_research", "system_healing", "refactoring", "code_refactoring", "auto_guerison_systeme", "engineering"],
        aliases=["3.1-pro", "pro-3.1", "gemini-pro"]
    ),
    ModelInfo(
        name="gemini-3.1-pro-preview",
        provider="gemini",
        tier="pro",
        supports_effort=True,
        context_window=2097152,
        cost_rank=2,
        latency_rank=2,
        strengths=["complex", "deep_research", "system_healing", "refactoring", "engineering"],
        aliases=["3.1-pro-preview"]
    ),
    ModelInfo(
        name="claude-3-7-sonnet",
        provider="claude",
        tier="sonnet",
        supports_effort=False,
        context_window=200000,
        cost_rank=3,
        latency_rank=2,
        strengths=["code", "reasoning_long", "complex_reasoning", "claude_preference", "software_architecture"],
        aliases=["claude-3.7-sonnet", "sonnet-3.7", "claude"]
    )
]


class ModelRegistry:
    """Registre de modèles avec découverte dynamique, lecture config et cache TTL."""

    def __init__(self, ttl_seconds: int = 3600):
        self.ttl_seconds = ttl_seconds
        self._cached_models: Dict[str, ModelInfo] = {}
        self._last_refresh_time: float = 0.0
        self._source_used: str = "init"

    def _discover_via_cli(self) -> Optional[List[ModelInfo]]:
        """Tente de découvrir dynamiquement les modèles via la commande Antigravity CLI."""
        agy_bin = shutil.which("agy") or shutil.which("antigravity-cli")
        if not agy_bin:
            # Vérifier les chemins connus sur Linux/VPS
            for cand in ["~/.local/bin/agy", "/home/opc/.local/bin/agy", "/usr/local/bin/agy"]:
                exp = os.path.expanduser(cand)
                if os.path.exists(exp) and os.access(exp, os.X_OK):
                    agy_bin = exp
                    break

        if not agy_bin:
            return None

        commands_to_try = [
            [agy_bin, "models", "list", "--json"],
            [agy_bin, "models", "list"],
            [agy_bin, "model", "list", "--json"],
            [agy_bin, "--help-models"]
        ]

        for cmd in commands_to_try:
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=3
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    raw_out = proc.stdout.strip()
                    # Si c'est du JSON
                    if raw_out.startswith("[") or raw_out.startswith("{"):
                        data = json.loads(raw_out)
                        if isinstance(data, list):
                            models = []
                            for item in data:
                                if isinstance(item, dict) and "name" in item:
                                    name = item["name"]
                                    prov = item.get("provider", "gemini" if "gemini" in name.lower() else "claude" if "claude" in name.lower() else "unknown")
                                    tier = item.get("tier", "flash" if "flash" in name.lower() else "pro" if "pro" in name.lower() else "sonnet" if "sonnet" in name.lower() else "standard")
                                    supp_effort = item.get("supports_effort", prov == "gemini")
                                    ctx = item.get("context_window", 2097152 if "pro" in name.lower() else 1048576 if "gemini" in name.lower() else 200000)
                                    models.append(ModelInfo(
                                        name=name,
                                        provider=prov,
                                        tier=tier,
                                        supports_effort=supp_effort,
                                        context_window=ctx,
                                        cost_rank=item.get("cost_rank", 1),
                                        latency_rank=item.get("latency_rank", 1),
                                        strengths=item.get("strengths", []),
                                        aliases=item.get("aliases", [])
                                    ))
                            if models:
                                logger.info(f"Découverte CLI réussie : {len(models)} modèles identifiés via {' '.join(cmd)}.")
                                return models
            except Exception as e:
                logger.debug(f"Tentative découverte CLI échouée pour {cmd}: {e}")
                continue

        return None

    def _load_from_config(self) -> Optional[List[ModelInfo]]:
        """Charge la configuration déclarative depuis models.json ou models.yaml."""
        # 1. Tester models.json
        if os.path.exists(CONFIG_JSON_PATH):
            try:
                with open(CONFIG_JSON_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                raw_models = data.get("models", [])
                models = []
                for item in raw_models:
                    models.append(ModelInfo(
                        name=item["name"],
                        provider=item.get("provider", "gemini"),
                        tier=item.get("tier", "flash"),
                        supports_effort=item.get("supports_effort", False),
                        context_window=item.get("context_window", 1048576),
                        cost_rank=item.get("cost_rank", 1),
                        latency_rank=item.get("latency_rank", 1),
                        strengths=item.get("strengths", []),
                        aliases=item.get("aliases", [])
                    ))
                if models:
                    logger.info(f"Chargement réussi depuis {CONFIG_JSON_PATH} ({len(models)} modèles).")
                    return models
            except Exception as e:
                logger.warning(f"Erreur lors de la lecture de {CONFIG_JSON_PATH}: {e}")

        # 2. Tester models.yaml si pyyaml présent
        if os.path.exists(CONFIG_YAML_PATH):
            try:
                import yaml
                with open(CONFIG_YAML_PATH, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                raw_models = data.get("models", [])
                models = []
                for item in raw_models:
                    models.append(ModelInfo(
                        name=item["name"],
                        provider=item.get("provider", "gemini"),
                        tier=item.get("tier", "flash"),
                        supports_effort=item.get("supports_effort", False),
                        context_window=item.get("context_window", 1048576),
                        cost_rank=item.get("cost_rank", 1),
                        latency_rank=item.get("latency_rank", 1),
                        strengths=item.get("strengths", []),
                        aliases=item.get("aliases", [])
                    ))
                if models:
                    logger.info(f"Chargement réussi depuis {CONFIG_YAML_PATH} ({len(models)} modèles).")
                    return models
            except ImportError:
                pass
            except Exception as e:
                logger.warning(f"Erreur lors de la lecture de {CONFIG_YAML_PATH}: {e}")

        return None

    def refresh(self, force: bool = False) -> List[ModelInfo]:
        """Actualise le cache de modèles selon la cascade : CLI -> Config -> Liste par défaut."""
        now = time.time()
        if not force and self._cached_models and (now - self._last_refresh_time < self.ttl_seconds):
            return list(self._cached_models.values())

        # 1. Tenter la découverte CLI
        discovered = self._discover_via_cli()
        if discovered:
            self._source_used = "cli"
            self._cached_models = {m.name: m for m in discovered}
            self._last_refresh_time = now
            return discovered

        # 2. Tenter le fichier de configuration
        from_config = self._load_from_config()
        if from_config:
            self._source_used = "config_file"
            self._cached_models = {m.name: m for m in from_config}
            self._last_refresh_time = now
            return from_config

        # 3. Repli liste par défaut
        self._source_used = "default_fallback"
        self._cached_models = {m.name: m for m in DEFAULT_MODELS}
        self._last_refresh_time = now
        return DEFAULT_MODELS

    def get_model(self, name_or_alias: str) -> Optional[ModelInfo]:
        """Recherche un modèle par son nom ou l'un de ses alias."""
        if not self._cached_models:
            self.refresh()
        q = name_or_alias.lower().strip()
        for m in self._cached_models.values():
            if m.matches(q):
                return m
        # Essayer un refresh forcé si non trouvé
        self.refresh(force=True)
        for m in self._cached_models.values():
            if m.matches(q):
                return m
        return None

    def list_models(self, provider: Optional[str] = None) -> List[ModelInfo]:
        """Retourne la liste des modèles enregistrés, éventuellement filtrée par provider."""
        if not self._cached_models:
            self.refresh()
        models = list(self._cached_models.values())
        if provider:
            p = provider.lower().strip()
            return [m for m in models if m.provider.lower() == p]
        return models

    def get_equivalent_gemini_model(self, model_name: str) -> str:
        """Retourne le meilleur modèle Gemini équivalent pour le repli de quota."""
        m_info = self.get_model(model_name)
        if m_info and m_info.provider == "claude":
            if "opus" in m_info.name.lower() or "sonnet" in m_info.name.lower() or m_info.tier in ("sonnet", "opus"):
                return "gemini-3.1-pro"
            return "gemini-3.7-flash"
        if m_info and "pro" in m_info.name.lower():
            return "gemini-3.7-flash"
        return "gemini-3.7-flash"

    @property
    def source(self) -> str:
        return self._source_used


# Instance globale du registre
model_registry = ModelRegistry()
