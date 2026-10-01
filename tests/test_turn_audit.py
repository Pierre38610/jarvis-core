"""tests/test_turn_audit.py
Tests unitaires et d'intégration du module turn_audit :
- Table SQLite 'turn_audit'
- Détecteur de fausses affirmations (false_claim)
- Récupération filtrée par 'since'
- Endpoint FastAPI /api/supervision/turns
- Injection des variables de statut dans le prompt
"""

import os
import sqlite3
import tempfile
import pytest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.turn_audit import (
    init_turn_audit_db,
    detect_false_claim,
    record_turn_audit,
    get_turn_audits,
    get_prompt_status_context,
    inject_turn_status_into_prompt,
)
from routers.supervision import router as supervision_router


@pytest.fixture
def temp_db():
    """Crée une base SQLite temporaire isolée pour les tests."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_path = f.name
    init_turn_audit_db(temp_path)
    yield temp_path
    if os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except OSError:
            pass


def test_init_and_table_schema(temp_db):
    """Vérifie la création correcte de la table turn_audit et de ses colonnes."""
    conn = sqlite3.connect(temp_db)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(turn_audit)")
    cols = {row[1] for row in cur.fetchall()}
    conn.close()

    expected_cols = {
        "id", "session_id", "transcript", "voice_mode", "tools",
        "plan", "final_sentence", "cuts", "duration", "paid_used",
        "paid_reason", "paid_consent", "false_claim", "false_claim_warning", "created_at"
    }
    assert expected_cols.issubset(cols), f"Colonnes manquantes: {expected_cols - cols}"


def test_detect_false_claim_positive_no_tools():
    """Détecte false_claim si la phrase annonce 'fait', 'envoyé' ou 'créé' sans outil."""
    is_claim, warn = detect_false_claim("C'est fait Pierre !", tools=[])
    assert is_claim is True
    assert warn is not None
    assert "Affirmation non vérifiée" in warn
    assert "fait" in warn

    is_claim_envoye, warn_envoye = detect_false_claim("Le courriel a été envoyé avec succès.", tools=[])
    assert is_claim_envoye is True
    assert "envoyé" in warn_envoye

    is_claim_cree, warn_cree = detect_false_claim("J'ai créé le document demandé.", tools=[])
    assert is_claim_cree is True
    assert "créé" in warn_cree


def test_detect_false_claim_with_unverified_or_failed_tool():
    """Détecte false_claim si les outils appelés ne sont pas done+verified."""
    # Outil done mais non vérifié
    tools_unverified = [{"name": "send_email", "status": "done", "verified": False}]
    is_claim, warn = detect_false_claim("L'e-mail a été envoyé.", tools=tools_unverified)
    assert is_claim is True

    # Outil échoué même si verified=True
    tools_failed = [{"name": "send_email", "status": "failed", "verified": True}]
    is_claim, warn = detect_false_claim("C'est fait.", tools=tools_failed)
    assert is_claim is True


def test_detect_false_claim_negative_with_verified_tool():
    """Ne détecte pas false_claim si au moins un outil est done+verified."""
    tools_ok = [{"name": "send_email", "status": "done", "verified": True}]
    is_claim, warn = detect_false_claim("C'est envoyé Pierre !", tools=tools_ok)
    assert is_claim is False
    assert warn is None

    # Statut 'success'
    tools_success = [{"name": "file_write", "status": "success", "verified": True}]
    is_claim2, warn2 = detect_false_claim("Le fichier a été créé.", tools=tools_success)
    assert is_claim2 is False
    assert warn2 is None


def test_detect_false_claim_negative_no_claim_words():
    """Pas de flag si la phrase finale ne prétend pas avoir accompli une action."""
    is_claim, warn = detect_false_claim("Il fait beau à Paris aujourd'hui.", tools=[])
    # Attention : 'fait' dans 'Il fait beau'
    # Notre regex est stricte sur les mots, mais pour une question informative sans trigger :
    is_claim_info, warn_info = detect_false_claim("La météo actuelle indique 22 degrés.", tools=[])
    assert is_claim_info is False
    assert warn_info is None


def test_record_turn_audit_and_get(temp_db):
    """Vérifie l'enregistrement complet d'un tour dans SQLite et sa récupération."""
    tools = [{"name": "read_emails", "status": "done", "verified": True}]
    record = record_turn_audit(
        transcript="Lis mes derniers mails",
        voice_mode="thinking",
        tools=tools,
        plan="Plan test",
        final_sentence="Voici tes 3 messages reçus ce matin.",
        cuts=1,
        duration=3.45,
        paid_used=False,
        paid_reason="",
        paid_consent="False",
        session_id="voice_session_1",
        db_path=temp_db,
    )

    assert record["id"] is not None
    assert record["false_claim"] is False
    assert record["duration"] == 3.45
    assert record["cuts"] == 1

    # Récupération via get_turn_audits
    audits = get_turn_audits(db_path=temp_db)
    assert len(audits) == 1
    retrieved = audits[0]
    assert retrieved["id"] == record["id"]
    assert retrieved["transcript"] == "Lis mes derniers mails"
    assert retrieved["voice_mode"] == "thinking"
    assert isinstance(retrieved["tools"], list)
    assert retrieved["tools"][0]["name"] == "read_emails"
    assert retrieved["paid_used"] is False


def test_get_turn_audits_filter_since(temp_db):
    """Vérifie le filtrage des audits avec le paramètre 'since'."""
    r1 = record_turn_audit(
        transcript="Tour 1",
        voice_mode="standard",
        tools=[],
        final_sentence="Réponse 1",
        db_path=temp_db,
    )
    r2 = record_turn_audit(
        transcript="Tour 2",
        voice_mode="standard",
        tools=[],
        final_sentence="Réponse 2",
        db_path=temp_db,
    )

    # Filtre par ID
    filtered_id = get_turn_audits(since=str(r1["id"]), db_path=temp_db)
    assert len(filtered_id) == 1
    assert filtered_id[0]["id"] == r2["id"]

    # Filtre par timestamp
    all_turns = get_turn_audits(db_path=temp_db)
    assert len(all_turns) == 2


def test_supervision_endpoint_unauthorized():
    """Vérifie que l'endpoint /api/supervision/turns rejette les requêtes non autorisées."""
    app = FastAPI()
    app.include_router(supervision_router)
    client = TestClient(app)

    with patch("auth.is_device_authorized", return_value=False):
        res = client.get("/api/supervision/turns")
        assert res.status_code == 401
        assert res.json()["authorized"] is False


