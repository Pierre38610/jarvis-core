"""tests/test_live_mode_policy.py
Tests unitaires pour la politique LiveModePolicy et le routeur LLM.
Vérifie :
1. Chaque règle du mode thinking (demande explicite, plan actif, échecs, tier_hint, standard).
2. L'hystérésis (au moins 2 tours en thinking, retour en standard après 3 tours tier 1 sans plan).
3. L'indépendance stricte entre voice_mode et needs_agentic.
4. L'attribution des clés API (FREE par défaut, secours PAID uniquement avec consentement).
"""

import pytest
import config
from services.live_mode_policy import (
    LiveModePolicy,
    decide,
    VOICE_MODE_STANDARD,
    VOICE_MODE_THINKING,
    LIVE_MODEL_STANDARD,
    LIVE_MODEL_THINKING,
)
from services.llm_router import (
    LLMRouter,
    route,
    get_live_model_and_key,
    resolve_live_fallback,
)
from services.key_gate import (
    grant_paid_consent,
    clear_all_consents,
    PaidKeyConsentRequired,
)


@pytest.fixture(autouse=True)
def clean_consent_and_policy():
    """Nettoie les consentements et réinitialise l'état avant chaque test."""
    clear_all_consents()
    yield
    clear_all_consents()


# ─────────────────────────────────────────────────────────────
# 1. TESTS DES RÈGLES DU MODE THINKING DANS L'ORDRE
# ─────────────────────────────────────────────────────────────

def test_rule_1_explicit_demand():
    """Règle 1 : Demande explicite (« vite » → standard ; « réfléchis bien », « prends ton temps », « en détail » → thinking)."""
    policy = LiveModePolicy()

    # Demande explicite standard
    res_vite = policy.decide(transcript="Réponds vite s'il te plaît", tier_hint=1)
    assert res_vite["voice_mode"] == VOICE_MODE_STANDARD
    assert "explicite" in res_vite["reason"]

    # Demande explicite thinking
    res_reflechis = policy.decide(transcript="Réfléchis bien à cette question", tier_hint=1)
    assert res_reflechis["voice_mode"] == VOICE_MODE_THINKING

    policy.reset()
    res_n3 = policy.decide(transcript="Fais une recherche de niveau 3 sur l'IA", tier_hint=1)
    assert res_n3["voice_mode"] == VOICE_MODE_THINKING
    assert res_n3["cognitive_level"] == 3

    policy.reset()
    res_temps = policy.decide(transcript="Prends ton temps pour me dire", tier_hint=1)
    assert res_temps["voice_mode"] == VOICE_MODE_THINKING

    policy.reset()
    res_detail = policy.decide(transcript="Explique-moi tout ça en détail", tier_hint=1)
    assert res_detail["voice_mode"] == VOICE_MODE_THINKING

    # Priorité : « vite » l'emporte sur tier_hint élevé et plan complexe
    policy.reset()
    res_priority = policy.decide(transcript="Fais vite !", plan_active=5, recent_failures=3, tier_hint=3)
    assert res_priority["voice_mode"] == VOICE_MODE_STANDARD


def test_rule_2_plan_active_ge_3():
    """Règle 2 : Plan actif ≥ 3 étapes → thinking."""
    policy = LiveModePolicy()

    # Entier >= 3
    res_int = policy.decide(transcript="Avancement du chantier", plan_active=3, tier_hint=1)
    assert res_int["voice_mode"] == VOICE_MODE_THINKING
    assert "Plan actif" in res_int["reason"]

    # Liste d'étapes >= 3
    policy.reset()
    res_list = policy.decide(transcript="Statut", plan_active=["step1", "step2", "step3"], tier_hint=1)
    assert res_list["voice_mode"] == VOICE_MODE_THINKING

    # Plan < 3 étapes (ne déclenche pas thinking à lui seul)
    policy.reset()
    res_small = policy.decide(transcript="Statut", plan_active=2, tier_hint=1)
    assert res_small["voice_mode"] == VOICE_MODE_STANDARD


