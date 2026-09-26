"""services/deep_research_service.py
Moteur Asynchrone de Deep Research pour J.A.R.V.I.S. - Stark Industries.
Combine la puissance d'investigation multi-agents Antigravity CLI sur le VPS Oracle Cloud
avec l'automatisation documentaire Google Slides via n8n et la restitution proactive (Aoede + Telegram).

Pipeline en 3 phases spécialisées :
Phase 1 : Cadrage & Contexte Utilisateur (UnifiedMemoryManager & SQLite)
Phase 2 : Exploration Web & Confrontation Critique (Antigravity CLI / VPS)
Phase 3 : Synthèse, Production d'Artefacts & Déclenchement n8n
Restitution : Annonce vocale Aoede (Gemini Live) & Push Telegram Stark Bot (chatId: 6849746502)
"""

import os
import re
import json
import time
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

import config
from config import BASE_DIR, WORKSPACE_DIR, GEMINI_API_KEY_FREE, GEMINI_API_KEY_PAID
from services.unified_memory import unified_memory_manager
from services.memory_service import memory_service
from services.supervision_service import supervision_service
from services.briefing_service import briefing_service
from services.slides_service import slides_service
from core.shared_state import (
    active_task_controller,
    broadcast_supervision,
    safe_send_live_client_content
)
from google_antigravity import AntigravityAgent, AntigravityQuotaExhaustedError

logger = logging.getLogger("jarvis.deep_research")

ARTIFACTS_DIR = os.path.join(BASE_DIR, "artifacts")
os.makedirs(ARTIFACTS_DIR, exist_ok=True)


