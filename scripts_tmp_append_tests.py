"""Script temporaire : ajoute les tests V5.15 à tests/unit/test_slides_service.py."""
import os, sys

TARGET = os.path.join(os.path.dirname(__file__), "tests", "unit", "test_slides_service.py")

APPEND = '''

# =============================================================================
# Tests V5.15 — Outline dynamique, nouveaux layouts, modify_presentation
# =============================================================================

class TestGeneratePresentationOutline:
    """Tests pour generate_presentation_outline (moteur déterministe en mode test)."""

    @pytest.mark.asyncio
    async def test_outline_3_slides(self):
        outline = await slides_service.generate_presentation_outline(
            sujet="IA generative",
            consignes="Fais 3 slides seulement",
            nb_slides=3,
        )
        slides = outline.get("slides", [])
        assert len(slides) == 3, f"Attendu 3 slides, obtenu {len(slides)}"

    @pytest.mark.asyncio
    async def test_outline_returns_required_keys(self):
        outline = await slides_service.generate_presentation_outline(
            sujet="cybersecurite",
            consignes="presente les enjeux de cybersecurite",
        )
        for key in ("title", "subtitle", "theme", "slides"):
            assert key in outline, f"Cle manquante : {key}"
        assert len(outline["slides"]) > 0

    @pytest.mark.asyncio
    async def test_outline_pitch_short(self):
        outline = await slides_service.generate_presentation_outline(
            sujet="pitch produit IA",
            consignes="pitch rapide",
        )
        slides = outline.get("slides", [])
        assert 2 <= len(slides) <= 5, f"Attendu 2-5 slides pour pitch, obtenu {len(slides)}"

    @pytest.mark.asyncio
    async def test_outline_layout_variety(self):
        outline = await slides_service.generate_presentation_outline(
            sujet="informatique",
            consignes="presentation detaillee exhaustive",
        )
        slides = outline.get("slides", [])
        layouts = [s.get("layout") for s in slides]
        assert len(set(layouts)) >= 2, f"Trop peu de layouts differents : {set(layouts)}"


class TestVerifyPresentationPartial:
    """Tests de verification partielle (outline count vs slides creees)."""

    @pytest.mark.asyncio
    async def test_verify_empty_id_fails(self):
        result = await slides_service.verify_presentation("", min_slides=1)
        assert not result.verified
        assert result.count == 0

    @pytest.mark.asyncio
    async def test_verify_partial_fewer_slides(self):
        original_count = slides_service._current_task.get("slides_count", 0)
        original_titles = slides_service._current_task.get("titles", [])
        slides_service._current_task["slides_count"] = 4
        slides_service._current_task["titles"] = ["T1", "T2", "T3", "T4"]
        try:
            result = await slides_service.verify_presentation(
                "fake_id", min_slides=1, expected_outline_count=6
            )
        finally:
            slides_service._current_task["slides_count"] = original_count
            slides_service._current_task["titles"] = original_titles
        assert not result.verified
        assert result.count == 4


class TestModifyPresentation:
    """Tests pour slides_service.modify_presentation."""

    @pytest.mark.asyncio
    async def test_no_instruction_fails(self):
        result = await slides_service.modify_presentation(
            presentation_id="abc123", instruction=""
        )
        assert result["status"] == "failed"

    @pytest.mark.asyncio
    async def test_no_last_id_fails(self):
        original = slides_service._last_presentation_id
        slides_service._last_presentation_id = ""
        try:
            result = await slides_service.modify_presentation(
                presentation_id="last",
                instruction="ajoute une slide sur le ROI"
            )
            assert result["status"] == "failed"
        finally:
            slides_service._last_presentation_id = original

    @pytest.mark.asyncio
    async def test_delete_action(self):
        slides_service._last_presentation_id = "test_pres_id"
        result = await slides_service.modify_presentation(
            presentation_id="test_pres_id",
            instruction="supprime la slide 2"
        )
        assert result["status"] == "done"
        assert result["action"] == "suppression_slide"

    @pytest.mark.asyncio
    async def test_add_action(self):
        slides_service._last_presentation_id = "test_pres_id"
        result = await slides_service.modify_presentation(
            presentation_id="test_pres_id",
            instruction="ajoute une slide sur le futur"
        )
        assert result["status"] == "done"
        assert result["action"] == "ajout_slide"

    @pytest.mark.asyncio
    async def test_rename_action(self):
        slides_service._last_presentation_id = "test_pres_id"
        result = await slides_service.modify_presentation(
            presentation_id="test_pres_id",
            instruction="change le titre de la slide 3 en Conclusion"
        )
        assert result["status"] == "done"
        assert result["action"] == "modification_titre"


class TestNewLayouts:
    """Tests des nouveaux layouts dans build_google_slides_batch_update."""

    def _build(self, layout, slide_data):
        return slides_service.build_google_slides_batch_update(
            titre="Test", subtitle="Sous-titre", theme="stark",
            slides=[{**slide_data, "layout": layout}],
        )

    def test_bullets_simple_bullets_present(self):
        reqs = self._build("bullets_simple", {"title": "T", "points": ["A", "B"]})
        texts = " ".join(r["insertText"]["text"] for r in reqs if "insertText" in r)
        assert "•" in texts

    def test_image_plus_text_no_url_substitution(self):
        reqs = self._build("image_plus_text", {"title": "T", "body": "Corps"})
        assert any("createShape" in r for r in reqs)
        texts = " ".join(r["insertText"]["text"] for r in reqs if "insertText" in r)
        assert any(k in texts for k in ["VISUEL", "IMAGE", "Corps", "illustration"])

    def test_image_plus_text_with_url(self):
        reqs = self._build("image_plus_text", {
            "title": "T", "body": "B",
            "image_url": "https://example.com/img.jpg"
        })
        imgs = [r for r in reqs if "createImage" in r]
        assert len(imgs) == 1
        assert imgs[0]["createImage"]["url"] == "https://example.com/img.jpg"

    def test_table_data_dimensions(self):
        reqs = self._build("table_data", {
            "title": "T",
            "headers": ["A", "B", "C"],
            "rows": [["1", "2", "3"], ["4", "5", "6"]]
        })
        tables = [r for r in reqs if "createTable" in r]
        assert len(tables) == 1
        assert tables[0]["createTable"]["rows"] == 3   # 1 header + 2 lignes
        assert tables[0]["createTable"]["columns"] == 3

    def test_section_divider_has_rectangle(self):
        reqs = self._build("section_divider", {"title": "Section II", "subtitle": "Sub"})
        rects = [r for r in reqs if r.get("createShape", {}).get("shapeType") == "RECTANGLE"]
        assert len(rects) >= 1

    def test_quote_highlight_guillemets(self):
        reqs = self._build("quote_highlight", {
            "title": "T", "quote": "Ceci est une citation.", "author": "Einstein"
        })
        texts = " ".join(r["insertText"]["text"] for r in reqs if "insertText" in r)
        assert "«" in texts or "»" in texts
        assert "Einstein" in texts

    def test_conclusion_call_to_action_cards(self):
        reqs = self._build("conclusion_call_to_action", {
            "title": "Conclusion", "summary": "Synthese.",
            "actions": [
                {"title": "A1", "body": "B1"},
                {"title": "A2", "body": "B2"},
                {"title": "A3", "body": "B3"},
            ]
        })
        rrs = [r for r in reqs if r.get("createShape", {}).get("shapeType") == "ROUND_RECTANGLE"]
        assert len(rrs) >= 3

    def test_all_new_layouts_no_out_of_bounds(self):
        cases = [
            ("bullets_simple", {"title": "T", "points": ["A"]}),
            ("image_plus_text", {"title": "T", "body": "B"}),
            ("table_data", {"title": "T", "headers": ["X"], "rows": [["1"]]}),
            ("section_divider", {"title": "T", "subtitle": "S"}),
            ("quote_highlight", {"title": "T", "quote": "Q", "author": "A"}),
            ("conclusion_call_to_action", {"title": "T", "summary": "S"}),
        ]
        for layout, data in cases:
            for r in self._build(layout, data):
                if "createShape" in r:
                    ep = r["createShape"]["elementProperties"]
                    w = ep["size"]["width"]["magnitude"]
                    h = ep["size"]["height"]["magnitude"]
                    x = ep["transform"]["translateX"]
                    y = ep["transform"]["translateY"]
                    assert x + w <= 720, f"[{layout}] Debordement horizontal"
                    assert y + h <= 405, f"[{layout}] Debordement vertical"
'''

with open(TARGET, "r", encoding="utf-8") as f:
    existing = f.read()

if "TestGeneratePresentationOutline" in existing:
    print("ALREADY_PRESENT")
    sys.exit(0)

with open(TARGET, "a", encoding="utf-8") as f:
    f.write(APPEND)

print("OK — tests appended")
