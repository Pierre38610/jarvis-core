"""backend/services/self_improvement_telegram.py
Adaptateur Telegram interactif pour les propositions d'auto-amélioration et de PRs J.A.R.V.I.S.
Permet à Pierre de recevoir un rapport concis et d'interagir via des boutons inline :
✅ Approuver, ❌ Rejeter, ✏️ Demander une modification.

Caractéristiques principales :
- Aucune IP ni chatId en dur dans le code (lecture stricte via config.py / variables d'environnement).
- Callbacks signés HMAC SHA-256 avec identifiant de proposition non devinable (< 64 octets).
- Machine à états persistante SQLite/JSON :
  proposed -> approved | rejected | edit_requested -> merging -> merged | failed
- Déduplication atomique des doubles clics et reprise d'état après redémarrage.
- Politique de merge sécurisée (AUTO_MERGE_ENABLED=false par défaut) :
  exige diff < 150 lignes, tests verts, aucun chemin protégé et revue second modèle validée.
"""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import logging
import os
import secrets
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import config
from ops.scripts.check_protected_paths import check_all_changes

logger = logging.getLogger("jarvis.self_improvement_telegram")

# ─── Constantes & États de la Machine à États ────────────────────────────────
STATE_PROPOSED = "proposed"
STATE_APPROVED = "approved"
STATE_REJECTED = "rejected"
STATE_EDIT_REQUESTED = "edit_requested"
STATE_MERGING = "merging"
STATE_MERGED = "merged"
STATE_FAILED = "failed"

VALID_STATES = {
    STATE_PROPOSED,
    STATE_APPROVED,
    STATE_REJECTED,
    STATE_EDIT_REQUESTED,
    STATE_MERGING,
    STATE_MERGED,
    STATE_FAILED,
}

# Codes d'action compacts pour respecter la limite Telegram de 64 octets dans callback_data
ACTION_APPROVE = "app"
ACTION_REJECT = "rej"
ACTION_EDIT = "edit"

ACTION_MAP = {
    ACTION_APPROVE: STATE_APPROVED,
    ACTION_REJECT: STATE_REJECTED,
    ACTION_EDIT: STATE_EDIT_REQUESTED,
}


# ─── Dataclass de Proposition ────────────────────────────────────────────────
@dataclass
class ImprovementProposal:
    """Représentation persistante d'une proposition d'auto-amélioration soumise à validation."""
    proposal_id: str
    goal: str
    subfolder: str
    model_used: str
    diff_summary: str
    diff_line_count: int
    pytest_results: str
    tests_passed: bool
    branch_name: str
    modified_files: List[str] = field(default_factory=list)
    pr_url: Optional[str] = None
    status: str = STATE_PROPOSED
    second_model_reviewed: bool = False
    second_model_name: Optional[str] = None
    telegram_message_id: Optional[int] = None
    rejection_reason: Optional[str] = None
    edit_feedback: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ImprovementProposal:
        d = dict(data)
        if isinstance(d.get("modified_files"), str):
            try:
                d["modified_files"] = json.loads(d["modified_files"])
            except Exception:
                d["modified_files"] = []
        d["tests_passed"] = bool(d.get("tests_passed"))
        d["second_model_reviewed"] = bool(d.get("second_model_reviewed"))
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ─── Gestion des Signatures HMAC ─────────────────────────────────────────────
def generate_proposal_id() -> str:
    """Génère un identifiant de proposition non devinable et compact."""
    return f"prop_{secrets.token_hex(6)}"


def generate_callback_signature(action: str, proposal_id: str, secret: str) -> str:
    """Génère une signature HMAC-SHA256 tronquée à 12 caractères hexadécimaux."""
    msg = f"{action}:{proposal_id}".encode("utf-8")
    key = secret.encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()[:12]


