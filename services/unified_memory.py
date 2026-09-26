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
                
        return results

    def get_user_profile(self) -> Dict[str, Any]:
        """
        Récupère le profil maître (données immuables) depuis SQLite.
        """
        return sqlite_memory.get_user_autofill_profile()
        
    async def build_live_context_prompt(self) -> str:
        """
        Construit un contexte mémoire complet pour Gemini Live (Profil + Vectoriel).
        """
        # Profil maître SQLite
        profile = self.get_user_profile()
        user_name = profile.get("first_name", profile.get("user_name", "Pierre"))
        
        contact_info = f"PROFIL UTILISATEUR : {profile.get('full_name')} | Email : {profile.get('email')}"
        if profile.get("address"):
            contact_info += f" | Adresse : {profile.get('address')} {profile.get('zip_code', '')} {profile.get('city', '')}"
            
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
            
        # SQLite build_system_memory_context renvoie parfois déjà "UTILISATEUR PRINCIPAL". 
        # Pour éviter les doublons on s'assure d'une bonne mise en page.
        if "UTILISATEUR PRINCIPAL" in semantic_context:
            return semantic_context # on utilise le fallback tel quel s'il est utilisé
            
        return f"UTILISATEUR PRINCIPAL : {user_name}\n{contact_info}\n\n{semantic_context}".strip()

unified_memory_manager = UnifiedMemoryManager()