def test_rule_3_consecutive_tool_failures():
    """Règle 3 : 2 échecs d'outil consécutifs → thinking."""
    policy = LiveModePolicy()

    # 1 échec -> reste standard si tier 1
    res_1_fail = policy.decide(transcript="Réessaie", recent_failures=1, tier_hint=1)
    assert res_1_fail["voice_mode"] == VOICE_MODE_STANDARD

    # 2 échecs -> thinking
    policy.reset()
    res_2_fail = policy.decide(transcript="Réessaie", recent_failures=2, tier_hint=1)
    assert res_2_fail["voice_mode"] == VOICE_MODE_THINKING
    assert "Échecs consécutifs" in res_2_fail["reason"]

    # 3 échecs -> thinking
    policy.reset()
    res_3_fail = policy.decide(transcript="Réessaie", recent_failures=3, tier_hint=1)
    assert res_3_fail["voice_mode"] == VOICE_MODE_THINKING


def test_rule_4_tier_hint_ge_2():
    """Règle 4 : tier_hint ≥ 2 → thinking."""
    policy = LiveModePolicy()

    res_t2 = policy.decide(transcript="Calcul d'orbite", tier_hint=2)
    assert res_t2["voice_mode"] == VOICE_MODE_THINKING
    assert "tier_hint=2" in res_t2["reason"]

    policy.reset()
    res_t3 = policy.decide(transcript="Architecture distribuée", tier_hint=3)
    assert res_t3["voice_mode"] == VOICE_MODE_THINKING


def test_rule_5_default_standard():
    """Règle 5 : Sinon standard (tier 1, pas de plan, pas d'échec, pas de demande thinking)."""
    policy = LiveModePolicy()
    res = policy.decide(transcript="Bonjour Jarvis", plan_active=0, recent_failures=0, tier_hint=1)
    assert res["voice_mode"] == VOICE_MODE_STANDARD
    assert "standard" in res["reason"].lower()


# ─────────────────────────────────────────────────────────────
# 2. TESTS DE L'HYSTÉRÉSIS
# ─────────────────────────────────────────────────────────────

def test_hysteresis_minimum_2_turns_in_thinking():
    """L'hystérésis garantit au moins 2 tours en thinking une fois le mode activé."""
    policy = LiveModePolicy()

    # Tour 1 : activation thinking via tier_hint=2
    t1 = policy.decide(transcript="Analyse", tier_hint=2)
    assert t1["voice_mode"] == VOICE_MODE_THINKING

    # Tour 2 : conditions retombées à tier 1 sans plan actif
    # Doit RESTER en thinking (minimum 2 tours requis)
    t2 = policy.decide(transcript="D'accord", tier_hint=1, plan_active=0, recent_failures=0)
    assert t2["voice_mode"] == VOICE_MODE_THINKING
    assert "minimum 2 tours" in t2["reason"]


def test_hysteresis_return_to_standard_after_3_turns_tier1_without_plan():
    """Retour en standard après 3 tours consécutifs tier 1 sans plan actif (et au moins 2 tours thinking)."""
    policy = LiveModePolicy()

    # Tour 1 : Passage en thinking
    t1 = policy.decide(transcript="Problème complexe", tier_hint=2)
    assert t1["voice_mode"] == VOICE_MODE_THINKING

    # Tour 2 : tier 1 sans plan (tour 1/3 sans plan, tour 2 thinking) -> RESTE thinking
    t2 = policy.decide(transcript="Merci", tier_hint=1, plan_active=0)
    assert t2["voice_mode"] == VOICE_MODE_THINKING

    # Tour 3 : tier 1 sans plan (tour 2/3 sans plan, tour 3 thinking) -> RESTE thinking
    t3 = policy.decide(transcript="Continue", tier_hint=1, plan_active=0)
    assert t3["voice_mode"] == VOICE_MODE_THINKING

    # Tour 4 : tier 1 sans plan (tour 3/3 sans plan, tour 4 thinking) -> RETOUR STANDARD
    t4 = policy.decide(transcript="Parfait", tier_hint=1, plan_active=0)
    assert t4["voice_mode"] == VOICE_MODE_STANDARD
    assert "3 tours tier 1 sans plan" in t4["reason"]

    # Tour 5 : reste en standard
    t5 = policy.decide(transcript="Quelle heure est-il ?", tier_hint=1, plan_active=0)
    assert t5["voice_mode"] == VOICE_MODE_STANDARD