def verify_callback_signature(action: str, proposal_id: str, signature: str, secret: str) -> bool:
    """Vérifie l'intégrité de la signature HMAC du callback Telegram en temps constant."""
    expected = generate_callback_signature(action, proposal_id, secret)
    return hmac.compare_digest(expected, signature)


def build_callback_data(action: str, proposal_id: str, secret: str) -> str:
    """Construit un callback_data compact garanti <= 64 octets pour l'API Telegram."""
    sig = generate_callback_signature(action, proposal_id, secret)
    data = f"si:{action}:{proposal_id}:{sig}"
    if len(data.encode("utf-8")) > 64:
        raise ValueError(f"callback_data trop long ({len(data)} octets > 64) : {data}")
    return data


def parse_callback_data(callback_data: str, secret: str) -> Tuple[bool, Optional[str], Optional[str], str]:
    """Parse et valide un callback_data Telegram.
    
    Returns:
        (valid, action, proposal_id, error_message)
    """
    parts = (callback_data or "").split(":")
    if len(parts) != 4 or parts[0] != "si":
        return False, None, None, "Format de callback Telegram invalide"

    _, action, proposal_id, signature = parts
    if action not in ACTION_MAP:
        return False, None, None, f"Action inconnue '{action}'"

    if not verify_callback_signature(action, proposal_id, signature, secret):
        return False, None, None, "Signature HMAC du callback invalide ou expirée"

    return True, action, proposal_id, "OK"


