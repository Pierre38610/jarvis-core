"""tests/test_transport_service.py
Tests unitaires pour le service de transport ferroviaire de J.A.R.V.I.S.
Vérifie la détection de pays, la génération de deep links (SNCF, Trainline, SJ, Trafikverket),
l'extraction d'itinéraires, la déclaration des outils et la validité du workflow n8n.
Conforme à la règle d'économie des tests (aucun appel à l'API payante).
"""

import json
import os
import unittest
from unittest.mock import AsyncMock, patch

from services.transport_service import transport_service, slugify
from core.tools.declarations import get_tools_list


class TestTransportService(unittest.IsolatedAsyncioTestCase):
    """Tests du service d'intelligence ferroviaire."""

    def test_slugify(self):
        """Vérifie la normalisation des noms de gares en slugs."""
        self.assertEqual(slugify("Malmö Central"), "malmo-central")
        self.assertEqual(slugify("Göteborg"), "goteborg")
        self.assertEqual(slugify("Paris Gare de Lyon"), "paris-gare-de-lyon")
        self.assertEqual(slugify("Marseille Saint-Charles"), "marseille-saint-charles")

    def test_detect_country(self):
        """Vérifie la détection automatique du pays selon les gares ou paramètres."""
        # Détection Suède
        self.assertEqual(transport_service.detect_country("Malmö", "Stockholm"), "SE")
        self.assertEqual(transport_service.detect_country("Lund C", "Göteborg"), "SE")
        self.assertEqual(transport_service.detect_country("Stockholm", "Uppsala"), "SE")
        self.assertEqual(transport_service.detect_country("Paris", "Lyon", pays="se"), "SE")

        # Détection France
        self.assertEqual(transport_service.detect_country("Paris", "Lyon"), "FR")
        self.assertEqual(transport_service.detect_country("Marseille", "Bordeaux"), "FR")
        self.assertEqual(transport_service.detect_country("Lille", "Strasbourg"), "FR")
        self.assertEqual(transport_service.detect_country("Malmö", "Stockholm", pays="fr"), "FR")

    def test_normalize_station(self):
        """Vérifie la résolution des noms et codes de gares."""
        se_stat = transport_service.normalize_station("Malmö", "SE")
        self.assertEqual(se_stat["name"], "Malmö Central")
        self.assertEqual(se_stat["slug"], "malmo-central")
        self.assertEqual(se_stat["code"], "M")

        fr_stat = transport_service.normalize_station("Paris", "FR")
        self.assertIn("Paris", fr_stat["name"])
        self.assertEqual(fr_stat["slug"], "paris-toutes-gares-intramuros")

    def test_parse_travel_date_and_time(self):
        """Vérifie le parsing des dates relatives et heures."""
        parsed_iso = transport_service.parse_travel_date("2026-10-15")
        self.assertEqual(parsed_iso, "2026-10-15")

        time_hhmm = transport_service.parse_travel_time("14h30")
        self.assertEqual(time_hhmm, "14:30")
        time_default = transport_service.parse_travel_time("matin")
        self.assertEqual(time_default, "08:00")

    def test_generate_deep_links_sweden(self):
        """Vérifie la génération de deep links suédois (SJ, Trafikverket, Skånetrafiken)."""
        res = transport_service.generate_deep_links("Malmö", "Stockholm", "2026-10-15", "14:00", "SE")
        self.assertEqual(res["country"], "SE")
        self.assertEqual(res["operator"], "SJ")
        self.assertIn("sj.se", res["primary_url"])
        self.assertIn("Malm", res["links"]["sj_direct"])
        self.assertIn("trafikverket.se", res["links"]["trafikverket_live"])
        self.assertIn("skanetrafiken.se", res["links"]["skanetrafiken"])

    def test_generate_deep_links_france(self):
        """Vérifie la génération de deep links français (SNCF Connect, Trainline)."""
        res = transport_service.generate_deep_links("Paris", "Lyon", "2026-10-15", "08:00", "FR")
        self.assertEqual(res["country"], "FR")
        self.assertEqual(res["operator"], "SNCF")
        self.assertIn("sncf-connect.com", res["primary_url"])
        self.assertIn("sncf-connect.com", res["links"]["sncf_connect"])
        self.assertIn("thetrainline.com", res["links"]["trainline"])

    async def test_rechercher_itineraires(self):
        """Vérifie l'orchestration complète d'une recherche de train."""
        res = await transport_service.rechercher_itineraires("Malmö", "Stockholm", "demain", "14:00")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["country"], "SE")
        self.assertIn("primary_deep_link", res)
        self.assertIn("best_option", res)
        self.assertGreater(len(res["all_options"]), 0)

        best = res["best_option"]
        self.assertTrue(best["heure_depart"].startswith("14"))
        self.assertIn("SJ", best["type_train"])
        self.assertIn("SEK", best["prix"])

    async def test_surveiller_train(self):
        """Vérifie l'enregistrement et l'appel de surveillance."""
        with patch("services.automation.trigger_webhook", new_callable=AsyncMock) as mock_wh:
            mock_wh.return_value = {"status": "ok"}
            res = await transport_service.surveiller_train("TGV 6612", "2026-10-15", "sncf")
            self.assertEqual(res["status"], "monitoring_active")
            self.assertEqual(res["numero_train"], "TGV 6612")
            mock_wh.assert_called_once()

    def test_tool_declarations(self):
        """Vérifie que les 3 nouveaux outils sont bien exposés dans declarations.py."""
        tools = get_tools_list()
        declarations = tools[0].function_declarations
        decl_names = [d.name for d in declarations]

        self.assertIn("rechercher_train", decl_names)
        self.assertIn("surveiller_train", decl_names)
        self.assertIn("reserver_billet_train_local", decl_names)

        # Vérification du schéma de rechercher_train
        rt_tool = next(d for d in declarations if d.name == "rechercher_train")
        self.assertIn("origine", rt_tool.parameters.properties)
        self.assertIn("destination", rt_tool.parameters.properties)
        self.assertIn("date_depart", rt_tool.parameters.properties)

    def test_n8n_workflow_json(self):
        """Vérifie la validité syntaxique et structurelle du workflow n8n train_monitoring.json."""
        workflow_path = os.path.join(
            os.path.dirname(__file__), "..", "docs", "n8n_workflows", "train_monitoring.json"
        )
        self.assertTrue(os.path.exists(workflow_path), f"Fichier {workflow_path} introuvable")

        with open(workflow_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertIsInstance(data, list)
        workflow = data[0]
        self.assertIn("nodes", workflow)
        self.assertIn("connections", workflow)

        node_names = [n["name"] for n in workflow["nodes"]]
        self.assertIn("Webhook Surveillance Train", node_names)
        self.assertIn("Interrogation Flux Trafikverket / SNCF", node_names)
        self.assertIn("Évaluer Retard et Perturbation", node_names)
        self.assertIn("Alerter Jarvis Webhook (Voix & Push)", node_names)


if __name__ == "__main__":
    unittest.main()