def test_hysteresis_interrupted_by_new_thinking_trigger():
    """Un nouveau déclencheur thinking réinitialise le compteur de retour tier 1."""
    policy = LiveModePolicy()

    # Tour 1 : thinking
    policy.decide(transcript="Calcul", tier_hint=2)
    # Tour 2 : tier 1 sans plan (1/3)
    t2 = policy.decide(transcript="Ok", tier_hint=1, plan_active=0)
    assert t2["voice_mode"] == VOICE_MODE_THINKING

    # Tour 3 : rechute dans un déclencheur thinking (2 échecs)
    t3 = policy.decide(transcript="Erreur", recent_failures=2)
    assert t3["voice_mode"] == VOICE_MODE_THINKING

    # Tour 4 : tier 1 sans plan (repart à 1/3)
    t4 = policy.decide(transcript="Bien", tier_hint=1, plan_active=0)
    assert t4["voice_mode"] == VOICE_MODE_THINKING
    # Tour 5 : tier 1 sans plan (2/3)
    t5 = policy.decide(transcript="Bien", tier_hint=1, plan_active=0)
    assert t5["voice_mode"] == VOICE_MODE_THINKING
    # Tour 6 : tier 1 sans plan (3/3) -> retour standard
    t6 = policy.decide(transcript="Bien", tier_hint=1, plan_active=0)
    assert t6["voice_mode"] == VOICE_MODE_STANDARD


def test_hysteresis_inhibited_if_plan_is_active():
    """Si un plan est actif (même < 3 étapes), ce n'est pas 'sans plan actif', le retour en standard est inhibé."""
    policy = LiveModePolicy()

    # Tour 1 : thinking
    policy.decide(transcript="Démarrage", tier_hint=2)
    # Tour 2 : tier 1, MAIS plan actif = 1 étape
    t2 = policy.decide(transcript="Étape 1 finie", tier_hint=1, plan_active=1)
    assert t2["voice_mode"] == VOICE_MODE_THINKING

    # Tour 3 : tier 1, plan actif = 1 étape
    t3 = policy.decide(transcript="Étape 2 en cours", tier_hint=1, plan_active=1)
    assert t3["voice_mode"] == VOICE_MODE_THINKING

    # Tour 4 : tier 1, plan actif = 1 étape -> ne revient toujours pas en standard
    t4 = policy.decide(transcript="Toujours une étape", tier_hint=1, plan_active=1)
    assert t4["voice_mode"] == VOICE_MODE_THINKING


def test_hysteresis_broken_immediately_by_explicit_vite():
    """Une demande explicite « vite » brise immédiatement l'hystérésis et bascule en standard."""
    policy = LiveModePolicy()

    # Tour 1 : thinking
    t1 = policy.decide(transcript="Question difficile", tier_hint=2)
    assert t1["voice_mode"] == VOICE_MODE_THINKING

    # Tour 2 : l'utilisateur dit « vite »
    t2 = policy.decide(transcript="Vite, je suis pressé !")
    assert t2["voice_mode"] == VOICE_MODE_STANDARD


# ─────────────────────────────────────────────────────────────
# 3. INDÉPENDANCE STRICTE THINKING / AGENTIC
# ─────────────────────────────────────────────────────────────