# ─── Stockage Persistant SQLite ──────────────────────────────────────────────
class ProposalStore:
    """Gestionnaire de persistance SQLite avec reprise après redémarrage et déduplication atomique."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            repo_root = getattr(config, "BASE_DIR", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            data_dir = os.path.join(repo_root, "data")
            os.makedirs(data_dir, exist_ok=True)
            self.db_path = os.path.join(data_dir, "self_improvement_proposals.db")
        else:
            self.db_path = db_path
            if self.db_path != ":memory:":
                os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS proposals (
                    proposal_id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    subfolder TEXT NOT NULL,
                    model_used TEXT NOT NULL,
                    diff_summary TEXT NOT NULL,
                    diff_line_count INTEGER DEFAULT 0,
                    pytest_results TEXT NOT NULL,
                    tests_passed INTEGER DEFAULT 0,
                    pr_url TEXT,
                    branch_name TEXT NOT NULL,
                    modified_files TEXT NOT NULL,
                    status TEXT NOT NULL,
                    second_model_reviewed INTEGER DEFAULT 0,
                    second_model_name TEXT,
                    telegram_message_id INTEGER,
                    rejection_reason TEXT,
                    edit_feedback TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status);")
            conn.commit()

    def save(self, proposal: ImprovementProposal) -> None:
        """Enregistre ou met à jour une proposition de manière persistante."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO proposals (
                    proposal_id, goal, subfolder, model_used, diff_summary,
                    diff_line_count, pytest_results, tests_passed, pr_url,
                    branch_name, modified_files, status, second_model_reviewed,
                    second_model_name, telegram_message_id, rejection_reason,
                    edit_feedback, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(proposal_id) DO UPDATE SET
                    goal = excluded.goal,
                    subfolder = excluded.subfolder,
                    model_used = excluded.model_used,
                    diff_summary = excluded.diff_summary,
                    diff_line_count = excluded.diff_line_count,
                    pytest_results = excluded.pytest_results,
                    tests_passed = excluded.tests_passed,
                    pr_url = excluded.pr_url,
                    branch_name = excluded.branch_name,
                    modified_files = excluded.modified_files,
                    status = excluded.status,
                    second_model_reviewed = excluded.second_model_reviewed,
                    second_model_name = excluded.second_model_name,
                    telegram_message_id = excluded.telegram_message_id,
                    rejection_reason = excluded.rejection_reason,
                    edit_feedback = excluded.edit_feedback,
                    updated_at = excluded.updated_at;
                """,
                (
                    proposal.proposal_id,
                    proposal.goal,
                    proposal.subfolder,
                    proposal.model_used,
                    proposal.diff_summary,
                    proposal.diff_line_count,
                    proposal.pytest_results,
                    1 if proposal.tests_passed else 0,
                    proposal.pr_url,
                    proposal.branch_name,
                    json.dumps(proposal.modified_files),
                    proposal.status,
                    1 if proposal.second_model_reviewed else 0,
                    proposal.second_model_name,
                    proposal.telegram_message_id,
                    proposal.rejection_reason,
                    proposal.edit_feedback,
                    proposal.created_at,
                    proposal.updated_at,
                ),
            )
            conn.commit()

    def get(self, proposal_id: str) -> Optional[ImprovementProposal]:
        """Récupère une proposition par son identifiant unique."""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM proposals WHERE proposal_id = ?", (proposal_id,))
            row = cur.fetchone()
            if not row:
                return None
            return ImprovementProposal.from_dict(dict(row))

    def list_active(self) -> List[ImprovementProposal]:
        """Liste les propositions en cours d'attente (reprise après redémarrage)."""
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM proposals WHERE status IN (?, ?) ORDER BY created_at DESC",
                (STATE_PROPOSED, STATE_MERGING),
            )
            return [ImprovementProposal.from_dict(dict(row)) for row in cur.fetchall()]

    def transition_status(
        self,
        proposal_id: str,
        from_states: List[str],
        to_state: str,
        extra_fields: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[ImprovementProposal], str]:
        """Effectue une transition atomique d'état avec déduplication des doubles clics."""
        now = time.time()
        extra = extra_fields or {}

        with self._get_connection() as conn:
            # 1. Vérifier l'état actuel
            cur = conn.execute("SELECT * FROM proposals WHERE proposal_id = ?", (proposal_id,))
            row = cur.fetchone()
            if not row:
                return False, None, f"Proposition '{proposal_id}' introuvable."

            current_prop = ImprovementProposal.from_dict(dict(row))

            # 2. Déduplication des doubles clics
            if current_prop.status == to_state:
                return False, current_prop, f"Action déjà enregistrée (état actuel : '{to_state}')."

            if current_prop.status not in from_states:
                return False, current_prop, f"Transition invalide depuis '{current_prop.status}' vers '{to_state}'."

            # 3. Mise à jour atomique conditionnelle
            placeholders = ",".join("?" for _ in from_states)
            set_clauses = ["status = ?", "updated_at = ?"]
            params: List[Any] = [to_state, now]

            if "rejection_reason" in extra:
                set_clauses.append("rejection_reason = ?")
                params.append(extra["rejection_reason"])
            if "edit_feedback" in extra:
                set_clauses.append("edit_feedback = ?")
                params.append(extra["edit_feedback"])
            if "telegram_message_id" in extra:
                set_clauses.append("telegram_message_id = ?")
                params.append(extra["telegram_message_id"])
            if "second_model_reviewed" in extra:
                set_clauses.append("second_model_reviewed = ?")
                params.append(1 if extra["second_model_reviewed"] else 0)
            if "second_model_name" in extra:
                set_clauses.append("second_model_name = ?")
                params.append(extra["second_model_name"])

            params.append(proposal_id)
            params.extend(from_states)

            sql = f"UPDATE proposals SET {', '.join(set_clauses)} WHERE proposal_id = ? AND status IN ({placeholders})"
            cursor = conn.execute(sql, params)
            conn.commit()

            if cursor.rowcount == 0:
                # Concurrence / double clic immédiat
                return False, current_prop, "Conflit de transition concurrente (déjà traitée)."

            updated_prop = self.get(proposal_id)
            return True, updated_prop, f"Transition réussie vers '{to_state}'."


