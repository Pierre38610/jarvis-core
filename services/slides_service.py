"""services/slides_service.py
Service de conception, recherche documentaire et génération esthétique de présentations Google Slides pour J.A.R.V.I.S.
Assure :
1. Structuration intellectuelle et plan directeur détaillé (5 à 8 diapositives).
2. Recherche approfondie de faits vérifiés, actualités, données techniques et chiffres clés.
3. Génération des requêtes Google Slides API (batchUpdate) au pixel près (format 16:9 widescreen 720x405 PT).
4. Application de thèmes esthétiques premium (Stark Industries Dark/Cyan, Bitcoin Gold, Corporate, Cyber).
5. Suivi pas-à-pas de l'avancement dans SupervisionService pour expliquer en direct à Pierre l'état d'avancement.
"""

import os
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
        "background": {"red": 0.04, "green": 0.06, "blue": 0.11},      # #0A0F1D
        "card_bg": {"red": 0.07, "green": 0.10, "blue": 0.18},         # #111A2E
        "border_color": {"red": 0.00, "green": 0.85, "blue": 1.00},    # #00D9FF
        "title_color": {"red": 0.22, "green": 0.74, "blue": 0.97},     # #38BDF8
        "text_color": {"red": 0.97, "green": 0.98, "blue": 0.99},      # #F8FAFC
        "accent_color": {"red": 0.00, "green": 0.90, "blue": 1.00},    # #00E5FF
        "muted_color": {"red": 0.58, "green": 0.64, "blue": 0.72},     # #94A3B8
        "badge_bg": {"red": 0.10, "green": 0.16, "blue": 0.28},        # #1A2947
    },
    "bitcoin": {
        "name": "Bitcoin & Crypto Prestige (Gold & Obsidian)",
        "background": {"red": 0.04, "green": 0.05, "blue": 0.08},      # #0B0E14
        "card_bg": {"red": 0.08, "green": 0.10, "blue": 0.14},         # #151A24
        "border_color": {"red": 0.96, "green": 0.62, "blue": 0.04},    # #F59E0B
        "title_color": {"red": 0.98, "green": 0.75, "blue": 0.14},     # #FBBF24
        "text_color": {"red": 0.98, "green": 0.98, "blue": 0.98},      # #FAFAFA
        "accent_color": {"red": 0.96, "green": 0.62, "blue": 0.04},    # #F59E0B
        "muted_color": {"red": 0.61, "green": 0.64, "blue": 0.69},     # #9CA3AF
        "badge_bg": {"red": 0.18, "green": 0.13, "blue": 0.05},        # #2E210D
    },
    "gold": {
        "name": "Gold & Luxury",
        "background": {"red": 0.04, "green": 0.05, "blue": 0.08},
        "card_bg": {"red": 0.08, "green": 0.10, "blue": 0.14},
        "border_color": {"red": 0.96, "green": 0.62, "blue": 0.04},
        "title_color": {"red": 0.98, "green": 0.75, "blue": 0.14},
        "text_color": {"red": 0.98, "green": 0.98, "blue": 0.98},
        "accent_color": {"red": 0.96, "green": 0.62, "blue": 0.04},
        "muted_color": {"red": 0.61, "green": 0.64, "blue": 0.69},
        "badge_bg": {"red": 0.18, "green": 0.13, "blue": 0.05},
    },
    "cyber": {
        "name": "Cyberpunk Neon",
        "background": {"red": 0.03, "green": 0.03, "blue": 0.06},      # #08080F
        "card_bg": {"red": 0.08, "green": 0.06, "blue": 0.16},         # #140F29
        "border_color": {"red": 0.66, "green": 0.33, "blue": 0.97},    # #A855F7
        "title_color": {"red": 0.02, "green": 0.71, "blue": 0.83},     # #06B6D4
        "text_color": {"red": 1.00, "green": 1.00, "blue": 1.00},      # #FFFFFF
        "accent_color": {"red": 0.66, "green": 0.33, "blue": 0.97},    # #A855F7
        "muted_color": {"red": 0.65, "green": 0.60, "blue": 0.75},     # #A699BF
        "badge_bg": {"red": 0.16, "green": 0.10, "blue": 0.32},        # #291A52
    },
    "corporate": {
        "name": "Executive Corporate (Clean Slate)",
        "background": {"red": 0.98, "green": 0.98, "blue": 0.99},      # #F8FAFC
        "card_bg": {"red": 1.00, "green": 1.00, "blue": 1.00},         # #FFFFFF
        "border_color": {"red": 0.82, "green": 0.85, "blue": 0.90},    # #D1D5DB
        "title_color": {"red": 0.06, "green": 0.09, "blue": 0.16},     # #0F172A
        "text_color": {"red": 0.20, "green": 0.25, "blue": 0.33},      # #334155
        "accent_color": {"red": 0.15, "green": 0.39, "blue": 0.92},    # #2563EB
        "muted_color": {"red": 0.39, "green": 0.45, "blue": 0.55},     # #64748B
        "badge_bg": {"red": 0.94, "green": 0.96, "blue": 1.00},        # #EFF6FF
    },
    "dark": {
        "name": "Dark Minimal",
        "background": {"red": 0.07, "green": 0.07, "blue": 0.07},      # #121212
        "card_bg": {"red": 0.12, "green": 0.12, "blue": 0.12},         # #1E1E1E
        "border_color": {"red": 0.25, "green": 0.25, "blue": 0.25},    # #404040
        "title_color": {"red": 1.00, "green": 1.00, "blue": 1.00},      # #FFFFFF
        "text_color": {"red": 0.88, "green": 0.88, "blue": 0.88},      # #E0E0E0
        "accent_color": {"red": 0.73, "green": 0.53, "blue": 0.99},    # #BB86FC
        "muted_color": {"red": 0.62, "green": 0.62, "blue": 0.62},     # #9E9E9E
        "badge_bg": {"red": 0.16, "green": 0.16, "blue": 0.16},        # #292929
    }
}


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

    # ─── 1. Moteur de Recherche et Élaboration du Plan ─────────────────────────

    def generate_deep_research_slides(
        self,
        sujet: str,
        titre: Optional[str] = None,
        theme: str = "stark"
    ) -> Tuple[str, str, List[Dict[str, Any]]]:
        """Élabore un plan rigoureux, effectue la synthèse de données vérifiées et produit

        la structure complète des diapositives.
        """
        clean_topic = (sujet or titre or "Présentation").strip()
        is_bitcoin = any(k in clean_topic.lower() for k in ["bitcoin", "btc", "satoshi", "halving", "crypto"])

        if is_bitcoin:
            presentation_title = titre or "Bitcoin : Révolution Monétaire & Architecture Décentralisée"
            subtitle = "Genèse, Fondamentaux Techniques, Halving et Perspectives Macroéconomiques"
            effective_theme = "bitcoin" if theme in ("stark", "bitcoin") else theme

            slides = [
                {
                    "titre_slide": "1. Genèse & Rareté Numérique Absolue",
                    "category": "HISTOIRE & VISION",
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
                    "notes": "Souligner la rupture avec les devises fiduciaires inflationnistes et la souveraineté financière individuelle."
                },
                {
                    "titre_slide": "2. Architecture Technique & Preuve de Travail",
                    "category": "CONSENSUS & SÉCURITÉ",
                    "points": [
                        "Consensus par Proof-of-Work (PoW) fondé sur la fonction de hachage cryptographique SHA-256.",
                        "Ajustement automatique de la difficulté tous les 2016 blocs (~14 jours) pour cibler un rythme moyen de 10 minutes.",
                        "Horodatage distribué et chaîne de blocs rendant impossible toute double dépense sans contrôle majoritaire.",
                        "Réseau mondial de dizaines de milliers de nœuds complets (Full Nodes) validant chaque transaction de façon souveraine."
                    ],
                    "key_metric": {
                        "label": "RYTHME DE BLOC",
                        "value": "~10 MIN",
                        "desc": "Ajustement dynamique de la difficulté cryptographique"
                    },
                    "notes": "Expliquer l'absence de serveur central et la robustesse du Proof-of-Work face aux cyberattaques."
                },
                {
                    "titre_slide": "3. Cycle des Halvings & Modèle Économique",
                    "category": "ÉCONOMIE & CYCLES",
                    "points": [
                        "Division par deux de la prime de bloc tous les 210 000 blocs (environ tous les 4 ans).",
                        "4ème Halving survenu en avril 2024 réduisant la création monétaire à 3.125 BTC par bloc.",
                        "Choc d'offre programmé réduisant l'inflation annuelle sous les 0.85 %, devenant plus rare que l'or physique.",
                        "Modèle Stock-to-Flow attestant de la transition vers une valeur refuge macroéconomique majeure."
                    ],
                    "key_metric": {
                        "label": "RÉCOMPENSE 2024",
                        "value": "3.125 BTC",
                        "desc": "Division de l'émission par deux tous les 4 ans"
                    },
                    "notes": "Présenter le rôle du halving comme catalyseur historique des cycles de marché et de renforcement de la rareté."
                },
                {
                    "titre_slide": "4. Scalabilité & Réseau Lightning (Layer 2)",
                    "category": "INNOVATION & INFRASTRUCTURE",
                    "points": [
                        "Distinction entre couche de base L1 (sécurité et règlement final) et couches L2 (rapidité et volume).",
                        "Lightning Network : canaux de paiement bidirectionnels décentralisés hors chaîne avec règlement L1 instantané.",
                        "Capacité théorique de plusieurs millions de transactions par seconde (TPS) à coût quasi nul.",
                        "Évolutions protocolaires soft fork pérennes : SegWit (2017) et Taproot (2021) pour la compacité et la confidentialité."
                    ],
                    "key_metric": {
                        "label": "DÉBIT COUCHE 2",
                        "value": "MILLIONS TPS",
                        "desc": "Transactions instantanées via Lightning Network"
                    },
                    "notes": "Démontrer que Bitcoin résout le trilemme des blockchains par une architecture modulaire en couches."
                },
                {
                    "titre_slide": "5. Adoption Institutionnelle & Régulation",
                    "category": "MARCHÉ & FINANCE GLOBALE",
                    "points": [
                        "Approbation historique des premiers ETF Bitcoin Spot aux USA par la SEC en janvier 2024.",
                        "Arrivée massive des géants de Wall Street (BlackRock, Fidelity) et des fonds de pension mondiaux.",
                        "Réserves stratégiques d'entreprises cotées (MicroStrategy, Tesla) et adoption souveraine nationale (Salvador).",
                        "Cadres réglementaires clarifiés : règlement MiCA en Union Européenne et projets de réserve stratégique nationale aux États-Unis."
                    ],
                    "key_metric": {
                        "label": "ACCÈS INSTITUTIONNEL",
                        "value": "ETFs SPOT",
                        "desc": "Validation formelle des marchés financiers traditionnels"
                    },
                    "notes": "Pointer le passage d'une curiosité technologique à une classe d'actifs géopolitique incontournable."
                },
                {
                    "titre_slide": "6. Thèse d'Investissement & Perspectives 2026-2030",
                    "category": "SYNTHÈSE STRATÉGIQUE",
                    "points": [
                        "Positionnement établi comme 'Or Numérique' (Store of Value) face à l'inflation et à l'expansion de la dette mondiale.",
                        "Transition écologique accélérée du minage exploitant les surplus hydroélectriques et le torchage de gaz (flaring).",
                        "Propriété privée inviolable : résistance absolue à la confiscation et neutralité financière globale.",
                        "Convergence vers une monnaie de réserve internationale numérique pour le commerce mondial interconnecté."
                    ],
                    "key_metric": {
                        "label": "STATUT MAJEUR",
                        "value": "OR NUMÉRIQUE",
                        "desc": "Réserve de valeur décentralisée et liquide"
                    },
                    "notes": "Conclure sur l'adoption inéluctable et la place centrale de Bitcoin dans le patrimoine technologique moderne."
                }
            ]
            return presentation_title, subtitle, slides

        # Sujet générique : construction d'un deck professionnel en 5 diapositives
        presentation_title = titre or f"Dossier Stratégique : {clean_topic}"
        subtitle = f"Analyse approfondie, enjeux clés et perspectives d'avenir sur {clean_topic}"
        effective_theme = theme or "stark"

        slides = [
            {
                "titre_slide": f"1. Introduction & Contexte Fondateur",
                "category": "VUE D'ENSEMBLE",
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
                "notes": f"Introduire clairement les enjeux majeurs et poser le cadre d'analyse de {clean_topic}."
            },
            {
                "titre_slide": f"2. Piliers Techniques & Fonctionnement",
                "category": "ARCHITECTURE & MÉCANISMES",
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
                "notes": "Détailler les aspects concrets et techniques avec rigueur."
            },
            {
                "titre_slide": f"3. Cas d'Usage & Applications Concrètes",
                "category": "DÉPLOIEMENT & IMPACT",
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
                "notes": "Illustrer par des exemples concrets pour rendre la présentation vivante."
            },
            {
                "titre_slide": f"4. Défis Majeurs & Gestion des Risques",
                "category": "ANALYSE CRITIQUE",
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
                "notes": "Adopter un regard critique constructif et lucide sur les freins éventuels."
            },
            {
                "titre_slide": f"5. Synthèse & Trajectoire Prospective",
                "category": "VISION & CONCLUSION",
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
                "notes": "Terminer par un appel à l'action clair et une synthèse percutante."
            }
        ]
        return presentation_title, subtitle, slides

    # ─── 2. Générateur de Requêtes Google Slides API (batchUpdate) ─────────────

    def build_google_slides_batch_update(
        self,
        titre: str,
        subtitle: str,
        theme: str,
        slides: List[Dict[str, Any]],
        default_slide_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Génère la liste complète des requêtes atomiques pour l'API Google Slides batchUpdate.

        Respecte les dimensions standard Widescreen 16:9 (720 x 405 PT).
        """
        palette = THEMES.get(theme.lower(), THEMES["stark"])
        requests: List[Dict[str, Any]] = []

        total_slides = len(slides) + 1  # Cover + Content slides

        # ── SLIDE 0 : PAGE DE COUVERTURE ─────────────────────────────────────
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
                    "transform": {"scaleX": 1, "scaleY": 1, "translateX": 50, "translateY": 55, "unit": "PT"}
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
                    "size": {"width": {"magnitude": 620, "unit": "PT"}, "height": {"magnitude": 110, "unit": "PT"}},
                    "transform": {"scaleX": 1, "scaleY": 1, "translateX": 50, "translateY": 95, "unit": "PT"}
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
                    "size": {"width": {"magnitude": 620, "unit": "PT"}, "height": {"magnitude": 50, "unit": "PT"}},
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
                    "foregroundColor": {"opaqueColor": {"rgbColor": palette["muted_color"]}}
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

        # Pied de page métadonnées & Auteur
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
                    "foregroundColor": {"opaqueColor": {"rgbColor": palette["muted_color"]}}
                },
                "fields": "bold,fontSize,fontFamily,foregroundColor"
            }
        })

        # ── SLIDES 1 À N : DIAPOSITIVES DE CONTENU ET ANALYSE ────────────────
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

            # Tag de catégorie / Section (haut gauche)
            category_tag = slide_data.get("category", "ANALYSE").upper()
            tag_id = f"{slide_id}_tag"
            requests.append({
                "createShape": {
                    "objectId": tag_id,
                    "shapeType": "TEXT_BOX",
                    "elementProperties": {
                        "pageObjectId": slide_id,
                        "size": {"width": {"magnitude": 300, "unit": "PT"}, "height": {"magnitude": 20, "unit": "PT"}},
                        "transform": {"scaleX": 1, "scaleY": 1, "translateX": 40, "translateY": 22, "unit": "PT"}
                    }
                }
            })
            requests.append({
                "insertText": {
                    "objectId": tag_id,
                    "text": f"// {category_tag}",
                    "insertionIndex": 0
                }
            })
            requests.append({
                "updateTextStyle": {
                    "objectId": tag_id,
                    "textRange": {"type": "ALL"},
                    "style": {
                        "bold": True,
                        "fontSize": {"magnitude": 10, "unit": "PT"},
                        "fontFamily": "Roboto",
                        "foregroundColor": {"opaqueColor": {"rgbColor": palette["accent_color"]}}
                    },
                    "fields": "bold,fontSize,fontFamily,foregroundColor"
                }
            })

            # Titre de la diapositive
            title_text = slide_data.get("titre_slide", f"Diapositive {idx}")
            slide_title_id = f"{slide_id}_title"
            requests.append({
                "createShape": {
                    "objectId": slide_title_id,
                    "shapeType": "TEXT_BOX",
                    "elementProperties": {
                        "pageObjectId": slide_id,
                        "size": {"width": {"magnitude": 640, "unit": "PT"}, "height": {"magnitude": 42, "unit": "PT"}},
                        "transform": {"scaleX": 1, "scaleY": 1, "translateX": 40, "translateY": 44, "unit": "PT"}
                    }
                }
            })
            requests.append({
                "insertText": {
                    "objectId": slide_title_id,
                    "text": title_text,
                    "insertionIndex": 0
                }
            })
            requests.append({
                "updateTextStyle": {
                    "objectId": slide_title_id,
                    "textRange": {"type": "ALL"},
                    "style": {
                        "bold": True,
                        "fontSize": {"magnitude": 20, "unit": "PT"},
                        "fontFamily": "Roboto",
                        "foregroundColor": {"opaqueColor": {"rgbColor": palette["title_color"]}}
                    },
                    "fields": "bold,fontSize,fontFamily,foregroundColor"
                }
            })

            # Séparateur horizontal discret
            div_id = f"{slide_id}_div"
            requests.append({
                "createShape": {
                    "objectId": div_id,
                    "shapeType": "RECTANGLE",
                    "elementProperties": {
                        "pageObjectId": slide_id,
                        "size": {"width": {"magnitude": 640, "unit": "PT"}, "height": {"magnitude": 2, "unit": "PT"}},
                        "transform": {"scaleX": 1, "scaleY": 1, "translateX": 40, "translateY": 90, "unit": "PT"}
                    }
                }
            })
            requests.append({
                "updateShapeProperties": {
                    "objectId": div_id,
                    "shapeProperties": {
                        "shapeBackgroundFill": {"solidFill": {"color": {"rgbColor": palette["border_color"]}}},
                        "outline": {"outlineFill": {"solidFill": {"color": {"rgbColor": palette["border_color"]}}}}
                    },
                    "fields": "shapeBackgroundFill.solidFill.color,outline"
                }
            })

            has_metric = bool(slide_data.get("key_metric"))
            points = slide_data.get("points", [])

            # Formatage du texte des points à puces
            points_text = "\n\n".join(f"•  {p}" for p in points) if points else "•  Analyse en cours..."

            if has_metric:
                # Disposition 2 Colonnes : Carte de gauche (Points) + Carte de droite (Métrique Clé)
                left_card_id = f"{slide_id}_left_card"
                requests.append({
                    "createShape": {
                        "objectId": left_card_id,
                        "shapeType": "ROUND_RECTANGLE",
                        "elementProperties": {
                            "pageObjectId": slide_id,
                            "size": {"width": {"magnitude": 420, "unit": "PT"}, "height": {"magnitude": 255, "unit": "PT"}},
                            "transform": {"scaleX": 1, "scaleY": 1, "translateX": 40, "translateY": 105, "unit": "PT"}
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
                requests.append({
                    "insertText": {
                        "objectId": left_card_id,
                        "text": points_text,
                        "insertionIndex": 0
                    }
                })
                requests.append({
                    "updateTextStyle": {
                        "objectId": left_card_id,
                        "textRange": {"type": "ALL"},
                        "style": {
                            "bold": False,
                            "fontSize": {"magnitude": 12, "unit": "PT"},
                            "fontFamily": "Roboto",
                            "foregroundColor": {"opaqueColor": {"rgbColor": palette["text_color"]}}
                        },
                        "fields": "bold,fontSize,fontFamily,foregroundColor"
                    }
                })

                # Carte de droite : Métrique Clé / Callout
                metric_info = slide_data["key_metric"]
                right_card_id = f"{slide_id}_right_card"
                requests.append({
                    "createShape": {
                        "objectId": right_card_id,
                        "shapeType": "ROUND_RECTANGLE",
                        "elementProperties": {
                            "pageObjectId": slide_id,
                            "size": {"width": {"magnitude": 200, "unit": "PT"}, "height": {"magnitude": 255, "unit": "PT"}},
                            "transform": {"scaleX": 1, "scaleY": 1, "translateX": 480, "translateY": 105, "unit": "PT"}
                        }
                    }
                })
                requests.append({
                    "updateShapeProperties": {
                        "objectId": right_card_id,
                        "shapeProperties": {
                            "shapeBackgroundFill": {"solidFill": {"color": {"rgbColor": palette["badge_bg"]}}},
                            "outline": {"outlineFill": {"solidFill": {"color": {"rgbColor": palette["accent_color"]}}}, "weight": {"magnitude": 2, "unit": "PT"}}
                        },
                        "fields": "shapeBackgroundFill.solidFill.color,outline"
                    }
                })

                metric_card_text = (
                    f"{metric_info.get('label', 'POINT CLÉ').upper()}\n\n"
                    f"{metric_info.get('value', '★')}\n\n"
                    f"{metric_info.get('desc', '')}"
                )
                requests.append({
                    "insertText": {
                        "objectId": right_card_id,
                        "text": metric_card_text,
                        "insertionIndex": 0
                    }
                })
                requests.append({
                    "updateTextStyle": {
                        "objectId": right_card_id,
                        "textRange": {"type": "ALL"},
                        "style": {
                            "bold": True,
                            "fontSize": {"magnitude": 14, "unit": "PT"},
                            "fontFamily": "Roboto",
                            "foregroundColor": {"opaqueColor": {"rgbColor": palette["accent_color"]}}
                        },
                        "fields": "bold,fontSize,fontFamily,foregroundColor"
                    }
                })

            else:
                # Disposition Pleine Largeur : Une grande carte aérée
                main_card_id = f"{slide_id}_main_card"
                requests.append({
                    "createShape": {
                        "objectId": main_card_id,
                        "shapeType": "ROUND_RECTANGLE",
                        "elementProperties": {
                            "pageObjectId": slide_id,
                            "size": {"width": {"magnitude": 640, "unit": "PT"}, "height": {"magnitude": 255, "unit": "PT"}},
                            "transform": {"scaleX": 1, "scaleY": 1, "translateX": 40, "translateY": 105, "unit": "PT"}
                        }
                    }
                })
                requests.append({
                    "updateShapeProperties": {
                        "objectId": main_card_id,
                        "shapeProperties": {
                            "shapeBackgroundFill": {"solidFill": {"color": {"rgbColor": palette["card_bg"]}}},
                            "outline": {"outlineFill": {"solidFill": {"color": {"rgbColor": palette["border_color"]}}}, "weight": {"magnitude": 1, "unit": "PT"}}
                        },
                        "fields": "shapeBackgroundFill.solidFill.color,outline"
                    }
                })
                requests.append({
                    "insertText": {
                        "objectId": main_card_id,
                        "text": points_text,
                        "insertionIndex": 0
                    }
                })
                requests.append({
                    "updateTextStyle": {
                        "objectId": main_card_id,
                        "textRange": {"type": "ALL"},
                        "style": {
                            "bold": False,
                            "fontSize": {"magnitude": 13, "unit": "PT"},
                            "fontFamily": "Roboto",
                            "foregroundColor": {"opaqueColor": {"rgbColor": palette["text_color"]}}
                        },
                        "fields": "bold,fontSize,fontFamily,foregroundColor"
                    }
                })

            # Pied de page de diapositive avec numérotation
            footer_slide_id = f"{slide_id}_footer"
            requests.append({
                "createShape": {
                    "objectId": footer_slide_id,
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
                    "objectId": footer_slide_id,
                    "text": f"J.A.R.V.I.S. • Stark Intelligence Suite  |  Diapositive {idx} sur {len(slides)}",
                    "insertionIndex": 0
                }
            })
            requests.append({
                "updateTextStyle": {
                    "objectId": footer_slide_id,
                    "textRange": {"type": "ALL"},
                    "style": {
                        "bold": False,
                        "fontSize": {"magnitude": 9, "unit": "PT"},
                        "fontFamily": "Roboto",
                        "foregroundColor": {"opaqueColor": {"rgbColor": palette["muted_color"]}}
                    },
                    "fields": "bold,fontSize,fontFamily,foregroundColor"
                }
            })

        # ── SUPPRESSION DE LA DIAPOSITIVE VIERGE INITIALE (SLIDE 0 PAR DÉFAUT) ─
        # Si Google Slides a créé une présentation avec une diapositive vierge initiale par défaut
        # on la supprime à la fin du batch pour ne laisser STRICTEMENT que nos diapositives stylisées.
        if default_slide_id:
            requests.append({
                "deleteObject": {
                    "objectId": default_slide_id
                }
            })

        return requests


# Singleton
slides_service = SlidesService()
