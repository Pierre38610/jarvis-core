import sys
import io
import time
import paramiko

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect('158.178.206.213', username='opc', key_filename='clés ssh/ssh-key-2026-09-25.key', timeout=20)
    
    # Écrire le mini batch
    mini_prompt_md = '''# Test Mini Auto-Amélioration

## Ordre d’exécution
Exécuter le prompt 1.

| Prompt | Sujet | Niveau / routage agy |
|---:|---|---|
| 1 | Ajout d'une constante TEST_BATCH_STATUS dans backend/services/system_service.py | `low` → Flash/low |

---

## Prompt 1 — Définition de TEST_BATCH_STATUS

**Niveau conseillé : low**

```
RÔLE : Développeur Python J.A.R.V.I.S.
OBJECTIF : Dans `backend/services/system_service.py`, ajouter la variable globale `TEST_BATCH_STATUS = "operational"` près des constantes système si elle n'est pas déjà présente.

LIS UNIQUEMENT :
1. `backend/services/system_service.py`

À CRÉER / MODIFIER :
1. Dans `backend/services/system_service.py`, ajoute :
TEST_BATCH_STATUS = "operational"

COMMANDES DE VALIDATION EXACTES :
python -m py_compile backend/services/system_service.py
```
'''
    sftp = c.open_sftp()
    with sftp.file("/home/opc/jarvis-core/data/prompt_batches/test_mini_batch.md", "w") as f:
        f.write(mini_prompt_md)
    sftp.close()

    # Exécuter le batch
    cmd = """
/home/opc/jarvis-core/venv/bin/python -c '
import asyncio
import os
import sys

sys.path.insert(0, "/home/opc/jarvis-core")
sys.path.insert(0, "/home/opc/jarvis-core/backend")

from services.prompt_batch_runner import run_prompt_batch

async def test():
    file_path = "/home/opc/jarvis-core/data/prompt_batches/test_mini_batch.md"
    print("=== Démarrage du test run_prompt_batch (Tour 3) ===", flush=True)
    state = await run_prompt_batch(file_path=file_path)
    print("=== Résultat du test run_prompt_batch ===", flush=True)
    print("Status:", state.get("status"))
    print("Results:", len(state.get("results", [])))
    print("Last Error:", state.get("last_error"))
    print("PR URL:", state.get("pr_url"))

asyncio.run(test())
'
"""
    print("Lancement du test de batch sur le VPS (Tour 3)...")
    stdin, stdout, stderr = c.exec_command(cmd, timeout=400)
    for line in iter(stdout.readline, ""):
        print(line, end="")
    err = stderr.read().decode('utf-8', errors='replace').strip()
    if err:
        print("\nSTDERR:\n" + err)
    c.close()

if __name__ == '__main__':
    main()