# ─── Politique de Merge Sécurisée ────────────────────────────────────────────
def evaluate_merge_policy(
    proposal: ImprovementProposal,
    auto_merge_enabled: Optional[bool] = None,
) -> Tuple[bool, str]:
    """Évalue la politique de sécurité stricte pour le merge automatique vers 'main'.
    
    Règles absolues :
    1. AUTO_MERGE_ENABLED doit être explicitement actif (désactivé par défaut).
    2. Petit correctif uniquement (< 150 lignes modifiées dans le diff).
    3. Tests unitaires ciblés verts (tests_passed=True).
    4. Aucun fichier critique ni chemin protégé touché.
    5. Revue de code validée par un second modèle indépendant.
    """
    # 1. Vérification du drapeau global (désactivé par défaut)
    if auto_merge_enabled is None:
        auto_merge_enabled = getattr(config, "AUTO_MERGE_ENABLED", False)
        if isinstance(auto_merge_enabled, str):
            auto_merge_enabled = auto_merge_enabled.lower() in ("true", "1", "yes")

    if not auto_merge_enabled:
        return False, "Le merge automatique est désactivé par défaut (AUTO_MERGE_ENABLED=false)."

    # 2. Taille du correctif (< 150 lignes)
    if proposal.diff_line_count >= 150:
        return (
            False,
            f"Diff trop volumineux ({proposal.diff_line_count} lignes >= 150). Merge automatique interdit.",
        )

    # 3. Tests unitaires ciblés
    if not proposal.tests_passed:
        return False, "Les tests unitaires ciblés ne sont pas tous validés avec succès."

    # 4. Chemins protégés (check_protected_paths)
    if proposal.modified_files:
        changes = [("M", f) for f in proposal.modified_files]
        violations = check_all_changes(changes)
        if violations:
            return False, f"Chemin(s) protégé(s) détecté(s) : {'; '.join(violations)}"

    # 5. Revue par un second modèle
    if not proposal.second_model_reviewed:
        return False, "La revue de code par un second modèle indépendant n'a pas été validée."

    return True, "Politique de sécurité validée avec succès : auto-merge autorisé."


# Alias de compatibilité
check_auto_merge_policy = evaluate_merge_policy


# ─── Formateur de Message Telegram & Clavier Inline ─────────────────────────
def format_telegram_report(proposal: ImprovementProposal) -> str:
    """Génère le texte HTML concis pour la notification Telegram."""
    goal_escaped = html.escape(proposal.goal)
    subfolder_escaped = html.escape(proposal.subfolder)
    model_escaped = html.escape(proposal.model_used)
    pytest_icon = "✅" if proposal.tests_passed else "❌"
    pytest_summary_escaped = html.escape(proposal.pytest_results[:200])

    # Résumé tronqué et nettoyé du diff
    diff_snippet = proposal.diff_summary[:500] if proposal.diff_summary else "Aucun diff disponible"
    diff_escaped = html.escape(diff_snippet)

    pr_line = ""
    if proposal.pr_url:
        pr_line = f"🔗 <b>Pull Request :</b> <a href=\"{html.escape(proposal.pr_url)}\">{html.escape(proposal.branch_name)}</a>\n"
    else:
        pr_line = f"🌿 <b>Branche :</b> <code>{html.escape(proposal.branch_name)}</code>\n"

    status_badge = {
        STATE_PROPOSED: "⏳ En attente de décision",
        STATE_APPROVED: "✅ Approuvé",
        STATE_REJECTED: "❌ Rejeté",
        STATE_EDIT_REQUESTED: "✏️ Modification demandée",
        STATE_MERGING: "🔄 Fusion en cours",
        STATE_MERGED: "🎉 Fusionné sur main",
        STATE_FAILED: "⚠️ Échec fusion",
    }.get(proposal.status, proposal.status)

    lines = [
        "🤖 <b>Proposition d'Auto-Amélioration J.A.R.V.I.S.</b>",
        f"📊 <b>Statut :</b> {status_badge}",
        f"🎯 <b>Objectif :</b> {goal_escaped}",
        f"📁 <b>Sous-dossier :</b> <code>{subfolder_escaped}</code>",
        f"🧠 <b>Modèle utilisé :</b> <code>{model_escaped}</code>",
        f"🧪 <b>Tests ciblés :</b> {pytest_icon} <i>{pytest_summary_escaped}</i>",
        pr_line.strip(),
        f"📝 <b>Diff ({proposal.diff_line_count} lignes) :</b>",
        f"<pre>{diff_escaped}</pre>",
    ]

    return "\n".join(lines)


