"""Service de Messagerie et d'Analyse Visuelle Multimodale pour J.A.R.V.I.S.
Gère l'historique des conversations écrites, la réception et l'analyse approfondie
de photos / captures d'écran, et les réponses intelligentes via Gemini Multimodal.
"""

import os
import sqlite3
import datetime
import uuid
import asyncio
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types

import config
from services.memory_service import memory_service
from services.console_monitor import console_monitor
from services.supervision_service import supervision_service
from services.email_service import read_received_emails_async

# Clients Gemini : clé payante en priorité pour zéro latence, repli sur clé gratuite
client_paid = genai.Client(api_key=config.GEMINI_API_KEY_PAID) if config.GEMINI_API_KEY_PAID else None
client_free = genai.Client(api_key=config.GEMINI_API_KEY_FREE) if config.GEMINI_API_KEY_FREE else None


class ChatService:
    def __init__(self, db_path: str = config.DB_PATH, uploads_dir: str = config.CHAT_UPLOADS_DIR):
        self.db_path = db_path
        self.uploads_dir = uploads_dir
        os.makedirs(self.uploads_dir, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    image_url TEXT,
                    model_used TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Récupère l'historique récent des messages ordonné chronologiquement."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, role, content, image_url, model_used, created_at
                FROM chat_messages
                ORDER BY id DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            messages = [
                {
                    "id": r["id"],
                    "role": r["role"],
                    "content": r["content"],
                    "image_url": r["image_url"],
                    "model_used": r["model_used"],
                    "created_at": r["created_at"]
                }
                for r in reversed(rows)
            ]
            return messages

    def clear_history(self) -> bool:
        """Efface l'historique complet de la messagerie."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chat_messages")
            conn.commit()
            print("[ChatService] Historique de messagerie effacé.")
            return True

    def save_message(
        self,
        role: str,
        content: str,
        image_url: Optional[str] = None,
        model_used: Optional[str] = None
    ) -> int:
        """Sauvegarde un message dans la base de données."""
        now = datetime.datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO chat_messages (role, content, image_url, model_used, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (role, content, image_url, model_used, now))
            msg_id = cursor.lastrowid
            conn.commit()
            return msg_id

    def save_uploaded_image(self, file_bytes: bytes, original_filename: Optional[str] = None) -> tuple[str, str]:
        """Enregistre une image uploadée dans le dossier static et retourne (image_url, abs_path)."""
        ext = ".jpg"
        if original_filename and "." in original_filename:
            raw_ext = original_filename.rsplit(".", 1)[-1].lower()
            if raw_ext in ("jpg", "jpeg", "png", "webp", "gif", "bmp", "heic"):
                ext = f".{raw_ext}"
        
        unique_name = f"chat_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{ext}"
        abs_path = os.path.join(self.uploads_dir, unique_name)
        with open(abs_path, "wb") as f:
            f.write(file_bytes)
        
        image_url = f"/static/uploads/chat/{unique_name}"
        return image_url, abs_path

    async def process_user_message(
        self,
        text: Optional[str] = None,
        image_bytes: Optional[bytes] = None,
        image_mime: str = "image/jpeg",
        filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """Traite un message utilisateur (texte et/ou photo) et génère la réponse de JARVIS."""
        clean_text = (text or "").strip()
        if not clean_text and not image_bytes:
            return {"status": "error", "message": "Aucun texte ni image fourni."}

        image_url = None
        if image_bytes:
            image_url, _ = self.save_uploaded_image(image_bytes, filename)

        # 1. Sauvegarde du message utilisateur
        user_msg_id = self.save_message(
            role="user",
            content=clean_text or "Photo transmise pour analyse visuelle.",
            image_url=image_url,
            model_used=None
        )

        # 2. Préparation du contexte système et de la mémoire persistante
        memory_ctx = memory_service.build_system_memory_context()

        # Si l'utilisateur mentionne ses e-mails / boîte de réception dans le message écrit
        email_context_str = ""
        prompt_lower = (clean_text or "").lower()
        email_keywords = ["email", "e-mail", "mail", "courriel", "boîte", "inbox", "reçu", "message"]
        if any(k in prompt_lower for k in email_keywords):
            try:
                inbox_res = await read_received_emails_async(max_count=4)
                if inbox_res.get("status") == "ok" and inbox_res.get("emails"):
                    lines = ["[DERNIERS E-MAILS REÇUS SUR PIERRECASSAGNETTES@GMAIL.COM VIA GMAIL IMAP]"]
                    for idx, em in enumerate(inbox_res["emails"], 1):
                        lines.append(f"- Mail {idx} : De '{em.get('from')}', Objet: '{em.get('subject')}', Reçu: {em.get('date')}")
                        lines.append(f"  Extrait : {em.get('snippet')}")
                        if em.get("has_attachments"):
                            lines.append(f"  Pièces jointes : {', '.join(em.get('attachments', []))}")
                    email_context_str = "\n".join(lines) + "\n\n"
            except Exception as e_err:
                print(f"[ChatService] Note : consultation email context échouée : {e_err}")

        system_instruction = (
            "Tu es J.A.R.V.I.S. (Just A Rather Very Intelligent System), l'intelligence artificielle d'élite "
            "conçue pour assister Pierre (Stark Industries).\n"
            "Ton ton est élégant, bienveillant, d'une grande rigueur intellectuelle et courtois (appelle Pierre 'Monsieur' ou 'Pierre').\n"
            "RÈGLE STRICTE DE LANGUE DE RÉPONSE : Tu réponds TOUJOURS dans la langue de l'entrée de l'utilisateur (français ou anglais uniquement). "
            "Si l'utilisateur écrit en français, réponds en français. S'il écrit en anglais, réponds en anglais. "
            "Si une troisième langue est utilisée, demande poliment une clarification en français ou en anglais sans répondre dans la troisième langue.\n\n"
            "GESTION DE LA MESSAGERIE (pierrecassagnettes@gmail.com) :\n"
            "- Si Pierre te demande de consulter ses courriels reçus ou les nouvelles de sa boîte de réception, "
            "tu as accès direct aux données relevées dans le contexte e-mails ci-dessous.\n\n"
            "CAPACITÉS MULTIMODALES & ANALYSE VISUELLE :\n"
            "- Quand Pierre te transmet une image, une photo ou une capture d'écran, effectue une analyse détaillée, experte et perspicace.\n"
            "- Identifie fidèlement les objets, le texte lisible (OCR), le code source affiché, les messages d'erreur, les interfaces ou l'environnement.\n"
            "- Si c'est un problème technique ou une panne, fournis un diagnostic limpide et la procédure pas-à-pas pour le résoudre.\n"
            "- Si une question précise est posée, apporte une réponse directe, complète et étayée.\n"
            "- Si aucune consigne n'accompagne la photo, donne une analyse synthétique des éléments clés observés et propose ton aide proactive.\n\n"
            "FORMATAGE DES RÉPONSES ÉCRITES :\n"
            "- Utilise un Markdown soigné : titres courts, puces claires, mise en valeur en gras, blocs de code balisés avec leur langage (ex: ```python).\n"
            "- Reste percutant et évite le verbiage superflu.\n\n"
            f"{email_context_str}"
            f"{memory_ctx}"
        )

        # 3. Récupération des tours de discussion récents pour la cohérence conversationnelle
        recent_history = self.get_history(limit=8)
        # Exclure le message qu'on vient d'insérer
        history_turns = [m for m in recent_history if m["id"] != user_msg_id]

        contents = []
        # Construction de l'historique préalable
        for m in history_turns:
            role = "user" if m["role"] == "user" else "model"
            contents.append(types.Content(
                role=role,
                parts=[types.Part.from_text(text=m["content"])]
            ))

        # Construction du tour actuel
        current_parts = []
        if image_bytes:
            # Ajout de l'image comme Blob multimédia
            current_parts.append(
                types.Part.from_bytes(data=image_bytes, mime_type=image_mime)
            )
        
        user_prompt = clean_text if clean_text else (
            "Voici une photo que je vous transmets. Veuillez l'analyser minutieusement, identifier ce qu'elle contient "
            "et me donner vos conclusions ou recommandations."
        )
        current_parts.append(types.Part.from_text(text=user_prompt))

        contents.append(types.Content(
            role="user",
            parts=current_parts
        ))

        # 4. Modèles candidats avec repli automatique
        models_to_try = [
            ("gemini-3.8-flash", "Gemini 3.8 Flash (Multimodal)"),
            ("gemini-3.5-flash", "Gemini 3.5 Flash (Multimodal)"),
            ("gemini-3.6-flash", "Gemini 3.6 Flash (Multimodal)"),
            ("gemini-flash-latest", "Gemini Flash Latest")
        ]

        # Priorité : client gratuit par défaut, clé payante uniquement sous consentement valide
        clients_to_try = []
        if client_free:
            clients_to_try.append((client_free, "Clé Gratuite"))
        try:
            from services.key_gate import has_paid_consent
            if client_paid and has_paid_consent():
                clients_to_try.append((client_paid, "Clé Payante"))
        except ImportError:
            pass

        if not clients_to_try:
            return {
                "status": "error",
                "message": "Aucune clé API Gemini configurée sur le serveur."
            }

        reply_text = ""
        used_model_label = "Gemini 3.8 Flash"
        used_key_label = "Clé Gratuite"
        gen_error = None

        # Notification de supervision
        action_id = f"chat_{uuid.uuid4().hex[:6]}"
        try:
            supervision_service.start_action(
                action_id=action_id,
                name="Messagerie & Analyse",
                tool="chat_multimodal_messaging",
                detail=f"Analyse de {('photo + ' if image_bytes else '')}message écrit : {user_prompt[:50]}...",
                model="Gemini 3.8 Flash",
                api_type="hybrid",
                api_label="En cours",
                cost_est="~0.002 $"
            )
        except Exception:
            pass

        for current_client, key_name in clients_to_try:
            for model_id, model_label in models_to_try:
                try:
                    print(f"[ChatService] Envoi requête multimodale à {model_id} via {key_name}...")
                    config_gen = types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.65,
                    )
                    resp = await current_client.aio.models.generate_content(
                        model=model_id,
                        contents=contents,
                        config=config_gen
                    )
                    if resp and resp.text:
                        reply_text = resp.text.strip()
                        used_model_label = f"{model_label} ({key_name})"
                        used_key_label = key_name
                        break
                except Exception as e:
                    gen_error = e
                    print(f"[ChatService] Erreur avec {model_id} ({key_name}): {e}")
                    console_monitor.record_error(
                        source="ChatService",
                        message=f"{model_id} ({key_name}): {str(e)}",
                        level="WARNING"
                    )
                    continue
            if reply_text:
                break

        supervision_service.complete_action(
            action_id=action_id,
            status="completed" if reply_text else "error",
            summary=reply_text[:120] if reply_text else str(gen_error)
        )

        if not reply_text:
            err_msg = f"Désolé Monsieur, je n'ai pas pu traiter votre demande : {str(gen_error or 'Erreur de génération')}"
            jarvis_msg_id = self.save_message(
                role="jarvis",
                content=err_msg,
                model_used="Erreur API"
            )
            return {
                "status": "error",
                "message": err_msg,
                "user_message_id": user_msg_id,
                "jarvis_message_id": jarvis_msg_id
            }

        # 5. Sauvegarde de la réponse de JARVIS
        jarvis_msg_id = self.save_message(
            role="jarvis",
            content=reply_text,
            image_url=None,
            model_used=used_model_label
        )

        return {
            "status": "success",
            "user_message": {
                "id": user_msg_id,
                "role": "user",
                "content": clean_text or "Photo transmise pour analyse visuelle.",
                "image_url": image_url,
                "created_at": datetime.datetime.now().isoformat()
            },
            "jarvis_message": {
                "id": jarvis_msg_id,
                "role": "jarvis",
                "content": reply_text,
                "model_used": used_model_label,
                "key_used": used_key_label,
                "created_at": datetime.datetime.now().isoformat()
            }
        }


# Instance globale singleton
chat_service = ChatService()
