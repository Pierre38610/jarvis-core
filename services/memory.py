"""
services/memory.py — Mémoire Long-Terme Vectorielle de J.A.R.V.I.S.

Architecture :
  - Qdrant  : stockage et recherche vectorielle sémantique (embeddings)
  - PostgreSQL : persistance relationnelle des souvenirs (metadata, catégorie, horodatage)
  - fastembed : génération locale des embeddings, sans API payante, CPU ARM friendly

Fallback : si Qdrant ou PostgreSQL est indisponible, retombe en mode dégradé
           silencieux pour ne jamais bloquer le démarrage de Jarvis.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.memory")

# ─── Imports optionnels (fallback silencieux si non installés) ─────────────────

try:
    from fastembed import TextEmbedding
    _FASTEMBED_OK = True
except ImportError:
    _FASTEMBED_OK = False
    logger.warning("[Memory] fastembed non installé – mode dégradé (pas d'embeddings)")

try:
    from qdrant_client import QdrantClient, models as qdrant_models
    _QDRANT_OK = True
except ImportError:
    _QDRANT_OK = False
    logger.warning("[Memory] qdrant-client non installé – mode dégradé (pas de recherche vectorielle)")

try:
    import asyncpg
    _ASYNCPG_OK = True
except ImportError:
    _ASYNCPG_OK = False
    logger.warning("[Memory] asyncpg non installé – mode dégradé (pas de persistance PostgreSQL)")

# ─── Configuration ─────────────────────────────────────────────────────────────

from config import (
    QDRANT_HOST, QDRANT_PORT, QDRANT_API_KEY,
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB,
    POSTGRES_USER, POSTGRES_PASSWORD,
)

QDRANT_COLLECTION   = "jarvis_memories"
EMBEDDING_MODEL     = "BAAI/bge-small-en-v1.5"   # Modèle multilingue léger, CPU ARM rapide
VECTOR_DIM          = 384                          # Dimension bge-small
VALID_CATEGORIES    = {"préférence", "fait", "tâche", "habitude", "projet", "contact", "général"}


# ─── Classe principale ─────────────────────────────────────────────────────────

class VectorMemoryService:
    """
    Service de mémoire vectorielle long-terme pour J.A.R.V.I.S.
    Combine Qdrant (recherche sémantique) + PostgreSQL (persistance relationnelle).
    """

    def __init__(self) -> None:
        self._embed_model: Optional[Any]     = None
        self._qdrant:      Optional[Any]     = None
        self._pg_pool:     Optional[Any]     = None
        self._ready        = False

    # ──────────────────────────────────────────────────────────────────────────
    # Initialisation
    # ──────────────────────────────────────────────────────────────────────────

    async def init(self) -> bool:
        """
        Initialise les connexions Qdrant et PostgreSQL.
        Toujours appelé au démarrage de Jarvis (non bloquant en cas d'échec).
        """
        ok_embed  = await asyncio.to_thread(self._init_embedding)
        ok_qdrant = await asyncio.to_thread(self._init_qdrant)
        ok_pg     = await self._init_postgres()
        self._ready = ok_embed and ok_qdrant and ok_pg
        if self._ready:
            logger.info("[Memory] ✅ Service vectoriel prêt (Qdrant + PostgreSQL + fastembed)")
        else:
            logger.warning(
                f"[Memory] ⚠️  Service partiellement opérationnel "
                f"(embed={ok_embed}, qdrant={ok_qdrant}, pg={ok_pg})"
            )
        return self._ready

    def _init_embedding(self) -> bool:
        if not _FASTEMBED_OK:
            return False
        try:
            self._embed_model = TextEmbedding(model_name=EMBEDDING_MODEL)
            logger.info(f"[Memory] Modèle d'embedding chargé : {EMBEDDING_MODEL}")
            return True
        except Exception as e:
            logger.error(f"[Memory] Erreur chargement embedding : {e}")
            return False

    def _init_qdrant(self) -> bool:
        if not _QDRANT_OK:
            return False
        try:
            kwargs: Dict[str, Any] = {"host": QDRANT_HOST, "port": QDRANT_PORT, "timeout": 5}
            if QDRANT_API_KEY:
                kwargs["api_key"] = QDRANT_API_KEY
            self._qdrant = QdrantClient(**kwargs)

            # Crée la collection si elle n'existe pas encore
            existing = [c.name for c in self._qdrant.get_collections().collections]
            if QDRANT_COLLECTION not in existing:
                self._qdrant.create_collection(
                    collection_name=QDRANT_COLLECTION,
                    vectors_config=qdrant_models.VectorParams(
                        size=VECTOR_DIM,
                        distance=qdrant_models.Distance.COSINE,
                    ),
                )
                logger.info(f"[Memory] Collection Qdrant '{QDRANT_COLLECTION}' créée")
            return True
        except Exception as e:
            logger.error(f"[Memory] Erreur connexion Qdrant : {e}")
            return False

    async def _init_postgres(self) -> bool:
        if not _ASYNCPG_OK:
            return False
        try:
            dsn = (
                f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
                f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
            )
            self._pg_pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5, command_timeout=10)

            # Applique le schéma SQL si nécessaire
            import os
            schema_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db", "schema.sql")
            if os.path.exists(schema_path):
                with open(schema_path, "r", encoding="utf-8") as f:
                    schema_sql = f.read()
                async with self._pg_pool.acquire() as conn:
                    await conn.execute(schema_sql)
            logger.info("[Memory] PostgreSQL connecté et schéma appliqué")
            return True
        except Exception as e:
            logger.error(f"[Memory] Erreur connexion PostgreSQL : {e}")
            return False

    # ──────────────────────────────────────────────────────────────────────────
    # Génération d'embeddings
    # ──────────────────────────────────────────────────────────────────────────

    def _embed(self, text: str) -> Optional[List[float]]:
        """Génère un vecteur d'embedding pour le texte donné (synchrone)."""
        if not self._embed_model:
            return None
        try:
            vectors = list(self._embed_model.embed([text]))
            return vectors[0].tolist() if vectors else None
        except Exception as e:
            logger.error(f"[Memory] Erreur embedding : {e}")
            return None

    # ──────────────────────────────────────────────────────────────────────────
    # API publique
    # ──────────────────────────────────────────────────────────────────────────

    async def save_memory(
        self,
        text: str,
        category: str = "fait",
        importance: int = 1,
        conversation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Enregistre un souvenir dans Qdrant (vecteur) et PostgreSQL (persistance).

        Args:
            text: Contenu textuel du souvenir.
            category: Catégorie parmi les valeurs VALID_CATEGORIES.
            importance: Niveau d'importance de 1 (faible) à 5 (critique).
            conversation_id: UUID de la session vocale courante (optionnel).
            metadata: Données supplémentaires libres au format JSON.

        Returns:
            Dict avec status, id et informations sur le souvenir créé.
        """
        text = (text or "").strip()
        if not text:
            return {"status": "error", "message": "Contenu vide"}

        category = category.strip().lower() if category else "fait"
        if category not in VALID_CATEGORIES:
            category = "fait"

        importance = max(1, min(5, int(importance or 1)))
        metadata   = metadata or {}
        memory_id  = str(uuid.uuid4())
        qdrant_id: Optional[str] = None

        # 1. Génération de l'embedding (thread pool pour ne pas bloquer la boucle async)
        vector = await asyncio.to_thread(self._embed, text)

        # 2. Insertion dans Qdrant
        if vector and self._qdrant:
            try:
                q_id = str(uuid.uuid4())
                await asyncio.to_thread(
                    self._qdrant.upsert,
                    collection_name=QDRANT_COLLECTION,
                    points=[
                        qdrant_models.PointStruct(
                            id=q_id,
                            vector=vector,
                            payload={
                                "memory_id": memory_id,
                                "category":  category,
                                "content":   text,
                                "created_at": datetime.now(timezone.utc).isoformat(),
                                **metadata,
                            },
                        )
                    ],
                )
                qdrant_id = q_id
            except Exception as e:
                logger.error(f"[Memory] Erreur insertion Qdrant : {e}")

        # 3. Insertion dans PostgreSQL
        if self._pg_pool:
            try:
                async with self._pg_pool.acquire() as conn:
                    row = await conn.fetchrow(
                        """
                        INSERT INTO memories
                            (id, category, content, qdrant_id, conversation_id, importance, metadata)
                        VALUES
                            ($1::uuid, $2::memory_category, $3, $4::uuid, $5::uuid, $6, $7::jsonb)
                        RETURNING id, created_at
                        """,
                        memory_id,
                        category,
                        text,
                        qdrant_id,
                        conversation_id,
                        importance,
                        __import__("json").dumps(metadata),
                    )
                    memory_id = str(row["id"])
                    logger.info(f"[Memory] ✅ Souvenir #{memory_id[:8]} mémorisé ({category})")
            except Exception as e:
                logger.error(f"[Memory] Erreur insertion PostgreSQL : {e}")

        return {
            "status":    "success",
            "id":        memory_id,
            "qdrant_id": qdrant_id,
            "category":  category,
            "content":   text,
            "importance": importance,
        }

    async def search_relevant_memories(
        self,
        query: str,
        limit: int = 5,
        category_filter: Optional[str] = None,
        score_threshold: float = 0.30,
    ) -> List[Dict[str, Any]]:
        """
        Recherche sémantiquement les souvenirs les plus pertinents via Qdrant.
        Si Qdrant est indisponible, retombe sur une recherche textuelle dans PostgreSQL.

        Args:
            query: Texte de la requête à comparer aux souvenirs.
            limit: Nombre maximum de résultats.
            category_filter: Si fourni, filtre par catégorie (ex: 'préférence').
            score_threshold: Score cosinus minimum pour conserver un résultat.

        Returns:
            Liste de dicts {content, category, score, id, created_at}.
        """
        query = (query or "").strip()

        # ── Recherche vectorielle Qdrant ──────────────────────────────────────
        if query and self._qdrant and self._embed_model:
            try:
                vector = await asyncio.to_thread(self._embed, query)
                if vector:
                    search_filter = None
                    if category_filter and category_filter in VALID_CATEGORIES:
                        search_filter = qdrant_models.Filter(
                            must=[qdrant_models.FieldCondition(
                                key="category",
                                match=qdrant_models.MatchValue(value=category_filter),
                            )]
                        )
                    results = await asyncio.to_thread(
                        self._qdrant.search,
                        collection_name=QDRANT_COLLECTION,
                        query_vector=vector,
                        limit=limit,
                        score_threshold=score_threshold,
                        query_filter=search_filter,
                        with_payload=True,
                    )
                    return [
                        {
                            "id":         str(r.id),
                            "content":    r.payload.get("content", ""),
                            "category":   r.payload.get("category", "fait"),
                            "score":      round(r.score, 3),
                            "created_at": r.payload.get("created_at", ""),
                        }
                        for r in results
                    ]
            except Exception as e:
                logger.error(f"[Memory] Erreur recherche Qdrant : {e}")

        # ── Fallback PostgreSQL (recherche textuelle ILIKE) ───────────────────
        if self._pg_pool:
            try:
                words = [w for w in (query or "").split() if len(w) > 2]
                async with self._pg_pool.acquire() as conn:
                    if not words:
                        rows = await conn.fetch(
                            "SELECT id, category, content, created_at FROM memories "
                            "ORDER BY created_at DESC LIMIT $1",
                            limit,
                        )
                    else:
                        clauses = " OR ".join([f"content ILIKE ${i+2}" for i in range(len(words))])
                        params  = [limit] + [f"%{w}%" for w in words]
                        rows = await conn.fetch(
                            f"SELECT id, category, content, created_at FROM memories "
                            f"WHERE {clauses} ORDER BY created_at DESC LIMIT $1",
                            *params,
                        )
                    return [
                        {
                            "id":         str(r["id"]),
                            "content":    r["content"],
                            "category":   r["category"],
                            "score":      None,
                            "created_at": str(r["created_at"]),
                        }
                        for r in rows
                    ]
            except Exception as e:
                logger.error(f"[Memory] Erreur fallback PostgreSQL : {e}")

        return []

    async def save_conversation(
        self,
        summary: str,
        tags: Optional[List[str]] = None,
        ended_at: Optional[datetime] = None,
    ) -> Optional[str]:
        """
        Enregistre un résumé de session vocale dans la table `conversations`.

        Returns:
            UUID de la conversation créée, ou None en cas d'erreur.
        """
        if not self._pg_pool:
            return None
        try:
            async with self._pg_pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO conversations (summary, ended_at, tags)
                    VALUES ($1, $2, $3::text[])
                    RETURNING id
                    """,
                    summary,
                    ended_at or datetime.now(timezone.utc),
                    tags or [],
                )
                return str(row["id"])
        except Exception as e:
            logger.error(f"[Memory] Erreur insertion conversation : {e}")
            return None

    async def build_memory_context_for_session(
        self,
        seed_queries: Optional[List[str]] = None,
        limit_per_query: int = 4,
    ) -> str:
        """
        Construit un bloc texte de contexte mémoire à injecter dans les
        system_instructions de Gemini Live au démarrage de la session.

        Effectue des recherches sémantiques sur des thèmes clés pour pré-charger
        les souvenirs les plus pertinents (préférences, projets, habitudes...).

        Args:
            seed_queries: Requêtes de seeds à utiliser. Si None, utilise les défauts.
            limit_per_query: Nombre de souvenirs à récupérer par requête seed.

        Returns:
            Bloc texte formaté prêt à l'injection dans le prompt système.
        """
        if seed_queries is None:
            seed_queries = [
                "préférences de Pierre",
                "projets en cours",
                "habitudes quotidiennes",
                "informations personnelles",
                "centres d'intérêt",
            ]

        seen:     set[str] = set()
        memories: list[dict] = []

        for q in seed_queries:
            results = await self.search_relevant_memories(q, limit=limit_per_query)
            for r in results:
                if r["content"] not in seen:
                    seen.add(r["content"])
                    memories.append(r)

        if not memories:
            return ""

        # Tri : score décroissant (None en dernier), puis date
        memories.sort(key=lambda m: (-(m.get("score") or 0), m.get("created_at", "")))
        memories = memories[:12]  # Garde les 12 meilleurs au max

        lines = [f"  • [{m['category']}] {m['content']}" for m in memories]
        block = (
            "MÉMOIRE LONG-TERME (souvenirs vectoriels pertinents chargés au démarrage) :\n"
            + "\n".join(lines)
        )
        return block

    async def close(self) -> None:
        """Ferme proprement les connexions."""
        if self._pg_pool:
            await self._pg_pool.close()
        if self._qdrant:
            try:
                self._qdrant.close()
            except Exception:
                pass
        self._ready = False


# ─── Instance singleton ────────────────────────────────────────────────────────

vector_memory = VectorMemoryService()
