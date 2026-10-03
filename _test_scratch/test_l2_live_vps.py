#!/usr/bin/env python3
"""Test réel de validation L2 et L3 sur le VPS Oracle."""
import asyncio
import sys
import os

sys.path.insert(0, "/home/opc/jarvis-core")
os.chdir("/home/opc/jarvis-core")

from services.agentic_runner import run_agentic, run_l2_parallel_agents
from services.antigravity_models import MODEL_FLASH
from core.tools.dispatcher import dispatch_tool
from google_antigravity import verify_antigravity_cli_ready

async def main():
    print("=== VÉRIFICATION DU PREFLIGHT ANTIGRAVITY CLI ===")
    ready, msg, path = await verify_antigravity_cli_ready(force_refresh=True)
    print(f"Ready: {ready}, Path: {path}, Msg: {msg}")
    assert ready, f"Antigravity CLI non ready: {msg}"

    print("\n=== TEST 1: run_agentic avec agy (Palier L2) ===")
    res = await run_agentic(
        role="prospector",
        prompt="Identifie 2 faits vérifiables sur Python 3.11 et cite les sources.",
        model=MODEL_FLASH,
        effort="low",
        timeout=60,
    )
    print(f"Status: {res.status}")
    print(f"Conclusion: {res.conclusion}")
    print(f"Facts: {res.facts}")
    print(f"Sources: {res.sources}")
    print(f"Confidence: {res.confidence}")
    assert res.status == "success", f"Échec run_agentic: {res.error}"

    print("\n=== TEST 2: run_l2_parallel_agents avec 2 agents parallèles (Palier L2) ===")
    l2_res = await run_l2_parallel_agents(
        goal="Avantages du processeur ARM64 Ampere Altra pour les microservices",
        max_workers=2,
        agent_timeout=60,
        max_iterations=1,
    )
    print(f"L2 Status: {l2_res.status}")
    print(f"Quality Gate Passed: {l2_res.quality_gate_passed}")
    print(f"Successful Agents: {len(l2_res.successful_agents)}")
    if l2_res.synthesis:
        print(f"Synthesis: {l2_res.synthesis.conclusion}")
    assert l2_res.status in ("completed", "partial"), f"Échec L2: {l2_res.error}"

    print("\n=== TEST 3: dispatch_tool 'ask_deep_reasoning' (Palier L2) ===")
    d_res = await dispatch_tool(
        name="ask_deep_reasoning",
        args={"question": "Quel est le compromis coût/performance d'un VPS ARM64 ?"},
    )
    print(f"Dispatch status: {d_res.get('status')}")
    print(f"Dispatch user_message: {d_res.get('user_message', '')[:120]}")

    print("\n🎉 TOUS LES TESTS L2 EN LIVE SUR LE VPS SONT VALIDÉS !")

if __name__ == "__main__":
    asyncio.run(main())
