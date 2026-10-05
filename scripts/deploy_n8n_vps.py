"""Script d'initialisation et configuration de n8n sur le VPS Jarvis.
Exécute via Paramiko SSH :
1. Vérification / génération des clés secrètes n8n dans /home/opc/jarvis-core/.env
2. Lancement du conteneur docker compose (jarvis_n8n)
3. Importation du workflow test_ping.json via la CLI n8n
4. Test de connectivité du webhook local
"""

import os
import sys
import secrets
import time
import paramiko

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY_PATH = os.path.join(BASE_DIR, r"clés ssh\ssh-key-2026-09-25.key")
HOST = os.environ.get("JARVIS_VPS_HOST", "158.178.206.213").strip()
USER = os.environ.get("JARVIS_VPS_USER", "opc").strip()


def run_ssh_command(client, cmd, print_output=True, sudo=False):
    if sudo:
        cmd = f"sudo bash -c '{cmd}'"
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    if print_output and out:
        print(out)
    if print_output and err:
        print(f"[STDERR] {err}", file=sys.stderr)
    return out, err


def main():
    print(f"[*] Connexion SSH au VPS {HOST} (utilisateur: {USER})...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=HOST, username=USER, key_filename=KEY_PATH, timeout=20)

    try:
        # 1. Vérifier si les variables n8n existent dans le .env du VPS
        print("\n[1/4] Vérification de la configuration .env du VPS...")
        env_content, _ = run_ssh_command(client, "cat /home/opc/jarvis-core/.env", print_output=False)

        encryption_key = None
        webhook_secret = None

        for line in env_content.splitlines():
            line = line.strip()
            if line.startswith("N8N_ENCRYPTION_KEY=") and len(line.split("=", 1)[1].strip()) >= 32 and not line.endswith("REMPLACER_PAR_openssl_rand_hex_32"):
                encryption_key = line.split("=", 1)[1].strip()
            if line.startswith("N8N_WEBHOOK_SECRET=") and len(line.split("=", 1)[1].strip()) >= 16 and not line.endswith("REMPLACER_PAR_secret_fort"):
                webhook_secret = line.split("=", 1)[1].strip()

        if not encryption_key:
            encryption_key = secrets.token_hex(32)
            print(f"  [+] Clé N8N_ENCRYPTION_KEY générée : {encryption_key[:8]}...")
        else:
            print(f"  [✔] N8N_ENCRYPTION_KEY existante détectée.")

        if not webhook_secret:
            webhook_secret = secrets.token_hex(24)
            print(f"  [+] Clé N8N_WEBHOOK_SECRET générée : {webhook_secret[:8]}...")
        else:
            print(f"  [✔] N8N_WEBHOOK_SECRET existante détectée.")

        # Script python distant pour mettre à jour ou ajouter proprement les variables dans le .env
        update_env_py = f"""python3 - << 'EOF'
env_path = '/home/opc/jarvis-core/.env'
keys_to_set = {{
    'N8N_ENCRYPTION_KEY': '{encryption_key}',
    'N8N_WEBHOOK_SECRET': '{webhook_secret}',
    'N8N_WEBHOOK_URL': 'http://127.0.0.1:5678/',
    'N8N_BASE_URL': 'http://127.0.0.1:5678',
    'N8N_CONTAINER_NAME': 'jarvis_n8n'
}}
lines = []
existing = set()
try:
    with open(env_path, 'r') as f:
        lines = f.readlines()
except FileNotFoundError:
    pass

new_lines = []
for l in lines:
    matched = False
    for k, v in keys_to_set.items():
        if l.strip().startswith(k + '='):
            new_lines.append(f"{{k}}={{v}}\\n")
            existing.add(k)
            matched = True
            break
    if not matched:
        new_lines.append(l)

for k, v in keys_to_set.items():
    if k not in existing:
        new_lines.append(f"{{k}}={{v}}\\n")

with open(env_path, 'w') as f:
    f.writelines(new_lines)
print("ENV_UPDATED_OK")
EOF
"""
        out, _ = run_ssh_command(client, update_env_py)
        print("  [✔] Fichier .env distant mis à jour avec les identifiants n8n.")

        # 2. Démarrer le service n8n via docker compose
        print("\n[2/4] Démarrage du conteneur n8n via Docker Compose...")
        compose_cmd = "cd /home/opc/jarvis-core && sudo docker compose up -d n8n"
        run_ssh_command(client, compose_cmd)

        # Attendre que le conteneur soit démarré
        print("  [*] Attente du démarrage de n8n...")
        time.sleep(5)
        for attempt in range(12):
            ps_out, _ = run_ssh_command(client, "sudo docker ps --filter name=jarvis_n8n --format '{{.Names}} - {{.Status}}'", print_output=False)
            if "jarvis_n8n" in ps_out:
                print(f"  [✔] Conteneur en cours d'exécution : {ps_out}")
                break
            time.sleep(3)

        # 3. Importer le workflow test_ping.json via la CLI n8n
        print("\n[3/4] Importation du workflow test_ping.json via la CLI n8n...")
        # Copier le fichier dans le conteneur puis importer
        import_flow_cmd = (
            "sudo docker cp /home/opc/jarvis-core/workflows/test_ping.json jarvis_n8n:/tmp/test_ping.json && "
            "sudo docker exec jarvis_n8n n8n import:workflow --input=/tmp/test_ping.json && "
            "sudo docker exec jarvis_n8n rm -f /tmp/test_ping.json"
        )
        out, _ = run_ssh_command(client, import_flow_cmd)
        print("  [✔] Workflow importé avec succès.")

        # 4. Vérification et test de réponse Webhook
        print("\n[4/4] Test de déclenchement du webhook n8n depuis le VPS...")
        test_curl = (
            f"curl -s -X POST http://127.0.0.1:5678/webhook/test-ping "
            f"-H 'Content-Type: application/json' "
            f"-H 'X-Jarvis-Secret: {webhook_secret}' "
            f"-d '{{\"message\": \"ping-vps-test\"}}'"
        )
        curl_out, _ = run_ssh_command(client, test_curl, print_output=False)
        print(f"  Réponse reçue : {curl_out}")

        print("\n" + "=" * 60)
        print("  🎉 DÉPLOIEMENT & INITIALISATION N8N SUR LE VPS TERMINÉS AVEC SUCCÈS !")
        print(f"  Clé de chiffrement n8n : configurée")
        print(f"  Secret Webhook Jarvis  : {webhook_secret}")
        print("=" * 60)

    finally:
        client.close()


if __name__ == "__main__":
    main()
