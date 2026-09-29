"""
tests/test_user_profile_service.py — Validation de la Connaissance Approfondie du Profil de Pierre.
Respecte la règle d'or : aucune API payante, test local mocké/offline pur.
"""

import unittest
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.user_profile_service import UserProfileKnowledgeService, user_profile_service
from services.unified_memory import unified_memory_manager


class TestUserProfileService(unittest.TestCase):
    def test_01_load_and_parse_candidature_profile(self):
        """Vérifie que PROFIL_CANDIDATURE_PIERRE_CASSAGNETTES.md est bien chargé et découpé."""
        self.assertTrue(os.path.exists(user_profile_service.file_path), "Fichier de profil introuvable")
        summary = user_profile_service.get_summary()
        self.assertIn("✦ DOSSIER DE CANDIDATURE & PROFIL COMPLET DE PIERRE CASSAGNETTES ✦", summary)
        self.assertIn("Pierre Cassagnettes", summary)
        self.assertIn("Grenoble INP – Phelma", summary)
        self.assertIn("SICOM", summary)
        self.assertIn("Scintil Photonics", summary)
        self.assertIn("Malmö", summary)

    def test_02_table_of_contents_and_lookup(self):
        """Vérifie l'extraction des sections et les recherches textuelles ciblées."""
        toc = user_profile_service.get_table_of_contents()
        self.assertTrue(len(toc) >= 8, f"Nombre de chapitres attendu >= 8, reçu : {len(toc)}")

        # Recherche Scintil Photonics
        res_scintil = user_profile_service.lookup(query="scintil")
        self.assertEqual(res_scintil["status"], "success")
        self.assertIn("Scintil Photonics", res_scintil["content"])
        self.assertIn("CustomTkinter", res_scintil["content"])

        # Recherche Phelma / SICOM
        res_phelma = user_profile_service.lookup(query="phelma sicom")
        self.assertEqual(res_phelma["status"], "success")
        self.assertIn("Phelma", res_phelma["content"])

        # Recherche Øresund / Scandinavie
        res_oresund = user_profile_service.lookup(query="oresund malmo")
        self.assertEqual(res_oresund["status"], "success")
        self.assertIn("Malmö", res_oresund["content"])

    def test_03_profile_dict_attributes(self):
        """Vérifie les attributs structurés du dictionnaire utilisateur."""
        pdict = user_profile_service.get_profile_dict()
        self.assertEqual(pdict["nom_complet"], "Pierre Cassagnettes")
        self.assertEqual(pdict["email"], "pierrecassagnettes@gmail.com")
        self.assertIn("+33 7 69 52 44 30", pdict["phone"])
        self.assertIn("Grenoble INP – Phelma", pdict["ecole"])
        self.assertIn("SICOM", pdict["filiere"])
        self.assertIn("Malmö", pdict["localisations"])

    def test_04_sync_to_sqlite(self):
        """Vérifie la synchronisation locale dans SQLite sans erreur."""
        sync_res = user_profile_service.sync_to_sqlite()
        self.assertEqual(sync_res["status"], "success")
        self.assertGreater(sync_res["profiles_updated"], 10)

    def test_05_unified_memory_integration(self):
        """Vérifie l'injection dans UnifiedMemoryManager (profil, live context prompt et recall)."""
        loop = asyncio.new_event_loop()
        try:
            # 1. get_user_profile
            prof = unified_memory_manager.get_user_profile()
            self.assertEqual(prof.get("full_name"), "Pierre Cassagnettes")
            self.assertEqual(prof.get("email"), "pierrecassagnettes@gmail.com")
            self.assertIn("Phelma", prof.get("ecole", ""))

            # 2. build_live_context_prompt
            prompt = loop.run_until_complete(unified_memory_manager.build_live_context_prompt())
            self.assertIn("PROFIL COMPLET DE PIERRE CASSAGNETTES", prompt)
            self.assertIn("Grenoble INP – Phelma", prompt)
            self.assertIn("Scintil Photonics", prompt)

            # 3. recall sur un mot-clé du profil
            mem_results = loop.run_until_complete(unified_memory_manager.recall("expérience stage scintil photonics", limit=3))
            self.assertTrue(len(mem_results) > 0)
            self.assertTrue(any("Scintil" in m.get("content", "") for m in mem_results))
        finally:
            loop.close()


if __name__ == "__main__":
    unittest.main()
