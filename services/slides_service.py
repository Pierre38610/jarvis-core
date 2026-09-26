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

    async def generate_deep_research_slides(
        self,
        sujet: str,
        titre: Optional[str] = None,
        theme: str = "stark"
    ) -> Tuple[str, str, List[Dict[str, Any]]]:
        """Élabore un plan rigoureux, effectue la synthèse de données vérifiées et produit
        la structure complète des diapositives via Antigravity CLI.
        """
        clean_topic = (sujet or titre or "Présentation").strip()
        effective_theme = theme or "stark"
        presentation_title = titre or f"Dossier Stratégique : {clean_topic}"
        subtitle = f"Analyse approfondie, enjeux clés et perspectives d'avenir sur {clean_topic}"

        instruction = (
            f"Tu es un expert consultant en stratégie de chez Stark Industries. "
            f"Fais une recherche web approfondie (cherche des chiffres récents, des sources vérifiées) "
            f"sur le sujet suivant : '{clean_topic}'. "
            f"Génère un plan de présentation percutant et professionnel comprenant 6 à 10 diapositives. "
            f"Tu DOIS ABSOLUMENT renvoyer le résultat STRICTEMENT sous la forme d'un objet JSON valide contenant "
            f"une liste de slides. "
            f"Le format JSON attendu est : "
            f"[\n"
            f"  {{\n"
            f"    \"titre_slide\": \"Titre de la diapositive\",\n"
            f"    \"category\": \"CATEGORIE\",\n"
            f"    \"points\": [\"Point 1\", \"Point 2\", \"Point 3\"],\n"
            f"    \"key_metric\": {{\n"
            f"      \"label\": \"LABEL\",\n"
            f"      \"value\": \"VALEUR\",\n"
            f"      \"desc\": \"Description\"\n"
            f"    }},\n"
            f"    \"notes\": \"Notes orateur\"\n"
            f"  }}\n"
            f"]\n"
            f"N'ajoute aucun texte avant ou après le JSON. Rends uniquement le JSON brut (pas de balises markdown ```json)."
        )

        from services.reasoning_service import run_deep_research_cli
        import json
        import re
        
        async def on_progress(data):
            # Pourrait être utilisé pour du log ou maj websocket si besoin
            pass
            
        res = await run_deep_research_cli(instruction, model="gemini-3.1-pro-high", on_progress=on_progress)
        
        # Si quota dépassé ou erreur, on renvoie une structure de secours
        if res.get("status") in ["error", "requires_user_confirmation", "cancelled"]:
            return presentation_title, subtitle, [{
                "titre_slide": "1. Erreur de Génération",
                "category": "ERREUR",
                "points": [f"Statut: {res.get('status')}", res.get('reason', res.get('summary', ''))],
                "key_metric": {"label": "STATUT", "value": "ÉCHEC", "desc": "Génération interrompue"},
                "notes": "La génération a été interrompue ou le quota est atteint."
            }]
            
        raw_output = res.get("summary", "")
        # Extraction du JSON
        json_match = re.search(r'\[.*\]', raw_output, re.DOTALL)
        slides = []
        if json_match:
            try:
                slides = json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
                
        if not slides:
            # Fallback basique en cas d'échec de parsing JSON
            slides = [
                {
                    "titre_slide": f"1. Introduction à {clean_topic}",
                    "category": "SYNTHÈSE",
                    "points": ["Analyse générée mais format inattendu.", "Veuillez consulter les logs pour plus de détails."],
                    "key_metric": {"label": "INFO", "value": "N/A", "desc": "Format JSON invalide"},
                    "notes": ""
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
