#!/usr/bin/env python3
"""Script de test rapide pour diagnostiquer L2/L3 sur le VPS."""
import asyncio
import sys
import os

sys.path.insert(0, "/home/opc/jarvis-core")
os.chdir("/home/opc/jarvis-core")

# Chargement de la config
try:
    import config
    print(f"[OK] config chargé. WORKSPACE_DIR={getattr(config, 'WORKSPACE_DIR', 'MISSING')}")
except Exception as e:
    print(f"[ERR] config: {e}")

# Test 1: vérification CLI
try:
    from services.google_antigravity import verify_antigravity_cli_ready
    ready, err, info = asyncio.run(verify_antigravity_cli_ready())
    print(f"[TEST CLI] ready={ready} err={err} info={info}")
except Exception as e:
    print(f"[ERR CLI] {e}")

# Test 2: run_agentic simple
try:
    from services.google_antigravity import run_agentic, MODEL_FLASH
    print("[TEST RUN_AGENTIC] Lancement d'un agent test...")
    result = asyncio.run(run_agentic(
        role="test",
        prompt="Réponds simplement : test réussi",
        model=MODEL_FLASH,
        effort="low",
        timeout=60,
    ))
    print(f"[TEST RUN_AGENTIC] status={result.status} conclusion={result.conclusion[:100]}")
except Exception as e:
    import traceback
    print(f"[ERR RUN_AGENTIC] {e}")
    traceback.print_exc()

# Test 3: BrowserTask / browser_agent (L3)
try:
    from services.browser_agent.loop import BrowserTask, run_browser_task
    print("[TEST BROWSER_TASK] Structure BrowserTask accessible")
except Exception as e:
    print(f"[ERR BROWSER_TASK] {e}")

print("[DONE]")
