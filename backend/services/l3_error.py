"""services/l3_error.py
Structure d'erreur standardisée et diagnostic pour le moteur Deep Research L3 de J.A.R.V.I.S.
Garantit la capture, la propagation et la journalisation sécurisée (sans secrets)
des erreurs de navigation autonome (Browser Agent / CDP) et du pipeline Map-Reduce.
"""

from __future__ import annotations

import logging
import os
import re
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import config

logger = logging.getLogger("jarvis.l3_error")

# Stockage global de la dernière erreur L3 pour diagnostic
_LAST_L3_ERROR: Optional[Dict[str, Any]] = None


def sanitize_error_text(text: str) -> str:
    """Supprime les clés d'API, tokens, cookies et secrets des messages d'erreur."""
    if not text:
        return ""
    # Clés d'API configurées
    for key_name in (
        "GEMINI_API_KEY_FREE",
        "GEMINI_API_KEY_PAID",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "STARK_EMAIL_PASSWORD",
    ):
        val = getattr(config, key_name, None)
        if val and isinstance(val, str) and len(val) > 6:
            text = text.replace(val, "[REDACTED_SECRET]")

    # Patterns courants
    text = re.sub(r"AIza[0-9A-Za-z\-_]{30,}", "[REDACTED_GEMINI_KEY]", text)
    text = re.sub(r"sk-[0-9A-Za-z\-_]{20,}", "[REDACTED_API_KEY]", text)
    text = re.sub(r"Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*", "Bearer [REDACTED_TOKEN]", text, flags=re.IGNORECASE)
    text = re.sub(r"password\s*=\s*['\"][^'\"]+['\"]", "password='[REDACTED]'", text, flags=re.IGNORECASE)
    text = re.sub(r"cookie\s*:\s*[^;\r\n]+", "cookie: [REDACTED_COOKIE]", text, flags=re.IGNORECASE)
    return text


@dataclass
class L3ErrorDetails:
    """Structure stable d'erreur L3 détaillée et sans secret."""

    etape: str
    exception: str
    traceback_court: str = ""
    capture_ecran: Optional[str] = None
    cause_courte: str = ""
    timestamp: float = field(default_factory=time.time)
    fallback_initiated: bool = False

    def __post_init__(self):
        # Assainissement automatique des secrets et limitation des tailles
        self.etape = sanitize_error_text(str(self.etape))
        self.exception = sanitize_error_text(str(self.exception))[:500]
        if self.traceback_court:
            self.traceback_court = sanitize_error_text(str(self.traceback_court))[-800:]
        if not self.cause_courte:
            self.cause_courte = self.exception
        else:
            self.cause_courte = sanitize_error_text(str(self.cause_courte))[:300]

    def format_user_message(self, include_fallback: bool = True) -> str:
        """Formate un message utilisateur utile et explicite."""
        msg = f"Échec à l'étape '{self.etape}' : {self.cause_courte}"
        if include_fallback and self.fallback_initiated:
            msg += " (repli en cours vers la recherche alternative)."
        return msg

    def to_dict(self) -> Dict[str, Any]:
        """Exporte un dictionnaire complet avec alias FR et EN."""
        return {
            "etape": self.etape,
            "step": self.etape,
            "exception": self.exception,
            "error": self.exception,
            "traceback_court": self.traceback_court,
            "short_traceback": self.traceback_court,
            "capture_ecran": self.capture_ecran,
            "screenshot_path": self.capture_ecran,
            "cause_courte": self.cause_courte,
            "short_cause": self.cause_courte,
            "timestamp": self.timestamp,
            "fallback_initiated": self.fallback_initiated,
            "user_message": self.format_user_message(include_fallback=self.fallback_initiated),
        }

    @classmethod
    def from_exception(
        cls,
        etape: str,
        exc: Exception,
        cause_courte: Optional[str] = None,
        capture_ecran: Optional[str] = None,
        fallback_initiated: bool = False,
        tb_limit: int = 3,
    ) -> "L3ErrorDetails":
        """Construit un L3ErrorDetails à partir d'une exception levée."""
        tb_str = traceback.format_exc(limit=tb_limit)
        exc_str = f"{exc.__class__.__name__}: {str(exc)}"
        short_c = cause_courte or (str(exc) if str(exc) else exc.__class__.__name__)
        return cls(
            etape=etape,
            exception=exc_str,
            traceback_court=tb_str,
            capture_ecran=capture_ecran,
            cause_courte=short_c,
            fallback_initiated=fallback_initiated,
        )


def set_last_l3_error(err: L3ErrorDetails | Dict[str, Any]) -> Dict[str, Any]:
    """Enregistre la dernière erreur L3 globale pour diagnostic."""
    global _LAST_L3_ERROR
    if isinstance(err, L3ErrorDetails):
        _LAST_L3_ERROR = err.to_dict()
    elif isinstance(err, dict):
        _LAST_L3_ERROR = dict(err)
    else:
        _LAST_L3_ERROR = {"etape": "unknown", "exception": str(err), "timestamp": time.time()}
    return _LAST_L3_ERROR


def get_last_l3_error() -> Optional[Dict[str, Any]]:
    """Retourne la dernière erreur L3 stockée pour diagnostic."""
    return _LAST_L3_ERROR


def clear_last_l3_error() -> None:
    """Réinitialise la dernière erreur L3."""
    global _LAST_L3_ERROR
    _LAST_L3_ERROR = None
