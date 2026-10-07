"""services/language_service.py
Service de gestion multilingue strict FR/EN pour J.A.R.V.I.S.

Fonctionnalités :
1. Détection robuste de langue (FR vs EN vs OTHER) avec prise en charge :
   - Des accents français (é, è, ê, à, ç, ô, ù, î, etc.)
   - Des élisions et apostrophes (j', c', l', d', qu', it's, don't, etc.)
   - Des entrées brèves ou ambiguës (ok, stop, merci, hello, chiffres) par héritage du contexte
   - Règle par défaut : FR au premier tour en cas d'ambiguïté
2. Détection de langues non prises en charge (espagnol, allemand, italien, etc.)
   - Exige une clarification en FR ou EN sans jamais répondre dans une 3e langue
3. Instructions explicites au LLM pour contraindre la langue de chaque tour
4. Routage vocal TTS (FR -> JARVIS_VOICE, EN -> JARVIS_VOICE_EN) avec repli sûr et observable
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any, Set

logger = logging.getLogger("jarvis.language_service")

SUPPORTED_LANGUAGES = {"fr", "en"}
DEFAULT_LANGUAGE = "fr"

# Voix préconstruites supportées par Gemini Live (Google GenAI)
VALID_GEMINI_LIVE_VOICES = {
    "Aoede", "Charon", "Fenrir", "Kore", "Puck", "Leda", "Orus", "Zephyr"
}

# ─── Lexiques et motifs caractéristiques ──────────────────────────────────────────

# Lexique français spécifique et fonctionnel (avec et sans accents)
FRENCH_EXACT_WORDS: Set[str] = {
    # Pronoms, déterminants, articles
    "le", "la", "les", "un", "une", "des", "du", "de", "d", "au", "aux",
    "ce", "cet", "cette", "ces", "ceci", "cela", "ça", "ca",
    "je", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles",
    "me", "te", "se", "lui", "leur", "y", "en", "moi", "toi", "soi",
    "mon", "ma", "mes", "ton", "ta", "tes", "son", "sa", "ses",
    "notre", "votre", "nos", "vos", "leurs",
    "qui", "que", "quoi", "dont", "où", "ou",
    # Conjonctions, prépositions, adverbes
    "et", "mais", "donc", "or", "ni", "car", "parce", "puisque", "lorsque",
    "dans", "sur", "sous", "avec", "sans", "pour", "par", "chez", "vers", "entre",
    "ici", "la", "là", "bas", "haut", "pres", "près", "loin", "devant", "derriere", "derrière",
    "aussi", "encore", "toujours", "jamais", "souvent", "parfois", "bien", "mal",
    "tres", "très", "trop", "peu", "beaucoup", "plus", "moins", "assez",
    "comment", "pourquoi", "combien", "quand", "quel", "quelle", "quels", "quelles",
    # Verbes courants (formes conjuguées et infinitifs fréquents)
    "est", "sont", "suis", "es", "sommes", "etes", "êtes", "ete", "été", "etre", "être",
    "a", "ai", "as", "avons", "avez", "ont", "avais", "avait", "avoir",
    "fait", "fais", "faire", "faisons", "faites", "font", "ferai", "fera",
    "va", "vais", "vas", "allons", "allez", "vont", "aller", "irai",
    "peux", "peut", "pouvons", "pouvez", "peuvent", "pourrais", "pourrait", "pouvoir",
    "veux", "veut", "voulons", "voulez", "veulent", "voudrais", "voudrait", "vouloir",
    "dis", "dit", "disons", "dites", "dire", "dirai",
    "sais", "sait", "savons", "savez", "savent", "savoir",
    "mets", "met", "mettons", "mettez", "mettre",
    "lance", "lances", "lancez", "lancer", "ouvre", "ouvres", "ouvrez", "ouvrir",
    "cherche", "cherches", "cherchez", "chercher", "trouve", "trouver",
    "joue", "joues", "jouez", "jouer", "ecoute", "écoute", "ecouter", "écouter",
    "arrete", "arrête", "arretez", "arrêtez", "arreter", "arrêter",
    "donne", "donnes", "donnez", "donner", "montre", "montrez", "montrer",
    # Salutations & expressions orales courantes
    "bonjour", "bonsoir", "salut", "merci", "mercis", "oui", "ouais", "non",
    "stp", "svp", "aujourd'hui", "aujourdhui", "demain", "hier", "matin", "soir",
    "plait", "plaît", "dis-moi", "dismoi", "peux-tu", "veuxtu", "veux-tu", "pourrais-tu",
    "c'est", "cest", "j'ai", "jai", "d'accord", "daccord", "qu'est-ce", "questce",
    "j'aimerais", "jaimerais", "j'espere", "jespere", "j'espére", "j'espère"
}

# Lexique anglais spécifique et fonctionnel
ENGLISH_EXACT_WORDS: Set[str] = {
    # Pronouns, determiners, articles
    "the", "a", "an", "this", "that", "these", "those",
    "i", "you", "he", "she", "it", "we", "they",
    "me", "him", "her", "us", "them",
    "my", "your", "his", "its", "our", "their",
    "mine", "yours", "hers", "ours", "theirs",
    "who", "whom", "whose", "which", "what", "where", "when", "why", "how",
    # Conjunctions, prepositions, adverbs
    "and", "but", "or", "so", "because", "although", "though", "if", "unless",
    "in", "on", "at", "to", "for", "with", "without", "from", "by", "about",
    "into", "through", "during", "before", "after", "above", "below", "between",
    "here", "there", "everywhere", "now", "then", "always", "never", "often", "sometimes",
    "very", "too", "much", "many", "little", "few", "more", "less", "quite", "really",
    # Common verbs & auxiliaries
    "is", "are", "am", "was", "were", "be", "been", "being",
    "have", "has", "had", "having",
    "do", "does", "did", "doing", "done",
    "will", "would", "shall", "should", "can", "could", "may", "might", "must",
    "make", "makes", "made", "making", "get", "gets", "got", "getting",
    "go", "goes", "went", "going", "gone",
    "say", "says", "said", "saying", "tell", "tells", "told",
    "see", "sees", "saw", "seeing", "look", "looks", "looking",
    "play", "plays", "played", "playing", "listen", "listens", "listening",
    "start", "starts", "started", "starting", "stop", "stops", "stopped", "stopping",
    "open", "opens", "opened", "opening", "close", "closes", "closed",
    "search", "searches", "searched", "searching", "find", "finds", "found",
    "give", "gives", "gave", "giving", "show", "shows", "showed", "showing",
    "turn", "turns", "turned", "switch", "switches", "switched",
    "read", "reads", "reading", "write", "writes", "wrote", "writing",
    "help", "helps", "helped", "check", "checks", "checked",
    # Greetings & oral expressions
    "hello", "hi", "hey", "goodbye", "bye", "thanks", "thank", "welcome",
    "please", "yes", "yeah", "yep", "no", "nope", "nah",
    "today", "tomorrow", "yesterday", "morning", "night", "evening",
    "it's", "its", "don't", "dont", "can't", "cant", "won't", "wont",
    "i'm", "im", "you're", "youre", "we're", "were", "they're", "theyre",
    "what's", "whats", "there's", "theres", "let's", "lets", "how's", "hows",
    "could've", "would've", "should've", "i'd", "you'd", "we'd", "they'd",
    "i'll", "you'll", "we'll", "they'll"
}

# Lexiques d'autres langues fréquentes (pour détection de 3e langue)
OTHER_LANGUAGES_WORDS: Dict[str, Set[str]] = {
    "es": {
        "hola", "gracias", "por", "favor", "buenos", "dias", "buenas", "noches",
        "como", "estas", "que", "tal", "amigo", "donde", "cuando", "hacer",
        "hablar", "espanol", "español", "adios", "hasta", "luego", "muchas",
        "quiero", "tengo", "puedo", "esta", "estoy", "somos", "pero", "porque",
        "muy", "bien", "nada", "todo", "senor", "señor"
    },
    "de": {
        "hallo", "guten", "tag", "morgen", "abend", "danke", "bitte", "wie",
        "gehts", "geht's", "ja", "nein", "deutsch", "sprechen", "nicht", "alles",
        "auf", "wiedersehen", "tschuss", "tschüss", "ich", "mochte", "möchte",
        "warum", "wohin", "wo", "wann", "ist", "sind", "haben", "sein"
    },
    "it": {
        "ciao", "grazie", "per", "favore", "buongiorno", "buonasera", "come",
        "stai", "italiano", "bene", "arrivederci", "prego", "perche", "perché",
        "dove", "quando", "cosa", "fare", "parlare", "molto", "tutto", "amico"
    },
    "pt": {
        "ola", "olá", "obrigado", "obrigada", "por", "bom", "dia", "boa", "noite",
        "tudo", "bem", "falar", "portugues", "português", "adeus", "ate", "até",
        "onde", "quando", "fazer", "como", "voce", "você"
    }
}

# Mots neutres ou ambigus (souvent prononcés seuls ou universels en audio/tech)
NEUTRAL_OR_AMBIGUOUS_WORDS: Set[str] = {
    "ok", "okay", "stop", "pause", "resume", "status", "test", "jarvis",
    "wifi", "bluetooth", "volume", "spotify", "chrome", "google", "pdf",
    "url", "api", "ip", "vps", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0",
    "10", "20", "30", "40", "50", "100"
}


@dataclass
class LanguageDetectionResult:
    language: str              # "fr", "en", ou "other"
    effective_language: str    # "fr" ou "en" (pour le routage LLM/TTS)
    confidence: float          # 0.0 à 1.0
    reason: str                # Explication synthétique
    is_other_language: bool    # True si langue tierce nécessitant clarification
    needs_clarification: bool  # True si tierce langue détectée


def _clean_and_tokenize(text: str) -> list[str]:
    """Découpe le texte en tokens de mots en gérant les apostrophes et élisions."""
    if not text:
        return []
    # Remplacer les apostrophes typographiques par l'apostrophe standard
    text = text.replace("’", "'").replace("`", "'").replace("ʻ", "'")
    # Séparer les élisions françaises (j', c', d', l', qu', n', m', s', t') en deux tokens
    text = re.sub(r"\b([jcdlnmst]|qu)'([a-zA-Zà-ÿÀ-Ý])", r"\1 \2", text, flags=re.IGNORECASE)
    # Extraire les mots (lettres avec accents et tirets/apostrophes internes pour anglais comme it's)
    tokens = re.findall(r"[a-zA-Zà-ÿÀ-Ý0-9']+", text)
    return [t.lower().strip("'") for t in tokens if t.strip("'")]


def detect_language(
    text: str,
    last_language: Optional[str] = None,
) -> LanguageDetectionResult:
    """Détecte la langue d'une entrée utilisateur (FR vs EN vs OTHER).
    
    Règles :
    1. Si le texte est vide, court ou composé uniquement de mots neutres/ambigus :
       - Hérite de `last_language` si 'fr' ou 'en'.
       - Sinon, prend 'fr' par défaut au premier tour.
    2. Analyse des scores lexicaux pondérés FR, EN et OTHER.
    3. Si des accents typiquement français ou des contractions sont présents -> pondération FR renforcée.
    4. Si une langue tierce est détectée avec certitude -> 'other'.
    """
    if not text or not text.strip():
        eff = last_language if last_language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
        return LanguageDetectionResult(
            language=eff,
            effective_language=eff,
            confidence=0.5,
            reason="empty_fallback",
            is_other_language=False,
            needs_clarification=False,
        )

    clean_text = text.strip()
    tokens = _clean_and_tokenize(clean_text)

    if not tokens:
        eff = last_language if last_language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
        return LanguageDetectionResult(
            language=eff,
            effective_language=eff,
            confidence=0.5,
            reason="no_tokens_fallback",
            is_other_language=False,
            needs_clarification=False,
        )

    # Filtrage des tokens utiles (hors neutres/ambigus)
    informative_tokens = [t for t in tokens if t not in NEUTRAL_OR_AMBIGUOUS_WORDS]

    # Si tous les mots sont ambigus ou neutres (ex: "ok", "stop", "1 2 3", "pause")
    if not informative_tokens:
        eff = last_language if last_language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
        return LanguageDetectionResult(
            language=eff,
            effective_language=eff,
            confidence=0.6,
            reason=f"ambiguous_inherited_{eff}" if last_language in SUPPORTED_LANGUAGES else "ambiguous_default_fr",
            is_other_language=False,
            needs_clarification=False,
        )

    fr_score = 0.0
    en_score = 0.0
    other_score = 0.0

    # Présence d'accents français caractéristiques (é, è, ê, à, ç, ô, ù, î, ï, ë, œ, æ)
    has_french_accents = bool(re.search(r"[éèêàçôùîïëœæ]", clean_text, re.IGNORECASE))
    if has_french_accents:
        fr_score += 1.5

    # Détection de motifs de contractions anglaises (it's, don't, won't, i'm, what's, you're, we'll)
    has_english_contractions = bool(re.search(r"\b(it's|don't|can't|won't|i'm|you're|we're|they're|what's|there's|let's|i've|i'll)\b", clean_text, re.IGNORECASE))
    if has_english_contractions:
        en_score += 1.5

    for token in informative_tokens:
        # Score FR
        if token in FRENCH_EXACT_WORDS:
            fr_score += 1.0

        # Score EN
        if token in ENGLISH_EXACT_WORDS:
            en_score += 1.0

        # Score Autres langues
        for _lang_code, word_set in OTHER_LANGUAGES_WORDS.items():
            if token in word_set and token not in FRENCH_EXACT_WORDS and token not in ENGLISH_EXACT_WORDS:
                other_score += 1.2

    total_score = fr_score + en_score + other_score

    # Cas 1 : Détection d'une 3e langue dominante (ni FR ni EN)
    if other_score > 0 and other_score > (fr_score + en_score) and other_score >= 1.2:
        context_lang = last_language if last_language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
        return LanguageDetectionResult(
            language="other",
            effective_language=context_lang,
            confidence=min(1.0, other_score / (total_score or 1.0)),
            reason="unsupported_third_language",
            is_other_language=True,
            needs_clarification=True,
        )

    # Cas 2 : Score FR nettement supérieur
    if fr_score > en_score:
        confidence = fr_score / (total_score or 1.0)
        return LanguageDetectionResult(
            language="fr",
            effective_language="fr",
            confidence=min(1.0, max(0.5, confidence)),
            reason="french_lexicon",
            is_other_language=False,
            needs_clarification=False,
        )

    # Cas 3 : Score EN nettement supérieur
    if en_score > fr_score:
        confidence = en_score / (total_score or 1.0)
        return LanguageDetectionResult(
            language="en",
            effective_language="en",
            confidence=min(1.0, max(0.5, confidence)),
            reason="english_lexicon",
            is_other_language=False,
            needs_clarification=False,
        )

    # Cas 4 : Égalité ou aucun mot reconnu dans les lexiques (phrase courte / mots inconnus)
    if last_language in SUPPORTED_LANGUAGES:
        return LanguageDetectionResult(
            language=last_language,
            effective_language=last_language,
            confidence=0.55,
            reason=f"tie_context_inherited_{last_language}",
            is_other_language=False,
            needs_clarification=False,
        )

    return LanguageDetectionResult(
        language=DEFAULT_LANGUAGE,
        effective_language=DEFAULT_LANGUAGE,
        confidence=0.5,
        reason="default_first_turn_fr",
        is_other_language=False,
        needs_clarification=False,
    )


# ─── Instructions Système et Clarifications ───────────────────────────────────────

def get_clarification_prompt(context_language: str = "fr") -> str:
    """Message de clarification imposé quand l'utilisateur parle une langue tierce.
    Règle : Demande en FR ou EN uniquement, sans répondre dans la langue tierce."""
    if context_language == "en":
        return "I only support French and English. Would you like to continue in French or English?"
    return "Je ne prends en charge que le français et l'anglais. Souhaitez-vous continuer en français ou en anglais ?"


def format_turn_language_instruction(language: str, is_clarification: bool = False, context_language: str = "fr") -> str:
    """Génère la consigne système explicite injectée au LLM pour le tour courant."""
    if is_clarification:
        clarif_msg = get_clarification_prompt(context_language)
        return (
            f"[INSTRUCTION STRICTE DE LANGUE : CLARIFICATION REQUISE]\n"
            f"L'utilisateur vient de s'exprimer dans une langue non prise en charge. "
            f"RÈGLE ABSOLUE : Tu ne dois JAMAIS répondre dans cette troisième langue. "
            f"Réponds exactement et poliment avec le message suivant : '{clarif_msg}'."
        )

    if language == "en":
        return (
            "[TURN LANGUAGE : ENGLISH]\n"
            "The user is speaking in English. You MUST respond completely and naturally in English for this turn. "
            "Do not translate into French."
        )

    return (
        "[LANGUE DU TOUR : FRANÇAIS]\n"
        "L'utilisateur s'exprime en français. Tu dois impérativement répondre en français pour ce tour de dialogue. "
        "Ne traduis pas en anglais."
    )


# ─── Routage Vocal TTS ────────────────────────────────────────────────────────────

def get_tts_voice_for_language(language: str) -> str:
    """Sélectionne la voix TTS appropriée selon la langue (FR vs EN).
    
    Règles :
    - FR : voix JARVIS_VOICE (défaut 'Aoede').
    - EN : voix JARVIS_VOICE_EN si valide (défaut 'Aoede' ou 'Puck').
    - En cas d'indisponibilité de la voix EN : repli observable et sûr sur JARVIS_VOICE sans casser le FR.
    """
    import config

    voice_fr = getattr(config, "JARVIS_VOICE", None) or "Aoede"
    voice_en = getattr(config, "JARVIS_VOICE_EN", None) or voice_fr

    if language == "en":
        # Vérification de la validité de la voix anglaise
        if voice_en and (voice_en in VALID_GEMINI_LIVE_VOICES or os.environ.get("JARVIS_VOICE_EN")):
            return voice_en
        # Repli observable et non sensible
        logger.warning(
            "[TTS Voice Routing] Voix EN non disponible ou non configurée ('%s'). "
            "Repli sûr sur la voix principale '%s'.",
            voice_en,
            voice_fr
        )
        return voice_fr

    # Langue française ou par défaut
    if voice_fr in VALID_GEMINI_LIVE_VOICES:
        return voice_fr
    return "Aoede"


# ─── Gestionnaire de Tours de Dialogue ───────────────────────────────────────────

class TurnLanguageManager:
    """Gestionnaire d'état de langue au fil des tours de conversation."""

    def __init__(self, initial_language: str = DEFAULT_LANGUAGE):
        self.last_language: str = initial_language if initial_language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
        self.turn_count: int = 0

    def process_turn(self, user_input: str) -> Dict[str, Any]:
        """Traite une entrée utilisateur et retourne les métadonnées de langue du tour."""
        detection = detect_language(
            text=user_input,
            last_language=self.last_language if self.turn_count > 0 else None,
        )

        effective_lang = detection.effective_language
        if detection.language in SUPPORTED_LANGUAGES:
            self.last_language = detection.language

        self.turn_count += 1
        voice = get_tts_voice_for_language(effective_lang)
        prompt_instruction = format_turn_language_instruction(
            language=effective_lang,
            is_clarification=detection.is_other_language,
            context_language=self.last_language,
        )

        return {
            "detected_language": detection.language,
            "effective_language": effective_lang,
            "confidence": detection.confidence,
            "reason": detection.reason,
            "is_other_language": detection.is_other_language,
            "needs_clarification": detection.needs_clarification,
            "voice": voice,
            "prompt_instruction": prompt_instruction,
            "clarification_message": get_clarification_prompt(self.last_language) if detection.is_other_language else "",
        }

    def reset(self, initial_language: str = DEFAULT_LANGUAGE) -> None:
        """Réinitialise l'état du gestionnaire."""
        self.last_language = initial_language if initial_language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
        self.turn_count = 0
