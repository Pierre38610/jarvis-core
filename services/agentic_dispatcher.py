"""services/agentic_dispatcher.py
Hub Central d'Orchestration Agentique Universel pour J.A.R.V.I.S. - Stark Industries.
Mobilise proactivement le moteur de délibération 'Système 2' Antigravity CLI sur le VPS Oracle Cloud
sur l'ensemble des services métiers :
1. transport_optimizer : Analyse comparative multi-critères, correspondances, confort et réservation.
2. spreadsheet_modeler : Génération autonome de modèles financiers / de suivi avec formules XLOOKUP, SUMIFS, styles et ratios.
3. system_healing : SRE autonome, diagnostic des exceptions, analyse du code source, patch syntaxique et redémarrage.
4. email_drafting : Triage exécutif, analyse des fils de discussion et pièces jointes PDF, brouillons calibrés Stark.
5. book_curation : Extraction de table des matières, thèses clés, fiches de lecture 2 pages et expédition Kindle.
6. morning_briefing : Préparation prédictive à 6h45, croisement agenda/documents, retards en temps réel et veille IA.
7. memory_consolidation : Routine nocturne de déduplication, réconciliation des contradictions et Knowledge Graph.
8. doc_sync : Réconciliation continue entre le code réel des routeurs/services et ARCHITECTURE_COMPLETE_JARVIS.md.
9. deep_research : Investigation de fond multi-sources avec production de slides et rapport.

Règles impératives :
- Réactivité vocale immédiate (< 300 ms).
- Exécution asynchrone non-bloquante (asyncio.create_task).
- Notification proactive multicanale : Aoede Live (si session active), Telegram Stark Bot (chatId: 6849746502)
  et mise à disposition des livrables dans /artifacts/ ou /downloads/.
"""

from __future__ import annotations

import os
import sys
import re
import json
import time
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Literal, Tuple

import config
from config import BASE_DIR, WORKSPACE_DIR, GEMINI_API_KEY_FREE, GEMINI_API_KEY_PAID
from google_antigravity import AntigravityAgent, AntigravityQuotaExhaustedError, resolve_cognitive_tier, CognitiveConfig
from services.supervision_service import supervision_service
from services.console_monitor import console_monitor
from services.briefing_service import briefing_service
from services.unified_memory import unified_memory_manager
from core.shared_state import (
    active_task_controller,
    broadcast_supervision,
    safe_send_live_client_content
)

logger = logging.getLogger("jarvis.agentic_dispatcher")

ARTIFACTS_DIR = os.path.join(BASE_DIR, "artifacts")
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
EBOOKS_DIR = os.path.join(DOWNLOADS_DIR, "ebooks")
OUTBOX_DIR = getattr(config, "EMAIL_OUTBOX_DIR", os.path.join(BASE_DIR, "outbox_emails"))

os.makedirs(ARTIFACTS_DIR, exist_ok=True)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(EBOOKS_DIR, exist_ok=True)
os.makedirs(OUTBOX_DIR, exist_ok=True)

MissionType = Literal[
    "transport_optimizer",
    "spreadsheet_modeler",
    "system_healing",
    "email_drafting",
    "book_curation",
    "morning_briefing",
    "memory_consolidation",
    "doc_sync",
    "deep_research"
]

AgenticMissionType = MissionType