def build_inline_keyboard(proposal_id: str, secret: str) -> Dict[str, Any]:
    """Construit les 3 boutons inline Telegram signés HMAC."""
    cb_approve = build_callback_data(ACTION_APPROVE, proposal_id, secret)
    cb_reject = build_callback_data(ACTION_REJECT, proposal_id, secret)
    cb_edit = build_callback_data(ACTION_EDIT, proposal_id, secret)

    return {
        "inline_keyboard": [
            [
                {"text": "✅ Approuver", "callback_data": cb_approve},
                {"text": "❌ Rejeter", "callback_data": cb_reject},
                {"text": "✏️ Modifier", "callback_data": cb_edit},
            ]
        ]
    }


# ─── Adaptateur Telegram Interactif (Injectable & Mockable) ──────────────────
class SelfImprovementTelegramAdapter:
    """Adaptateur central pour l'envoi et la gestion des callbacks Telegram d'auto-amélioration."""

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        hmac_secret: Optional[str] = None,
        auto_merge_enabled: Optional[bool] = None,
        store: Optional[ProposalStore] = None,
        http_client: Optional[Any] = None,
        on_approved_hook: Optional[Any] = None,
    ):
        # Lecture stricte via config / variables d'environnement (aucune IP ni chatId en dur)
        self.bot_token = (bot_token or getattr(config, "TELEGRAM_BOT_TOKEN", "") or os.environ.get("TELEGRAM_BOT_TOKEN", "")).strip()
        self.chat_id = (chat_id or getattr(config, "TELEGRAM_CHAT_ID", "") or os.environ.get("TELEGRAM_CHAT_ID", "")).strip()
        self.hmac_secret = (
            hmac_secret
            or getattr(config, "TELEGRAM_HMAC_SECRET", "")
            or os.environ.get("TELEGRAM_HMAC_SECRET", "")
            or getattr(config, "JWT_SECRET_KEY", "")
            or "jarvis-self-improve-hmac-fallback"
        ).strip()
        self.auto_merge_enabled = (
            auto_merge_enabled
            if auto_merge_enabled is not None
            else getattr(config, "AUTO_MERGE_ENABLED", False)
        )
        self.store = store or ProposalStore()
        self.http_client = http_client
        self.on_approved_hook = on_approved_hook

    def is_configured(self) -> bool:
        """Vérifie si les identifiants Telegram sont disponibles."""
        return bool(self.bot_token and self.chat_id)

    async def send_proposal(
        self,
        proposal: ImprovementProposal,
    ) -> Tuple[bool, Optional[int], str]:
        """Enregistre la proposition en base et transmet le rapport interactif sur Telegram."""
        # Sauvegarde persistante de la proposition initiale
        self.store.save(proposal)

        if not self.is_configured():
            msg = "Telegram non configuré (TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID absent). Envoi ignoré."
            logger.info(f"[SelfImprovementTelegram] {msg}")
            return False, None, msg

        text = format_telegram_report(proposal)
        reply_markup = build_inline_keyboard(proposal.proposal_id, self.hmac_secret)

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_markup": reply_markup,
        }

        try:
            if self.http_client:
                resp = await self.http_client.post(url, json=payload, timeout=10.0)
            else:
                import httpx
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(url, json=payload)

            status_code = getattr(resp, "status_code", 200)
            data = resp.json() if hasattr(resp, "json") else {}

            if status_code == 200 and data.get("ok"):
                message_id = data.get("result", {}).get("message_id")
                proposal.telegram_message_id = message_id
                proposal.updated_at = time.time()
                self.store.save(proposal)
                logger.info(f"[SelfImprovementTelegram] Notification envoyée (message_id={message_id})")
                return True, message_id, "Notification transmise avec succès."
            else:
                err_msg = data.get("description", f"Code HTTP {status_code}")
                logger.warning(f"[SelfImprovementTelegram] Erreur API Telegram : {err_msg}")
                return False, None, err_msg
        except Exception as e:
            logger.error(f"[SelfImprovementTelegram] Exception lors de l'envoi Telegram : {e}")
            return False, None, str(e)

    async def update_message_text(
        self,
        message_id: int,
        text: str,
        remove_keyboard: bool = True,
    ) -> bool:
        """Met à jour le message Telegram pour refléter le changement d'état."""
        if not self.is_configured() or not message_id:
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/editMessageText"
        payload: Dict[str, Any] = {
            "chat_id": self.chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if remove_keyboard:
            payload["reply_markup"] = {"inline_keyboard": []}

        try:
            if self.http_client:
                resp = await self.http_client.post(url, json=payload, timeout=10.0)
            else:
                import httpx
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(url, json=payload)

            status_code = getattr(resp, "status_code", 200)
            return status_code == 200
        except Exception as e:
            logger.warning(f"[SelfImprovementTelegram] Erreur mise à jour message {message_id} : {e}")
            return False

    async def handle_callback_query(
        self,
        callback_data: str,
        user_id: Optional[str] = None,
        feedback: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Traite une action utilisateur cliquée depuis Telegram avec validation HMAC et déduplication."""
        # 1. Vérification du format et de la signature HMAC
        valid, action, proposal_id, msg = parse_callback_data(callback_data, self.hmac_secret)
        if not valid or not action or not proposal_id:
            return {"status": "error", "message": msg}

        # 2. Vérification de l'expéditeur si user_id fourni
        if user_id and self.chat_id and str(user_id) != str(self.chat_id):
            return {"status": "forbidden", "message": "Utilisateur non autorisé à interagir avec cette proposition."}

        proposal = self.store.get(proposal_id)
        if not proposal:
            return {"status": "not_found", "message": f"Proposition '{proposal_id}' introuvable."}

        # 3. Traitement selon l'action
        if action == ACTION_APPROVE:
            # Transition proposed -> approved
            trans_ok, updated_prop, trans_msg = self.store.transition_status(
                proposal_id=proposal_id,
                from_states=[STATE_PROPOSED],
                to_state=STATE_APPROVED,
            )
            if not trans_ok:
                return {"status": "deduplicated", "message": trans_msg, "proposal": proposal.to_dict()}

            assert updated_prop is not None

            # Hook asynchrone pour déclenchement automatique (ex: self_improve pour weekly_improvement_watch)
            if self.on_approved_hook:
                try:
                    await self.on_approved_hook(updated_prop)
                except Exception as hook_err:
                    logger.warning(f"[SelfImprovementTelegram] Erreur on_approved_hook : {hook_err}")

            # Vérification de la politique de merge automatique sécurisée
            merge_allowed, merge_reason = evaluate_merge_policy(updated_prop, self.auto_merge_enabled)
            if merge_allowed:
                # Transition approved -> merging -> merged
                self.store.transition_status(proposal_id, [STATE_APPROVED], STATE_MERGING)
                # Exécution sécurisée du merge
                merge_ok, merge_detail = await self._execute_merge(updated_prop)
                final_state = STATE_MERGED if merge_ok else STATE_FAILED
                self.store.transition_status(proposal_id, [STATE_MERGING], final_state)
                updated_prop = self.store.get(proposal_id) or updated_prop
                result_msg = f"Approuvé et fusionné sur main : {merge_detail}"
            else:
                result_msg = f"Approuvé par Pierre (Merge auto non éligible : {merge_reason})."

            # Mise à jour du message Telegram pour figer l'action
            if updated_prop.telegram_message_id:
                new_text = format_telegram_report(updated_prop)
                await self.update_message_text(updated_prop.telegram_message_id, new_text)

            return {
                "status": "success",
                "action": "approved",
                "message": result_msg,
                "merge_allowed": merge_allowed,
                "proposal": updated_prop.to_dict(),
            }

        elif action == ACTION_REJECT:
            trans_ok, updated_prop, trans_msg = self.store.transition_status(
                proposal_id=proposal_id,
                from_states=[STATE_PROPOSED],
                to_state=STATE_REJECTED,
                extra_fields={"rejection_reason": feedback or "Rejeté par l'utilisateur"},
            )
            if not trans_ok:
                return {"status": "deduplicated", "message": trans_msg, "proposal": proposal.to_dict()}

            assert updated_prop is not None
            if updated_prop.telegram_message_id:
                new_text = format_telegram_report(updated_prop)
                await self.update_message_text(updated_prop.telegram_message_id, new_text)

            return {
                "status": "success",
                "action": "rejected",
                "message": "Proposition rejetée.",
                "proposal": updated_prop.to_dict(),
            }

        elif action == ACTION_EDIT:
            trans_ok, updated_prop, trans_msg = self.store.transition_status(
                proposal_id=proposal_id,
                from_states=[STATE_PROPOSED],
                to_state=STATE_EDIT_REQUESTED,
                extra_fields={"edit_feedback": feedback or "Modification demandée"},
            )
            if not trans_ok:
                return {"status": "deduplicated", "message": trans_msg, "proposal": proposal.to_dict()}

            assert updated_prop is not None
            if updated_prop.telegram_message_id:
                new_text = format_telegram_report(updated_prop)
                await self.update_message_text(updated_prop.telegram_message_id, new_text)

            return {
                "status": "success",
                "action": "edit_requested",
                "message": "Modification demandée. L'agent prépare une nouvelle révision.",
                "proposal": updated_prop.to_dict(),
            }

        return {"status": "error", "message": "Action non reconnue"}

    async def _execute_merge(self, proposal: ImprovementProposal) -> Tuple[bool, str]:
        """Fusionne la branche vers main via l'API GitHub ou un mécanisme local contrôlé."""
        token = os.environ.get("GITHUB_TOKEN") or getattr(config, "GITHUB_TOKEN", None)
        repo = os.environ.get("GITHUB_REPOSITORY", "Pierre38610/jarvis-core")

        if not token:
            logger.info(f"[SelfImprovementTelegram] Aucun GITHUB_TOKEN. Merge simulé pour {proposal.branch_name}.")
            return True, "Merge simulé avec succès (aucun token GitHub configuré)."

        url = f"https://api.github.com/repos/{repo}/merges"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Jarvis-AutoMerge-Service",
        }
        payload = {
            "base": "main",
            "head": proposal.branch_name,
            "commit_message": f"🤖 Auto-merge Jarvis : {proposal.goal[:60]} (approuvé par Pierre)",
        }

        try:
            if self.http_client:
                res = await self.http_client.post(url, json=payload, headers=headers, timeout=15.0)
            else:
                import httpx
                async with httpx.AsyncClient(timeout=15.0) as client:
                    res = await client.post(url, json=payload, headers=headers)

            status_code = getattr(res, "status_code", 200)
            if status_code in (201, 204):
                return True, "Branche fusionnée avec succès sur main via l'API GitHub."
            elif status_code == 409:
                return False, "Conflit de merge détecté sur la branche main."
            else:
                text_err = getattr(res, "text", str(status_code))
                return False, f"Erreur API GitHub ({status_code}) : {text_err[:120]}"
        except Exception as e:
            return False, f"Exception lors de l'appel de merge : {e}"


# Singleton par défaut
telegram_proposal_adapter = SelfImprovementTelegramAdapter()
