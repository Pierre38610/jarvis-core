"""tests/unit/test_slides_service.py
Tests unitaires pour services.slides_service et l'ingénierie des présentations Google Slides.
Vérifie la génération du plan expert, la synthèse documentaire, et la structure des requêtes Google Slides API (batchUpdate).
"""

import pytest
from services.slides_service import slides_service, THEMES
from services.automation import build_slides_payload


class TestSlidesServiceResearch:
    """Tests du moteur d'élaboration de plan et de recherche approfondie."""

    def test_generate_deep_research_bitcoin(self):
        """Vérifie la génération d'un deck complet et documenté sur le Bitcoin."""
        titre, sub, slides = slides_service.generate_deep_research_slides(
            sujet="Bitcoin",
            titre="Présentation complète sur le Bitcoin",
            theme="stark"
        )

        assert "Bitcoin" in titre
        assert len(slides) == 6  # 6 diapositives thématiques complètes
        assert sub != ""

        # Vérification des contenus clés vérifiés
        all_text = " ".join(" ".join(s["points"]) for s in slides)
        assert "Satoshi Nakamoto" in all_text
        assert "21 millions" in all_text
        assert "Proof-of-Work" in all_text or "SHA-256" in all_text
        assert "Halving" in all_text or "2024" in all_text
        assert "Lightning Network" in all_text or "Layer 2" in all_text
        assert "ETF" in all_text or "Wall Street" in all_text

        # Vérification des métriques et notes d'orateur sur chaque slide
        for s in slides:
            assert "titre_slide" in s
            assert "category" in s
            assert len(s["points"]) >= 3
            assert "key_metric" in s
            assert "label" in s["key_metric"]
            assert "value" in s["key_metric"]
            assert "notes" in s

    def test_generate_deep_research_generic_topic(self):
        """Vérifie la génération d'un dossier stratégique sur un sujet arbitraire."""
        titre, sub, slides = slides_service.generate_deep_research_slides(
            sujet="Intelligence Artificielle Générative",
            theme="corporate"
        )

        assert "Intelligence Artificielle Générative" in titre
        assert len(slides) == 5
        for s in slides:
            assert len(s["points"]) >= 3
            assert "key_metric" in s


class TestGoogleSlidesBatchRequests:
    """Tests du constructeur de requêtes atomiques Google Slides API batchUpdate."""

    def test_build_batch_update_structure(self):
        """Vérifie que les requêtes batchUpdate sont valides et complètes."""
        titre = "Bitcoin : Révolution Monétaire"
        subtitle = "Analyse Fondamentale & Technique"
        slides = [
            {
                "titre_slide": "1. Genèse & Vision",
                "category": "HISTOIRE",
                "points": ["Point 1", "Point 2", "Point 3"],
                "key_metric": {"label": "PLAFOND", "value": "21M BTC", "desc": "Immuabilité"},
                "notes": "Parler de la création"
            },
            {
                "titre_slide": "2. Preuve de Travail",
                "category": "ARCHITECTURE",
                "points": ["Consensus décentralisé", "Sécurité globale"],
                "notes": "Parler de la sécurité"
            }
        ]

        requests = slides_service.build_google_slides_batch_update(
            titre=titre,
            subtitle=subtitle,
            theme="bitcoin",
            slides=slides,
            default_slide_id="default_empty_slide_p"
        )

        assert isinstance(requests, list)
        assert len(requests) > 10

        # Vérifier la présence de createSlide
        create_slide_reqs = [r for r in requests if "createSlide" in r]
        assert len(create_slide_reqs) == 3  # 1 Cover + 2 Content slides

        # Vérifier la présence de deleteObject pour supprimer la diapositive vierge initiale
        delete_reqs = [r for r in requests if "deleteObject" in r]
        assert len(delete_reqs) == 1
        assert delete_reqs[0]["deleteObject"]["objectId"] == "default_empty_slide_p"

        # Vérifier la présence des formes et du texte
        insert_text_reqs = [r for r in requests if "insertText" in r]
        inserted_texts = [r["insertText"]["text"] for r in insert_text_reqs]
        assert any(titre in t for t in inserted_texts)
        assert any("Genèse & Vision" in t for t in inserted_texts)
        assert any("21M BTC" in t for t in inserted_texts)

        # Vérifier le respect du format 16:9 widescreen (720 x 405 PT max)
        for r in requests:
            if "createShape" in r:
                elem_props = r["createShape"]["elementProperties"]
                size = elem_props["size"]
                transform = elem_props["transform"]
                w = size["width"]["magnitude"]
                h = size["height"]["magnitude"]
                x = transform["translateX"]
                y = transform["translateY"]
                assert x + w <= 720, f"Shape déborde horizontalement : {x} + {w} > 720"
                assert y + h <= 405, f"Shape déborde verticalement : {y} + {h} > 405"


class TestBuildSlidesPayloadIntegration:
    """Tests d'intégration de build_slides_payload dans automation.py."""

    def test_build_slides_payload_auto_generation(self):
        """Vérifie que build_slides_payload génère automatiquement les slides si non fournies."""
        payload = build_slides_payload(
            titre="Bitcoin",
            theme="stark",
            slides=[]
        )

        assert payload["titre"] != ""
        assert payload["slides_count"] >= 5
        assert len(payload["slides"]) >= 5
        assert len(payload["batch_requests"]) > 0
        assert payload["filename"].endswith(".pptx")

    def test_slides_service_task_tracking(self):
        """Vérifie le suivi en temps réel de l'état de la tâche."""
        status_idle = slides_service.get_current_task()
        assert status_idle["active"] is False

        # Simulation tâche active
        slides_service._current_task = {
            "active": True,
            "action_id": "test_act",
            "topic": "Bitcoin",
            "step": "Étape 2/4 : Recherche documentaire",
            "details": "Agrégation des données",
            "started_at": 100.0,
            "slides_count": 6,
            "presentation_url": ""
        }

        status_active = slides_service.get_current_task()
        assert status_active["active"] is True
        assert status_active["topic"] == "Bitcoin"
        assert "Étape 2/4" in status_active["step"]
        assert "Bitcoin" in status_active["explanation"]

        # Remise à zéro
        slides_service._current_task["active"] = False
