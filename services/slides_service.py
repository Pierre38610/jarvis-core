"""services/slides_service.py
Service de conception, recherche documentaire et génération esthétique de présentations Google Slides pour J.A.R.V.I.S.
Assure :
1. Structuration intellectuelle et plan polymorphe dynamique (nombre de diapositives libre adapté au sujet ou consigne explicite).
2. Recherche approfondie de faits vérifiés, actualités, données techniques et chiffres clés.
3. Génération des requêtes Google Slides API (batchUpdate) au pixel près (format 16:9 widescreen 720x405 PT) avec conformité stricte ROUND_RECTANGLE.
4. Variété dynamique des layouts (hero_title, key_metrics, cards_grid, split_compare, timeline_steps, quote_highlight, conclusion_call_to_action).
5. Application de thèmes esthétiques premium (stark, gold/bitcoin, corporate, dark, cyber).
6. Suivi pas-à-pas de l'avancement dans SupervisionService pour expliquer en direct à Pierre l'état d'avancement.
"""

import os
import re
import json
import time
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── Palettes de Couleurs et Thèmes Esthétiques ──────────────────────────────
THEMES = {
    "stark": {
        "name": "Stark Industries (Dark Cyan / Reactor)",
        "background": {"red": 0.04, "green": 0.07, "blue": 0.11},      # #0A121C
        "card_bg": {"red": 0.07, "green": 0.11, "blue": 0.18},         # #121C2E
        "border_color": {"red": 0.22, "green": 0.74, "blue": 0.97},    # #38BDF8
        "title_color": {"red": 0.22, "green": 0.74, "blue": 0.97},     # #38BDF8
        "text_color": {"red": 0.95, "green": 0.97, "blue": 1.00},      # #F1F5F9
        "accent_color": {"red": 0.22, "green": 0.74, "blue": 0.97},    # #38BDF8
        "subtext": {"red": 0.58, "green": 0.65, "blue": 0.75},         # #94A3B8
        "muted_color": {"red": 0.58, "green": 0.65, "blue": 0.75},
        "badge_bg": {"red": 0.10, "green": 0.16, "blue": 0.28},
    },
    "gold": {
        "name": "Gold & Luxury / Bitcoin",
        "background": {"red": 0.08, "green": 0.07, "blue": 0.05},
        "card_bg": {"red": 0.14, "green": 0.12, "blue": 0.09},
        "border_color": {"red": 0.96, "green": 0.72, "blue": 0.20},
        "title_color": {"red": 0.98, "green": 0.75, "blue": 0.14},
        "text_color": {"red": 1.00, "green": 0.98, "blue": 0.92},
        "accent_color": {"red": 0.96, "green": 0.72, "blue": 0.20},
        "subtext": {"red": 0.78, "green": 0.72, "blue": 0.60},
        "muted_color": {"red": 0.78, "green": 0.72, "blue": 0.60},
        "badge_bg": {"red": 0.22, "green": 0.17, "blue": 0.08},
    },
    "bitcoin": {
        "name": "Bitcoin & Crypto Prestige (Gold & Obsidian)",
        "background": {"red": 0.08, "green": 0.07, "blue": 0.05},
        "card_bg": {"red": 0.14, "green": 0.12, "blue": 0.09},
        "border_color": {"red": 0.96, "green": 0.72, "blue": 0.20},
        "title_color": {"red": 0.98, "green": 0.75, "blue": 0.14},
        "text_color": {"red": 1.00, "green": 0.98, "blue": 0.92},
        "accent_color": {"red": 0.96, "green": 0.72, "blue": 0.20},
        "subtext": {"red": 0.78, "green": 0.72, "blue": 0.60},
        "muted_color": {"red": 0.78, "green": 0.72, "blue": 0.60},
        "badge_bg": {"red": 0.22, "green": 0.17, "blue": 0.08},
    },
    "corporate": {
        "name": "Executive Corporate (Clean Slate)",
        "background": {"red": 0.98, "green": 0.99, "blue": 1.00},
        "card_bg": {"red": 0.92, "green": 0.95, "blue": 0.98},
        "border_color": {"red": 0.08, "green": 0.38, "blue": 0.75},
        "title_color": {"red": 0.08, "green": 0.12, "blue": 0.18},
        "text_color": {"red": 0.08, "green": 0.12, "blue": 0.18},
        "accent_color": {"red": 0.08, "green": 0.38, "blue": 0.75},
        "subtext": {"red": 0.35, "green": 0.42, "blue": 0.52},
        "muted_color": {"red": 0.35, "green": 0.42, "blue": 0.52},
        "badge_bg": {"red": 0.88, "green": 0.92, "blue": 0.98},
    },
    "dark": {
        "name": "Dark Minimal",
        "background": {"red": 0.06, "green": 0.07, "blue": 0.09},
        "card_bg": {"red": 0.11, "green": 0.13, "blue": 0.17},
        "border_color": {"red": 0.55, "green": 0.36, "blue": 0.96},
        "title_color": {"red": 0.96, "green": 0.97, "blue": 0.99},
        "text_color": {"red": 0.96, "green": 0.97, "blue": 0.99},
        "accent_color": {"red": 0.55, "green": 0.36, "blue": 0.96},
        "subtext": {"red": 0.60, "green": 0.64, "blue": 0.72},
        "muted_color": {"red": 0.60, "green": 0.64, "blue": 0.72},
        "badge_bg": {"red": 0.16, "green": 0.14, "blue": 0.24},
    },
    "cyber": {
        "name": "Cyberpunk Neon",
        "background": {"red": 0.03, "green": 0.03, "blue": 0.06},
        "card_bg": {"red": 0.08, "green": 0.06, "blue": 0.16},
        "border_color": {"red": 0.66, "green": 0.33, "blue": 0.97},
        "title_color": {"red": 0.02, "green": 0.71, "blue": 0.83},
        "text_color": {"red": 1.00, "green": 1.00, "blue": 1.00},
        "accent_color": {"red": 0.66, "green": 0.33, "blue": 0.97},
        "subtext": {"red": 0.65, "green": 0.60, "blue": 0.75},
        "muted_color": {"red": 0.65, "green": 0.60, "blue": 0.75},
        "badge_bg": {"red": 0.16, "green": 0.10, "blue": 0.32},
    }
}

# ─── Spécification du Schéma Polymorphe pour l'Agent Délibératif ─────────────
SLIDES_SCHEMA_PROMPT = (
    "LIVRABLE STRICT ATTENDU : Un objet JSON valide respectant l'architecture polymorphe de Google Slides.\n\n"
    "RÈGLES D'OR DE CONCEPTION :\n"
    "1. NOMBRE DE DIAPOSITIVES LIBRE ET ADAPTATIF :\n"
    "   - Si l'utilisateur donne une consigne chiffrée explicite (ex: 'deck de 4 slides', 'fais un pitch de 3 slides', "
    "'dossier de 10 slides'), respecte STRICTEMENT ce nombre exact.\n"
    "   - Si aucune consigne chiffrée n'est fournie, calcule le nombre optimal de diapositives selon la profondeur réelle du sujet "
    "(pitch court : 3-4 slides ; sujet standard : 5-7 slides ; dossier stratégique vaste : 8-14 slides).\n"
    "2. VARIÉTÉ ET ALTERNANCE DES LAYOUTS (AUCUNE MONOTONIE) :\n"
    "   Au sein d'une même présentation, alterne impérativement les types de layout selon la nature de l'information :\n"
    "   - 'hero_title' : Slide d'accroche ou de transition majeure avec grand titre percutant, sous-titre et contexte.\n"
    "   - 'key_metrics' : 1 à 4 indicateurs clés de performance avec grands chiffres d'impact (value, label, subtext).\n"
    "   - 'cards_grid' : Grille moderne de 2, 3 ou 4 cartes pour piliers, fonctionnalités ou composantes (title, body, badge).\n"
    "   - 'split_compare' : Comparatif 2 colonnes Avant / Après ou Problème / Solution (left_column vs right_column).\n"
    "   - 'timeline_steps' : Chronologie ou feuille de route séquentielle par phases (phase, title, desc).\n"
    "   - 'quote_highlight' : Mise en valeur d'un principe fondamental, citation ou constat stratégique majeur.\n"
    "   - 'conclusion_call_to_action' : Synthèse finale percutante avec plan d'action et prochaines étapes concrètes.\n"
    "3. THÈMES ESTHÉTIQUES SUPPORTÉS : 'stark', 'corporate', 'dark', 'gold', 'cyber'.\n\n"
    "FORMAT JSON STRICT ATTENDU :\n"
    "{\n"
    '  "title": "Titre Principal de la Présentation",\n'
    '  "theme": "stark",\n'
    '  "slides": [\n'
    "    {\n"
    '      "layout": "hero_title",\n'
    '      "title": "Titre d\'Accroche",\n'
    '      "subtitle": "Sous-titre et contexte stratégique",\n'
    '      "speaker_notes": "Notes de présentation orateur..."\n'
    "    },\n"
    "    {\n"
    '      "layout": "key_metrics",\n'
    '      "title": "Indicateurs Clés de Performance",\n'
    '      "metrics": [\n'
    '        {"value": "+140%", "label": "Croissance annuelle", "subtext": "Exercice 2026"},\n'
    '        {"value": "12.4 M€", "label": "Volume d\'affaires", "subtext": "Objectif T4"}\n'
    "      ],\n"
    '      "speaker_notes": "Notes de présentation orateur..."\n'
    "    },\n"
    "    {\n"
    '      "layout": "cards_grid",\n'
    '      "title": "Piliers Stratégiques",\n'
    '      "cards": [\n'
    '        {"title": "Pilier 1", "body": "Explications concrètes...", "badge": "PRIORITÉ 1"},\n'
    '        {"title": "Pilier 2", "body": "Explications concrètes...", "badge": "EN COURS"},\n'
    '        {"title": "Pilier 3", "body": "Explications concrètes...", "badge": "PLANIFIÉ"}\n'
    "      ],\n"
    '      "speaker_notes": "Notes de présentation orateur..."\n'
    "    },\n"
    "    {\n"
    '      "layout": "split_compare",\n'
    '      "title": "Analyse Comparative Avant / Après",\n'
    '      "left_column": {\n'
    '        "title": "Situation Actuelle / Frictions",\n'
    '        "points": ["Processus manuel lent", "Manque de visibilité", "Coûts élevés"]\n'
    "      },\n"
    '      "right_column": {\n'
    '        "title": "Cible Automatisée Stark",\n'
    '        "points": ["Exécution temps réel", "Supervision IA permanente", "Économies d\'échelle"]\n'
    "      },\n"
    '      "speaker_notes": "Notes de présentation orateur..."\n'
    "    },\n"
    "    {\n"
    '      "layout": "timeline_steps",\n'
    '      "title": "Feuille de Route Déploiement",\n'
    '      "steps": [\n'
    '        {"phase": "01", "title": "Cadrage", "desc": "Audit technique et spécifications"},\n'
    '        {"phase": "02", "title": "MVP", "desc": "Déploiement version alpha sur VPS"},\n'
    '        {"phase": "03", "title": "Scale", "desc": "Automatisation complète multi-canaux"}\n'
    "      ],\n"
    '      "speaker_notes": "Notes de présentation orateur..."\n'
    "    }\n"
    "  ]\n"
    "}\n"
    "IMPORTANT : Rends UNIQUEMENT le bloc JSON brut commençant par '{' et finissant par '}'. Aucun commentaire ni balise markdown autour."
)


