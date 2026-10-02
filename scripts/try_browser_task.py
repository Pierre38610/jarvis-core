#!/usr/bin/env python3
"""scripts/try_browser_task.py
Script de test manuel de bout en bout pour la boucle Browser Agent de J.A.R.V.I.S.
Exécute run_browser_task directement sans synthèse vocale avec affichage temps réel.
"""

import argparse
import asyncio
import os
import sys
import time
import uuid
from typing import Any, Dict, List, Optional

# Configuration de l'environnement racine
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.tools.result import ToolResult
from services.browser_agent import cli_brain, loop
from services.browser_agent.loop import BrowserTask, run_browser_task


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test manuel de bout en bout pour le Browser Agent J.A.R.V.I.S."
    )
    parser.add_argument(
        "--goal",
        type=str,
        default="",
        help="Objectif de la tâche de navigation (ex: 'Chercher les horaires de train Paris Lyon')",
    )
    parser.add_argument(
        "--recipe",
        type=str,
        default=None,
        help="Nom ou chemin du fichier de recette (ex: 'recherche_amazon' ou 'train')",
    )
    parser.add_argument(
        "--start-url",
        type=str,
        default=None,
        help="URL de départ de la navigation",
    )

    args = parser.parse_args()

    if not args.goal and not args.recipe:
        parser.error("Veuillez spécifier au moins --goal ou --recipe.")

    task_id = f"manual_{int(time.time())}_{uuid.uuid4().hex[:4]}"
    goal = args.goal or (f"Exécuter la recette {args.recipe}" if args.recipe else "")

    task = BrowserTask(
        task_id=task_id,
        goal=goal,
        start_url=args.start_url,
        recipe=args.recipe,
    )

    print("=" * 65)
    print("🚀 DÉMARRAGE DU TEST MANUEL BROWSER AGENT")
    print("=" * 65)
    print(f"• Task ID   : {task.task_id}")
    print(f"• Objectif  : {task.goal}")
    print(f"• Recette   : {task.recipe or 'Aucune'}")
    print(f"• Start URL : {task.start_url or 'Défini par la recette / vide'}")
    print("=" * 65)

    # Compteurs et instrumentation
    cli_call_count = 0
    screenshot_count = 0
    last_known_url = task.start_url or ""

    # 1. Instrumentation des appels agy CLI pour mesurer la durée exacte
    orig_call_agy = cli_brain._call_agy

    async def timed_call_agy(prompt: str, model: str, timeout: float) -> str:
        nonlocal cli_call_count
        cli_call_count += 1
        return await orig_call_agy(prompt, model, timeout)

    cli_brain._call_agy = timed_call_agy

    # 2. Instrumentation de cli_brain.decide
    orig_decide = cli_brain.decide

    async def tracked_decide(*d_args, **d_kwargs) -> Dict[str, Any]:
        t0 = time.perf_counter()
        decision = await orig_decide(*d_args, **d_kwargs)
        duration = time.perf_counter() - t0

        thought = decision.get("thought", "")
        actions = decision.get("actions", [])
        done = decision.get("done", False)
        handoff = decision.get("handoff")
        need_screenshot = decision.get("need_screenshot", False)

        print(f"\n[Étape {task.steps}] 🧠 Brain Décision :")
        if thought:
            print(f"  💭 Pensée       : {thought}")
        if actions:
            print(f"  ⚡ Actions ({len(actions)}) : {actions}")
        elif done:
            print("  🏁 Actions     : [done=True] Objectif signalé atteint")
        elif handoff:
            print(f"  🤝 Handoff     : {handoff}")
        else:
            print("  ⚠️ Aucune action décidée")

        if need_screenshot:
            print("  📸 Capture demandée par le modèle pour analyse visuelle")

        print(f"  ⏱️  Durée appel CLI : {duration:.2f}s")
        return decision

    cli_brain.decide = tracked_decide

    # 3. Instrumentation de cli_brain.verify
    orig_verify = cli_brain.verify

    async def tracked_verify(*v_args, **v_kwargs) -> Dict[str, Any]:
        t0 = time.perf_counter()
        verif_res = await orig_verify(*v_args, **v_kwargs)
        duration = time.perf_counter() - t0

        ok = verif_res.get("ok", False)
        reason = verif_res.get("reason", "")
        print("\n[Vérification] 🔍 Brain Verify :")
        print(f"  Résultat       : {'✅ SUCCÈS' if ok else '❌ ÉCHEC'}")
        print(f"  Raison         : {reason}")
        print(f"  ⏱️  Durée appel CLI : {duration:.2f}s")
        return verif_res

    cli_brain.verify = tracked_verify

    # 4. Instrumentation de loop._call_rpc pour suivre les captures d'écran et l'URL courante
    orig_call_rpc = loop._call_rpc

    async def tracked_call_rpc(action: str, timeout: float = 30.0, **params) -> Dict[str, Any]:
        nonlocal screenshot_count, last_known_url
        if action == "browser_screenshot":
            screenshot_count += 1
            print(f"  📷 [RPC] Capture d'écran #{screenshot_count} en cours...")
        elif action == "browser_act":
            act_list = params.get("actions", [])
            print(f"  🖱️  [RPC] Exécution de {len(act_list)} action(s) sur le navigateur...")

        res = await orig_call_rpc(action, timeout=timeout, **params)
        if isinstance(res, dict) and res.get("url"):
            last_known_url = str(res.get("url"))
        return res

    loop._call_rpc = tracked_call_rpc

    # Fonction notify passée à run_browser_task
    async def async_notify(message: str) -> None:
        print(f"\n📢 [NOTIFY] {message}\n")

    # Exécution de la tâche
    start_time = time.time()
    try:
        result: ToolResult = await run_browser_task(task, notify=async_notify)
    finally:
        # Restauration des fonctions d'origine
        cli_brain._call_agy = orig_call_agy
        cli_brain.decide = orig_decide
        cli_brain.verify = orig_verify
        loop._call_rpc = orig_call_rpc

    total_duration = time.time() - start_time
    final_url = (
        result.data.get("url")
        or last_known_url
        or task.start_url
        or "N/A"
    )

    # Affichage du bilan final
    print("\n" + "=" * 65)
    print("📊 BILAN FINAL DE LA TÂCHE DE NAVIGATION")
    print("=" * 65)
    print(f"• Statut             : {result.status} (task.status={task.status})")
    print(f"• URL finale         : {final_url}")
    print(f"• Nombre d'étapes    : {task.steps}")
    print(f"• Appels CLI agy     : {cli_call_count}")
    print(f"• Captures d'écran   : {screenshot_count}")
    print(f"• Durée totale       : {total_duration:.2f}s")
    if result.user_message:
        print(f"• Message retour     : {result.user_message}")
    if result.evidence:
        print(f"• Preuve (evidence)  : {result.evidence}")
    if result.error_hint:
        print(f"• Indice d'erreur    : {result.error_hint}")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
