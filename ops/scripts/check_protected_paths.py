"""ops/scripts/check_protected_paths.py
Script anti-régression bloquant toute modification ou suppression non autorisée
de fichiers critiques par un agent d'auto-amélioration ou une PR.

Périmètre protégé :
1. Modification ou suppression interdite :
   - .env* (secrets et variables d'environnement)
   - backend/services/auth_service.py
   - backend/auth.py
   - backend/services/key_gate.py
   - backend/core/tools/arg_validator.py
   - ops/deploy/jarvis_deployer.py
   - .github/workflows/ (tous les fichiers de workflows CI/CD)
2. Suppression interdite :
   - Tout fichier de test existant sous backend/tests/
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import subprocess
import sys
from typing import List, Optional, Tuple

EXACT_PROTECTED_FILES = {
    "backend/services/auth_service.py",
    "backend/auth.py",
    "backend/services/key_gate.py",
    "backend/core/tools/arg_validator.py",
    "ops/deploy/jarvis_deployer.py",
}

PROTECTED_PREFIXES = (
    ".github/workflows/",
)

PROTECTED_TEST_PREFIX = "backend/tests/"


def normalize_path(path: str) -> str:
    """Normalise un chemin de fichier pour comparaison unifiée."""
    if not path:
        return ""
    p = path.replace("\\", "/").strip()
    while p.startswith("./"):
        p = p[2:]
    return p


def is_env_file(norm_path: str) -> bool:
    """Vérifie si le fichier correspond au pattern .env*."""
    base_name = os.path.basename(norm_path)
    return base_name.startswith(".env") or norm_path.startswith(".env") or fnmatch.fnmatch(norm_path, "*.env*")


def check_change(status: str, path: str) -> Optional[str]:
    """Vérifie si un changement spécifique (status, path) viole les règles de protection.
    
    Status usuels git :
    - 'M' : Modifié
    - 'A' : Ajouté
    - 'D' : Supprimé
    - 'R' : Renommé
    
    Returns:
        Message d'erreur descriptif si violation, None si autorisé.
    """
    norm = normalize_path(path)
    if not norm:
        return None

    status_code = status.strip().upper()
    if status_code and len(status_code) > 1:
        # Ex: 'R100', 'C100' -> conserve le premier caractère
        status_code = status_code[0]

    norm_lower = norm.lower()

    # 1. Vérification des fichiers d'environnement (.env*)
    if is_env_file(norm):
        return f"[BLOCKED] Modification ou suppression non autorisée d'un fichier .env* : '{norm}'"

    # 2. Vérification des fichiers sensibles exacts
    for protected in EXACT_PROTECTED_FILES:
        if norm_lower == protected.lower():
            action_desc = "Suppression" if status_code == "D" else "Modification"
            return f"[BLOCKED] {action_desc} non autorisée d'un fichier critique : '{norm}'"

    # 3. Vérification des répertoires protégés (.github/workflows/)
    for prefix in PROTECTED_PREFIXES:
        if norm_lower.startswith(prefix.lower()):
            action_desc = "Suppression" if status_code == "D" else "Modification"
            return f"[BLOCKED] {action_desc} non autorisée d'un workflow CI/CD : '{norm}'"

    # 4. Vérification de la suppression de tests existants
    if status_code == "D" and norm_lower.startswith(PROTECTED_TEST_PREFIX.lower()):
        return f"[BLOCKED] Suppression non autorisée d'un fichier de test sous '{PROTECTED_TEST_PREFIX}' : '{norm}'"

    return None


def check_all_changes(changes: List[Tuple[str, str]]) -> List[str]:
    """Valide une liste de couples (status, path) et retourne la liste des violations."""
    violations: List[str] = []
    for status, path in changes:
        err = check_change(status, path)
        if err:
            violations.append(err)
    return violations


def parse_file_argument(item: str) -> Tuple[str, str]:
    """Parse une chaîne passée via --files en (status, path)."""
    item = item.strip()
    # Support préfixes 'D\tpath', 'D path', 'D:path', 'M path', etc.
    for prefix in ("D\t", "D ", "D:", "M\t", "M ", "M:", "A\t", "A ", "A:"):
        if item.startswith(prefix):
            return prefix[0], item[len(prefix):].strip()
    return "M", item


def get_git_diff_changes(base: str, head: str) -> List[Tuple[str, str]]:
    """Récupère la liste des fichiers modifiés entre base et head via git diff."""
    # Essaie d'abord un diff direct base head
    cmd = ["git", "diff", "--name-status", base, head]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        # Fallback pour remote branch ou merge-base
        alt_cmd = ["git", "diff", "--name-status", f"{base}...{head}"]
        proc = subprocess.run(alt_cmd, capture_output=True, text=True, check=True)

    changes: List[Tuple[str, str]] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            status = parts[0]
            if status.startswith("R") and len(parts) >= 3:
                # Renommage : parts[1] est l'ancien chemin (supprimé), parts[2] est le nouveau (ajouté)
                changes.append(("D", parts[1]))
                changes.append(("A", parts[2]))
            else:
                changes.append((status, parts[1]))
    return changes


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Vérifie qu'aucun fichier critique n'est modifié ou supprimé par une PR ou un agent."
    )
    parser.add_argument("--base", default="main", help="Git base ref (défaut: main)")
    parser.add_argument("--head", default="HEAD", help="Git head ref (défaut: HEAD)")
    parser.add_argument(
        "--files",
        nargs="*",
        default=None,
        help="Liste explicite de fichiers modifiés (usage pré-commit ou tests)",
    )
    parser.add_argument(
        "--deleted-files",
        nargs="*",
        default=None,
        help="Liste explicite de fichiers supprimés",
    )

    args = parser.parse_args(argv)

    changes: List[Tuple[str, str]] = []

    if args.files is not None or args.deleted_files is not None:
        if args.files:
            for f in args.files:
                changes.append(parse_file_argument(f))
        if args.deleted_files:
            for f in args.deleted_files:
                changes.append(("D", f.strip()))
    else:
        try:
            changes = get_git_diff_changes(args.base, args.head)
        except Exception as e:
            sys.stderr.write(f"Erreur lors de l'exécution de git diff ({args.base} -> {args.head}) : {e}\n")
            return 2

    violations = check_all_changes(changes)

    if violations:
        print("\n========================================================")
        print("[VIOLATION] REGLES DE PROTECTION DE CHEMINS DETECTEES")
        print("========================================================")
        for v in violations:
            print(f" - {v}")
        print("\nUn agent d'auto-amelioration ou une PR sans autorisation explicite")
        print("ne peut pas modifier ou supprimer ces fichiers sensibles.")
        print("Veuillez solliciter la validation orale ou la revue de @Pierre38610.\n")
        return 1

    print("[OK] Controle d'integrite valide : aucun chemin protege altere.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
