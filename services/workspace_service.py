"""services/workspace_service.py
Service d'accès en LECTURE SEULE STRICTE à l'espace local _anti_gravity de Pierre.
Permet à J.A.R.V.I.S. (sur VPS via WebSocket local-agent ou directement sur PC) d'explorer,
consulter et analyser l'ensemble de ses projets (Stages, LTH, Micro-SaaS, jarvis, Extensions_chrome, Cleaning, bin).

GARDE-FOU INVIOLABLE :
- Strictement aucune écriture, modification, suppression ou déplacement de fichier.
- Vérification stricte d'étanchéité de chemin (anti-path-traversal via realpath).
- Masquage et exclusion systématique des fichiers sensibles (.env, clés privées, tokens).
"""

from __future__ import annotations

import os
import sys
import fnmatch
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import config


# Répertoire racine canonique _anti_gravity
ANTI_GRAVITY_ROOT = os.path.realpath(config.ANTI_GRAVITY_DIR)

# Répertoires lourds ou temporaires systématiquement exclus de l'exploration
IGNORED_DIR_NAMES = {
    ".git",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".cache",
    ".venv",
    "venv",
    "dist",
    "build",
    ".idea",
    ".vscode",
    "target",
    "bin_obj",
}

# Motifs de fichiers sensibles ou confidentiels exclus de la lecture
SENSITIVE_PATTERNS = [
    ".env*",
    "*.pem",
    "*.key",
    "id_rsa*",
    "id_ed25519*",
    "*.pfx",
    "*.kdbx",
    "authorized_devices.json",
    "*credentials*.json",
    "*service_account*.json",
    "*secret*",
]

# Extensions considérées binaires
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svgz",
    ".mp3", ".wav", ".ogg", ".flac", ".m4a",
    ".mp4", ".mkv", ".avi", ".mov", ".webm",
    ".pdf", ".exe", ".dll", ".so", ".bin", ".dat",
    ".zip", ".tar", ".gz", ".7z", ".rar",
    ".pyc", ".pyo", ".pyd",
    ".ttf", ".otf", ".woff", ".woff2",
}


def is_path_safe(target_path: str, root_dir: str = ANTI_GRAVITY_ROOT) -> Tuple[bool, str]:
    """Vérifie que target_path réside strictement à l'intérieur de root_dir et n'est pas un fichier sensible."""
    try:
        real_root = os.path.realpath(root_dir)
        real_target = os.path.realpath(target_path)

        # Vérification d'étanchéité stricte (path traversal)
        if not (real_target == real_root or real_target.startswith(real_root + os.sep)):
            return False, f"Accès interdit : le chemin est hors du périmètre autorisé ({real_root})."

        # Vérification des fichiers sensibles
        base_name = os.path.basename(real_target).lower()
        for pat in SENSITIVE_PATTERNS:
            if fnmatch.fnmatch(base_name, pat.lower()):
                return False, "Accès refusé : fichier confidentiel ou sensible exclu de la consultation."

        return True, ""
    except Exception as e:
        return False, f"Erreur validation chemin : {e}"


def is_binary_file(file_path: str) -> bool:
    """Détecte si un fichier est binaire d'après son extension ou ses premiers octets."""
    _, ext = os.path.splitext(file_path)
    if ext.lower() in BINARY_EXTENSIONS:
        return True
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(1024)
            if b"\x00" in chunk:
                return True
    except Exception:
        pass
    return False


