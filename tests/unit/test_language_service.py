"""tests/unit/test_language_service.py
Tests unitaires pour la gestion de langue multilingue FR/EN dans J.A.R.V.I.S.
Couvre :
- Détection FR/EN nominale
- Gestion des accents français et contractions (j', c', qu', don't, it's)
- Entrées brèves/ambiguës et héritage du contexte
- Premier tour par défaut en FR
- Détection de 3e langue et clarification obligatoire en FR/EN
- Routage vocal TTS (FR vs EN) et repli sûr
- Non-régression voix française
- Audit de tour avec champ language
"""

import pytest
import sqlite3
from unittest.mock import patch, MagicMock

import config
from services.language_service import (
    detect_language,
    get_clarification_prompt,
    format_turn_language_instruction,
    get_tts_voice_for_language,
    TurnLanguageManager,
    DEFAULT_LANGUAGE,
)
from services.turn_audit import record_turn_audit, get_turn_audits, init_turn_audit_db


def test_french_detection_nominal():
    """Vérifie la détection fiable de requêtes françaises usuelles."""
    queries = [
        "Bonjour Jarvis, comment vas-tu aujourd'hui ?",
        "Peux-tu me lancer de la musique douce sur Spotify ?",
        "Je voudrais consulter mes derniers emails reçus.",
        "Ouvre le terminal et donne-moi la météo à Paris.",
        "Quelle est l'heure actuelle ?",
    ]
    for q in queries:
        res = detect_language(q)
        assert res.language == "fr", f"Échec détection FR pour: '{q}' (obtenu: {res.language})"
        assert res.effective_language == "fr"
        assert not res.is_other_language
        assert not res.needs_clarification


def test_english_detection_nominal():
    """Vérifie la détection fiable de requêtes anglaises usuelles."""
    queries = [
        "Hello Jarvis, how are you today?",
        "Can you please play some jazz music on Spotify?",
        "I would like to check my latest unread emails.",
        "Search the web for the latest advancements in artificial intelligence.",
        "What time is it in New York right now?",
    ]
    for q in queries:
        res = detect_language(q)
        assert res.language == "en", f"Échec détection EN pour: '{q}' (obtenu: {res.language})"
        assert res.effective_language == "en"
        assert not res.is_other_language
        assert not res.needs_clarification


def test_accents_and_contractions_french():
    """Vérifie la prise en charge des accents et des élisions françaises."""
    french_accented = [
        "J'aimerais que tu vérifies l'état général du système.",
        "Qu'est-ce que c'est que ce processus ?",
        "Aujourd'hui, nous allons préparer une synthèse détaillée.",
        "N'oublie pas de vérifier la boîte de réception.",
        "C'est parfait, je te remercie pour cette analyse.",
    ]
    for text in french_accented:
        res = detect_language(text)
        assert res.language == "fr", f"Échec détection accents FR pour: '{text}'"
        assert res.confidence >= 0.5


def test_english_contractions():
    """Vérifie la prise en charge des contractions anglaises."""
    english_contractions = [
        "It's not working as expected, let's fix it.",
        "Don't run that task right now, please wait.",
        "I can't find the file you mentioned.",
        "What's the weather like in London today?",
        "We'll see if the script completes successfully.",
    ]
    for text in english_contractions:
        res = detect_language(text)
        assert res.language == "en", f"Échec détection contractions EN pour: '{text}'"
        assert res.confidence >= 0.5


def test_short_and_ambiguous_first_turn_defaults_to_french():
    """Au premier tour sans contexte, une entrée courte ou ambiguë prend 'fr' par défaut."""
    short_inputs = ["ok", "stop", "pause", "1 2 3", "status", "test", "jarvis"]
    for inp in short_inputs:
        res = detect_language(inp, last_language=None)
        assert res.language == "fr", f"Premier tour ambigu doit valoir 'fr': '{inp}'"
        assert res.effective_language == "fr"


def test_short_and_ambiguous_inherits_context():
    """Une entrée brève/ambiguë hérite fidèlement de la dernière langue active."""
    ambiguous_inputs = ["ok", "stop", "pause", "resume", "status", "42"]
    
    # Contexte anglais
    for inp in ambiguous_inputs:
        res_en = detect_language(inp, last_language="en")
        assert res_en.effective_language == "en", f"Devait hériter 'en' pour '{inp}'"
        assert res_en.language == "en"

    # Contexte français
    for inp in ambiguous_inputs:
        res_fr = detect_language(inp, last_language="fr")
        assert res_fr.effective_language == "fr", f"Devait hériter 'fr' pour '{inp}'"
        assert res_fr.language == "fr"


