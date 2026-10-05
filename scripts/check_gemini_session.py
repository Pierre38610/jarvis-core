#!/usr/bin/env python3
"""scripts/check_gemini_session.py
J.A.R.V.I.S. - Vérification de la Session Google Gemini active sur Chrome VPS (P5).

Objectif :
  Vérifie si Google Chrome CDP dispose d'une session Google/Gemini Web authentifiée
  et prête pour Deep Research L3, sans jamais saisir de mot de passe ni afficher
  de cookies/tokens secrets.

Codes de retour (Exit Codes) :
  0 : Session Gemini active et authentifiée (Prêt pour Deep Research L3).
  1 : Authentification requise (Redirection accounts.google.com ou écran de login).
  2 : Chrome CDP inaccessible ou erreur critique.

Usage :
  python scripts/check_gemini_session.py [--cdp-url http://127.0.0.1:9222] [--timeout 15] [--json] [--quiet]
"""

import argparse
import asyncio
import json
import os
import sys

# Ajout de la racine du projet au PYTHONPATH
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from services.vps_chrome import check_gemini_session, get_effective_cdp_url


def parse_args():
    parser = argparse.ArgumentParser(
        description="J.A.R.V.I.S. - Vérification de Session Google Gemini active (P5)"
    )
    parser.add_argument(
        "--cdp-url",
        type=str,
        default=None,
        help="URL du port de débogage Chrome CDP (défaut : JARVIS_CDP_URL ou http://127.0.0.1:9222)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Délai maximum en secondes pour l'inspection de page (défaut : 15s)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Affiche le résultat sous forme de dictionnaire JSON brut",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="N'affiche aucun message en dehors des erreurs fatales",
    )
    return parser.parse_args()


async def main_async() -> int:
    args = parse_args()
    target_url = get_effective_cdp_url(args.cdp_url)

    if not args.quiet and not args.json_output:
        print("=" * 68)
        print("  ✦  J . A . R . V . I . S .   G E M I N I   S E S S I O N   C H E C K  ✦")
        print("=" * 68)
        print(f"Cible CDP : {target_url}")
        print("Inspection de l'état d'authentification Google Gemini...")

    result = await check_gemini_session(
        cdp_url=target_url,
        timeout=args.timeout,
    )

    exit_code = result.get("exit_code", 1)

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return exit_code

    if not args.quiet:
        status = result.get("status", "unknown").upper()
        message = result.get("message", "")
        current_url = result.get("current_url")

        print("-" * 68)
        if exit_code == 0:
            print(f"[✔ SUCCÈS] Statut : {status}")
            print(f"Message  : {message}")
            if current_url:
                print(f"URL vue  : {current_url}")
            print("\n👉 Chrome VPS est authentifié. Prêt pour les recherches L3 autonomes.")
        elif exit_code == 1:
            print(f"[⚠️ ACTION REQUISE] Statut : {status}")
            print(f"Message         : {message}")
            if current_url:
                print(f"URL vue         : {current_url}")
            print("\n👉 Connexion manuelle unique requise.")
            print("   Consultez 'docs/VPS_GOOGLE_SESSION_SETUP.md' pour la procédure de")
            print("   connexion via VNC ou de copie sécurisée de profil depuis le PC.")
        else:
            print(f"[❌ ERREUR] Statut : {status}")
            print(f"Message   : {message}")
            if result.get("error"):
                print(f"Détail    : {result['error']}")
            print("\n👉 Vérifiez que Chrome VPS est démarré : sudo systemctl status jarvis-chrome")
        print("=" * 68)

    return exit_code


def main():
    try:
        code = asyncio.run(main_async())
        sys.exit(code)
    except KeyboardInterrupt:
        print("\nVérification interrompue par l'utilisateur.")
        sys.exit(130)


if __name__ == "__main__":
    main()