def test_independence_thinking_and_agentic():
    """Vérifie les 4 combinaisons possibles démontrant l'indépendance de voice_mode et needs_agentic."""
    policy = LiveModePolicy()

    # Combinaison 1 : Standard + Agentic
    # L'utilisateur demande d'aller vite, mais sollicite une recherche approfondie
    c1 = policy.decide(transcript="Vite, lance une recherche approfondie sur les semi-conducteurs", tier_hint=1)
    assert c1["voice_mode"] == VOICE_MODE_STANDARD
    assert c1["needs_agentic"] is True
    assert c1["task_kind"] == "deep_research"

    # Combinaison 2 : Thinking + Non-Agentic
    # L'utilisateur demande de réfléchir bien, mais c'est une simple question conversationnelle
    policy.reset()
    c2 = policy.decide(transcript="Prends ton temps et réfléchis bien à cette devinette", tier_hint=1)
    assert c2["voice_mode"] == VOICE_MODE_THINKING
    assert c2["needs_agentic"] is False
    assert c2["task_kind"] == "conversation"

    # Combinaison 3 : Thinking + Agentic
    # Modèle financier complexe avec réflexion en détail
    policy.reset()
    c3 = policy.decide(transcript="Explique en détail et génère le tableur financier", tier_hint=2)
    assert c3["voice_mode"] == VOICE_MODE_THINKING
    assert c3["needs_agentic"] is True
    assert c3["task_kind"] == "spreadsheet_modeler"

    # Combinaison 4 : Standard + Non-Agentic
    policy.reset()
    c4 = policy.decide(transcript="Bonjour Jarvis, comment vas-tu ?", tier_hint=1)
    assert c4["voice_mode"] == VOICE_MODE_STANDARD
    assert c4["needs_agentic"] is False
    assert c4["task_kind"] == "conversation"


# ─────────────────────────────────────────────────────────────
# 4. TESTS DU ROUTEUR LLM ET DE LA GOUVERNANCE DES CLÉS (KEY_GATE)
# ─────────────────────────────────────────────────────────────

def test_llm_router_models_and_free_key_by_default(monkeypatch):
    """Les deux modèles Live utilisent la clé FREE par défaut."""
    monkeypatch.setattr(config, "GEMINI_API_KEY_FREE", "FAKE_FREE_KEY_12345")
    monkeypatch.setattr(config, "GEMINI_API_KEY_PAID", "FAKE_PAID_KEY_99999")

    # Mode standard -> gemini-3.8-live avec clé FREE
    res_std = route(transcript="Bonjour", tier_hint=1)
    assert res_std["voice_mode"] == VOICE_MODE_STANDARD
    assert res_std["model_name"] == LIVE_MODEL_STANDARD
    assert res_std["api_key"] == "FAKE_FREE_KEY_12345"

    # Mode thinking -> gemini-3.8-live-extended-thinking avec clé FREE
    res_th = route(transcript="Réfléchis bien", tier_hint=2)
    assert res_th["voice_mode"] == VOICE_MODE_THINKING
    assert res_th["model_name"] == LIVE_MODEL_THINKING
    assert res_th["api_key"] == "FAKE_FREE_KEY_12345"


def test_llm_router_paid_key_fallback_requires_consent(monkeypatch):
    """La clé PAID n'intervient qu'en secours qualifié et exige le consentement vocal."""
    monkeypatch.setattr(config, "GEMINI_API_KEY_FREE", "FAKE_FREE_KEY_12345")
    monkeypatch.setattr(config, "GEMINI_API_KEY_PAID", "FAKE_PAID_KEY_99999")

    # Sans consentement, demander la clé payante lève PaidKeyConsentRequired
    with pytest.raises(PaidKeyConsentRequired):
        route(transcript="Test secours", require_paid=True)

    # Avec consentement enregistré pour la session
    session_id = "test_session_abc"
    grant_paid_consent(session_id=session_id)

    res_paid = route(transcript="Test secours avec consentement", session_id=session_id, require_paid=True)
    assert res_paid["api_key"] == "FAKE_PAID_KEY_99999"


# ─────────────────────────────────────────────────────────────
# 5. TESTS DU NOUVEAU COMPORTEMENT DE BASCULE ET DE REPLI
# ─────────────────────────────────────────────────────────────