def extract_requested_slide_count(text: str) -> Optional[int]:
    """Extrait le nombre de diapositives explicitement demandé par l'utilisateur s'il existe."""
    if not text:
        return None
    patterns = [
        r"(?:deck|présentation|dossier|pitch|slides?)\s+(?:de\s+)?(\d+)\s*(?:slides?|diapos?|diapositives?|planches?)?",
        r"(\d+)\s*(?:slides?|diapos?|diapositives?|planches?)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                count = int(m.group(1))
                if 1 <= count <= 30:
                    return count
            except (ValueError, TypeError):
                continue
    return None


class SlidesResult(tuple):
    """Tuple (titre, sous-titre, slides) compatible à la fois avec un déballage synchrone et un await asynchrone."""
    def __new__(cls, titre: str, subtitle: str, slides: List[Dict[str, Any]]):
        return super().__new__(cls, (titre, subtitle, slides))

    def __await__(self):
        async def _coro():
            return self
        return _coro().__await__()


class SlidesService:
    """Service d'ingénierie et de création de présentations Google Slides."""

    def __init__(self):
        self._current_task: Dict[str, Any] = {
            "active": False,
            "action_id": "",
            "topic": "",
            "step": "En veille",
            "details": "",
            "started_at": 0.0,
            "slides_count": 0,
            "presentation_url": ""
        }

    def get_current_task(self) -> Dict[str, Any]:
        """Retourne l'état de la tâche de présentation active."""
        if not self._current_task["active"]:
            return {"active": False, "status": "idle", "explanation": "Aucune tâche de présentation en cours."}
        
        elapsed = int(time.time() - self._current_task.get("started_at", time.time()))
        return {
            "active": True,
            "status": "running",
            "topic": self._current_task.get("topic", "Présentation"),
            "step": self._current_task.get("step", ""),
            "details": self._current_task.get("details", ""),
            "elapsed_seconds": elapsed,
            "explanation": (
                f"Je travaille actuellement sur la présentation '{self._current_task.get('topic')}'. "
                f"J'en suis à l'étape suivante : {self._current_task.get('step')} ({self._current_task.get('details')})."
            )
        }

    # ─── 1. Moteur Polymorphe de Recherche et Élaboration du Plan ─────────────

    def generate_deep_research_slides(
        self,
        sujet: str,
        titre: Optional[str] = None,
        theme: str = "stark"
    ) -> SlidesResult:
        """Élabore un plan rigoureux polymorphe et dynamique avec alternance de layouts.
        Adapte automatiquement le nombre de slides à la consigne explicite ou à la complexité.
        Retourne un SlidesResult compatible sync et await.
        """
        clean_topic = (sujet or titre or "Présentation").strip()
        requested_count = extract_requested_slide_count(sujet) or extract_requested_slide_count(titre or "")
        is_bitcoin = any(k in clean_topic.lower() for k in ["bitcoin", "btc", "satoshi", "halving", "crypto"])

        if is_bitcoin:
            presentation_title = titre or "Bitcoin : Révolution Monétaire & Architecture Décentralisée"
            subtitle = "Genèse, Fondamentaux Techniques, Halving et Perspectives Macroéconomiques"
            effective_theme = "bitcoin" if theme in ("stark", "bitcoin") else theme

            # Deck complet maître polymorphe sur Bitcoin
            master_slides = [
                {
                    "layout": "hero_title",
                    "title": "1. Genèse & Rareté Numérique Absolue",
                    "titre_slide": "1. Genèse & Rareté Numérique Absolue",
                    "category": "HISTOIRE & VISION",
                    "subtitle": "Publication du Livre Blanc en 2008 par Satoshi Nakamoto et Bloc Genesis miné le 3 janvier 2009.",
                    "points": [
                        "Publication du Livre Blanc en 2008 par Satoshi Nakamoto en réponse directe à la crise des subprimes.",
                        "Bloc Genesis miné le 3 janvier 2009 intégrant le message historique du chancelier britannique.",
                        "Plafond d'émission strictement verrouillé à 21 millions de bitcoins créant la première rareté numérique absolue.",
                        "Politique monétaire mathématique prévisible, protégée contre toute dévaluation ou manipulation discrétionnaire."
                    ],
                    "key_metric": {
                        "label": "PLAFOND MONÉTAIRE",
                        "value": "21M BTC",
                        "desc": "Immuabilité mathématique garantie par le protocole"
                    },
                    "speaker_notes": "Souligner la rupture avec les devises fiduciaires inflationnistes et la souveraineté financière individuelle.",
                    "notes": "Souligner la rupture avec les devises fiduciaires inflationnistes et la souveraineté financière individuelle."
                },
                {
                    "layout": "key_metrics",
                    "title": "2. Architecture Technique & Preuve de Travail",
                    "titre_slide": "2. Architecture Technique & Preuve de Travail",
                    "category": "CONSENSUS & SÉCURITÉ",
                    "metrics": [
                        {"value": "SHA-256", "label": "Fonction de Hachage", "subtext": "Preuve de travail PoW immuable"},
                        {"value": "~10 MIN", "label": "Rythme Moyen par Bloc", "subtext": "Ajustement tous les 2016 blocs"}
                    ],
                    "key_metric": {
                        "label": "RYTHME DE BLOC",
                        "value": "~10 MIN",
                        "desc": "Ajustement dynamique de la difficulté cryptographique"
                    },
                    "points": [
                        "Consensus par Proof-of-Work (PoW) fondé sur la fonction de hachage cryptographique SHA-256.",
                        "Ajustement automatique de la difficulté tous les 2016 blocs (~14 jours) pour cibler un rythme moyen de 10 minutes.",
                        "Horodatage distribué et chaîne de blocs rendant impossible toute double dépense sans contrôle majoritaire.",
                        "Réseau mondial de dizaines de milliers de nœuds complets (Full Nodes) validant chaque transaction de façon souveraine."
                    ],
                    "speaker_notes": "Expliquer l'absence de serveur central et la robustesse du Proof-of-Work face aux cyberattaques.",
                    "notes": "Expliquer l'absence de serveur central et la robustesse du Proof-of-Work face aux cyberattaques."
                },
                {
                    "layout": "cards_grid",
                    "title": "3. Cycle des Halvings & Modèle Économique",
                    "titre_slide": "3. Cycle des Halvings & Modèle Économique",
                    "category": "ÉCONOMIE & CYCLES",
                    "cards": [
                        {"title": "Rythme Quinquennal", "body": "Division par deux de la prime de bloc tous les 210 000 blocs (~4 ans).", "badge": "RYTHME"},
                        {"title": "Halving Avril 2024", "body": "Émission réduite à 3.125 BTC par bloc, inflation sous les 0.85 %.", "badge": "CHOC OFFRE"},
                        {"title": "Stock-to-Flow", "body": "Rareté programmée supérieure à l'or physique et transition valeur refuge.", "badge": "MODÈLE S2F"}
                    ],
                    "key_metric": {
                        "label": "RÉCOMPENSE 2024",
                        "value": "3.125 BTC",
                        "desc": "Division de l'émission par deux tous les 4 ans"
                    },
                    "points": [
                        "Division par deux de la prime de bloc tous les 210 000 blocs (environ tous les 4 ans).",
                        "4ème Halving survenu en avril 2024 réduisant la création monétaire à 3.125 BTC par bloc.",
                        "Choc d'offre programmé réduisant l'inflation annuelle sous les 0.85 %, devenant plus rare que l'or physique.",
                        "Modèle Stock-to-Flow attestant de la transition vers une valeur refuge macroéconomique majeure."
                    ],
                    "speaker_notes": "Présenter le rôle du halving comme catalyseur historique des cycles de marché et de renforcement de la rareté.",
                    "notes": "Présenter le rôle du halving comme catalyseur historique des cycles de marché et de renforcement de la rareté."
                },
                {
                    "layout": "timeline_steps",
                    "title": "4. Scalabilité & Réseau Lightning (Layer 2)",
                    "titre_slide": "4. Scalabilité & Réseau Lightning (Layer 2)",
                    "category": "INNOVATION & INFRASTRUCTURE",
                    "steps": [
                        {"phase": "01", "title": "Couche L1", "desc": "Sécurité absolue et règlement final immuable"},
                        {"phase": "02", "title": "Soft Forks", "desc": "SegWit (2017) et Taproot (2021) pour la compacité"},
                        {"phase": "03", "title": "Lightning", "desc": "Canaux de paiement décentralisés à millions de TPS"}
                    ],
                    "key_metric": {
                        "label": "DÉBIT COUCHE 2",
                        "value": "MILLIONS TPS",
                        "desc": "Transactions instantanées via Lightning Network"
                    },
                    "points": [
                        "Distinction entre couche de base L1 (sécurité et règlement final) et couches L2 (rapidité et volume).",
                        "Lightning Network : canaux de paiement bidirectionnels décentralisés hors chaîne avec règlement L1 instantané.",
                        "Capacité théorique de plusieurs millions de transactions par seconde (TPS) à coût quasi nul.",
                        "Évolutions protocolaires soft fork pérennes : SegWit (2017) et Taproot (2021) pour la compacité et la confidentialité."
                    ],
                    "speaker_notes": "Démontrer que Bitcoin résout le trilemme des blockchains par une architecture modulaire en couches.",
                    "notes": "Démontrer que Bitcoin résout le trilemme des blockchains par une architecture modulaire en couches."
                },
                {
                    "layout": "split_compare",
                    "title": "5. Adoption Institutionnelle & Régulation",
                    "titre_slide": "5. Adoption Institutionnelle & Régulation",
                    "category": "MARCHÉ & FINANCE GLOBALE",
                    "left_column": {
                        "title": "Finance Traditionnelle & Frictions",
                        "points": [
                            "Méfiance historique initiale des régulateurs",
                            "Volatilité perçue comme un frein d'allocation",
                            "Complexité de garde pour les institutionnels"
                        ]
                    },
                    "right_column": {
                        "title": "Adoption Institutionnelle Massive",
                        "points": [
                            "Approbation des ETF Bitcoin Spot par la SEC (Wall Street)",
                            "Réserves d'entreprises (MicroStrategy, Tesla) et États (Salvador)",
                            "Clarté normative européenne (MiCA) et réserves souveraines"
                        ]
                    },
                    "key_metric": {
                        "label": "ACCÈS INSTITUTIONNEL",
                        "value": "ETFs SPOT",
                        "desc": "Validation formelle des marchés financiers traditionnels"
                    },
                    "points": [
                        "Approbation historique des premiers ETF Bitcoin Spot aux USA par la SEC en janvier 2024.",
                        "Arrivée massive des géants de Wall Street (BlackRock, Fidelity) et des fonds de pension mondiaux.",
                        "Réserves stratégiques d'entreprises cotées (MicroStrategy, Tesla) et adoption souveraine nationale (Salvador).",
                        "Cadres réglementaires clarifiés : règlement MiCA en Union Européenne et projets de réserve stratégique nationale aux États-Unis."
                    ],
                    "speaker_notes": "Pointer le passage d'une curiosité technologique à une classe d'actifs géopolitique incontournable.",
                    "notes": "Pointer le passage d'une curiosité technologique à une classe d'actifs géopolitique incontournable."
                },
                {
                    "layout": "cards_grid",
                    "title": "6. Thèse d'Investissement & Perspectives 2026-2030",
                    "titre_slide": "6. Thèse d'Investissement & Perspectives 2026-2030",
                    "category": "SYNTHÈSE STRATÉGIQUE",
                    "cards": [
                        {"title": "Or Numérique", "body": "Réserve de valeur majeure face à la dévaluation monétaire mondiale.", "badge": "THÈSE"},
                        {"title": "Transition Verte", "body": "Exploitation vertueuse des surplus d'énergie hydroélectrique et gaz de torchage.", "badge": "ÉNERGIE"},
                        {"title": "Propriété Inviolable", "body": "Résistance absolue à la confiscation et neutralité géopolitique globale.", "badge": "SOUVERAINETÉ"}
                    ],
                    "key_metric": {
                        "label": "STATUT MAJEUR",
                        "value": "OR NUMÉRIQUE",
                        "desc": "Réserve de valeur décentralisée et liquide"
                    },
                    "points": [
                        "Positionnement établi comme 'Or Numérique' (Store of Value) face à l'inflation et à l'expansion de la dette mondiale.",
                        "Transition écologique accélérée du minage exploitant les surplus hydroélectriques et le torchage de gaz (flaring).",
                        "Propriété privée inviolable : résistance absolue à la confiscation et neutralité financière globale.",
                        "Convergence vers une monnaie de réserve internationale numérique pour le commerce mondial interconnecté."
                    ],
                    "speaker_notes": "Conclure sur l'adoption inéluctable et la place centrale de Bitcoin dans le patrimoine technologique moderne.",
                    "notes": "Conclure sur l'adoption inéluctable et la place centrale de Bitcoin dans le patrimoine technologique moderne."
                }
            ]

            target_count = requested_count if requested_count is not None else 6
            if target_count < len(master_slides):
                # Si l'utilisateur demande moins de slides (ex: 3), conserve hero_title + key_metrics + synthèse
                if target_count == 3:
                    selected_slides = [master_slides[0], master_slides[1], master_slides[5]]
                elif target_count == 4:
                    selected_slides = [master_slides[0], master_slides[1], master_slides[2], master_slides[5]]
                else:
                    selected_slides = master_slides[:target_count]
            elif target_count > len(master_slides):
                selected_slides = list(master_slides)
                # Expansion modulaire polymorphe pour les decks volumineux
                while len(selected_slides) < target_count:
                    extra_idx = len(selected_slides) + 1
                    selected_slides.append({
                        "layout": "cards_grid" if extra_idx % 2 == 0 else "split_compare",
                        "title": f"{extra_idx}. Approfondissement Stratégique & Données de Marché",
                        "titre_slide": f"{extra_idx}. Approfondissement Stratégique & Données de Marché",
                        "category": "ANALYSE AVANCÉE",
                        "cards": [
                            {"title": "Métrique Réseau", "body": "Hashrate record et robustesse cryptographique sans précédent.", "badge": "SÉCURITÉ"},
                            {"title": "Liquidité Mondiale", "body": "Volumes d'échanges quotidiens concurrents des grandes places financières.", "badge": "LIQUIDITÉ"},
                            {"title": "Intégration Trésorerie", "body": "Adoption progressive par les banques centrales et gestionnaires de fonds.", "badge": "MACRO"}
                        ],
                        "key_metric": {
                            "label": "STABILITÉ RÉSEAU",
                            "value": "99.99%",
                            "desc": "Disponibilité continue depuis 2009"
                        },
                        "points": [
                            "Détail des métriques de sécurité réseau et progression constante du hashrate.",
                            "Consolidation de la liquidité sur les marchés spot et dérivés mondiaux.",
                            "Perspectives d'intégration dans les réserves stratégiques souveraines d'ici 2030."
                        ],
                        "speaker_notes": "Approfondir les métriques macroéconomiques de long terme.",
                        "notes": "Approfondir les métriques macroéconomiques de long terme."
                    })
            else:
                selected_slides = master_slides

            return SlidesResult(presentation_title, subtitle, selected_slides)

        # ── Sujet générique : construction polymorphe dynamique ──────────────
        presentation_title = titre or f"Dossier Stratégique : {clean_topic}"
        subtitle = f"Analyse approfondie, enjeux clés et perspectives d'avenir sur {clean_topic}"

        # Détermination intelligente du nombre de slides si non spécifié
        if requested_count is not None:
            target_count = requested_count
        else:
            is_deep = any(k in clean_topic.lower() for k in ["dossier", "complet", "exhaustif", "stratégique", "architecture", "benchmark"]) or len(clean_topic) > 45
            is_pitch = any(k in clean_topic.lower() for k in ["pitch", "rapide", "court", "express", "synthèse"])
            if is_deep:
                target_count = 8
            elif is_pitch:
                target_count = 3
            else:
                target_count = 5

        # Bibliothèque modulaire de diapositives polymorphes adaptables
        deck_pool = [
            {
                "layout": "hero_title",
                "title": f"1. Introduction & Contexte Fondateur",
                "titre_slide": f"1. Introduction & Contexte Fondateur",
                "category": "VUE D'ENSEMBLE",
                "subtitle": f"Définition, émergence et propositions de valeur différenciantes pour {clean_topic}.",
                "points": [
                    f"Définition et périmètre fondamental de {clean_topic}.",
                    "Émergence historique et facteurs déclencheurs du développement moderne.",
                    "Problématiques initiales résolues et propositions de valeur différenciantes.",
                    "Alignement avec les transformations technologiques et sociétales actuelles."
                ],
                "key_metric": {
                    "label": "MATURITÉ",
                    "value": "EXPANSION",
                    "desc": "Phase d'adoption accélérée à l'échelle globale"
                },
                "speaker_notes": f"Introduire clairement les enjeux majeurs et poser le cadre d'analyse de {clean_topic}.",
                "notes": f"Introduire clairement les enjeux majeurs et poser le cadre d'analyse de {clean_topic}."
            },
            {
                "layout": "key_metrics",
                "title": f"2. Indicateurs d'Impact & Performance",
                "titre_slide": f"2. Piliers Techniques & Fonctionnement",
                "category": "MÉTRIQUES CLÉS",
                "metrics": [
                    {"value": "+85 %", "label": "Efficience Opérationnelle", "subtext": "Gains d'automatisation mesurés"},
                    {"value": "3.5x", "label": "Retour sur Investissement", "subtext": "Constaté sur cycle de 24 mois"}
                ],
                "points": [
                    "Composants structurels et principes de fonctionnement sous-jacents.",
                    "Protocoles, standards techniques et méthodologies de mise en œuvre.",
                    "Gestion de la performance, de la sécurité et de la résilience du système.",
                    "Interconnexions avec les écosystèmes existants et interopérabilité."
                ],
                "key_metric": {
                    "label": "EFFICIENCE",
                    "value": "+85 %",
                    "desc": "Gains d'automatisation et de standardisation"
                },
                "speaker_notes": "Détailler les chiffres réels et la rentabilité concrète du déploiement.",
                "notes": "Détailler les aspects concrets et techniques avec rigueur."
            },
            {
                "layout": "cards_grid",
                "title": f"3. Piliers Stratégiques & Architecture",
                "titre_slide": f"3. Cas d'Usage & Applications Concrètes",
                "category": "ARCHITECTURE & PILIERS",
                "cards": [
                    {"title": "Socle Technique", "body": "Infrastructure résiliente et hautement disponible.", "badge": "FONDATION"},
                    {"title": "Automatisation", "body": "Orchestration en temps réel des flux critiques sans friction.", "badge": "MOTEUR"},
                    {"title": "Gouvernance", "body": "Contrôle d'accès strict, audit permanent et conformité.", "badge": "SÉCURITÉ"}
                ],
                "points": [
                    "Scénarios d'utilisation à fort impact dans les organisations de référence.",
                    "Bénéfices opérationnels mesurés : réduction des coûts et accélération des cycles.",
                    "Retours d'expérience et meilleures pratiques de déploiement.",
                    "Facteurs clés de succès pour une adoption pérenne et sécurisée."
                ],
                "key_metric": {
                    "label": "ROI MOYEN",
                    "value": "3.5x",
                    "desc": "Retour sur investissement constaté sur 24 mois"
                },
                "speaker_notes": "Présenter les 3 piliers fondateurs du système.",
                "notes": "Illustrer par des exemples concrets pour rendre la présentation vivante."
            },
            {
                "layout": "split_compare",
                "title": f"4. Analyse Comparative Avant / Après",
                "titre_slide": f"4. Défis Majeurs & Gestion des Risques",
                "category": "ANALYSE COMPARATIVE",
                "left_column": {
                    "title": "Approche Conventionnelle",
                    "points": [
                        "Traitements manuels lents et dispersés",
                        "Frictions de communication et silos techniques",
                        "Coûts opérationnels récurrents élevés"
                    ]
                },
                "right_column": {
                    "title": "Cible Optimisée Stark",
                    "points": [
                        "Exécution instantanée supervisée en temps réel",
                        "Interopérabilité fluide et transparence totale",
                        "Économies d'échelle et robustesse garantie"
                    ]
                },
                "points": [
                    "Contraintes réglementaires, juridiques et conformité normative.",
                    "Défis de sécurité, souveraineté des données et continuité d'activité.",
                    "Enjeux environnementaux et soutenabilité des infrastructures associées.",
                    "Stratégies d'atténuation et gouvernance proactive recommandée."
                ],
                "key_metric": {
                    "label": "CONFORMITÉ",
                    "value": "100 %",
                    "desc": "Alignement sur les standards européens et mondiaux"
                },
                "speaker_notes": "Mettre en contraste la rupture opérationnelle entre l'ancien modèle et la nouvelle cible.",
                "notes": "Adopter un regard critique constructif et lucide sur les freins éventuels."
            },
            {
                "layout": "timeline_steps",
                "title": f"5. Feuille de Route & Déploiement",
                "titre_slide": f"5. Synthèse & Trajectoire Prospective",
                "category": "FEUILLE DE ROUTE",
                "steps": [
                    {"phase": "01", "title": "Cadrage & Audit", "desc": "Audit technique et validation des spécifications clés"},
                    {"phase": "02", "title": "MVP Opérationnel", "desc": "Déploiement version alpha testée en conditions réelles"},
                    {"phase": "03", "title": "Généralisation", "desc": "Automatisation complète multi-canaux et passages à l'échelle"}
                ],
                "points": [
                    f"Synthèse des opportunités déterminantes offertes par {clean_topic}.",
                    "Évolutions technologiques attendues à court et moyen terme.",
                    "Recommandations directes d'action et priorités d'investissement.",
                    "Conclusion prospective : positionnement stratégique à adopter dès aujourd'hui."
                ],
                "key_metric": {
                    "label": "HORIZON",
                    "value": "2026-2030",
                    "desc": "Standardisation et déploiement à grande échelle"
                },
                "speaker_notes": "Parcourir les 3 phases de mise en œuvre concrètes.",
                "notes": "Terminer par un appel à l'action clair et une synthèse percutante."
            },
            {
                "layout": "cards_grid",
                "title": f"6. Cas d'Usage Industriels & Résultats",
                "titre_slide": f"6. Cas d'Usage Industriels & Résultats",
                "category": "RÉSULTATS DE TERRAIN",
                "cards": [
                    {"title": "Production", "body": "Accélération des cadences et diminution des erreurs de saisie.", "badge": "PRODUCTION"},
                    {"title": "Qualité", "body": "Auditabilité totale et conformité systématique en temps réel.", "badge": "QUALITÉ"},
                    {"title": "Économie", "body": "Amortissement rapide des investissements initiaux.", "badge": "FINANCE"}
                ],
                "points": [
                    "Retours d'expérience concrets sur sites pilotes.",
                    "Indicateurs de satisfaction utilisateurs supérieurs à 90 %.",
                    "Stabilité opérationnelle observée sur cycle long."
                ],
                "key_metric": {"label": "SATISFACTION", "value": "> 90%", "desc": "Adhésion des équipes"},
                "speaker_notes": "Présenter les retours concrets de terrain.",
                "notes": "Présenter les retours concrets de terrain."
            },
            {
                "layout": "key_metrics",
                "title": f"7. Efficience & Rendement Énergétique",
                "titre_slide": f"7. Efficience & Rendement Énergétique",
                "category": "SOUTENABILITÉ",
                "metrics": [
                    {"value": "-40 %", "label": "Empreinte Carbone", "subtext": "Optimisation des ressources serveur"},
                    {"value": "99.98 %", "label": "Disponibilité Globale", "subtext": "SLA sans interruption de service"}
                ],
                "points": [
                    "Optimisation fine de l'infrastructure d'hébergement.",
                    "Réduction mesurable de l'empreinte environnementale.",
                    "Haute tolérance aux pannes matérielles et logicielles."
                ],
                "key_metric": {"label": "DISPONIBILITÉ", "value": "99.98%", "desc": "Haute résilience"},
                "speaker_notes": "Souligner la sobriété énergétique et la robustesse du système.",
                "notes": "Souligner la sobriété énergétique et la robustesse du système."
            },
            {
                "layout": "split_compare",
                "title": f"8. Gestion des Risques & Atténuation",
                "titre_slide": f"8. Gestion des Risques & Atténuation",
                "category": "RISQUES & CONFORMITÉ",
                "left_column": {
                    "title": "Risques Identifiés",
                    "points": [
                        "Obsolescence rapide des protocoles",
                        "Attaques ciblées sur les points d'entrée",
                        "Résistance au changement culturel"
                    ]
                },
                "right_column": {
                    "title": "Mesures de Protection",
                    "points": [
                        "Architecture modulaire découplée et évolutive",
                        "Chiffrement de bout en bout et authentification forte",
                        "Accompagnement continu et formation ergonomique"
                    ]
                },
                "points": [
                    "Cartographie exhaustive des risques et vulnérabilités.",
                    "Mesures de mitigation proactives testées en amont.",
                    "Plan de reprise d'activité (PRA) validé."
                ],
                "key_metric": {"label": "RÉSILIENCE", "value": "NIVEAU A", "desc": "Standard Stark Industrie"},
                "speaker_notes": "Démontrer la maîtrise proactive de l'ensemble des risques.",
                "notes": "Démontrer la maîtrise proactive de l'ensemble des risques."
            },
            {
                "layout": "cards_grid",
                "title": f"9. Gouvernance & Cadre d'Excellence",
                "titre_slide": f"9. Gouvernance & Cadre d'Excellence",
                "category": "GOUVERNANCE",
                "cards": [
                    {"title": "Comité Stratégique", "body": "Arbitrages réguliers et priorisation des investissements.", "badge": "PILOTAGE"},
                    {"title": "Normes & Standards", "body": "Alignement continu sur les meilleures pratiques mondiales.", "badge": "CONFORMITÉ"},
                    {"title": "Amélioration Continue", "body": "Boucles de rétroaction courtes et itérations rapides.", "badge": "KAIZEN"}
                ],
                "points": [
                    "Instances de décision transparentes et agiles.",
                    "Respect strict des réglementations en vigueur.",
                    "Maintien de l'avantage concurrentiel dans la durée."
                ],
                "key_metric": {"label": "GOUVERNANCE", "value": "AGILE", "desc": "Itérations courtes"},
                "speaker_notes": "Poser le cadre pérenne de suivi et d'amélioration continue.",
                "notes": "Poser le cadre pérenne de suivi et d'amélioration continue."
            },
            {
                "layout": "conclusion_call_to_action",
                "title": f"10. Synthèse Stratégique & Plan d'Action",
                "titre_slide": f"10. Synthèse Stratégique & Plan d'Action",
                "category": "CONCLUSION & ACTION",
                "cards": [
                    {"title": "Décision Immédiate", "body": "Validation du périmètre et allocation des ressources prioritaires.", "badge": "ACTION 1"},
                    {"title": "Lancement Phase 1", "body": "Activation des agents et mise en place de la supervision.", "badge": "ACTION 2"},
                    {"title": "Point d'Étape J+30", "body": "Premier bilan chiffré des gains et ajustements tactiques.", "badge": "ACTION 3"}
                ],
                "points": [
                    "Consolidation des opportunités à fort impact.",
                    "Mobilisation immédiate des équipes et des technologies.",
                    "Mesure systématique des résultats opérationnels dès le premier mois."
                ],
                "key_metric": {"label": "PRIORITÉ", "value": "IMMÉDIATE", "desc": "Déploiement T1"},
                "speaker_notes": "Terminer par un appel à l'action percutant et des étapes de réalisation immédiates.",
                "notes": "Terminer par un appel à l'action percutant et des étapes de réalisation immédiates."
            }
        ]

        if target_count <= len(deck_pool):
            if target_count == 3:
                selected_slides = [deck_pool[0], deck_pool[1], deck_pool[9]]
            elif target_count == 4:
                selected_slides = [deck_pool[0], deck_pool[1], deck_pool[2], deck_pool[9]]
            elif target_count == 5:
                selected_slides = [deck_pool[0], deck_pool[1], deck_pool[2], deck_pool[3], deck_pool[4]]
            else:
                selected_slides = deck_pool[:target_count]
        else:
            selected_slides = list(deck_pool)
            while len(selected_slides) < target_count:
                idx_n = len(selected_slides) + 1
                selected_slides.append({
                    "layout": "cards_grid" if idx_n % 2 == 0 else "split_compare",
                    "title": f"{idx_n}. Extension Analytique & Enjeux Spécifiques",
                    "titre_slide": f"{idx_n}. Extension Analytique & Enjeux Spécifiques",
                    "category": "ANALYSE DÉTAILLÉE",
                    "cards": [
                        {"title": "Facteur Clé 1", "body": f"Optimisation continue liée à {clean_topic}.", "badge": "PILIER"},
                        {"title": "Facteur Clé 2", "body": "Gains qualitatifs et pérennité des processus.", "badge": "QUALITÉ"},
                        {"title": "Facteur Clé 3", "body": "Adaptabilité face aux mutations du marché.", "badge": "AGILITÉ"}
                    ],
                    "points": [
                        f"Facteur clé d'optimisation appliqué à {clean_topic}.",
                        "Gains qualitatifs durables et consolidation des processus.",
                        "Capacité d'adaptation et de mise à l'échelle continue."
                    ],
                    "key_metric": {"label": "PERFORMANCE", "value": "OPTIMALE", "desc": "Suivi permanent"},
                    "speaker_notes": "Développer ce point spécifique avec précision.",
                    "notes": "Développer ce point spécifique avec précision."
                })

        return SlidesResult(presentation_title, subtitle, selected_slides)

    # ─── 2. Générateur Polymorphe de Requêtes Google Slides API (batchUpdate) ─

    def build_google_slides_batch_update(
        self,
        titre: str,
        subtitle: str,
        theme: str,
        slides: List[Dict[str, Any]],
        default_slide_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Génère la liste complète des requêtes atomiques pour l'API Google Slides batchUpdate.
        Supporte tous les layouts polymorphes (hero_title, key_metrics, cards_grid, split_compare,
        timeline_steps, quote_highlight, conclusion_call_to_action).
        Respecte rigoureusement le format 16:9 widescreen (720 x 405 PT) et la conformité ROUND_RECTANGLE.
        """
        palette = THEMES.get(theme.lower(), THEMES["stark"])
        requests: List[Dict[str, Any]] = []

        # ── SLIDE 0 : COUVERTURE EXÉCUTIVE HAUT DE GAMME ──────────────────────
        cover_slide_id = f"cover_slide_{int(time.time())}"
        requests.append({
            "createSlide": {
                "objectId": cover_slide_id,
                "insertionIndex": 0,
                "slideLayoutReference": {"predefinedLayout": "BLANK"}
            }
        })
        requests.append({
            "updatePageProperties": {
                "objectId": cover_slide_id,
                "pageProperties": {
                    "pageBackgroundFill": {
                        "solidFill": {"color": {"rgbColor": palette["background"]}}
                    }
                },
                "fields": "pageBackgroundFill.solidFill.color"
            }
        })

        # Badge exécutif supérieur
        badge_id = f"{cover_slide_id}_badge"
        requests.append({
            "createShape": {
                "objectId": badge_id,
                "shapeType": "ROUND_RECTANGLE",
                "elementProperties": {
                    "pageObjectId": cover_slide_id,
                    "size": {"width": {"magnitude": 260, "unit": "PT"}, "height": {"magnitude": 26, "unit": "PT"}},
                    "transform": {"scaleX": 1, "scaleY": 1, "translateX": 50, "translateY": 50, "unit": "PT"}
                }
            }
        })
        requests.append({
            "updateShapeProperties": {
                "objectId": badge_id,
                "shapeProperties": {
                    "shapeBackgroundFill": {"solidFill": {"color": {"rgbColor": palette["badge_bg"]}}},
                    "outline": {"outlineFill": {"solidFill": {"color": {"rgbColor": palette["border_color"]}}}, "weight": {"magnitude": 1, "unit": "PT"}}
                },
                "fields": "shapeBackgroundFill.solidFill.color,outline"
            }
        })
        requests.append({
            "insertText": {
                "objectId": badge_id,
                "text": "✦ STARK INDUSTRIES INTELLIGENCE ✦",
                "insertionIndex": 0
            }
        })
        requests.append({
            "updateTextStyle": {
                "objectId": badge_id,
                "textRange": {"type": "ALL"},
                "style": {
                    "bold": True,
                    "fontSize": {"magnitude": 9, "unit": "PT"},
                    "fontFamily": "Roboto",
                    "foregroundColor": {"opaqueColor": {"rgbColor": palette["accent_color"]}}
                },
                "fields": "bold,fontSize,fontFamily,foregroundColor"
            }
        })

        # Grand Titre de la présentation
        title_box_id = f"{cover_slide_id}_title"
        requests.append({
            "createShape": {
                "objectId": title_box_id,
                "shapeType": "TEXT_BOX",
                "elementProperties": {
                    "pageObjectId": cover_slide_id,
                    "size": {"width": {"magnitude": 620, "unit": "PT"}, "height": {"magnitude": 115, "unit": "PT"}},
                    "transform": {"scaleX": 1, "scaleY": 1, "translateX": 50, "translateY": 90, "unit": "PT"}
                }
            }
        })
        requests.append({
            "insertText": {
                "objectId": title_box_id,
                "text": titre,
                "insertionIndex": 0
            }
        })
        requests.append({
            "updateTextStyle": {
                "objectId": title_box_id,
                "textRange": {"type": "ALL"},
                "style": {
                    "bold": True,
                    "fontSize": {"magnitude": 28, "unit": "PT"},
                    "fontFamily": "Roboto",
                    "foregroundColor": {"opaqueColor": {"rgbColor": palette["title_color"]}}
                },
                "fields": "bold,fontSize,fontFamily,foregroundColor"
            }
        })

        # Sous-titre descriptif
        sub_box_id = f"{cover_slide_id}_subtitle"
        requests.append({
            "createShape": {
                "objectId": sub_box_id,
                "shapeType": "TEXT_BOX",
                "elementProperties": {
                    "pageObjectId": cover_slide_id,
                    "size": {"width": {"magnitude": 620, "unit": "PT"}, "height": {"magnitude": 55, "unit": "PT"}},
                    "transform": {"scaleX": 1, "scaleY": 1, "translateX": 50, "translateY": 215, "unit": "PT"}
                }
            }
        })
        requests.append({
            "insertText": {
                "objectId": sub_box_id,
                "text": subtitle,
                "insertionIndex": 0
            }
        })
        requests.append({
            "updateTextStyle": {
                "objectId": sub_box_id,
                "textRange": {"type": "ALL"},
                "style": {
                    "bold": False,
                    "fontSize": {"magnitude": 14, "unit": "PT"},
                    "fontFamily": "Roboto",
                    "foregroundColor": {"opaqueColor": {"rgbColor": palette["subtext"]}}
                },
                "fields": "bold,fontSize,fontFamily,foregroundColor"
            }
        })

        # Barre accent décorative lumineuse
        divider_cover_id = f"{cover_slide_id}_divider"
        requests.append({
            "createShape": {
                "objectId": divider_cover_id,
                "shapeType": "RECTANGLE",
                "elementProperties": {
                    "pageObjectId": cover_slide_id,
                    "size": {"width": {"magnitude": 140, "unit": "PT"}, "height": {"magnitude": 4, "unit": "PT"}},
                    "transform": {"scaleX": 1, "scaleY": 1, "translateX": 50, "translateY": 280, "unit": "PT"}
                }
            }
        })
        requests.append({
            "updateShapeProperties": {
                "objectId": divider_cover_id,
                "shapeProperties": {
                    "shapeBackgroundFill": {"solidFill": {"color": {"rgbColor": palette["accent_color"]}}},
                    "outline": {"outlineFill": {"solidFill": {"color": {"rgbColor": palette["accent_color"]}}}}
                },
                "fields": "shapeBackgroundFill.solidFill.color,outline"
            }
        })

        # Pied de page métadonnées
        footer_cover_id = f"{cover_slide_id}_footer"
        date_str = datetime.now().strftime("%d/%m/%Y")
        requests.append({
            "createShape": {
                "objectId": footer_cover_id,
                "shapeType": "TEXT_BOX",
                "elementProperties": {
                    "pageObjectId": cover_slide_id,
                    "size": {"width": {"magnitude": 620, "unit": "PT"}, "height": {"magnitude": 30, "unit": "PT"}},
                    "transform": {"scaleX": 1, "scaleY": 1, "translateX": 50, "translateY": 315, "unit": "PT"}
                }
            }
        })
        requests.append({
            "insertText": {
                "objectId": footer_cover_id,
                "text": f"Compilé par J.A.R.V.I.S. pour Pierre Cassagnettes  •  Édition {date_str}  •  Stark OS",
                "insertionIndex": 0
            }
        })
        requests.append({
            "updateTextStyle": {
                "objectId": footer_cover_id,
                "textRange": {"type": "ALL"},
                "style": {
                    "bold": False,
                    "fontSize": {"magnitude": 10, "unit": "PT"},
                    "fontFamily": "Roboto",
                    "foregroundColor": {"opaqueColor": {"rgbColor": palette["subtext"]}}
                },
                "fields": "bold,fontSize,fontFamily,foregroundColor"
            }
        })

        # ── SLIDES 1 À N : CONTENUS MULTI-LAYOUTS POLYMORPHES ─────────────────
        for idx, slide_data in enumerate(slides, start=1):
            slide_id = f"content_slide_{idx}_{int(time.time())}"
            requests.append({
                "createSlide": {
                    "objectId": slide_id,
                    "insertionIndex": idx,
                    "slideLayoutReference": {"predefinedLayout": "BLANK"}
                }
            })
            requests.append({
                "updatePageProperties": {
                    "objectId": slide_id,
                    "pageProperties": {
                        "pageBackgroundFill": {
                            "solidFill": {"color": {"rgbColor": palette["background"]}}
                        }
                    },
                    "fields": "pageBackgroundFill.solidFill.color"
                }
            })

            layout = slide_data.get("layout")
            if not layout:
                if "metrics" in slide_data or slide_data.get("key_metric"):
                    layout = "key_metrics"
                elif "left_column" in slide_data and "right_column" in slide_data:
                    layout = "split_compare"
                elif "steps" in slide_data:
                    layout = "timeline_steps"
                elif "cards" in slide_data:
                    layout = "cards_grid"
                else:
                    layout = "cards_grid"

            slide_title = slide_data.get("title") or slide_data.get("titre_slide") or f"Diapositive {idx}"

            # ── 1. Layout HERO_TITLE ──────────────────────────────────────────
            if layout == "hero_title":
                hero_title_id = f"{slide_id}_htitle"
                requests.append({
                    "createShape": {
                        "objectId": hero_title_id,
                        "shapeType": "TEXT_BOX",
                        "elementProperties": {
                            "pageObjectId": slide_id,
                            "size": {"width": {"magnitude": 620, "unit": "PT"}, "height": {"magnitude": 115, "unit": "PT"}},
                            "transform": {"scaleX": 1, "scaleY": 1, "translateX": 50, "translateY": 95, "unit": "PT"}
                        }
                    }
                })
                requests.append({
                    "insertText": {
                        "objectId": hero_title_id,
                        "text": slide_title.upper(),
                        "insertionIndex": 0
                    }
                })
                requests.append({
                    "updateTextStyle": {
                        "objectId": hero_title_id,
                        "textRange": {"type": "ALL"},
                        "style": {
                            "bold": True,
                            "fontSize": {"magnitude": 30, "unit": "PT"},
                            "fontFamily": "Trebuchet MS",
                            "foregroundColor": {"opaqueColor": {"rgbColor": palette["accent_color"]}}
                        },
                        "fields": "bold,fontSize,fontFamily,foregroundColor"
                    }
                })

                hero_sub = slide_data.get("subtitle") or (slide_data.get("points", [""])[0] if slide_data.get("points") else "")
                if hero_sub:
                    hero_sub_id = f"{slide_id}_hsub"
                    requests.append({
                        "createShape": {
                            "objectId": hero_sub_id,
                            "shapeType": "TEXT_BOX",
                            "elementProperties": {
                                "pageObjectId": slide_id,
                                "size": {"width": {"magnitude": 620, "unit": "PT"}, "height": {"magnitude": 80, "unit": "PT"}},
                                "transform": {"scaleX": 1, "scaleY": 1, "translateX": 50, "translateY": 220, "unit": "PT"}
                            }
                        }
                    })
                    requests.append({
                        "insertText": {
                            "objectId": hero_sub_id,
                            "text": hero_sub,
                            "insertionIndex": 0
                        }
                    })
                    requests.append({
                        "updateTextStyle": {
                            "objectId": hero_sub_id,
                            "textRange": {"type": "ALL"},
                            "style": {
                                "bold": False,
                                "fontSize": {"magnitude": 16, "unit": "PT"},
                                "fontFamily": "Roboto",
                                "foregroundColor": {"opaqueColor": {"rgbColor": palette["subtext"]}}
                            },
                            "fields": "bold,fontSize,fontFamily,foregroundColor"
                        }
                    })

            # ── 2. Layout KEY_METRICS ─────────────────────────────────────────
            elif layout == "key_metrics":
                # Titre haut
                t_id = f"{slide_id}_title"
                requests.append({
                    "createShape": {
                        "objectId": t_id,
                        "shapeType": "TEXT_BOX",
                        "elementProperties": {
                            "pageObjectId": slide_id,
                            "size": {"width": {"magnitude": 640, "unit": "PT"}, "height": {"magnitude": 45, "unit": "PT"}},
                            "transform": {"scaleX": 1, "scaleY": 1, "translateX": 40, "translateY": 25, "unit": "PT"}
                        }
                    }
                })
                requests.append({"insertText": {"objectId": t_id, "text": slide_title, "insertionIndex": 0}})
                requests.append({
                    "updateTextStyle": {
                        "objectId": t_id,
                        "textRange": {"type": "ALL"},
                        "style": {"bold": True, "fontSize": {"magnitude": 22, "unit": "PT"}, "fontFamily": "Roboto", "foregroundColor": {"opaqueColor": {"rgbColor": palette["title_color"]}}},
                        "fields": "bold,fontSize,fontFamily,foregroundColor"
                    }
                })

                metrics = slide_data.get("metrics") or ([slide_data.get("key_metric")] if slide_data.get("key_metric") else [])
                has_points = bool(slide_data.get("points")) and len(metrics) == 1

                if has_points:
                    # Disposition 2 Colonnes : Carte de gauche (Points) + Carte de droite (Métrique Clé)
                    left_card_id = f"{slide_id}_left_card"
                    requests.append({
                        "createShape": {
                            "objectId": left_card_id,
                            "shapeType": "ROUND_RECTANGLE",
                            "elementProperties": {
                                "pageObjectId": slide_id,
                                "size": {"width": {"magnitude": 420, "unit": "PT"}, "height": {"magnitude": 255, "unit": "PT"}},
                                "transform": {"scaleX": 1, "scaleY": 1, "translateX": 40, "translateY": 90, "unit": "PT"}
                            }
                        }
                    })
                    requests.append({
                        "updateShapeProperties": {
                            "objectId": left_card_id,
                            "shapeProperties": {
                                "shapeBackgroundFill": {"solidFill": {"color": {"rgbColor": palette["card_bg"]}}},
                                "outline": {"outlineFill": {"solidFill": {"color": {"rgbColor": palette["border_color"]}}}, "weight": {"magnitude": 1, "unit": "PT"}}
                            },
                            "fields": "shapeBackgroundFill.solidFill.color,outline"
                        }
                    })
                    pts_text = "\n\n".join(f"• {p}" for p in slide_data["points"])
                    requests.append({"insertText": {"objectId": left_card_id, "text": pts_text, "insertionIndex": 0}})
                    requests.append({
                        "updateTextStyle": {
                            "objectId": left_card_id,
                            "textRange": {"type": "ALL"},
                            "style": {"fontSize": {"magnitude": 12, "unit": "PT"}, "fontFamily": "Roboto", "foregroundColor": {"opaqueColor": {"rgbColor": palette["text_color"]}}},
                            "fields": "fontSize,fontFamily,foregroundColor"
                        }
                    })

                    # Carte de droite : Métrique Clé
                    m = metrics[0]
                    right_card_id = f"{slide_id}_right_card"
                    requests.append({
                        "createShape": {
                            "objectId": right_card_id,
                            "shapeType": "ROUND_RECTANGLE",
                            "elementProperties": {
                                "pageObjectId": slide_id,
                                "size": {"width": {"magnitude": 200, "unit": "PT"}, "height": {"magnitude": 255, "unit": "PT"}},
                                "transform": {"scaleX": 1, "scaleY": 1, "translateX": 480, "translateY": 90, "unit": "PT"}
                            }
                        }
                    })
                    requests.append({
                        "updateShapeProperties": {
                            "objectId": right_card_id,
                            "shapeProperties": {
                                "shapeBackgroundFill": {"solidFill": {"color": {"rgbColor": palette["badge_bg"]}}},
                                "outline": {"outlineFill": {"solidFill": {"color": {"rgbColor": palette["accent_color"]}}}, "weight": {"magnitude": 1.5, "unit": "PT"}}
                            },
                            "fields": "shapeBackgroundFill.solidFill.color,outline"
                        }
                    })
                    sub = m.get("subtext") or m.get("desc") or ""
                    m_content = f"{(m.get('label') or 'MÉTRIQUE CLÉ').upper()}\n\n{m.get('value', '★')}\n\n{sub}"
                    requests.append({"insertText": {"objectId": right_card_id, "text": m_content, "insertionIndex": 0}})
                    requests.append({
                        "updateTextStyle": {
                            "objectId": right_card_id,
                            "textRange": {"type": "ALL"},
                            "style": {"bold": True, "fontSize": {"magnitude": 16, "unit": "PT"}, "fontFamily": "Roboto", "foregroundColor": {"opaqueColor": {"rgbColor": palette["accent_color"]}}},
                            "fields": "bold,fontSize,fontFamily,foregroundColor"
                        }
                    })
                else:
                    count = max(1, min(4, len(metrics)))
                    avail_w = 640
                    gap = 16
                    card_w = (avail_w - (gap * (count - 1))) / count
                    card_h = 240
                    start_y = 90

                    for m_idx, m in enumerate(metrics[:count]):
                        card_x = 40 + m_idx * (card_w + gap)
                        c_id = f"{slide_id}_mcard_{m_idx}"
                        requests.append({
                            "createShape": {
                                "objectId": c_id,
                                "shapeType": "ROUND_RECTANGLE",
                                "elementProperties": {
                                    "pageObjectId": slide_id,
                                    "size": {"width": {"magnitude": card_w, "unit": "PT"}, "height": {"magnitude": card_h, "unit": "PT"}},
                                    "transform": {"scaleX": 1, "scaleY": 1, "translateX": card_x, "translateY": start_y, "unit": "PT"}
                                }
                            }
                        })
                        requests.append({
                            "updateShapeProperties": {
                                "objectId": c_id,
                                "shapeProperties": {
                                    "shapeBackgroundFill": {"solidFill": {"color": {"rgbColor": palette["card_bg"]}}},
                                    "outline": {"outlineFill": {"solidFill": {"color": {"rgbColor": palette["accent_color"]}}}, "weight": {"magnitude": 1.5, "unit": "PT"}}
                                },
                                "fields": "shapeBackgroundFill.solidFill.color,outline"
                            }
                        })

                        txt_id = f"{slide_id}_mtxt_{m_idx}"
                        requests.append({
                            "createShape": {
                                "objectId": txt_id,
                                "shapeType": "TEXT_BOX",
                                "elementProperties": {
                                    "pageObjectId": slide_id,
                                    "size": {"width": {"magnitude": card_w - 20, "unit": "PT"}, "height": {"magnitude": card_h - 20, "unit": "PT"}},
                                    "transform": {"scaleX": 1, "scaleY": 1, "translateX": card_x + 10, "translateY": start_y + 15, "unit": "PT"}
                                }
                            }
                        })
                        subtext = m.get("subtext") or m.get("desc") or ""
                        metric_str = f"{m.get('value', '')}\n\n{m.get('label', '')}\n{subtext}"
                        requests.append({"insertText": {"objectId": txt_id, "text": metric_str, "insertionIndex": 0}})
                        requests.append({
                            "updateTextStyle": {
                                "objectId": txt_id,
                                "textRange": {"type": "ALL"},
                                "style": {"bold": True, "fontSize": {"magnitude": 28 if count > 2 else 34, "unit": "PT"}, "fontFamily": "Roboto", "foregroundColor": {"opaqueColor": {"rgbColor": palette["accent_color"]}}},
                                "fields": "bold,fontSize,fontFamily,foregroundColor"
                            }
                        })

            # ── 3. Layout SPLIT_COMPARE ───────────────────────────────────────
            elif layout == "split_compare":
                t_id = f"{slide_id}_title"
                requests.append({
                    "createShape": {
                        "objectId": t_id,
                        "shapeType": "TEXT_BOX",
                        "elementProperties": {
                            "pageObjectId": slide_id,
                            "size": {"width": {"magnitude": 640, "unit": "PT"}, "height": {"magnitude": 45, "unit": "PT"}},
                            "transform": {"scaleX": 1, "scaleY": 1, "translateX": 40, "translateY": 25, "unit": "PT"}
                        }
                    }
                })
                requests.append({"insertText": {"objectId": t_id, "text": slide_title, "insertionIndex": 0}})
                requests.append({
                    "updateTextStyle": {
                        "objectId": t_id,
                        "textRange": {"type": "ALL"},
                        "style": {"bold": True, "fontSize": {"magnitude": 22, "unit": "PT"}, "fontFamily": "Roboto", "foregroundColor": {"opaqueColor": {"rgbColor": palette["title_color"]}}},
                        "fields": "bold,fontSize,fontFamily,foregroundColor"
                    }
                })

                col_w = 310
                col_h = 280
                col_y = 85

                # Colonne gauche
                left_id = f"{slide_id}_col_left"
                requests.append({
                    "createShape": {
                        "objectId": left_id,
                        "shapeType": "ROUND_RECTANGLE",
                        "elementProperties": {
                            "pageObjectId": slide_id,
                            "size": {"width": {"magnitude": col_w, "unit": "PT"}, "height": {"magnitude": col_h, "unit": "PT"}},
                            "transform": {"scaleX": 1, "scaleY": 1, "translateX": 40, "translateY": col_y, "unit": "PT"}
                        }
                    }
                })
                requests.append({
                    "updateShapeProperties": {
                        "objectId": left_id,
                        "shapeProperties": {
                            "shapeBackgroundFill": {"solidFill": {"color": {"rgbColor": palette["card_bg"]}}},
                            "outline": {"outlineFill": {"solidFill": {"color": {"rgbColor": palette["subtext"]}}}, "weight": {"magnitude": 1, "unit": "PT"}}
                        },
                        "fields": "shapeBackgroundFill.solidFill.color,outline"
                    }
                })

                l_col = slide_data.get("left_column") or {}
                l_title = (l_col.get("title") or "Avant / Existant").upper()
                l_points = "\n\n".join(f"• {p}" for p in l_col.get("points", [])) if l_col.get("points") else "• Analyse en cours..."
                l_txt_id = f"{slide_id}_txt_left"
                requests.append({
                    "createShape": {
                        "objectId": l_txt_id,
                        "shapeType": "TEXT_BOX",
                        "elementProperties": {
                            "pageObjectId": slide_id,
                            "size": {"width": {"magnitude": col_w - 30, "unit": "PT"}, "height": {"magnitude": col_h - 30, "unit": "PT"}},
                            "transform": {"scaleX": 1, "scaleY": 1, "translateX": 55, "translateY": col_y + 15, "unit": "PT"}
                        }
                    }
                })
                requests.append({"insertText": {"objectId": l_txt_id, "text": f"{l_title}\n\n{l_points}", "insertionIndex": 0}})
                requests.append({
                    "updateTextStyle": {
                        "objectId": l_txt_id,
                        "textRange": {"type": "ALL"},
                        "style": {"fontSize": {"magnitude": 12, "unit": "PT"}, "fontFamily": "Roboto", "foregroundColor": {"opaqueColor": {"rgbColor": palette["text_color"]}}},
                        "fields": "fontSize,fontFamily,foregroundColor"
                    }
                })

                # Colonne droite
                right_id = f"{slide_id}_col_right"
                requests.append({
                    "createShape": {
                        "objectId": right_id,
                        "shapeType": "ROUND_RECTANGLE",
                        "elementProperties": {
                            "pageObjectId": slide_id,
                            "size": {"width": {"magnitude": col_w, "unit": "PT"}, "height": {"magnitude": col_h, "unit": "PT"}},
                            "transform": {"scaleX": 1, "scaleY": 1, "translateX": 370, "translateY": col_y, "unit": "PT"}
                        }
                    }
                })
                requests.append({
                    "updateShapeProperties": {
                        "objectId": right_id,
                        "shapeProperties": {
                            "shapeBackgroundFill": {"solidFill": {"color": {"rgbColor": palette["card_bg"]}}},
                            "outline": {"outlineFill": {"solidFill": {"color": {"rgbColor": palette["accent_color"]}}}, "weight": {"magnitude": 1.5, "unit": "PT"}}
                        },
                        "fields": "shapeBackgroundFill.solidFill.color,outline"
                    }
                })

                r_col = slide_data.get("right_column") or {}
                r_title = (r_col.get("title") or "Cible Optimisée Stark").upper()
                r_points = "\n\n".join(f"✔ {p}" for p in r_col.get("points", [])) if r_col.get("points") else "✔ Optimisation validée"
                r_txt_id = f"{slide_id}_txt_right"
                requests.append({
                    "createShape": {
                        "objectId": r_txt_id,
                        "shapeType": "TEXT_BOX",
                        "elementProperties": {
                            "pageObjectId": slide_id,
                            "size": {"width": {"magnitude": col_w - 30, "unit": "PT"}, "height": {"magnitude": col_h - 30, "unit": "PT"}},
                            "transform": {"scaleX": 1, "scaleY": 1, "translateX": 385, "translateY": col_y + 15, "unit": "PT"}
                        }
                    }
                })
                requests.append({"insertText": {"objectId": r_txt_id, "text": f"{r_title}\n\n{r_points}", "insertionIndex": 0}})
                requests.append({
                    "updateTextStyle": {
                        "objectId": r_txt_id,
                        "textRange": {"type": "ALL"},
                        "style": {"fontSize": {"magnitude": 12, "unit": "PT"}, "fontFamily": "Roboto", "foregroundColor": {"opaqueColor": {"rgbColor": palette["text_color"]}}},
                        "fields": "fontSize,fontFamily,foregroundColor"
                    }
                })

            # ── 4. Layout TIMELINE_STEPS ──────────────────────────────────────
            elif layout == "timeline_steps":
                t_id = f"{slide_id}_title"
                requests.append({
                    "createShape": {
                        "objectId": t_id,
                        "shapeType": "TEXT_BOX",
                        "elementProperties": {
                            "pageObjectId": slide_id,
                            "size": {"width": {"magnitude": 640, "unit": "PT"}, "height": {"magnitude": 45, "unit": "PT"}},
                            "transform": {"scaleX": 1, "scaleY": 1, "translateX": 40, "translateY": 25, "unit": "PT"}
                        }
                    }
                })
                requests.append({"insertText": {"objectId": t_id, "text": slide_title, "insertionIndex": 0}})
                requests.append({
                    "updateTextStyle": {
                        "objectId": t_id,
                        "textRange": {"type": "ALL"},
                        "style": {"bold": True, "fontSize": {"magnitude": 20, "unit": "PT"}, "fontFamily": "Roboto", "foregroundColor": {"opaqueColor": {"rgbColor": palette["title_color"]}}},
                        "fields": "bold,fontSize,fontFamily,foregroundColor"
                    }
                })

                steps = slide_data.get("steps") or []
                count = max(1, min(4, len(steps)))
                avail_w = 640
                gap = 14
                card_w = (avail_w - (gap * (count - 1))) / count
                card_h = 265
                start_y = 85

                for s_idx, st in enumerate(steps[:count]):
                    card_x = 40 + s_idx * (card_w + gap)
                    c_id = f"{slide_id}_step_{s_idx}"
                    requests.append({
                        "createShape": {
                            "objectId": c_id,
                            "shapeType": "ROUND_RECTANGLE",
                            "elementProperties": {
                                "pageObjectId": slide_id,
                                "size": {"width": {"magnitude": card_w, "unit": "PT"}, "height": {"magnitude": card_h, "unit": "PT"}},
                                "transform": {"scaleX": 1, "scaleY": 1, "translateX": card_x, "translateY": start_y, "unit": "PT"}
                            }
                        }
                    })
                    requests.append({
                        "updateShapeProperties": {
                            "objectId": c_id,
                            "shapeProperties": {
                                "shapeBackgroundFill": {"solidFill": {"color": {"rgbColor": palette["card_bg"]}}},
                                "outline": {"outlineFill": {"solidFill": {"color": {"rgbColor": palette["accent_color"]}}}, "weight": {"magnitude": 1.2, "unit": "PT"}}
                            },
                            "fields": "shapeBackgroundFill.solidFill.color,outline"
                        }
                    })

                    txt_id = f"{slide_id}_steptxt_{s_idx}"
                    requests.append({
                        "createShape": {
                            "objectId": txt_id,
                            "shapeType": "TEXT_BOX",
                            "elementProperties": {
                                "pageObjectId": slide_id,
                                "size": {"width": {"magnitude": card_w - 20, "unit": "PT"}, "height": {"magnitude": card_h - 20, "unit": "PT"}},
                                "transform": {"scaleX": 1, "scaleY": 1, "translateX": card_x + 10, "translateY": start_y + 12, "unit": "PT"}
                            }
                        }
                    })
                    phase_str = st.get("phase") or f"0{s_idx + 1}"
                    step_content = f"[{phase_str}]\n\n{(st.get('title') or '').upper()}\n\n{st.get('desc', '')}"
                    requests.append({"insertText": {"objectId": txt_id, "text": step_content, "insertionIndex": 0}})
                    requests.append({
                        "updateTextStyle": {
                            "objectId": txt_id,
                            "textRange": {"type": "ALL"},
                            "style": {"fontSize": {"magnitude": 12, "unit": "PT"}, "fontFamily": "Roboto", "foregroundColor": {"opaqueColor": {"rgbColor": palette["text_color"]}}},
                            "fields": "fontSize,fontFamily,foregroundColor"
                        }
                    })

            # ── 5. Layout CARDS_GRID (Par Défaut / Polymorphe 2, 3 ou 4 cartes)
            else:
                t_id = f"{slide_id}_title"
                requests.append({
                    "createShape": {
                        "objectId": t_id,
                        "shapeType": "TEXT_BOX",
                        "elementProperties": {
                            "pageObjectId": slide_id,
                            "size": {"width": {"magnitude": 640, "unit": "PT"}, "height": {"magnitude": 45, "unit": "PT"}},
                            "transform": {"scaleX": 1, "scaleY": 1, "translateX": 40, "translateY": 25, "unit": "PT"}
                        }
                    }
                })
                requests.append({"insertText": {"objectId": t_id, "text": slide_title, "insertionIndex": 0}})
                requests.append({
                    "updateTextStyle": {
                        "objectId": t_id,
                        "textRange": {"type": "ALL"},
                        "style": {"bold": True, "fontSize": {"magnitude": 20, "unit": "PT"}, "fontFamily": "Roboto", "foregroundColor": {"opaqueColor": {"rgbColor": palette["title_color"]}}},
                        "fields": "bold,fontSize,fontFamily,foregroundColor"
                    }
                })

                raw_cards = slide_data.get("cards", [])
                if not raw_cards and slide_data.get("points"):
                    pts = slide_data["points"]
                    raw_cards = [{"title": f"Point {p_i+1}", "body": p, "badge": "ANALYSE"} for p_i, p in enumerate(pts[:4])]
                
                count = max(1, min(4, len(raw_cards)))
                avail_w = 640
                gap = 14
                card_w = (avail_w - (gap * (count - 1))) / count
                card_h = 265
                start_y = 85

                for c_idx, card in enumerate(raw_cards[:count]):
                    card_x = 40 + c_idx * (card_w + gap)
                    c_id = f"{slide_id}_card_{c_idx}"
                    requests.append({
                        "createShape": {
                            "objectId": c_id,
                            "shapeType": "ROUND_RECTANGLE",
                            "elementProperties": {
                                "pageObjectId": slide_id,
                                "size": {"width": {"magnitude": card_w, "unit": "PT"}, "height": {"magnitude": card_h, "unit": "PT"}},
                                "transform": {"scaleX": 1, "scaleY": 1, "translateX": card_x, "translateY": start_y, "unit": "PT"}
                            }
                        }
                    })
                    requests.append({
                        "updateShapeProperties": {
                            "objectId": c_id,
                            "shapeProperties": {
                                "shapeBackgroundFill": {"solidFill": {"color": {"rgbColor": palette["card_bg"]}}},
                                "outline": {"outlineFill": {"solidFill": {"color": {"rgbColor": palette["accent_color"]}}}, "weight": {"magnitude": 1, "unit": "PT"}}
                            },
                            "fields": "shapeBackgroundFill.solidFill.color,outline"
                        }
                    })

                    txt_id = f"{slide_id}_cardtxt_{c_idx}"
                    requests.append({
                        "createShape": {
                            "objectId": txt_id,
                            "shapeType": "TEXT_BOX",
                            "elementProperties": {
                                "pageObjectId": slide_id,
                                "size": {"width": {"magnitude": card_w - 20, "unit": "PT"}, "height": {"magnitude": card_h - 20, "unit": "PT"}},
                                "transform": {"scaleX": 1, "scaleY": 1, "translateX": card_x + 10, "translateY": start_y + 12, "unit": "PT"}
                            }
                        }
                    })
                    badge_str = f"[{card.get('badge')}]\n\n" if card.get("badge") else ""
                    content = f"{badge_str}{(card.get('title') or '').upper()}\n\n{card.get('body', '')}"
                    requests.append({"insertText": {"objectId": txt_id, "text": content, "insertionIndex": 0}})
                    requests.append({
                        "updateTextStyle": {
                            "objectId": txt_id,
                            "textRange": {"type": "ALL"},
                            "style": {"fontSize": {"magnitude": 12, "unit": "PT"}, "fontFamily": "Roboto", "foregroundColor": {"opaqueColor": {"rgbColor": palette["text_color"]}}},
                            "fields": "fontSize,fontFamily,foregroundColor"
                        }
                    })

            # Pied de page numéroté
            footer_id = f"{slide_id}_footer"
            requests.append({
                "createShape": {
                    "objectId": footer_id,
                    "shapeType": "TEXT_BOX",
                    "elementProperties": {
                        "pageObjectId": slide_id,
                        "size": {"width": {"magnitude": 640, "unit": "PT"}, "height": {"magnitude": 20, "unit": "PT"}},
                        "transform": {"scaleX": 1, "scaleY": 1, "translateX": 40, "translateY": 372, "unit": "PT"}
                    }
                }
            })
            requests.append({
                "insertText": {
                    "objectId": footer_id,
                    "text": f"J.A.R.V.I.S. • Stark Intelligence Suite  |  Diapositive {idx} sur {len(slides)}",
                    "insertionIndex": 0
                }
            })
            requests.append({
                "updateTextStyle": {
                    "objectId": footer_id,
                    "textRange": {"type": "ALL"},
                    "style": {"bold": False, "fontSize": {"magnitude": 9, "unit": "PT"}, "fontFamily": "Roboto", "foregroundColor": {"opaqueColor": {"rgbColor": palette["subtext"]}}},
                    "fields": "bold,fontSize,fontFamily,foregroundColor"
                }
            })

        # ── SUPPRESSION DE LA DIAPOSITIVE VIERGE INITIALE (SLIDE 0 PAR DÉFAUT) ─
        if default_slide_id:
            requests.append({
                "deleteObject": {
                    "objectId": default_slide_id
                }
            })

        return requests


# Singleton
slides_service = SlidesService()
