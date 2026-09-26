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

    def test_detect_multi_segment_route_arctic(self):
        """Vérifie la décomposition automatique d'un trajet long vers le Nord de la Suède (Malmö -> Kiruna)."""
        multi = transport_service.detect_multi_segment_route("Malmö", "Kiruna", "2026-09-28", "09:00", "SE")
        self.assertIsNotNone(multi, "Le trajet Malmö -> Kiruna doit déclencher la décomposition multi-segments")
        self.assertEqual(len(multi["segments"]), 2, "Le voyage doit comporter 2 segments distincts")

        # Segment 1 : Train à grande vitesse vers Stockholm
        seg1 = multi["segments"][0]
        self.assertEqual(seg1["segment_index"], 1)
        self.assertIn("SJ Snabbtåg", seg1["type_train"])
        self.assertEqual(seg1["destination"], "Stockholm Central")
        self.assertNotIn(".html", seg1["url_reservation"])

        # Segment 2 : Train de nuit couchette vers Kiruna
        seg2 = multi["segments"][1]
        self.assertEqual(seg2["segment_index"], 2)
        self.assertIn("Nattåg", seg2["type_train"])
        self.assertEqual(seg2["destination"], "Kiruna")
        self.assertEqual(seg2["origine"], "Stockholm Central")

        # Escale et URLs de réservation
        self.assertEqual(multi["escale"]["gare"], "Stockholm Central")
        self.assertEqual(len(multi["booking_urls"]), 2)
        for url in multi["booking_urls"]:
            self.assertTrue(url.startswith("https://www.sj.se/en"))
            self.assertNotIn("/sok-resa.html", url)

    async def test_rechercher_itineraires_multi_segment(self):
        """Vérifie que rechercher_itineraires renvoie les informations multi-billets pour le Nord de la Suède."""
        res = await transport_service.rechercher_itineraires(
            "Malmö", "nord de la suède", "la semaine prochaine"
        )
        self.assertEqual(res["status"], "success")
        self.assertTrue(res.get("is_multi_segment"))
        self.assertIn("segments", res)
        self.assertIn("booking_urls", res)
        self.assertEqual(len(res["booking_urls"]), 2)
        self.assertEqual(res["hub"], "Stockholm Central")

    async def test_reserver_billet_train_local_multi_urls(self):
        """Vérifie que reserver_billet_train_local transmet une liste de plusieurs URLs au local-agent."""
        from services.local_agent_service import local_agent_service
        with patch.object(local_agent_service, "is_connected", return_value=True), \
             patch.object(local_agent_service, "execute_command", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {"status": "success", "action": "prepare_train_checkout"}
            urls = [
                "https://www.sj.se/en?from=Malm%C3%B6&to=Stockholm",
                "https://www.sj.se/en/travel-info/sj-night-train.html",
            ]
            res = await transport_service.reserver_billet_train_local(
                operateur="sj",
                url_trajet=urls[0],
                urls_trajets=urls,
                description_trajet="Enchaînement 2 trains Malmö -> Kiruna"
            )
            self.assertEqual(res["status"], "success")
            mock_exec.assert_called_once()
            call_kwargs = mock_exec.call_args[1]
            self.assertEqual(call_kwargs["urls"], urls)
            self.assertEqual(call_kwargs["operateur"], "sj")


if __name__ == "__main__":
    unittest.main()