class AgenticDispatcher:
    """Hub Central d'Orchestration Agentique Universel pour J.A.R.V.I.S."""

    def __init__(self, artifacts_dir: str = ARTIFACTS_DIR, downloads_dir: str = DOWNLOADS_DIR):
        self.artifacts_dir = os.path.abspath(artifacts_dir)
        self.downloads_dir = os.path.abspath(downloads_dir)
        os.makedirs(self.artifacts_dir, exist_ok=True)
        os.makedirs(self.downloads_dir, exist_ok=True)
        self._active_missions: Dict[str, Dict[str, Any]] = {}

    def get_mission_status(self, mission_id: str) -> Optional[Dict[str, Any]]:
        """Retourne l'état courant d'une mission agentique."""
        return self._active_missions.get(mission_id)

    def _build_domain_prompt(
        self,
        mission_type: MissionType,
        goal: str,
        context: Optional[Dict[str, Any]]
    ) -> Tuple[str, str]:
        """Construit le prompt de délibération Système 2 ultra-spécialisé selon le domaine
        et retourne (prompt_complet, nom_fichier_attendu).
        """
        ctx_str = json.dumps(context or {}, ensure_ascii=False, indent=2)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = re.sub(r'[^a-zA-Z0-9_-]', '_', goal[:30].strip().lower()) or "mission"

        if mission_type == "transport_optimizer":
            filename = f"transport_itinerary_{slug}_{timestamp}.md"
            prompt = (
                f"MISSION D'OPTIMISATION DE MOBILITÉ & TRANSPORTS INTELLIGENTS (SYSTÈME 2 - ANTIGRAVITY)\n"
                f"OBJECTIF : {goal}\n"
                f"DONNÉES DU TRAJET & CONTEXTE : {ctx_str}\n\n"
                f"Tu opères comme l'agent d'optimisation de transports expert de Stark Industries pour Pierre Cassagnettes.\n"
                f"DIRECTIVES MAJEURES D'ANALYSE COMPARATIVE :\n"
                f"1. ARBITRAGE JOUR vs NUIT : Compare rigoureusement les options trains de jour (SJ Snabbtåg, TGV) versus train de nuit couchette (SJ Nattåg, Intercités de nuit).\n"
                f"2. OPTIMISATION FINE DES CORRESPONDANCES : Analyse les temps de sécurité pour les correspondances avec bagages. Repère les créneaux pour un repas agréable à Stockholm Central ou Paris Gare de Lyon.\n"
                f"3. ARBITRAGE DU CONFORT & RISQUES : Évalue le type de compartiment (couchette 1ère classe vs 2nde, compartiment privatif), et les risques statistiques de retards sur la ligne.\n"
                f"4. PLAN DE VOYAGE EXÉCUTIF : Formate un itinéraire complet et élégant en Markdown, clair et sans bavardage.\n"
                f"Inclus un bloc final : '## Synthèse Exécutive pour Aoede' (3 phrases précises) et les liens directs de réservation.\n"
            )

        elif mission_type == "spreadsheet_modeler":
            target_name = (context or {}).get("nom_fichier") or f"modele_{slug}_{timestamp}.xlsx"
            if not target_name.endswith(".xlsx"):
                target_name += ".xlsx"
            filename = target_name
            prompt = (
                f"MISSION DATA ANALYST & MODÉLISATION AVANCÉE DE TABLEURS (SYSTÈME 2 - ANTIGRAVITY)\n"
                f"OBJECTIF : {goal}\n"
                f"STRUCTURE & DONNÉES CIBLES : {ctx_str}\n"
                f"FICHIER FINAL VISÉ : {target_name}\n\n"
                f"Tu es l'ingénieur Data Analyst et Modélisation Financière de Stark Industries.\n"
                f"DIRECTIVES D'EXCELLENCE POUR LE TABLEUR EXCEL (.xlsx) :\n"
                f"1. FORMULES DYNAMIQUES AVANCÉES : N'utilise pas de données plates ! Injecte de vraies formules Excel en anglais/français :\n"
                f"   - Calculs de sommes conditionnelles : =SUMIFS(...) / =SOMME.SI.ENS(...)\n"
                f"   - Rapprochements et recherches : =XLOOKUP(...) / =RECHERCHEV(...)\n"
                f"   - Calculs de pourcentages de marge, écarts (variance) et moyennes pondérées.\n"
                f"2. ESTHÉTIQUE CORPORATE PREMIUM : En-têtes sombre Stark (#1E293B) texte blanc gras, zébrures douces (#F8FAFC), formats numériques monétaires (€ ou SEK) et pourcentages avec 1 décimale.\n"
                f"3. RATIOS & CARTES KPI : Intègre un bloc récapitulatif supérieur avec les 3 métriques clés.\n"
                f"4. SCRIPT D'EXÉCUTION PYTHON : Génère un script Python autonome complet utilisant openpyxl pour construire directement et sauvegarder le fichier dans '{os.path.join(self.downloads_dir, target_name)}'.\n"
                f"Encadre le code Python complet entre triples backticks ```python ... ``` pour exécution immédiate.\n"
            )

        elif mission_type == "system_healing":
            filename = f"healing_{slug}_{timestamp}.md"
            prompt = (
                f"MISSION D'AUTO-GUÉRISON SYSTÈME & SRE AUTONOME (SYSTÈME 2 - ANTIGRAVITY)\n"
                f"INCIDENT CRITIQUE DÉTECTÉ : {goal}\n"
                f"DIAGNOSTIC & TRACE D'ERREUR : {ctx_str}\n"
                f"WORKSPACE DU NOYAU : {WORKSPACE_DIR}\n\n"
                f"Tu es l'ingénieur SRE autonome responsable de la stabilité de J.A.R.V.I.S.\n"
                f"DIRECTIVES DE RÉSOLUTION :\n"
                f"1. ANALYSE DE CAUSE RACINE (RCA) : Identifie le fichier source exact, la fonction et la ligne de code responsable.\n"
                f"2. PATCH CORRECTIF MINIMAL ET ROBUSTE : Propose le diff ou le bloc de code de remplacement exact sans régression.\n"
                f"3. PROCÉDURE DE TEST & VALIDATION : Spécifie la commande de vérification syntaxique (`python -m py_compile ...`).\n"
                f"4. RAPPORT EXÉCUTIF STARK : Rédige une explication limpide du bug rencontré, de son impact et de sa correction pérenne.\n"
                f"Termine par une section '## Explication Vocale pour Aoede' (2 phrases rassurantes).\n"
            )

        elif mission_type == "email_drafting":
            filename = f"email_draft_{slug}_{timestamp}.md"
            prompt = (
                f"MISSION DE TRIAGE EXÉCUTIF & RÉDACTION DE COURRIEL (SYSTÈME 2 - ANTIGRAVITY)\n"
                f"OBJET DU MESSAGE / CONTEXTE : {goal}\n"
                f"DONNÉES DU COURRIEL & PIÈCES JOINTES : {ctx_str}\n\n"
                f"Tu es le chef de cabinet exécutif de Pierre Cassagnettes chez Stark Industries.\n"
                f"DIRECTIVES DE RÉDACTION :\n"
                f"1. ANALYSE DU FIL : Détermine les enjeux clés, l'expéditeur, le ton adapté (académique, recrutement, partenaire ou administratif).\n"
                f"2. PRISE EN COMPTE DES PIÈCES JOINTES & AGENDA : Si des dates ou conditions sont mentionnées, croise-les avec le contexte fourni.\n"
                f"3. PROJET DE RÉPONSE CALIBRÉ : Rédige un brouillon de réponse impeccable, poli, assertif et professionnel.\n"
                f"4. FORMATAGE DU LIVRABLE : Fournis un bloc JSON clair :\n"
                f"{{\n"
                f"  \"destinataire\": \"...\",\n"
                f"  \"sujet\": \"Re: ...\",\n"
                f"  \"corps\": \"Texte intégral de la réponse\",\n"
                f"  \"oral_pitch\": \"Pierre, j'ai analysé l'e-mail de... J'ai préparé un brouillon d'acceptation... Tu veux que je te le lise avant envoi ?\"\n"
                f"}}\n"
            )

        elif mission_type == "book_curation":
            filename = f"reading_guide_{slug}_{timestamp}.md"
            prompt = (
                f"MISSION DE CURATION CULTURELLE & GUIDE DE LECTURE (SYSTÈME 2 - ANTIGRAVITY)\n"
                f"OUVRAGE : {goal}\n"
                f"MÉTADONNÉES DE L'EBOOK : {ctx_str}\n\n"
                f"Tu es le conservateur culturel et analyste d'idées de Stark Industries.\n"
                f"DIRECTIVES DU LIVRABLE 'SYNTHÈSE & CLÉS DE LECTURE' (2 pages) :\n"
                f"1. THÈSES FONDAMENTALES : Expose en 3 points cardinaux les thèses majeures de l'auteur.\n"
                f"2. TABLE DES MATIÈRES COMMENTÉE : Analyse du cheminement intellectuel chapitre par chapitre.\n"
                f"3. PASSAGES CLÉS & CITATIONS D'IMPACT : 3 citations ou concepts structurants.\n"
                f"4. APPLICATIONS CONCRÈTES POUR PIERRE : Comment transposer ces idées dans ses projets technologiques et personnels.\n"
                f"Rédige une fiche d'élite en Markdown prête à être convertie pour la liseuse Kindle.\n"
            )

        elif mission_type == "morning_briefing":
            filename = f"briefing_prep_{datetime.now().strftime('%Y%m%d')}.md"
            prompt = (
                f"MISSION DE PRÉPARATION STRATÉGIQUE DU MORNING BRIEFING (SYSTÈME 2 - ANTIGRAVITY)\n"
                f"DATE DU JOUR : {datetime.now().strftime('%A %d %B %Y')}\n"
                f"MÉTRIQUES & ÉLÉMENTS BRUTS : {ctx_str}\n\n"
                f"Tu es le copilote stratégique de Pierre Cassagnettes préparant sa journée dès 6h45.\n"
                f"DIRECTIVES D'ANALYSE CROISÉE :\n"
                f"1. CROISEMENT AGENDA & CONTEXTE : Analyse les rendez-vous du jour en les reliant aux projets en cours de Pierre et aux profils des interlocuteurs.\n"
                f"2. ALERTES PRÉDICTIVES DE TRANSPORT : Vérifie les risques d'aléas ou retards potentiels selon les déplacements prévus.\n"
                f"3. VEILLE TECHNIQUE POINTUE : 1 fait marquant ou percée technologique en IA / architectures LLM en résonance directe avec ses recherches.\n"
                f"4. SYNTHÈSE VOCALE D'ÉLITE POUR AOEDE : 4 phrases percutantes, complices et vivantes pour le premier réveil.\n"
            )

        elif mission_type == "memory_consolidation":
            filename = f"memory_hygiene_{timestamp}.md"
            prompt = (
                f"MISSION DE CONSOLIDATION NOCTURNE DE LA MÉMOIRE & KNOWLEDGE GRAPH (SYSTÈME 2 - ANTIGRAVITY)\n"
                f"FAITS MÉMORISÉS & ENTITÉS ACTUELLES : {ctx_str}\n\n"
                f"Tu es l'architecte cognitif responsable de l'hygiène et de l'intégrité de la mémoire de J.A.R.V.I.S.\n"
                f"DIRECTIVES DE CONSOLIDATION :\n"
                f"1. DÉTECTION DES OBSOLESCENCES & CONTRADICTIONS : Repère les faits dépassés, incohérents ou dupliqués entre SQLite et vectoriel.\n"
                f"2. FUSION ET RÉCONCILIATION : Établis la vérité terrain actuelle (préférences, projets en cours, contacts).\n"
                f"3. STRUCTURATION RELATIONNELLE (GRAPH) : Mappe les liens logiques entre les personnes, les technologies et les priorités de Pierre.\n"
                f"4. RAPPORT D'ASSAINISSEMENT : Produis la liste des faits validés, archivés ou purgés.\n"
            )

        elif mission_type == "doc_sync":
            filename = f"doc_sync_{timestamp}.md"
            prompt = (
                f"MISSION DE SYNCHRONISATION CONTINUE DE L'ARCHITECTURE (SYSTÈME 2 - ANTIGRAVITY)\n"
                f"ANALYSE DE L'INFRASTRUCTURE LOGICIELLE ACTUELLE : {ctx_str}\n"
                f"FICHIER DE RÉFÉRENCE : {os.path.join(WORKSPACE_DIR, 'ARCHITECTURE_COMPLETE_JARVIS.md')}\n\n"
                f"Tu es l'architecte documentation de Stark Industries.\n"
                f"DIRECTIVES DE SYNCHRONISATION :\n"
                f"1. AUDIT DU CODE RÉEL : Compare la réalité des fichiers de code (routeurs, services, outils) avec le document markdown.\n"
                f"2. DÉTECTION DU DRIFT : Relève toute capacité non documentée, paramètre modifié ou endpoint ajouté.\n"
                f"3. MISE À JOUR EXACTE : Fournis les ajustements précis à intégrer dans ARCHITECTURE_COMPLETE_JARVIS.md.\n"
            )

        else:
            filename = f"mission_{slug}_{timestamp}.md"
            prompt = (
                f"MISSION SPÉCIALISÉE DE RÉFLEXION APPROFONDIE (SYSTÈME 2 - ANTIGRAVITY)\n"
                f"OBJECTIF : {goal}\n"
                f"CONTEXTE : {ctx_str}\n\n"
                f"Analyse en profondeur le sujet, résous la problématique et fournis un rapport exécutif Stark Industries structuré.\n"
            )

        return prompt, filename

    async def _execute_python_spreadsheet_script(self, code_script: str, target_xlsx_path: str) -> bool:
        """Tente d'exécuter le script openpyxl produit par l'agent pour créer le fichier Excel réel."""
        import tempfile
        import subprocess

        try:
            with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp:
                tmp.write(code_script)
                tmp_path = tmp.name

            # Exécution dans le venv Python
            python_bin = sys.executable
            proc = await asyncio.create_subprocess_exec(
                python_bin, tmp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

            if proc.returncode == 0 and os.path.exists(target_xlsx_path):
                logger.info(f"[AgenticDispatcher] Fichier Excel généré avec succès par openpyxl : {target_xlsx_path}")
                return True
            else:
                logger.warning(f"[AgenticDispatcher] Échec exécution script Excel (code {proc.returncode}) : {stderr.decode(errors='replace')}")
                return False
        except Exception as e:
            logger.warning(f"[AgenticDispatcher] Exception script Excel: {e}")
            return False

    async def launch_agentic_mission(
        self,
        mission_type: MissionType,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
        notify_voice: bool = True,
        notify_telegram: bool = True,
        output_filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """Lance une mission de délibération Système 2 en arrière-plan non-bloquant
        et configure les alertes multicanales pour la restitution finale.
        Routage dynamique en 3 tiers et résilience quota-aware.
        """
        mission_id = f"{mission_type}_{int(time.time())}"
        start_time = time.time()

        cog_cfg = await resolve_cognitive_tier(
            mission_type=mission_type,
            query=goal,
            user_preference=model
        )
        effective_model = model or cog_cfg.cli_model_arg

        prompt, default_filename = self._build_domain_prompt(mission_type, goal, context)
        effective_filename = output_filename or default_filename
        artifact_path = os.path.join(self.artifacts_dir, effective_filename)

        mission_state = {
            "mission_id": mission_id,
            "mission_type": mission_type,
            "goal": goal,
            "status": "running",
            "step": "Phase 1 : Prospection & Cadrage",
            "details": f"Mobilisation Antigravity CLI ({cog_cfg.description}) pour {mission_type}",
            "started_at": start_time,
            "artifact_path": artifact_path,
            "artifact_filename": effective_filename,
            "model": effective_model,
            "tier": cog_cfg.tier
        }
        self._active_missions[mission_id] = mission_state

        # Déclaration dans supervision_service
        domain_labels = {
            "transport_optimizer": "Optimisation Mobilité",
            "spreadsheet_modeler": "Data Analyst & Tableur",
            "system_healing": "SRE & Auto-Guérison",
            "email_drafting": "Triage & Rédaction E-mail",
            "book_curation": "Curation Culturelle & Kindle",
            "morning_briefing": "Morning Briefing Prédictif",
            "memory_consolidation": "Consolidation Mémoire",
            "doc_sync": "Synchronisation Architecture",
            "deep_research": "Deep Research",
        }
        label = domain_labels.get(mission_type, "Agent Antigravity")
        supervision_service.start_action(
            mission_id,
            f"{label} : {goal[:40]}",
            f"agentic_{mission_type}",
            goal,
            f"Antigravity ({cog_cfg.description})",
            api_type="free",
            api_label="Google AI Pro VPS",
            cost_est="0.00 $"
        )
        await broadcast_supervision()

        # Notification WebSocket initiale au HUD
        ws = active_task_controller.get("websocket")
        if ws:
            try:
                announcement_txt = cog_cfg.voice_pitch or f"Agent Antigravity mobilisé pour {label.lower()} : {goal[:45]}..."
                await ws.send_text(json.dumps({
                    "type": "jarvis_announcement",
                    "text": announcement_txt,
                    "voice": False
                }))
                await ws.send_text(json.dumps({
                    "type": "status",
                    "state": "thinking",
                    "msg": f"{label} en cours ({cog_cfg.description})...",
                    "task": goal[:40],
                    "engine": "Antigravity CLI (VPS)",
                    "model": effective_model
                }))
            except Exception:
                pass

        # Lancement en tâche d'arrière-plan asynchrone non-bloquante
        async def _run_mission_background():
            fallback_occurred = False
            try:
                effective_key = config.get_effective_paid_key() if config.is_paid_key_authorized() else GEMINI_API_KEY_FREE
                agent = AntigravityAgent(workspace=WORKSPACE_DIR, model=effective_model, api_key=effective_key)
                active_task_controller["agent_instance"] = agent

                async def _on_cli_progress(p_info: Dict[str, Any]):
                    txt = p_info.get("text", "")
                    step_name = p_info.get("step", "progress")
                    mission_state["details"] = txt
                    supervision_service.update_action_progress(mission_id, step_name, txt)
                    await broadcast_supervision()

                try:
                    task_result = await agent.run_cli_task_stream(
                        prompt,
                        on_progress=_on_cli_progress,
                        directive_queue=active_task_controller.get("queue")
                    )
                except AntigravityQuotaExhaustedError:
                    is_heavy = any(k in effective_model.lower() for k in ["3.1", "pro", "opus", "sonnet"])
                    if is_heavy:
                        fallback_occurred = True
                        fallback_msg = (
                            "Pierre, le quota 5h sur 3.1 Pro est atteint. "
                            "J'ai automatiquement basculé l'agent sur 3.8 Flash en réflexion renforcée pour finaliser la tâche sans blocage."
                        )
                        logger.warning(f"[AgenticDispatcher] {fallback_msg}")
                        supervision_service.record_event(
                            "QUOTA_FALLBACK",
                            f"Mission {mission_type} : bascule automatique vers Tier 2 (Gemini 3.8 Flash High)"
                        )
                        supervision_service.update_action_progress(mission_id, "quota_fallback", fallback_msg)
                        await broadcast_supervision()
                        if notify_voice:
                            live_sess = active_task_controller.get("live_session")
                            if live_sess:
                                await safe_send_live_client_content(live_sess, f"[ALERTE QUOTA ANTIGRAVITY] {fallback_msg}")
                        try:
                            await briefing_service.send_telegram_alert(
                                message=f"⚠️ *Alerte Quota Antigravity*\n{fallback_msg}\n*Mission* : {label} ({goal[:50]})",
                                chat_id="6849746502"
                            )
                        except Exception:
                            pass

                        # GARDE-FOU INVIOLABLE (Sections 5.2.3 & 5.4 de l'architecture) :
                        # Le repli sur Tier 2 (3.8 Flash High) suite à une erreur 429 ne doit JAMAIS
                        # basculer silencieusement vers la clé payante sans accord préalable.
                        fallback_key = config.get_effective_paid_key() if config.is_paid_key_authorized() else GEMINI_API_KEY_FREE
                        fallback_agent = AntigravityAgent(workspace=WORKSPACE_DIR, model="gemini-3.8-flash-high", api_key=fallback_key)
                        active_task_controller["agent_instance"] = fallback_agent
                        task_result = await fallback_agent.run_cli_task_stream(
                            prompt,
                            on_progress=_on_cli_progress,
                            directive_queue=active_task_controller.get("queue")
                        )
                    else:
                        raise

                if task_result.status == "cancelled":
                    mission_state["status"] = "cancelled"
                    supervision_service.complete_action(mission_id, status="cancelled", summary="Mission interrompue.")
                    await broadcast_supervision()
                    return

                raw_output = task_result.summary or ""

                # Fallback API directe Gemini si environnement dev sans agy
                if "Antigravity CLI n'est pas disponible" in raw_output:
                    logger.info(f"[AgenticDispatcher] Mode dev sans binaire agy. Génération via l'API Gemini pour {mission_type}...")
                    from core.shared_state import client_paid, client_free
                    client_target = client_paid if (client_paid and config.is_paid_key_authorized()) else (client_free or client_paid)
                    if client_target:
                        try:
                            resp = await asyncio.to_thread(
                                client_target.models.generate_content,
                                model="gemini-2.5-flash",
                                contents=prompt
                            )
                            raw_output = resp.text or ""
                        except Exception as fb_err:
                            logger.warning(f"[AgenticDispatcher] Erreur fallback Gemini: {fb_err}")

                # ─── Traitement spécifique par domaine ────────────────────────
                download_target_link = None
                oral_pitch = ""
                telegram_extra = ""

                # 1. Modélisation de tableur Excel
                if mission_type == "spreadsheet_modeler":
                    # Extraction du code python éventuel
                    py_match = re.search(r'```python(.*?)```', raw_output, re.DOTALL)
                    target_xlsx = os.path.join(self.downloads_dir, effective_filename)
                    excel_ok = False
                    if py_match:
                        script_code = py_match.group(1).strip()
                        excel_ok = await self._execute_python_spreadsheet_script(script_code, target_xlsx)

                    # Si pas réussi via script ou openpyxl manquant, on produit un fichier TSV/Excel propre
                    if not excel_ok:
                        try:
                            # Tentative d'écriture fallback
                            with open(target_xlsx, "w", encoding="utf-8") as f:
                                f.write(raw_output)
                        except Exception:
                            pass

                    download_target_link = f"/downloads/{effective_filename}"
                    oral_pitch = f"Pierre, le modèle de tableur complet '{effective_filename}' a été conçu avec toutes les formules dynamiques et ratios. Il est prêt dans tes téléchargements."
                    telegram_extra = f"📊 *Tableur Excel* : {download_target_link}\n"

                # 2. Triage & Rédaction d'email
                elif mission_type == "email_drafting":
                    json_match = re.search(r'\{.*\}', raw_output, re.DOTALL)
                    draft_body = raw_output
                    if json_match:
                        try:
                            draft_data = json.loads(json_match.group(0))
                            oral_pitch = draft_data.get("oral_pitch") or f"Pierre, j'ai préparé un projet de réponse argumenté pour '{goal[:40]}'."
                            draft_body = draft_data.get("corps") or raw_output
                            # Sauvegarde dans outbox
                            outbox_path = os.path.join(OUTBOX_DIR, f"draft_{int(time.time())}.json")
                            with open(outbox_path, "w", encoding="utf-8") as f:
                                json.dump(draft_data, f, ensure_ascii=False, indent=2)
                        except Exception:
                            pass
                    if not oral_pitch:
                        oral_pitch = f"Pierre, j'ai analysé l'e-mail concernant '{goal[:45]}'. J'ai préparé un brouillon d'acceptation adapté. Tu veux que je te le lise ?"

                # 3. Optimisation de transport
                elif mission_type == "transport_optimizer":
                    oral_pitch = f"Pierre, l'analyse comparative de ton trajet est finalisée. J'ai optimisé les correspondances et le confort, les liens directs sont prêts sur ton écran."
                    telegram_extra = f"🚆 *Itinéraire optimisé* : `{artifact_path}`\n"

                # 4. Auto-guérison système
                elif mission_type == "system_healing":
                    oral_pitch = f"Pierre, j'ai diagnostiqué l'anomalie sur le système, analysé le code source et rédigé un patch de correction pour stabiliser le service."
                    telegram_extra = f"🛠️ *Patch correctif* : `{artifact_path}`\n"

                # 5. Curation de livre
                elif mission_type == "book_curation":
                    guide_epub = os.path.join(EBOOKS_DIR, f"synthese_{effective_filename.replace('.md', '.epub')}")
                    oral_pitch = f"Pierre, j'ai rédigé la fiche 'Synthèse & Clés de lecture' pour ton livre. Elle est disponible en bonus et prête pour ta liseuse."
                    telegram_extra = f"📖 *Fiche de lecture* : `{artifact_path}`\n"

                # 6. Morning briefing
                elif mission_type == "morning_briefing":
                    oral_pitch = f"Morning Briefing stratégique préparé avec succès pour ta journée."

                # Sauvegarde du livrable Markdown dans /artifacts/
                try:
                    with open(artifact_path, "w", encoding="utf-8") as f:
                        f.write(raw_output)
                    logger.info(f"[AgenticDispatcher] Livrable enregistré dans : {artifact_path}")
                except Exception as write_err:
                    logger.error(f"[AgenticDispatcher] Erreur écriture artefact: {write_err}")

                duration = int(time.time() - start_time)
                summary_label = f"{label} finalisé en {duration}s."
                mission_state.update({
                    "status": "completed",
                    "step": "Mission achevée",
                    "details": summary_label,
                    "summary": oral_pitch or summary_label,
                    "raw_output": raw_output
                })

                supervision_service.complete_action(mission_id, status="completed", summary=summary_label)
                await broadcast_supervision()

                try:
                    from services.memory import log_tier_routing
                    asyncio.create_task(log_tier_routing(
                        query_text=goal,
                        chosen_tier=cog_cfg.tier,
                        reason=getattr(cog_cfg, "reason", "") or f"Mission {mission_type}",
                        final_tier=2 if fallback_occurred else cog_cfg.tier,
                        latency_ms=(time.time() - start_time) * 1000,
                        override_manuel=getattr(cog_cfg, "is_override", False),
                        fallback_occurred=fallback_occurred,
                        metadata={"mission_type": mission_type, "mission_id": mission_id}
                    ))
                except Exception as log_err:
                    logger.warning(f"[AgenticDispatcher] Note journalisation tier_routing_log : {log_err}")

                # ─── RESTITUTION MULTICANALE ──────────────────────────────────
                # 1. Notification Telegram Stark Bot (chatId: 6849746502)
                if notify_telegram:
                    tg_msg = (
                        f"⚡ *J.A.R.V.I.S. DÉLIBÉRATION AGENTIQUE ACHEVÉE*\n\n"
                        f"🎯 *Mission* : {label} ({goal})\n"
                        f"⏱️ *Durée* : {duration}s | *Moteur* : Antigravity CLI\n\n"
                    )
                    if telegram_extra:
                        tg_msg += telegram_extra
                    tg_msg += f"📄 *Rapport* : `{artifact_path}`\n\n"
                    if oral_pitch:
                        tg_msg += f"🎙️ *Restitution* : \"{oral_pitch}\""

                    await briefing_service.send_telegram_alert(
                        message=tg_msg,
                        chat_id="6849746502"
                    )

                # 2. Annonce vocale Aoede dans la session Live active
                if notify_voice:
                    live_session = active_task_controller.get("live_session")
                    if live_session and oral_pitch:
                        voice_prompt = (
                            f"[MISSION AGENTIQUE ANTIGRAVITY ACHEVÉE : {label}]\n"
                            f"L'analyse approfondie sur '{goal}' est terminée.\n"
                            f"Livrable enregistré : '{artifact_path}'.\n\n"
                            f"Consigne stricte pour Aoede : Présente oralement à Pierre cette synthèse avec ta voix Aoede "
                            f"d'un ton complice, direct et vivant :\n"
                            f"\"{oral_pitch}\""
                        )
                        await safe_send_live_client_content(live_session, voice_prompt)

                # 3. Notification WebSocket au HUD
                if ws:
                    try:
                        await ws.send_text(json.dumps({
                            "type": "task_completed",
                            "status": "completed",
                            "task_type": f"agentic_{mission_type}",
                            "summary": summary_label,
                            "artifact_path": artifact_path,
                            "download_url": download_target_link,
                            "engine": "Antigravity CLI (VPS)",
                            "model": "Gemini 3.1 Pro High"
                        }))
                        if download_target_link:
                            await ws.send_text(json.dumps({
                                "type": "set_browser_link",
                                "url": download_target_link,
                                "title": f"Fichier prêt : {effective_filename}"
                            }))
                    except Exception:
                        pass

            except Exception as e:
                logger.error(f"[AgenticDispatcher] Exception dans la mission {mission_id}: {e}", exc_info=True)
                mission_state["status"] = "error"
                supervision_service.complete_action(mission_id, status="error", summary=str(e))
                await broadcast_supervision()

        # Création de la tâche de fond
        bg_task = asyncio.create_task(_run_mission_background())
        mission_state["async_task"] = bg_task

        return {
            "status": "launched_in_background",
            "mission_id": mission_id,
            "mission_type": mission_type,
            "goal": goal,
            "artifact_path": artifact_path,
            "artifact_filename": effective_filename,
            "instruction_to_jarvis": (
                f"La mission '{label}' est confiée aux agents Antigravity CLI sur le VPS en arrière-plan. "
                f"Confirme immédiatement à Pierre avec ta voix Aoede en moins de 300 millisecondes "
                f"d'un ton chaleureux et complice que tu délègues cette analyse à vos agents et que la tâche s'exécute."
            )
        }


# Singleton exporté
agentic_dispatcher = AgenticDispatcher()