def test_language_alternation_session():
    """Vérifie le bon fonctionnement d'une session alternant tours FR et EN."""
    mgr = TurnLanguageManager(initial_language="fr")

    # Tour 1 : Français
    t1 = mgr.process_turn("Bonjour Jarvis, peux-tu m'aider ?")
    assert t1["effective_language"] == "fr"
    assert mgr.last_language == "fr"

    # Tour 2 : Entrée brève en français
    t2 = mgr.process_turn("Merci beaucoup")
    assert t2["effective_language"] == "fr"
    assert mgr.last_language == "fr"

    # Tour 3 : Bascule vers l'anglais
    t3 = mgr.process_turn("Can you switch to English and summarize this article for me?")
    assert t3["effective_language"] == "en"
    assert mgr.last_language == "en"

    # Tour 4 : Entrée courte en anglais (hérite du contexte EN)
    t4 = mgr.process_turn("OK, please proceed")
    assert t4["effective_language"] == "en"
    assert mgr.last_language == "en"

    # Tour 5 : Retour au français
    t5 = mgr.process_turn("Parfait, remets-toi en français s'il te plaît")
    assert t5["effective_language"] == "fr"
    assert mgr.last_language == "fr"


def test_unsupported_third_language_triggers_clarification():
    """Une langue tierce (espagnol, allemand, italien) est identifiée comme 'other' et exige une clarification."""
    other_inputs = [
        "Hola amigo como estas buenos dias por favor",
        "Guten Tag danke wie gehts bitte sprechen",
        "Ciao grazie per favore buongiorno come stai",
        "Ola obrigado tudo bem falar portugues",
    ]
    for inp in other_inputs:
        res = detect_language(inp, last_language="fr")
        assert res.language == "other", f"Devait détecter 'other' pour '{inp}'"
        assert res.is_other_language is True
        assert res.needs_clarification is True
        # La langue effective de repli pour la clarification est le contexte précédent
        assert res.effective_language == "fr"

    # Clarification en contexte anglais
    res_en_ctx = detect_language("Hola amigo como estas buenos dias", last_language="en")
    assert res_en_ctx.language == "other"
    assert res_en_ctx.effective_language == "en"


def test_clarification_prompt_content():
    """Vérifie que les messages de clarification sont formulés en FR ou EN uniquement."""
    prompt_fr = get_clarification_prompt("fr")
    assert "Je ne prends en charge que le français et l'anglais" in prompt_fr
    assert "français ou en anglais" in prompt_fr

    prompt_en = get_clarification_prompt("en")
    assert "I only support French and English" in prompt_en
    assert "French or English" in prompt_en


def test_format_turn_language_instruction():
    """Vérifie la génération des consignes système strictes selon la langue."""
    inst_fr = format_turn_language_instruction("fr")
    assert "[LANGUE DU TOUR : FRANÇAIS]" in inst_fr
    assert "répondre en français" in inst_fr

    inst_en = format_turn_language_instruction("en")
    assert "[TURN LANGUAGE : ENGLISH]" in inst_en
    assert "respond completely and naturally in English" in inst_en

    inst_clarif = format_turn_language_instruction("fr", is_clarification=True, context_language="fr")
    assert "CLARIFICATION REQUISE" in inst_clarif
    assert "Je ne prends en charge que le français et l'anglais" in inst_clarif


def test_tts_voice_routing_fr_and_en(monkeypatch):
    """Vérifie que le routage TTS attribue les bonnes voix FR et EN."""
    monkeypatch.setattr(config, "JARVIS_VOICE", "Aoede")
    monkeypatch.setattr(config, "JARVIS_VOICE_EN", "Puck")

    assert get_tts_voice_for_language("fr") == "Aoede"
    assert get_tts_voice_for_language("en") == "Puck"


def test_tts_voice_routing_fallback_safe(monkeypatch):
    """Si la voix EN est invalide ou absente, repli sécurisé sur la voix FR sans casser le FR."""
    monkeypatch.setattr(config, "JARVIS_VOICE", "Aoede")
    monkeypatch.setattr(config, "JARVIS_VOICE_EN", "")

    # Repli automatique sur JARVIS_VOICE
    assert get_tts_voice_for_language("en") == "Aoede"
    assert get_tts_voice_for_language("fr") == "Aoede"


def test_turn_audit_records_language():
    """Vérifie que record_turn_audit enregistre et restitue fidèlement la langue du tour."""
    import os
    db_file = os.path.join(config.BASE_DIR, "tests", "_temp_test_turn_audit.db")
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
        except Exception:
            pass

    try:
        t1 = record_turn_audit(
            transcript="Bonjour Jarvis",
            voice_mode="standard",
            language="fr",
            final_sentence="Bonjour Pierre.",
            db_path=db_file,
        )
        assert t1["language"] == "fr"

        t2 = record_turn_audit(
            transcript="Hello Jarvis, what time is it?",
            voice_mode="standard",
            language="en",
            final_sentence="It is twelve o'clock.",
            db_path=db_file,
        )
        assert t2["language"] == "en"

        audits = get_turn_audits(db_path=db_file)
        assert len(audits) == 2
        # get_turn_audits returns ordered by id
        langs = [a["language"] for a in audits]
        assert "fr" in langs
        assert "en" in langs
    finally:
        if os.path.exists(db_file):
            try:
                os.remove(db_file)
            except Exception:
                pass
