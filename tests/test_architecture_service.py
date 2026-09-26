"""
tests/test_architecture_service.py — Validation de la Connaissance Architecturale Dynamique
Respecte la règle d'or : aucune API payante, test local mocké/offline pur.
"""

import unittest
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.architecture_service import ArchitectureKnowledgeService, architecture_service
from services.unified_memory import unified_memory_manager
from core.tools.declarations import get_tools_list


class TestArchitectureService(unittest.TestCase):
    def test_01_load_and_parse_master_file(self):
        """Vérifie que ARCHITECTURE_COMPLETE_JARVIS.md est bien chargé et découpé."""
        self.assertTrue(os.path.exists(architecture_service.file_path), "Fichier d'architecture introuvable")
        summary = architecture_service.get_summary()
        self.assertIn("✦ CONNAISSANCE DE TON ARCHITECTURE", summary)
        self.assertIn("J.A.R.V.I.S.", summary)
        self.assertIn("Oracle Cloud VPS", summary)
        self.assertIn("10 SUPER-POUVOIRS", summary)
        self.assertIn("GARDE-FOUS INVIOLABLES", summary)

    def test_02_table_of_contents_and_sections(self):
        """Vérifie l'extraction du sommaire et la recherche par chapitre."""
        toc = architecture_service.get_table_of_contents()
        self.assertTrue(len(toc) >= 10, f"Nombre de chapitres attendu >= 10, reçu : {len(toc)}")
        
        # Recherche par mot clé
        res_deezer = architecture_service.lookup(query="deezer")
        self.assertEqual(res_deezer["status"], "success")
        self.assertIn("Deezer", res_deezer["content"])

        # Recherche par section
        res_sec2 = architecture_service.lookup(section="2")
        self.assertEqual(res_sec2["status"], "success")
        self.assertIn("TOPOLOGIE", res_sec2["content"].upper())

    def test_03_mtime_hot_reload(self):
        """Vérifie que la modification de mtime recharge le service sans erreur."""
        initial_mtime = architecture_service._last_mtime
        self.assertGreater(initial_mtime, 0)

        # Forcer le rechargement
        reloaded = architecture_service._ensure_loaded(force=True)
        self.assertTrue(reloaded)

    def test_04_unified_memory_injection(self):
        """Vérifie que le prompt Live Context de mémoire contient la synthèse architecturale."""
        loop = asyncio.new_event_loop()
        try:
            live_context = loop.run_until_complete(unified_memory_manager.build_live_context_prompt())
            self.assertIn("✦ CONNAISSANCE DE TON ARCHITECTURE", live_context)
            self.assertIn("UTILISATEUR PRINCIPAL", live_context)
        finally:
            loop.close()

    def test_05_tool_declaration_registered(self):
        """Vérifie que l'outil consulter_architecture_jarvis est exposé dans le catalogue."""
        tools = get_tools_list()
        decl_names = [f.name for t in tools for f in getattr(t, "function_declarations", [])]
        self.assertIn("consulter_architecture_jarvis", decl_names)


if __name__ == "__main__":
    unittest.main()
