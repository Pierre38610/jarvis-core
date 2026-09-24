"""Service de mémoire persistante locale (SQLite) pour J.A.R.V.I.S."""

import sqlite3
import datetime
from typing import List, Dict, Any
from config import DB_PATH

class MemoryService:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Table des souvenirs et faits mémorisés
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL DEFAULT 'general',
                    fact TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            # Table du profil utilisateur (clé / valeur)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_profile (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()

            # Profil initial par défaut si vide
            cursor.execute("SELECT COUNT(*) FROM user_profile")
            if cursor.fetchone()[0] == 0:
                now = datetime.datetime.now().isoformat()
                defaults = [
                    ("user_name", "Pierre"),
                    ("ai_identity", "J.A.R.V.I.S. (Just A Rather Very Intelligent System)"),
                    ("tone", "Élégant, concis, confiant, digne de Tony Stark"),
                    ("preferred_language", "Français")
                ]
                cursor.executemany("INSERT INTO user_profile (key, value, updated_at) VALUES (?, ?, ?)", 
                                   [(k, v, now) for k, v in defaults])
                conn.commit()

    def add_memory(self, fact: str, category: str = "general") -> Dict[str, Any]:
        """Mémorise un fait ou une préférence utilisateur."""
        fact_clean = (fact or "").strip()
        if not fact_clean:
            return {"status": "error", "message": "Fait vide"}

        now = datetime.datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO memories (category, fact, created_at) VALUES (?, ?, ?)",
                           (category, fact_clean, now))
            memory_id = cursor.lastrowid
            conn.commit()

        print(f"[Memory] Fait mémorisé (#{memory_id}) : {fact_clean}")
        return {
            "status": "success",
            "id": memory_id,
            "fact": fact_clean,
            "category": category
        }

    def search_memories(self, query: str, limit: int = 6) -> List[Dict[str, Any]]:
        """Recherche les souvenirs pertinents selon des mots-clés."""
        words = [w.strip() for w in (query or "").split() if len(w.strip()) > 2]
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if not words:
                cursor.execute("SELECT id, category, fact, created_at FROM memories ORDER BY id DESC LIMIT ?", (limit,))
            else:
                like_clauses = " OR ".join(["fact LIKE ?" for _ in words])
                params = [f"%{w}%" for w in words] + [limit]
                cursor.execute(f"SELECT id, category, fact, created_at FROM memories WHERE {like_clauses} ORDER BY id DESC LIMIT ?", params)
            
            rows = cursor.fetchall()
            return [{"id": r["id"], "category": r["category"], "fact": r["fact"], "date": r["created_at"]} for r in rows]

    def get_profile(self) -> Dict[str, str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM user_profile")
            return {r["key"]: r["value"] for r in cursor.fetchall()}

    def set_profile_value(self, key: str, value: str):
        now = datetime.datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_profile (key, value, updated_at) 
                VALUES (?, ?, ?) 
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """, (key, value, now))
            conn.commit()

    def build_system_memory_context(self) -> str:
        """Construit un résumé textuel concis à injecter dans le prompt système de J.A.R.V.I.S."""
        profile = self.get_profile()
        user_name = profile.get("user_name", "Monsieur")

        recent_memories = self.search_memories("", limit=8)
        memories_text = ""
        if recent_memories:
            items = [f"- {m['fact']}" for m in recent_memories]
            memories_text = "SOUVENIRS ET PRÉFÉRENCES CONNUES DE L'UTILISATEUR :\n" + "\n".join(items)
        else:
            memories_text = "AUCUN SOUVENIR ENREGISTRÉ POUR L'INSTANT."

        return f"UTILISATEUR PRINCIPAL : {user_name}\n{memories_text}"

# Instance globale prête à l'emploi
memory_service = MemoryService()
