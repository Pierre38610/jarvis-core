"""
services/architecture_service.py — Service de Connaissance Architecturale Dynamique de J.A.R.V.I.S.

Charge, surveille et extrait les spécifications techniques du fichier ARCHITECTURE_COMPLETE_JARVIS.md.
Grâce à la détection d'empreinte mtime (dernière modification), toute mise à jour du fichier est
instantanément rechargée en mémoire vive sans nécessiter de redémarrage.
"""

from __future__ import annotations

import os
import re
import time
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger("jarvis.architecture")


class ArchitectureKnowledgeService:
    """
    Gestionnaire dynamique de la connaissance architecturale de J.A.R.V.I.S.
    Assure que Jarvis connaît à tout moment sa nature, son fonctionnement, ses outils et ses limites.
    """

    def __init__(self, file_path: Optional[str] = None):
        if file_path:
            self.file_path = file_path
        else:
            # Racine du projet jarvis-core
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.file_path = os.path.join(base_dir, "ARCHITECTURE_COMPLETE_JARVIS.md")

        self._last_mtime: float = 0.0
        self._raw_content: str = ""
        self._sections: Dict[str, Dict[str, Any]] = {}
        self._cached_summary: str = ""
        self._table_of_contents: List[str] = []

    def _ensure_loaded(self, force: bool = False) -> bool:
        """Vérifie le mtime du fichier et recharge si une modification est détectée."""
        if not os.path.exists(self.file_path):
            logger.warning(f"[ArchitectureService] Fichier introuvable : {self.file_path}")
            return False

        try:
            current_mtime = os.path.getmtime(self.file_path)
            if not force and current_mtime == self._last_mtime and self._raw_content:
                return True

            with open(self.file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            self._raw_content = content
            self._last_mtime = current_mtime
            self._parse_document(content, current_mtime)

            logger.info(
                f"[ArchitectureService] ✦ Architecture rechargée dynamiquement : {len(content)} caractères, "
                f"{len(self._sections)} sections ({time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(current_mtime))})"
            )
            return True
        except Exception as e:
            logger.error(f"[ArchitectureService] Erreur lors du chargement de l'architecture : {e}")
            return False

    def _parse_document(self, content: str, mtime: float):
        """Découpe le document Markdown en sections et sous-sections structurées."""
        self._sections.clear()
        self._table_of_contents.clear()

        # Expression régulière pour découper les titres H2 et H3
        header_regex = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)
        matches = list(header_regex.finditer(content))

        for i, match in enumerate(matches):
            level = len(match.group(1))
            title = match.group(2).strip()
            start_pos = match.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            body = content[start_pos:end_pos].strip()

            sec_id = self._normalize_key(title)
            self._sections[sec_id] = {
                "title": title,
                "level": level,
                "body": body,
                "full_text": f"{match.group(0)}\n\n{body}"
            }
            if level == 2:
                self._table_of_contents.append(title)

        # Génération du résumé condensé pour injection système
        mtime_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
        self._cached_summary = (
            f"✦ CONNAISSANCE DE TON ARCHITECTURE, DE TON FONCTIONNEMENT & DE TES CAPACITÉS ✦\n"
            f"(Source dynamique synchronisée : ARCHITECTURE_COMPLETE_JARVIS.md — Dernière mise à jour : {mtime_str})\n\n"
            f"1. IDENTITÉ, RÔLE & RELATION D'ÉGAL À ÉGAL :\n"
            f"- Tu es J.A.R.V.I.S. (Just A Rather Very Intelligent System), l'assistant IA d'élite et le binôme direct de Pierre Cassagnettes (Stark Industries).\n"
            f"- Voix féminine naturelle 'Aoede'. Ton d'égal à égal : franc, direct, complice, pragmatique et décontracté (tutoiement naturel, zéro servilité, zéro flatterie artificielle).\n"
            f"- Règle d'or : Annonce toujours immédiatement à voix haute à Pierre la prise en compte de sa demande dès que tu lances une action.\n\n"
            f"2. TOPOLOGIE DISTRIBUÉE & FONCTIONNEMENT HYBRIDE :\n"
            f"- Serveur Cloud Central (Oracle Cloud VPS ARM64 Ubuntu - IP 158.178.206.213) : Cerveau applicatif permanent.\n"
            f"  * FastAPI Backend (port 8000) et passerelle Cloudflare Zero Trust (jarvis.signalcraftapps.com).\n"
            f"  * Redis 7 (port 6379) : Cache ultra-rapide, présence heartbeat des appareils, briefings du matin compilés.\n"
            f"  * PostgreSQL 16 (port 5432) : Persistance relationnelle des conversations et métadonnées.\n"
            f"  * Qdrant (port 6333) : Recherche vectorielle sémantique RAG (embeddings locaux fastembed BAAI/bge-small 384 dim).\n"
            f"  * n8n Community (port 5678) : Workflows d'automatisation no-code et webhooks locaux.\n"
            f"- PC Personnel Windows 11 de Pierre (Agent Relais jarvis_local_agent.py via WebSocket) : Exécutant local de bureau.\n"
            f"  * Pilote l'interface graphique : navigateur Google Chrome avec profil authentifié (.jarvis_chrome_profile), VS Code, VLC, Stremio, Bloc-notes, Calculatrice.\n"
            f"  * Contrôleur Deezer Web Player officiel (WebSocket port 8765).\n"
            f"  * Détection liseuses USB physiques (Kindle, Kobo).\n"
            f"  * Télémétrie matérielle physique en direct (CPU réel, RAM, batterie, processus).\n"
            f"- Exécution Asynchrone : Tu restes 100% disponible pour converser avec Pierre pendant que tes outils lourds s'exécutent en arrière-plan.\n\n"
            f"3. CATALOGUE DE TES 10 SUPER-POUVOIRS & OUTILS DISPONIBLES :\n"
            f"  1) Ingénierie Logicielle : 'run_antigravity_task' (délégation de code, tests, refactoring autonome sous Antigravity IDE).\n"
            f"  2) Navigation Web & E-commerce : 'run_browser_task', 'interact_web_page', 'prepare_web_cart_or_checkout'.\n"
            f"  3) E-Books & Liseuses : 'search_and_download_ebook', 'send_file_to_kindle', 'send_page_to_kindle', 'send_to_ereader'.\n"
            f"  4) Streaming & Média : 'play_music_deezer' (contrôle total Deezer), 'play_video_stremio' (films/séries 1080p).\n"
            f"  5) Messagerie Stark : 'send_email', 'read_emails' (Gmail pierrecassagnettes@gmail.com).\n"
            f"  6) Mémoire Hybride Unifiée : 'remember_user_fact', 'recall_user_memories', 'memoriser_information'.\n"
            f"  7) Télémétrie & Diagnostics : 'get_system_status', 'check_console_errors'.\n"
            f"  8) Automatisation n8n : 'generer_presentation' (Google Slides expertes avec recherche approfondie), 'get_active_task_status'.\n"
            f"  9) Agenda & Mobilité : 'agenda_gerer_evenement' (Google/Samsung Calendar), 'demander_morning_briefing', 'creer_rappel_push'.\n"
            f"  10) Réseau Ferroviaire France & Suède : 'rechercher_train', 'surveiller_train', 'reserver_billet_train_local'.\n"
            f"  11) Connaissance Architecturale : 'consulter_architecture_jarvis' pour explorer tes spécifications détaillées.\n\n"
            f"4. CE DONT TU N'ES PAS CAPABLE & GARDE-FOUS INVIOLABLES :\n"
            f"- AUCUN PAIEMENT BANCAIRE AUTOMATIQUE : Tu t'arrêtes STRICTEMENT avant l'étape de validation d'achat et laisses Pierre payer lui-même.\n"
            f"- AUCUN TÉLÉCHARGEMENT SANS ACCORD : Accord oral préalable explicite obligatoire de Pierre ('download_file').\n"
            f"- INTERDICTION DE CODER À L'ORAL : Ne récite jamais de code en direct dans la voix ; délègue impérativement à 'run_antigravity_task'.\n"
            f"- GESTION STRICTE DE LA CLÉ PAYANTE : Impossibilité physique d'utiliser l'API payante si l'encoche n'est pas cochée à l'écran.\n"
            f"- ARRÊT IMMÉDIAT : Arrête instantanément tout traitement sur consigne ('stop_current_action') sans chercher à continuer en secret."
        )

    def _normalize_key(self, text: str) -> str:
        """Nettoie une clé de section pour recherche insensible à la casse et aux accents."""
        clean = text.lower()
        clean = re.sub(r"[✦>#\(\)\[\]_`]", " ", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    def get_summary(self) -> str:
        """Retourne la synthèse architecturale à jour à injecter dans le prompt système ou la mémoire."""
        self._ensure_loaded()
        return self._cached_summary

    def get_full_content(self) -> str:
        """Retourne le contenu brut complet de ARCHITECTURE_COMPLETE_JARVIS.md."""
        self._ensure_loaded()
        return self._raw_content

    def get_table_of_contents(self) -> List[str]:
        """Retourne la liste des grands chapitres du document."""
        self._ensure_loaded()
        return list(self._table_of_contents)

    def lookup(self, query: Optional[str] = None, section: Optional[str] = None, max_chars: int = 4000) -> Dict[str, Any]:
        """
        Recherche et renvoie la section ou les passages les plus pertinents de l'architecture.
        """
        self._ensure_loaded()

        if not self._raw_content:
            return {
                "status": "error",
                "message": "Fichier ARCHITECTURE_COMPLETE_JARVIS.md non accessible."
            }

        # 1. Recherche par section exacte ou mot-clé dans le titre de section
        target_section = (section or query or "").strip().lower()
        if target_section:
            # Essayer de trouver une section correspondante
            matched_sections = []
            for sec_key, sec_data in self._sections.items():
                if target_section in sec_key:
                    matched_sections.append(sec_data)

            if matched_sections:
                combined_text = "\n\n---\n\n".join(s["full_text"] for s in matched_sections[:3])
                if len(combined_text) > max_chars:
                    combined_text = combined_text[:max_chars] + "\n\n[... Extrait tronqué pour concision ...]"
                return {
                    "status": "success",
                    "type": "section_match",
                    "matched_titles": [s["title"] for s in matched_sections[:3]],
                    "content": combined_text
                }

        # 2. Recherche textuelle par mots-clés dans le contenu
        if query:
            query_clean = query.strip().lower()
            keywords = [w for w in re.split(r"[\s,;']+", query_clean) if len(w) >= 3]

            scored_sections = []
            for sec_key, sec_data in self._sections.items():
                score = 0
                body_lower = sec_data["body"].lower()
                for kw in keywords:
                    if kw in sec_key:
                        score += 5
                    score += body_lower.count(kw)
                if score > 0:
                    scored_sections.append((score, sec_data))

            scored_sections.sort(key=lambda x: x[0], reverse=True)
            if scored_sections:
                top_results = [s[1]["full_text"] for s in scored_sections[:2]]
                combined = "\n\n---\n\n".join(top_results)
                if len(combined) > max_chars:
                    combined = combined[:max_chars] + "\n\n[... Extrait tronqué ...]"
                return {
                    "status": "success",
                    "type": "keyword_search",
                    "query": query,
                    "matched_titles": [s[1]["title"] for s in scored_sections[:2]],
                    "content": combined
                }

        # 3. Défaut : renvoie le sommaire et le résumé global
        toc_text = "\n".join(f"- {title}" for title in self._table_of_contents)
        return {
            "status": "success",
            "type": "summary_and_toc",
            "table_of_contents": toc_text,
            "content": f"{self._cached_summary}\n\nSOMMAIRE DES SECTIONS DISPONIBLES :\n{toc_text}"
        }


# Instance singleton
architecture_service = ArchitectureKnowledgeService()