def test_deferred_switch_when_speech_active():
    """Test 1 : Bascule différée quand Jarvis parle (SpeechState != IDLE), puis appliquée dès que IDLE."""
    policy = LiveModePolicy()

    # 1. Jarvis est en train de parler (speech_state="model_speaking")
    # L'utilisateur envoie une consigne cognitive (tier_hint=2) qui réclame le mode thinking
    res_speaking = policy.decide(
        transcript="Analyse cette trajectoire d'injection",
        tier_hint=2,
        speech_state="model_speaking",
    )

    # La bascule doit être différée pour ne pas couper la parole
    assert res_speaking["switch_deferred"] is True
    assert res_speaking["target_mode"] == VOICE_MODE_THINKING
    assert res_speaking["voice_mode"] == VOICE_MODE_STANDARD
    assert res_speaking["switch_source"] == "policy"
    assert res_speaking["announcement_phrase"] == "Je passe en mode réflexion."
    assert policy.pending_switch == VOICE_MODE_THINKING

    # 2. Au tour suivant, Jarvis a fini de parler (speech_state="idle")
    # La bascule différée est appliquée
    new_mode = policy.apply_deferred_switch()
    assert new_mode == VOICE_MODE_THINKING
    assert policy.current_mode == VOICE_MODE_THINKING
    assert policy.pending_switch is None

    # Si la bascule vient d'une demande explicite de l'utilisateur, l'annonce est vide
    policy.reset()
    res_user = policy.decide(transcript="Réfléchis bien à cela", speech_state="idle")
    assert res_user["voice_mode"] == VOICE_MODE_THINKING
    assert res_user["switch_source"] == "user_demand"
    assert res_user["announcement_phrase"] == ""


def test_fallback_free_thinking_to_free_standard(monkeypatch):
    """Test 2 : Échec de la clé FREE sur modèle thinking -> repli d'abord sur Live standard FREE."""
    monkeypatch.setattr(config, "GEMINI_API_KEY_FREE", "FAKE_FREE_KEY_777")
    monkeypatch.setattr(config, "GEMINI_API_KEY_PAID", "FAKE_PAID_KEY_888")

    # En cas d'échec sur extended-thinking avec clé FREE, resolve_live_fallback retourne standard en FREE
    fallback_res = resolve_live_fallback(
        current_model=LIVE_MODEL_THINKING,
        standard_already_failed=False,
    )

    assert fallback_res["model_name"] == LIVE_MODEL_STANDARD
    assert fallback_res["voice_mode"] == VOICE_MODE_STANDARD
    assert fallback_res["is_paid"] is False
    assert fallback_res["api_key"] == "FAKE_FREE_KEY_777"
    assert fallback_res["action"] == "fallback_to_standard_free"


def test_fallback_free_standard_failure_requires_paid_consent(monkeypatch):
    """Test 3 : Si le standard FREE échoue aussi -> PaidKeyConsentRequired, puis PAID seulement après consentement."""
    monkeypatch.setattr(config, "GEMINI_API_KEY_FREE", "FAKE_FREE_KEY_777")
    monkeypatch.setattr(config, "GEMINI_API_KEY_PAID", "FAKE_PAID_KEY_888")

    session_id = "voice_session_fallback_test"

    # Sans consentement : lève PaidKeyConsentRequired
    with pytest.raises(PaidKeyConsentRequired) as exc_info:
        resolve_live_fallback(
            current_model=LIVE_MODEL_STANDARD,
            session_id=session_id,
            standard_already_failed=True,
        )
    assert exc_info.value.reason == "free_key_failure"

    # Avec consentement accordé par l'utilisateur (oralement ou interface)
    grant_paid_consent(session_id=session_id, reason="free_key_failure")

    paid_fallback = resolve_live_fallback(
        current_model=LIVE_MODEL_STANDARD,
        session_id=session_id,
        standard_already_failed=True,
    )
    assert paid_fallback["model_name"] == LIVE_MODEL_STANDARD
    assert paid_fallback["is_paid"] is True
    assert paid_fallback["api_key"] == "FAKE_PAID_KEY_888"
    assert paid_fallback["action"] == "fallback_to_standard_paid"