class WorkspaceService:
    """Service d'accès en lecture seule aux projets de Pierre dans _anti_gravity."""

    def __init__(self, root_dir: str = ANTI_GRAVITY_ROOT):
        self.root_dir = os.path.realpath(root_dir)

    def is_available_locally(self) -> bool:
        """Indique si le dossier racine _anti_gravity est présent physiquement sur la machine courante."""
        return os.path.exists(self.root_dir) and os.path.isdir(self.root_dir)

    async def list_directory(
        self,
        relative_path: str = "",
        depth: int = 1,
        pattern: Optional[str] = None
    ) -> Dict[str, Any]:
        """Liste le contenu d'un répertoire dans _anti_gravity (mode lecture seule)."""
        clean_rel = relative_path.strip().lstrip("/\\")

        # Repli RPC vers jarvis_local_agent si exécuté sur VPS et PC Windows connecté
        try:
            from services.local_agent_service import local_agent_service, is_pc_connected
            if not self.is_available_locally() and is_pc_connected():
                rpc_res = await local_agent_service.execute_command(
                    "list_workspace_dir",
                    timeout=10.0,
                    relative_path=clean_rel,
                    depth=depth,
                    pattern=pattern
                )
                if isinstance(rpc_res, dict) and rpc_res.get("status") in ("success", "error"):
                    return rpc_res
        except Exception as rpc_err:
            print(f"[WorkspaceService] Erreur RPC PC pour list_directory : {rpc_err}")

        # Exécution locale directe sur le système de fichiers
        if not self.is_available_locally():
            return {
                "status": "error",
                "message": (
                    f"Le dossier _anti_gravity est introuvable sur ce serveur ({self.root_dir}) "
                    "et le PC personnel de Pierre est hors-ligne."
                )
            }

        target_dir = os.path.realpath(os.path.join(self.root_dir, clean_rel))
        safe, err = is_path_safe(target_dir, self.root_dir)
        if not safe:
            return {"status": "error", "message": err}

        if not os.path.exists(target_dir):
            return {"status": "error", "message": f"Dossier introuvable : '{clean_rel or '.'}'"}
        if not os.path.isdir(target_dir):
            return {"status": "error", "message": f"'{clean_rel}' n'est pas un dossier."}

        max_depth = max(1, min(depth, 3))
        items: List[Dict[str, Any]] = []
        truncated = False
        max_entries = 150

        try:
            for root, dirs, files in os.walk(target_dir):
                # Calculer la profondeur relative
                rel_from_target = os.path.relpath(root, target_dir)
                cur_depth = 0 if rel_from_target == "." else len(rel_from_target.split(os.sep))
                if cur_depth >= max_depth:
                    dirs.clear()
                    continue

                # Filtrer les dossiers exclus
                dirs[:] = [d for d in dirs if d not in IGNORED_DIR_NAMES and not d.startswith(".")]

                # Enregistrer les sous-dossiers
                for d in sorted(dirs):
                    full_d = os.path.join(root, d)
                    rel_to_root = os.path.relpath(full_d, self.root_dir).replace("\\", "/")
                    mtime = os.path.getmtime(full_d)
                    items.append({
                        "name": d,
                        "relative_path": rel_to_root,
                        "type": "dir",
                        "modified_at": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                    })
                    if len(items) >= max_entries:
                        truncated = True
                        break

                if truncated:
                    break

                # Enregistrer les fichiers
                for f in sorted(files):
                    if f.startswith(".") or f in IGNORED_DIR_NAMES:
                        continue
                    full_f = os.path.join(root, f)
                    safe_f, _ = is_path_safe(full_f, self.root_dir)
                    if not safe_f:
                        continue

                    if pattern and not fnmatch.fnmatch(f.lower(), pattern.lower()):
                        continue

                    rel_to_root = os.path.relpath(full_f, self.root_dir).replace("\\", "/")
                    try:
                        st = os.stat(full_f)
                        size_kb = round(st.st_size / 1024, 1)
                        mtime = st.st_mtime
                    except Exception:
                        size_kb = 0.0
                        mtime = 0.0

                    items.append({
                        "name": f,
                        "relative_path": rel_to_root,
                        "type": "file",
                        "size_kb": size_kb,
                        "modified_at": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M") if mtime else ""
                    })
                    if len(items) >= max_entries:
                        truncated = True
                        break

                if truncated:
                    break

            return {
                "status": "success",
                "base_folder": "_anti_gravity",
                "queried_path": clean_rel or ".",
                "items_count": len(items),
                "truncated": truncated,
                "items": items,
                "message": f"{len(items)} élément(s) recensé(s) dans '_anti_gravity/{clean_rel}'."
            }
        except Exception as e:
            return {"status": "error", "message": f"Erreur lors de la lecture du dossier : {e}"}

    async def read_file(
        self,
        file_path: str,
        max_lines: int = 200,
        offset_line: int = 1
    ) -> Dict[str, Any]:
        """Lit le contenu textuel d'un fichier dans _anti_gravity (mode lecture seule stricte)."""
        clean_path = file_path.strip().lstrip("/\\")

        # Repli RPC vers jarvis_local_agent si exécuté sur VPS et PC Windows connecté
        try:
            from services.local_agent_service import local_agent_service, is_pc_connected
            if not self.is_available_locally() and is_pc_connected():
                rpc_res = await local_agent_service.execute_command(
                    "read_workspace_file",
                    timeout=10.0,
                    file_path=clean_path,
                    max_lines=max_lines,
                    offset_line=offset_line
                )
                if isinstance(rpc_res, dict) and rpc_res.get("status") in ("success", "binary_file", "error"):
                    return rpc_res
        except Exception as rpc_err:
            print(f"[WorkspaceService] Erreur RPC PC pour read_file : {rpc_err}")

        if not self.is_available_locally():
            return {
                "status": "error",
                "message": (
                    f"Le dossier _anti_gravity est introuvable sur ce serveur ({self.root_dir}) "
                    "et le PC de Pierre est hors-ligne."
                )
            }

        target_file = os.path.realpath(os.path.join(self.root_dir, clean_path))
        safe, err = is_path_safe(target_file, self.root_dir)
        if not safe:
            return {"status": "error", "message": err}

        if not os.path.exists(target_file):
            return {"status": "error", "message": f"Fichier introuvable : '{clean_path}'"}
        if not os.path.isfile(target_file):
            return {"status": "error", "message": f"'{clean_path}' est un dossier, pas un fichier."}

        rel_to_root = os.path.relpath(target_file, self.root_dir).replace("\\", "/")

        # Vérification fichier binaire
        if is_binary_file(target_file):
            st = os.stat(target_file)
            return {
                "status": "binary_file",
                "relative_path": rel_to_root,
                "filename": os.path.basename(target_file),
                "size_kb": round(st.st_size / 1024, 1),
                "message": (
                    f"'{os.path.basename(target_file)}' est un fichier binaire "
                    f"({round(st.st_size / 1024, 1)} Ko). Son contenu brut ne peut pas être affiché sous forme textuelle."
                )
            }

        # Limite de lecture brute à 500 Ko
        st = os.stat(target_file)
        if st.st_size > 500 * 1024:
            return {
                "status": "error",
                "message": (
                    f"Fichier trop volumineux pour lecture intégrale en mémoire ({round(st.st_size / 1024, 1)} Ko > 500 Ko). "
                    "Veuillez cibler un sous-extrait ou un fichier plus spécifique."
                )
            }

        try:
            content = ""
            for encoding in ("utf-8", "latin-1", "cp1252"):
                try:
                    with open(target_file, "r", encoding=encoding, errors="replace") as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue

            lines = content.splitlines()
            total_lines = len(lines)
            start_idx = max(0, offset_line - 1)
            end_idx = min(total_lines, start_idx + max(1, min(max_lines, 500)))

            sliced_lines = lines[start_idx:end_idx]
            truncated = end_idx < total_lines

            numbered_content = "\n".join([f"{start_idx + i + 1:4d}: {line}" for i, line in enumerate(sliced_lines)])

            return {
                "status": "success",
                "relative_path": rel_to_root,
                "filename": os.path.basename(target_file),
                "total_lines": total_lines,
                "offset_line": offset_line,
                "lines_shown": len(sliced_lines),
                "truncated": truncated,
                "content": numbered_content,
                "message": (
                    f"Lecture de '{rel_to_root}' (lignes {start_idx + 1} à {end_idx} sur {total_lines})."
                )
            }
        except Exception as e:
            return {"status": "error", "message": f"Erreur lors de la lecture du fichier : {e}"}

    async def search_files(
        self,
        query: str,
        subpath: str = "",
        extension: Optional[str] = None,
        max_results: int = 30
    ) -> Dict[str, Any]:
        """Recherche une chaîne textuelle ou un mot-clé dans les fichiers de code et documents de _anti_gravity."""
        clean_q = query.strip()
        if not clean_q:
            return {"status": "error", "message": "Requête de recherche vide."}

        clean_sub = subpath.strip().lstrip("/\\")

        # Repli RPC vers jarvis_local_agent si exécuté sur VPS et PC Windows connecté
        try:
            from services.local_agent_service import local_agent_service, is_pc_connected
            if not self.is_available_locally() and is_pc_connected():
                rpc_res = await local_agent_service.execute_command(
                    "search_workspace_files",
                    timeout=15.0,
                    query=clean_q,
                    subpath=clean_sub,
                    extension=extension,
                    max_results=max_results
                )
                if isinstance(rpc_res, dict) and rpc_res.get("status") in ("success", "error"):
                    return rpc_res
        except Exception as rpc_err:
            print(f"[WorkspaceService] Erreur RPC PC pour search_files : {rpc_err}")

        if not self.is_available_locally():
            return {
                "status": "error",
                "message": (
                    f"Le dossier _anti_gravity est introuvable sur ce serveur ({self.root_dir}) "
                    "et le PC de Pierre est hors-ligne."
                )
            }

        start_dir = os.path.realpath(os.path.join(self.root_dir, clean_sub))
        safe, err = is_path_safe(start_dir, self.root_dir)
        if not safe:
            return {"status": "error", "message": err}

        matches: List[Dict[str, Any]] = []
        clean_q_lower = clean_q.lower()
        limit = max(1, min(max_results, 50))
        ext_filter = extension.lower().strip() if extension else ""
        if ext_filter and not ext_filter.startswith("."):
            ext_filter = f".{ext_filter}"

        try:
            for root, dirs, files in os.walk(start_dir):
                dirs[:] = [d for d in dirs if d not in IGNORED_DIR_NAMES and not d.startswith(".")]

                for f in sorted(files):
                    if f.startswith(".") or f in IGNORED_DIR_NAMES:
                        continue
                    full_f = os.path.join(root, f)
                    safe_f, _ = is_path_safe(full_f, self.root_dir)
                    if not safe_f or is_binary_file(full_f):
                        continue

                    if ext_filter and not f.lower().endswith(ext_filter):
                        continue

                    # Ignorer les très gros fichiers pour la recherche rapide
                    try:
                        if os.path.getsize(full_f) > 300 * 1024:
                            continue
                        with open(full_f, "r", encoding="utf-8", errors="replace") as fh:
                            for idx, line in enumerate(fh):
                                if clean_q_lower in line.lower():
                                    rel_to_root = os.path.relpath(full_f, self.root_dir).replace("\\", "/")
                                    matches.append({
                                        "file": rel_to_root,
                                        "line": idx + 1,
                                        "snippet": line.strip()[:180]
                                    })
                                    if len(matches) >= limit:
                                        break
                    except Exception:
                        continue

                    if len(matches) >= limit:
                        break
                if len(matches) >= limit:
                    break

            return {
                "status": "success",
                "query": clean_q,
                "matches_count": len(matches),
                "matches": matches,
                "message": f"{len(matches)} occurrence(s) trouvée(s) pour '{clean_q}' dans '_anti_gravity/{clean_sub}'."
            }
        except Exception as e:
            return {"status": "error", "message": f"Erreur lors de la recherche dans les fichiers : {e}"}


# Instance singleton globale
workspace_service = WorkspaceService()