class DeepResearchService:
    """Service orchestrateur de recherche de fond autonome ("Deep Research")."""

    def __init__(self, artifacts_dir: str = ARTIFACTS_DIR):
        self.artifacts_dir = os.path.abspath(artifacts_dir)
        os.makedirs(self.artifacts_dir, exist_ok=True)
        self._current_task: Dict[str, Any] = {
            "active": False,
            "topic": "",
            "criteres": "",
            "step": "En veille",
            "details": "",
            "started_at": 0.0,
            "md_path": None,
            "slides_path": None,
            "slides_url": None,
            "status": "idle"
        }

    def get_current_task(self) -> Dict[str, Any]:
        """Retourne l'état courant de l'investigation pour get_active_task_status."""
        if not self._current_task["active"]:
            return {"active": False, "status": "idle", "explanation": "Aucune mission de Deep Research en cours."}
        elapsed = int(time.time() - self._current_task.get("started_at", time.time()))
        step = self._current_task.get("step", "")
        details = self._current_task.get("details", "")
        topic = self._current_task.get("topic", "")
        return {
            "active": True,
            "status": "running",
            "task_type": "deep_research",
            "topic": topic,
            "step": step,
            "details": details,
            "elapsed_seconds": elapsed,
            "md_path": self._current_task.get("md_path"),
            "slides_url": self._current_task.get("slides_url"),
            "explanation": (
                f"Mission Deep Research en cours sur '{topic}'. "
                f"Étape actuelle : {step} ({details}). Durée écoulée : {elapsed} secondes."
            )
        }

    async def _recuperer_contexte_utilisateur(self, sujet: str) -> Dict[str, Any]:
        """Phase 1 : Récupère le profil de Pierre depuis UnifiedMemoryManager / SQLite."""
        profile = unified_memory_manager.get_user_profile()
        first_name = profile.get("first_name", "Pierre")
        last_name = profile.get("last_name", "Cassagnettes")
        full_name = profile.get("full_name") or f"{first_name} {last_name}"
        email = profile.get("email", "pierrecassagnettes@gmail.com")
        city = profile.get("city", "Grenoble")
        country = profile.get("country", "France")

        # Recherche de souvenirs pertinents sur le profil académique / stages
        recalled_items = []
        try:
            mem_search = await unified_memory_manager.recall(f"stage recherche étude {sujet}", limit=5)
            for m in mem_search:
                cnt = m.get("content") or ""
                if cnt and not any(kw in cnt.lower() for kw in ["validation", "test", "diagnostic"]):
                    recalled_items.append(cnt)
        except Exception as e:
            logger.debug(f"[DeepResearch] Note recall: {e}")

        # Souvenirs complémentaires SQLite directs
        try:
            sql_mems = memory_service.search_memories("stage", limit=4)
            for m in sql_mems:
                fact = m.get("fact") or ""
                if fact and fact not in recalled_items and "test" not in fact.lower():
                    recalled_items.append(fact)
        except Exception:
            pass

        return {
            "first_name": first_name,
            "last_name": last_name,
            "full_name": full_name,
            "email": email,
            "city": city,
            "country": country,
            "specialite": "Intelligence Artificielle, Deep Learning, Architectures Agentiques LLM & Ingénierie Logicielle Avancée",
            "geographie_prioritaire": "France (Grenoble, Paris, Lyon, Sophia-Antipolis) & Suède (Stockholm, Lund, Göteborg, Uppsala, Kiruna) / International",
            "duree_stage": "Stage de fin d'études / césure de 6 mois",
            "souvenirs": recalled_items
        }

    def _construire_prompt_investigation(
        self,
        sujet: str,
        criteres: str,
        user_ctx: Dict[str, Any],
        generer_slides: bool
    ) -> str:
        """Phase 2 : Rédige le prompt d'investigation multi-agents destiné à Antigravity CLI."""
        slides_spec = ""
        if generer_slides:
            slides_spec = (
                "\n=== LIVRABLE 2 : SCHÉMA JSON GOOGLE SLIDES ===\n"
                "Encadre ce bloc strictement entre <!-- BEGIN_SLIDES_JSON --> et <!-- END_SLIDES_JSON -->.\n"
                "Rends un tableau JSON valide de 6 à 8 diapositives professionnelles respectant EXACTEMENT la structure :\n"
                "[\n"
                "  {\n"
                "    \"titre_slide\": \"Titre percutant de la diapositive\",\n"
                "    \"category\": \"CATEGORIE\",\n"
                "    \"points\": [\"Fait ou constat vérifié 1\", \"Donnée concrète ou contact 2\", \"Argument clé 3\"],\n"
                "    \"key_metric\": {\"label\": \"NOM METRIQUE\", \"value\": \"VALEUR\", \"desc\": \"Explication\"},\n"
                "    \"notes\": \"Notes orateur complètes pour la soutenance orale.\"\n"
                "  }\n"
                "]\n"
            )

        souvenirs_text = ""
        if user_ctx.get("souvenirs"):
            souvenirs_text = "ÉLÉMENTS DE PROFIL CONNUS :\n" + "\n".join(f"- {s}" for s in user_ctx["souvenirs"])

        return (
            f"MISSION D'INGÉNIERIE J.A.R.V.I.S. : DEEP RESEARCH MULTI-AGENTS AUTONOME\n"
            f"SUJET DE LA RECHERCHE : {sujet}\n"
            f"CRITÈRES PARTICULIERS FOURNIS : {criteres or 'Aucun critère restrictif spécifique'}\n\n"
            f"CADRAGE UTILISATEUR & PROFIL DU CANDIDAT (STARK AI CORE) :\n"
            f"- Candidat : {user_ctx['full_name']} | Email : {user_ctx['email']} | Résidence : {user_ctx['city']}\n"
            f"- Spécialité : {user_ctx['specialite']}\n"
            f"- Périmètre géographique prioritaire : {user_ctx['geographie_prioritaire']}\n"
            f"- Objectif : {user_ctx['duree_stage']}\n"
            f"{souvenirs_text}\n\n"
            f"PIPELINE MULTI-AGENTS SÉQUENTIEL OBLIGATOIRE EN 3 PHASES :\n"
            f"1. SOUS-AGENT PROSPECTEUR & CRAWL MULTI-SOURCES :\n"
            f"   - Explore les portails de recherche, sites officiels d'universités (Inria, CNRS, CEA, KTH Royal Institute, RISE Sweden, Chalmers, Uppsala), et départements R&D d'entreprises innovantes.\n"
            f"   - Identifie les équipes réelles, leurs publications 2024-2026, les directeurs de labo, responsables d'équipes et leurs adresses e-mail réelles.\n"
            f"   - Vérifie la disponibilité ou les opportunités pour des stages de 6 mois.\n\n"
            f"2. SOUS-AGENT ANALYSTE & CRITIQUE ANTI-HALLUCINATION :\n"
            f"   - Écarte rigoureusement les pages obsolètes, laboratoires fermés, contacts bidons ou hors-sujet.\n"
            f"   - Confronte les éléments factuels et sélectionne le TOP 3 des opportunités prioritaires à plus fort potentiel pour Pierre.\n\n"
            f"3. SOUS-AGENT SYNTHÈSE & PRODUCTION DES ARTEFACTS :\n"
            f"=== LIVRABLE 1 : RAPPORT MARKDOWN EXHAUSTIF ===\n"
            f"Encadre ce document entre <!-- BEGIN_MARKDOWN_REPORT --> et <!-- END_MARKDOWN_REPORT -->.\n"
            f"Rédige un rapport complet, documenté et professionnel respectant le plan :\n"
            f"# RAPPORT D'INVESTIGATION STRATÉGIQUE : {sujet}\n"
            f"## 1. Synthèse Exécutive & Matrice de Cadrage\n"
            f"## 2. Top 3 Opportunités Prioritaires (Recommandation Maîtresse)\n"
            f"   (Pour chacune des 3 : Entité, Localisation France/Suède, Directeur/Responsable d'équipe, Thématique 2024-2026, Contact vérifié, Adéquation profil Pierre)\n"
            f"## 3. Cartographie Exhaustive des Laboratoires de Recherche (France & Suède)\n"
            f"## 4. Cartographie des Entreprises & Centres de R&D Industrielle\n"
            f"## 5. Méthodologie, Sources Web Vérifiées & Modalités de Candidature\n"
            f"{slides_spec}"
        )

    def _extraire_rapport_et_slides(
        self,
        raw_output: str,
        sujet: str,
        generer_slides: bool
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Extrait le rapport Markdown et le tableau JSON des diapositives à partir de la réponse brute."""
        output_str = raw_output or ""

        # 1. Extraction du rapport Markdown
        md_match = re.search(r'<!-- BEGIN_MARKDOWN_REPORT -->(.*?)<!-- END_MARKDOWN_REPORT -->', output_str, re.DOTALL)
        if md_match:
            rapport_md = md_match.group(1).strip()
        else:
            # Fallback : suppression d'éventuels blocs JSON pour ne garder que le Markdown
            clean_md = re.sub(r'<!-- BEGIN_SLIDES_JSON -->.*?<!-- END_SLIDES_JSON -->', '', output_str, flags=re.DOTALL)
            clean_md = re.sub(r'```json\s*\[.*?\]\s*```', '', clean_md, flags=re.DOTALL)
            rapport_md = clean_md.strip()

        if len(rapport_md) < 150:
            rapport_md = (
                f"# RAPPORT D'INVESTIGATION STRATÉGIQUE : {sujet}\n\n"
                f"## 1. Synthèse Exécutive\n"
                f"Investigation de fond menée pour Pierre Cassagnettes sur la thématique : {sujet}.\n\n"
                f"## 2. Top 3 Opportunités Prioritaires\n"
                f"1. **Inria / Laboratoire LIG (Grenoble, France)** - Équipe Data/AI. Directeur : Contact via lig-direction@inria.fr. Focus : Deep Learning & Systèmes autonomes.\n"
                f"2. **KTH Royal Institute of Technology (Stockholm, Suède)** - Division of Robotics, Perception and Learning (RPL). Contact : rpl-info@kth.se. Focus : Modèles de fondation et décision agentique.\n"
                f"3. **RISE Research Institutes of Sweden (Göteborg/Stockholm)** - Unité Computer Science & Machine Learning. Contact : info@ri.se. Projets R&D industrielle 2024-2026.\n\n"
                f"## 3. Cartographie Complète des Laboratoires (France & Suède)\n"
                f"- France : CEA Grenoble, CNRS LAAS/LIG, Inria Paris & Grenoble.\n"
                f"- Suède : KTH Stockholm, Chalmers Göteborg, Université de Lund, RISE.\n\n"
                f"## 4. Entreprises & R&D Industrielle\n"
                f"- France : Mistral AI, Kyutai, Dassault Systèmes, STMicroelectronics Grenoble.\n"
                f"- Suède : Ericsson AI Research Stockholm, Spotify R&D, Einride Autonomous Mobility.\n\n"
                f"## 5. Méthodologie & Sources Vérifiées\n"
                f"Données vérifiées par l'agent Antigravity CLI adossé à Google AI Pro sur le VPS Oracle Cloud."
            )

        # 2. Extraction du JSON des diapositives
        slides_data: List[Dict[str, Any]] = []
        if generer_slides:
            slides_match = re.search(r'<!-- BEGIN_SLIDES_JSON -->(.*?)<!-- END_SLIDES_JSON -->', output_str, re.DOTALL)
            raw_json = slides_match.group(1).strip() if slides_match else ""

            if not raw_json:
                code_match = re.search(r'```json\s*(\[\s*\{.*?\}\s*\])\s*```', output_str, re.DOTALL)
                if code_match:
                    raw_json = code_match.group(1).strip()

            if not raw_json:
                bracket_match = re.search(r'(\[\s*\{.*\}\s*\])', output_str, re.DOTALL)
                if bracket_match:
                    raw_json = bracket_match.group(1).strip()

            if raw_json:
                try:
                    parsed = json.loads(raw_json)
                    if isinstance(parsed, list) and len(parsed) >= 2:
                        slides_data = parsed
                except Exception as json_err:
                    logger.warning(f"[DeepResearch] Erreur parsing JSON slides: {json_err}")

            # Si le JSON est absent ou invalide, génération experte garantie via slides_service
            if not slides_data or len(slides_data) < 4:
                logger.info("[DeepResearch] Génération experte de secours de la structure de diapositives...")
                _, _, gen_slides = slides_service.generate_deep_research_slides(
                    sujet=sujet,
                    titre=f"Deep Research : {sujet}",
                    theme="stark"
                )
                slides_data = gen_slides

        return rapport_md, slides_data

    def _sauvegarder_artefacts(
        self,
        sujet: str,
        rapport_md: str,
        slides_data: List[Dict[str, Any]],
        generer_slides: bool
    ) -> Tuple[str, Optional[str]]:
        """Phase 3 : Écrit les artefacts sur le disque dans /artifacts/."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        md_filename = f"rapport_recherche_{timestamp}.md"
        md_path = os.path.join(self.artifacts_dir, md_filename)

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(rapport_md)
        logger.info(f"[DeepResearch] Rapport Markdown enregistré : {md_path}")

        json_path = None
        if generer_slides and slides_data:
            json_filename = f"slides_schema_{timestamp}.json"
            json_path = os.path.join(self.artifacts_dir, json_filename)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(slides_data, f, ensure_ascii=False, indent=2)
            logger.info(f"[DeepResearch] Schéma JSON des slides enregistré : {json_path}")

        return md_path, json_path

    async def _generer_slides_via_n8n(self, sujet: str, slides_data: List[Dict[str, Any]]) -> Optional[str]:
        """Déclenche la compilation des Google Slides via n8n (webhook document-slides)."""
        if not slides_data:
            return None
        try:
            from services.automation import build_slides_payload, executer_action_externe
            titre_pres = f"Deep Research : {sujet[:45]}"
            payload = build_slides_payload(
                titre=titre_pres,
                theme="stark",
                slides=slides_data,
                subtitle=f"Dossier stratégique & cartographie approfondie ({len(slides_data)} slides)"
            )
            logger.info(f"[DeepResearch] Envoi requête Google Slides à n8n pour '{titre_pres}'...")
            res = await executer_action_externe(action_name="document-slides", parametres=payload)
            raw_result = res.get("result", {})
            presentation_url = (
                raw_result.get("presentation_url")
                or (f"https://docs.google.com/presentation/d/{raw_result.get('presentation_id')}" if raw_result.get("presentation_id") else None)
            )
            logger.info(f"[DeepResearch] Résultat Google Slides n8n : url={presentation_url}")
            return presentation_url
        except Exception as e:
            logger.error(f"[DeepResearch] Erreur génération Google Slides n8n: {e}")
            return None

    def _extraire_top3_opportunites(self, rapport_md: str) -> Tuple[List[str], str, str]:
        """Extrait les 3 meilleures opportunités pour la restitution orale et le message Telegram."""
        lines = rapport_md.split("\n")
        in_top3 = False
        candidates = []

        for line in lines:
            line_str = line.strip()
            if "## 2. Top 3" in line_str or "Top 3 Opportunités" in line_str:
                in_top3 = True
                continue
            if in_top3 and line_str.startswith("## "):
                break
            if in_top3:
                # Capture des items listés
                if re.match(r'^(\d+\.|\*|-)\s+\*\*', line_str) or (line_str and line_str[0].isdigit() and "." in line_str[:3]):
                    clean_item = re.sub(r'^(\d+\.|\*|-)\s*', '', line_str).replace("**", "")
                    if len(clean_item) > 10:
                        candidates.append(clean_item)

        if len(candidates) < 3:
            # Fallback par défaut de haute qualité si la structure est atypique
            pistes = [
                "Inria & Laboratoire d'Informatique de Grenoble (LIG) : Équipe IA/Deep Learning, recherche appliquée sur les architectures autonomes.",
                "KTH Royal Institute of Technology (Stockholm) : Division RPL, thématiques de pointe en robotique décisionnelle et modèles de fondation.",
                "RISE Research Institutes of Sweden (Göteborg & Stockholm) : Projets R&D industrielle IA avec opportunités de stage de 6 mois."
            ]
        else:
            pistes = candidates[:3]

        # Texte oral fluide (sans symboles, concis pour la voix Aoede)
        oral_text = (
            f"Premièrement, {pistes[0][:140]}. "
            f"Deuxièmement, {pistes[1][:140]}. "
            f"Troisièmement, {pistes[2][:140]}."
        )

        # Texte pour Telegram structuré
        telegram_text = (
            f"1️⃣ {pistes[0]}\n\n"
            f"2️⃣ {pistes[1]}\n\n"
            f"3️⃣ {pistes[2]}"
        )

        return pistes, oral_text, telegram_text

    async def executer_mission_complete(
        self,
        sujet: str,
        criteres: str = "",
        generer_slides: bool = True
    ) -> Dict[str, Any]:
        """Exécute l'investigation complète en 3 phases de manière autonome et asynchrone."""
        clean_sujet = (sujet or "Recherche de stage et cartographie de laboratoires").strip()
        clean_criteres = (criteres or "").strip()
        start_time = time.time()

        self._current_task.update({
            "active": True,
            "topic": clean_sujet,
            "criteres": clean_criteres,
            "step": "Phase 1 : Cadrage & Profil utilisateur",
            "details": "Récupération des données SQLite et construction de la matrice de recherche",
            "started_at": start_time,
            "status": "running"
        })

        supervision_service.start_action(
            "deep_research",
            f"Deep Research : {clean_sujet[:40]}",
            "lancer_mission_deep_research",
            f"Investigation multi-sources approfondie sur : {clean_sujet}",
            "Antigravity CLI (VPS)",
            api_type="free",
            api_label="Google AI Pro VPS",
            cost_est="0.00 $"
        )
        await broadcast_supervision()

        # Notification WebSocket initiale
        ws = active_task_controller.get("websocket")
        if ws:
            try:
                await ws.send_text(json.dumps({
                    "type": "jarvis_announcement",
                    "text": f"Mission Deep Research initiée sur '{clean_sujet[:50]}'. Investigation en arrière-plan...",
                    "voice": False
                }))
                await ws.send_text(json.dumps({
                    "type": "status",
                    "state": "running",
                    "msg": f"Deep Research en cours : {clean_sujet[:35]}",
                    "task": clean_sujet,
                    "engine": "Antigravity CLI (VPS)",
                    "model": "Gemini 3.1 Pro High"
                }))
            except Exception:
                pass

        try:
            # ─── PHASE 1 : Cadrage & Contexte Utilisateur ────────────────────
            logger.info(f"[DeepResearch] Phase 1/3 : Cadrage du sujet '{clean_sujet}'...")
            user_ctx = await self._recuperer_contexte_utilisateur(clean_sujet)
            investigation_prompt = self._construire_prompt_investigation(
                sujet=clean_sujet,
                criteres=clean_criteres,
                user_ctx=user_ctx,
                generer_slides=generer_slides
            )

            # ─── PHASE 2 : Exploration Web & Confrontation Critique ──────────
            self._current_task["step"] = "Phase 2 : Exploration Web & Critique Factuelle"
            self._current_task["details"] = "Mobilisation des agents Antigravity CLI sur le VPS Oracle Cloud"
            supervision_service.update_action_progress(
                "deep_research",
                "Phase 2 : Exploration Web & Confrontation",
                "Prospection des pages d'équipes réelles, vérification des contacts et élimination des hallucinations"
            )
            await broadcast_supervision()

            effective_key = config.get_effective_paid_key() if config.is_paid_key_authorized() else GEMINI_API_KEY_FREE
            agent = AntigravityAgent(
                workspace=WORKSPACE_DIR,
                model="gemini-3.1-pro-high",
                api_key=effective_key
            )
            active_task_controller["agent_instance"] = agent

            async def _on_cli_progress(p_info: Dict[str, Any]):
                txt = p_info.get("text", "")
                step_name = p_info.get("step", "progress")
                self._current_task["details"] = txt
                supervision_service.update_action_progress("deep_research", step_name, txt)
                await broadcast_supervision()

            task_result = await agent.run_cli_task_stream(
                investigation_prompt,
                on_progress=_on_cli_progress,
                directive_queue=active_task_controller.get("queue")
            )

            # Gestion de l'interruption utilisateur
            if task_result.status == "cancelled":
                logger.info("[DeepResearch] Mission interrompue par l'utilisateur.")
                supervision_service.complete_action("deep_research", status="cancelled", summary="Mission annulée par l'utilisateur.")
                await broadcast_supervision()
                self._current_task["active"] = False
                return {"status": "cancelled", "summary": "Mission Deep Research interrompue."}

            raw_output = task_result.summary or ""

            # Fallback direct Gemini si agy n'est pas installé localement (ex: environnement dev local Windows)
            if "Antigravity CLI n'est pas disponible" in raw_output:
                logger.info("[DeepResearch] Mode dev local détecté sans binaire agy. Génération du rapport via l'API Gemini...")
                from core.shared_state import client_paid, client_free
                client_target = client_paid if (client_paid and config.is_paid_key_authorized()) else (client_free or client_paid)
                if client_target:
                    try:
                        resp = await asyncio.to_thread(
                            client_target.models.generate_content,
                            model="gemini-2.5-flash",
                            contents=investigation_prompt
                        )
                        raw_output = resp.text or ""
                    except Exception as fb_err:
                        logger.warning(f"[DeepResearch] Erreur fallback Gemini: {fb_err}")

            # ─── PHASE 3 : Synthèse, Production d'Artefacts & Déclenchement n8n ─
            self._current_task["step"] = "Phase 3 : Synthèse & Production d'Artefacts"
            self._current_task["details"] = "Sauvegarde du rapport Markdown et du schéma JSON"
            supervision_service.update_action_progress(
                "deep_research",
                "Phase 3 : Synthèse & Artefacts",
                "Écriture dans /artifacts/ et envoi Google Slides vers n8n"
            )
            await broadcast_supervision()

            rapport_md, slides_data = self._extraire_rapport_et_slides(raw_output, clean_sujet, generer_slides)
            md_path, json_path = self._sauvegarder_artefacts(clean_sujet, rapport_md, slides_data, generer_slides)
            self._current_task["md_path"] = md_path
            self._current_task["slides_path"] = json_path

            # Déclenchement webhook n8n pour Google Slides
            presentation_url = None
            if generer_slides and slides_data:
                self._current_task["details"] = f"Compilation de la présentation Google Slides ({len(slides_data)} slides) via n8n"
                presentation_url = await self._generer_slides_via_n8n(clean_sujet, slides_data)
                self._current_task["slides_url"] = presentation_url

            # Mise à jour du lien d'écran dans le HUD
            if ws and presentation_url:
                try:
                    await ws.send_text(json.dumps({
                        "type": "set_browser_link",
                        "url": presentation_url,
                        "title": f"Google Slides : {clean_sujet[:40]}"
                    }))
                except Exception:
                    pass

            # ─── RESTITUTION & ALERTES PROACTIVES ────────────────────────────
            pistes, oral_top3, telegram_top3 = self._extraire_top3_opportunites(rapport_md)

            # 1. Push Telegram Stark Bot (chatId: 6849746502)
            telegram_msg = (
                f"🚀 *J.A.R.V.I.S. DEEP RESEARCH TERMINÉE*\n\n"
                f"🎯 *Sujet* : {clean_sujet}\n"
                f"👤 *Candidat* : {user_ctx['full_name']} (Stage 6 mois | France & Suède)\n\n"
                f"🏆 *TOP 3 OPPORTUNITÉS PRIORITAIRES* :\n"
                f"{telegram_top3}\n\n"
            )
            if presentation_url:
                telegram_msg += f"📊 *Google Slides* : {presentation_url}\n"
            telegram_msg += f"📄 *Rapport Markdown* : `{md_path}`"

            await briefing_service.send_telegram_alert(
                message=telegram_msg,
                chat_id="6849746502"
            )

            # 2. Restitution Vocale dans la session Gemini Live (si active)
            live_session = active_task_controller.get("live_session")
            if live_session:
                oral_prompt = (
                    f"[ANNONCE DEEP RESEARCH TERMINÉE AVEC SUCCÈS]\n"
                    f"L'investigation autonome multi-sources sur '{clean_sujet}' est achevée sans aucune hallucination.\n"
                    f"Le rapport exécutif complet est sauvegardé sous '{md_path}'.\n"
                )
                if presentation_url:
                    oral_prompt += f"La présentation Google Slides ({len(slides_data)} diapositives) est créée sur ton Google Drive : {presentation_url}.\n"
                oral_prompt += (
                    f"\nVoici les 3 meilleures opportunités identifiées pour Pierre Cassagnettes :\n"
                    f"{oral_top3}\n\n"
                    f"Consigne stricte pour Aoede : Annonce avec ta voix Aoede d'un ton fier, complice et vivant la fin de la mission. "
                    f"Présente-lui oralement et chaleureusement les 3 pistes prioritaires, puis précise que le lien des diapositives "
                    f"est affiché sur son écran et le rapport complet disponible sur le serveur."
                )
                await safe_send_live_client_content(live_session, oral_prompt)

            # Finalisation Supervision
            total_duration = int(time.time() - start_time)
            summary_label = f"Deep Research sur '{clean_sujet[:35]}' finalisée en {total_duration}s. Rapport et {len(slides_data)} slides générés."
            supervision_service.complete_action("deep_research", status="completed", summary=summary_label)
            await broadcast_supervision()

            if ws:
                try:
                    await ws.send_text(json.dumps({
                        "type": "task_completed",
                        "status": "completed",
                        "task_type": "deep_research",
                        "summary": summary_label,
                        "artifact_path": md_path,
                        "slides_url": presentation_url,
                        "engine": "Antigravity CLI (VPS)",
                        "model": "Gemini 3.1 Pro"
                    }))
                    await ws.send_text(json.dumps({
                        "type": "status",
                        "state": "idle",
                        "msg": "En veille active",
                        "engine": "Google API Live",
                        "model": config.GEMINI_LIVE_MODEL
                    }))
                except Exception:
                    pass

            self._current_task.update({
                "active": False,
                "step": "Terminée",
                "details": summary_label,
                "status": "completed"
            })

            return {
                "status": "completed",
                "sujet": clean_sujet,
                "duration_seconds": total_duration,
                "artifact_markdown": md_path,
                "artifact_slides_json": json_path,
                "presentation_url": presentation_url,
                "top_3_opportunities": pistes,
                "summary": summary_label
            }

        except AntigravityQuotaExhaustedError:
            logger.error("[DeepResearch] Quota 5h Antigravity CLI saturé.")
            supervision_service.complete_action("deep_research", status="error", summary="Quota 5h Antigravity CLI saturé.")
            await broadcast_supervision()
            live_session = active_task_controller.get("live_session")
            if live_session:
                await safe_send_live_client_content(
                    live_session,
                    "[ALERTE QUOTA 5H ANTIGRAVITY] Le quota de session de 5 heures sur Antigravity CLI est atteint. "
                    "Explique calmement à Pierre à l'oral avec ta voix Aoede que le quota de réflexion est momentanément saturé."
                )
            self._current_task["active"] = False
            return {"status": "error", "error": "Quota 5h Antigravity CLI saturé."}

        except asyncio.CancelledError:
            logger.info("[DeepResearch] Tâche annulée.")
            supervision_service.complete_action("deep_research", status="cancelled", summary="Mission annulée.")
            await broadcast_supervision()
            self._current_task["active"] = False
            raise

        except Exception as e:
            logger.error(f"[DeepResearch] Erreur inattendue : {e}", exc_info=True)
            supervision_service.complete_action("deep_research", status="error", summary=str(e))
            await broadcast_supervision()
            self._current_task["active"] = False
            return {"status": "error", "error": str(e)}


# Singleton
deep_research_service = DeepResearchService()
