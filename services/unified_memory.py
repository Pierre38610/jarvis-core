"""
services/unified_memory.py — Façade unifiée pour la mémoire hybride de J.A.R.V.I.S.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional

from services.memory_service import memory_service as sqlite_memory
from services.memory import vector_memory

logger = logging.getLogger("jarvis.unified_memory")

class UnifiedMemoryManager:
    """
    Façade unifiant la mémoire relationnelle SQLite et vectorielle Qdrant.
    Gère la déduplication, la synchronisation non-bloquante et la dégradation gracieuse.
    """

    async def memorize(self, fact: str, category: str = "général", importance: int = 1) -> Dict[str, Any]:
        """
        Mémorise un fait ou une information.
        Gère la déduplication des données immuables du profil.
        """
        fact_clean = fact.strip()
        category_clean = category.strip().lower()
        
        # 1. Déduplication : détecter les informations de profil immuables
        profil_keywords = ["pointure", "adresse", "email", "taille", "téléphone", "nom", "prénom", "code postal", "ville", "pays"]
        is_profile = category_clean in ["contact", "profil", "profile"] or any(kw in fact_clean.lower() for kw in profil_keywords)
        
        if is_profile:
            # Enregistrement exclusif dans SQLite (pour ne pas polluer l'espace vectoriel)
            sqlite_res = sqlite_memory.add_memory(fact_clean, category="profil_immuable")
            logger.info(f"[UnifiedMemory] Donnée de profil immuable détectée et sauvegardée uniquement dans SQLite : {fact_clean}")
            return {"status": "success", "id": sqlite_res.get("id"), "fact": fact_clean, "category": "profil_immuable", "message": "Enregistré dans le profil maître (dédupliqué)."}
            
        # 2. Sauvegarde relationnelle (SQLite) - Synchrone rapide
        sqlite_res = sqlite_memory.add_memory(fact_clean, category=category_clean)
        sqlite_id = sqlite_res.get("id")
        
        # 3. Synchronisation vectorielle (Qdrant + Postgres) - Asynchrone non-bloquante
        asyncio.create_task(
            self._async_vector_sync(fact_clean, category_clean, importance, metadata={"sqlite_id": sqlite_id})
        )
        
        return {"status": "success", "id": sqlite_id, "fact": fact_clean, "category": category_clean}

    async def _async_vector_sync(self, fact: str, category: str, importance: int, metadata: Dict[str, Any]):
        try:
            if vector_memory._ready:
                await vector_memory.save_memory(fact, category=category, importance=importance, metadata=metadata)
        except Exception as e:
            logger.error(f"[UnifiedMemory] Erreur lors de la synchro vectorielle: {e}")

    async def recall(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Recherche sémantique de souvenirs.
        Tente Qdrant/PostgreSQL d'abord. Si indisponible ou vide, bascule sur SQLite textuel.
        """
        results = []
        
        # 1. Tentative Qdrant / Postgres (VectorMemoryService gère déjà le fallback Postgres interne)
        if vector_memory._ready:
            try:
                results = await vector_memory.search_relevant_memories(query, limit=limit)
            except Exception as e:
                logger.error(f"[UnifiedMemory] Erreur recherche vectorielle: {e}")
                
        # 2. Fallback gracieux sur SQLite textuel si vector_memory n'est pas prêt ou erreur
        if not results:
            logger.info("[UnifiedMemory] Dégradation gracieuse : recherche via SQLite local.")
            try:
                sqlite_results = sqlite_memory.search_memories(query, limit=limit)
                results = [
                    {
                        "id": str(r.get("id")),
                        "content": r.get("fact"),
                        "category": r.get("category"),
                        "score": None,
                        "created_at": r.get("date")
                    } for r in sqlite_results
                ]
            except Exception as e:
                logger.error(f"[UnifiedMemory] Erreur fallback SQLite: {e}")
                
        # 3. Enrichissement si la recherche concerne le profil, CV ou parcours de Pierre
        profile_keywords = [
            "pierre", "profil", "cv", "stage", "candidature", "formation", "phelma",
            "sicom", "scintil", "teem", "école", "études", "compétences", "expérience",
            "lettre de motivation", "cold email", "suède", "malmö", "danemark", "oresund",
            "øresund", "photonique", "dsp", "traitement du signal", "anglais", "permis"
        ]
        if any(kw in query.lower() for kw in profile_keywords):
            try:
                from services.user_profile_service import user_profile_service
                prof_res = user_profile_service.lookup(query=query)
                if prof_res.get("status") == "success" and prof_res.get("content"):
                    results.insert(0, {
                        "id": "candidature_profile_doc",
                        "content": prof_res["content"][:1500],
                        "category": "profil_candidature_pierre",
                        "score": 1.0,
                        "created_at": "live_sync"
                    })
            except Exception as e:
                logger.error(f"[UnifiedMemory] Erreur injection profil candidature dans recall: {e}")

        # 4. Enrichissement architectural si la recherche concerne les capacités de Jarvis
        arch_keywords = [
            "architecture", "fonctionnement", "comment tu marches", "qui es-tu",
            "capacités", "que sais-tu faire", "serveur", "infrastructure", "vps",
            "docker", "limites", "antigravity", "stremio", "deezer", "composants", "spécifications"
        ]
        if any(kw in query.lower() for kw in arch_keywords):
            try:
                from services.architecture_service import architecture_service
                arch_res = architecture_service.lookup(query=query)
                if arch_res.get("status") == "success" and arch_res.get("content"):
                    results.insert(0, {
                        "id": "arch_doc",
                        "content": arch_res["content"][:1000],
                        "category": "architecture_système",
                        "score": 1.0,
                        "created_at": "live_sync"
                    })
            except Exception as e:
                logger.error(f"[UnifiedMemory] Erreur injection architecture dans recall: {e}")

        return results

    def get_user_profile(self) -> Dict[str, Any]:
        """
        Récupère le profil maître (données immuables) depuis SQLite enrichi par user_profile_service.
        """
        profile = sqlite_memory.get_user_autofill_profile()
        try:
            from services.user_profile_service import user_profile_service
            profile.update(user_profile_service.get_profile_dict())
        except Exception:
            pass
        return profile
        
    async def build_live_context_prompt(self) -> str:
        """
        Construit un contexte mémoire complet pour Gemini Live (Profil + Candidature + Vectoriel + Architecture).
        """
        # Profil maître SQLite
        profile = self.get_user_profile()
        user_name = profile.get("first_name", profile.get("user_name", "Pierre"))
        
        contact_info = f"PROFIL UTILISATEUR : {profile.get('full_name')} | Email : {profile.get('email')}"
        if profile.get("address"):
            contact_info += f" | Adresse : {profile.get('address')} {profile.get('zip_code', '')} {profile.get('city', '')}"
        if profile.get("phone"):
            contact_info += f" | Tél : {profile.get('phone')}"
            
        # Connaissance approfondie du profil et dossier de candidature de Pierre
        user_candidature_summary = ""
        try:
            from services.user_profile_service import user_profile_service
            user_candidature_summary = user_profile_service.get_summary()
        except Exception as e:
            logger.error(f"[UnifiedMemory] Erreur chargement résumé profil candidature: {e}")

        # Souvenirs contextuels
        semantic_context = ""
        try:
            if vector_memory._ready:
                semantic_context = await vector_memory.build_memory_context_for_session()
            else:
                # Fallback SQLite si Qdrant non prêt
                semantic_context = sqlite_memory.build_system_memory_context()
        except Exception as e:
            logger.error(f"[UnifiedMemory] Erreur génération contexte mémoire: {e}")
            semantic_context = sqlite_memory.build_system_memory_context()

        # Connaissance de l'architecture dynamique issue de ARCHITECTURE_COMPLETE_JARVIS.md
        arch_summary = ""
        try:
            from services.architecture_service import architecture_service
            arch_summary = architecture_service.get_summary()
        except Exception as e:
            logger.error(f"[UnifiedMemory] Erreur chargement résumé architecture: {e}")

        # SQLite build_system_memory_context renvoie parfois déjà "UTILISATEUR PRINCIPAL". 
        # Pour éviter les doublons on s'assure d'une bonne mise en page.
        if "UTILISATEUR PRINCIPAL" in semantic_context:
            base_prompt = semantic_context
        else:
            base_prompt = f"UTILISATEUR PRINCIPAL : {user_name}\n{contact_info}\n\n{semantic_context}".strip()
            
        fluidity_guideline = (
            "POSTURE RELATIONNELLE & FLUIDITÉ CONVERSATIONNELLE :\n"
            "- Relation directe d'égal à égal avec Pierre, naturelle, complice et sans servilité.\n"
            "- Bannis formellement toute amorce robotique répétitive en début de phrase ('C'est noté', 'C'est bien noté Pierre', 'Très bien', 'Entendu', 'C'est compris').\n"
            "- Démarre directement par le verbe d'action ('J'ouvre...', 'Je regarde ça', 'Je m'en charge') ou réagis comme un pair sans préambule inutile.\n"
            "- Ne pose JAMAIS de questions proactives sur les rêves, le sommeil ou la nuit de Pierre. Réponds directement aux ordres demandés."
        )

        full_prompt = f"{base_prompt}\n\n{fluidity_guideline}".strip()

        if user_candidature_summary:
            full_prompt = f"{full_prompt}\n\n{user_candidature_summary}".strip()

        if arch_summary and arch_summary not in full_prompt:
            return f"{full_prompt}\n\n{arch_summary}".strip()
        return full_prompt

    async def consolider_memoire_nocturne(self) -> Dict[str, Any]:
        """Déclenche la routine nocturne d'assainissement et de consolidation de la mémoire
        via l'agent Antigravity CLI 'memory_consolidation' (Système 2) : détection des obsolescences,
        fusion des contradictions et structuration Knowledge Graph.
        """
        from services.agentic_dispatcher import agentic_dispatcher
        all_mems = sqlite_memory.search_memories("", limit=50)
        profile = self.get_user_profile()
        goal = "Assainissement nocturne, déduplication et Knowledge Graph de la mémoire de Pierre"
        context = {
            "profil": profile,
            "souvenirs_actuels": all_mems,
            "nb_souvenirs": len(all_mems)
        }
        return await agentic_dispatcher.launch_agentic_mission(
            mission_type="memory_consolidation",
            goal=goal,
            context=context
        )

unified_memory_manager = UnifiedMemoryManager()