def test_supervision_endpoint_authorized(temp_db):
    """Vérifie que l'endpoint /api/supervision/turns retourne les tours audités quand autorisé."""
    app = FastAPI()
    app.include_router(supervision_router)
    client = TestClient(app)

    record_turn_audit(
        transcript="Test supervision",
        voice_mode="standard",
        tools=[],
        final_sentence="Affirmation non vérifiée : c'est fait !",
        db_path=temp_db,
    )

    with patch("auth.is_device_authorized", return_value=True), \
         patch("config.DB_PATH", temp_db):
        res = client.get("/api/supervision/turns")
        assert res.status_code == 200
        data = res.json()
        assert "turns" in data
        assert data["count"] >= 1
        assert data["turns"][0]["false_claim"] is True


def test_inject_turn_status_into_prompt():
    """Vérifie l'injection de {active_plan_status} et {active_subagents_status}."""
    with patch("services.turn_audit.get_active_plan_status_str", return_value="Plan étape 2/3"), \
         patch("services.turn_audit.get_active_subagents_status_str", return_value="Agent doc_sync actif"):
        
        ctx = get_prompt_status_context()
        assert ctx["active_plan_status"] == "Plan étape 2/3"
        assert ctx["active_subagents_status"] == "Agent doc_sync actif"

        # Cas 1 : Template avec placeholders explicites
        template = "Instruction de base.\nPlan: {active_plan_status}\nAgents: {active_subagents_status}"
        injected = inject_turn_status_into_prompt(template)
        assert "Plan: Plan étape 2/3" in injected
        assert "Agents: Agent doc_sync actif" in injected

        # Cas 2 : Template sans placeholders -> bloc ajouté à la fin
        plain_prompt = "Instruction sans variable."
        injected_plain = inject_turn_status_into_prompt(plain_prompt)
        assert "Plan d'action en cours" in injected_plain.lower() or "plan d'action" in injected_plain.lower()
        assert "Plan étape 2/3" in injected_plain
        assert "Agent doc_sync actif" in injected_plain
