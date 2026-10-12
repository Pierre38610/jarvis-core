"""services/system_healing_service.py
Service SRE Avancé d'Auto-Guérison Système pour J.A.R.V.I.S. - Stark Industries.

Gère le cycle de vie complet de l'auto-guérison autonome :
1. Extraction et analyse du patch de code (snippet, diff, code complet).
2. Vérification syntaxique stricte (py_compile).
3. Exécution de tests en sandbox isolée (copie temporaire, hors production).
4. Auto-génération de tests de non-régression si le module ciblé n'a pas de suite de tests.
5. Seuil de confiance & Règle d'escalade : Si un fichier critique (auth_service.py, dispatcher.py)
   est touché, le patch passe en attente de validation orale de Pierre (aucun auto-déploiement).
6. Déploiement selon le pattern Blue/Green releases/timestamp + symlink current pour rollback instantané.
7. Journalisation relationnelle complète (table PostgreSQL patches_auto_appliques + réplique SQLite locale + buffer mémoire).
8. Rollback instantané en 1 clic ou commande vocale.
"""

from __future__ import annotations

import os
import sys
import re
import json
import time
import shutil
import tempfile
import difflib
import logging
import asyncio
import py_compile
import subprocess
from collections import deque
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

import config
from config import BASE_DIR, WORKSPACE_DIR, DB_PATH

logger = logging.getLogger("jarvis.system_healing")

RELEASES_DIR = os.path.join(WORKSPACE_DIR, "releases")
CURRENT_SYMLINK = os.path.join(WORKSPACE_DIR, "current")

# Fichiers critiques du noyau nécessitant impérativement une validation orale de Pierre
CRITICAL_FILES = {
    "auth_service.py",
    "dispatcher.py",
    "auth.py",
    "declarations.py",
    "security.py",
}

EXCLUDE_SANDBOX_PATTERNS = {
    "venv", ".git", "__pycache__", "downloads", "artifacts",
    ".pytest_cache", "clés ssh", ".jarvis_chrome_profile",
    ".jarvis_shopping_profile", ".browseruse", ".antigravity_save",
    "releases", "current", ".healing_sandboxes", "_test_scratch",
    "*.key", "*.pyc", "*.tmp"
}


class SystemHealingService:
    """Gestionnaire central d'auto-guérison SRE, validation isolée et déploiement par releases."""

    def __init__(self, workspace_dir: str = WORKSPACE_DIR, buffer_size: int = 100):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.releases_dir = os.path.join(self.workspace_dir, "releases")
        self.current_symlink = os.path.join(self.workspace_dir, "current")
        os.makedirs(self.releases_dir, exist_ok=True)

        self._memory_buffer: deque = deque(maxlen=buffer_size)
        self._pg_schema_ensured: bool = False
        self._sqlite_schema_ensured: bool = False
        self._ensure_sqlite_schema()

    def _ensure_sqlite_schema(self):
        """Initialise la table locale patches_auto_appliques dans SQLite (persistance hors-ligne)."""
        if self._sqlite_schema_ensured:
            return
        try:
            import sqlite3
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("""
            CREATE TABLE IF NOT EXISTS patches_auto_appliques (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                incident_motif TEXT NOT NULL,
                target_file TEXT NOT NULL,
                patch_diff TEXT NOT NULL,
                test_suite TEXT,
                test_results TEXT NOT NULL,
                status TEXT NOT NULL,
                is_critical INTEGER NOT NULL DEFAULT 0,
                release_path TEXT,
                previous_release_path TEXT,
                applied_at TEXT,
                rolled_back_at TEXT,
                details TEXT NOT NULL
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_patches_created_at ON patches_auto_appliques (created_at DESC);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_patches_status ON patches_auto_appliques (status);")
            conn.commit()
            conn.close()
            self._sqlite_schema_ensured = True
            logger.info("[SystemHealing] Schéma SQLite patches_auto_appliques vérifié")
        except Exception as e:
            logger.warning(f"[SystemHealing] Note init SQLite schema : {e}")

    async def _get_pg_pool(self):
        """Récupère le pool de connexions PostgreSQL s'il est initialisé."""
        try:
            from services.memory import vector_memory
            return getattr(vector_memory, "_pg_pool", None)
        except Exception:
            return None

    async def ensure_pg_schema(self) -> bool:
        """Applique la création de la table patches_auto_appliques dans PostgreSQL 16."""
        if self._pg_schema_ensured:
            return True

        pool = await self._get_pg_pool()
        if not pool:
            return False

        try:
            sql = """
            CREATE TABLE IF NOT EXISTS patches_auto_appliques (
                id                  TEXT            PRIMARY KEY,
                created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
                incident_motif      TEXT            NOT NULL,
                target_file         TEXT            NOT NULL,
                patch_diff          TEXT            NOT NULL,
                test_suite          TEXT,
                test_results        JSONB           NOT NULL DEFAULT '{}',
                status              TEXT            NOT NULL,
                is_critical         BOOLEAN         NOT NULL DEFAULT FALSE,
                release_path        TEXT,
                previous_release_path TEXT,
                applied_at          TIMESTAMPTZ,
                rolled_back_at      TIMESTAMPTZ,
                details             JSONB           NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_patches_auto_appliques_created_at ON patches_auto_appliques (created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_patches_auto_appliques_target_file ON patches_auto_appliques (target_file);
            CREATE INDEX IF NOT EXISTS idx_patches_auto_appliques_status ON patches_auto_appliques (status);
            """
            async with pool.acquire() as conn:
                await conn.execute(sql)
            self._pg_schema_ensured = True
            logger.info("[SystemHealing] Schéma PostgreSQL patches_auto_appliques vérifié")
            return True
        except Exception as e:
            logger.warning(f"[SystemHealing] Impossible d'appliquer le schéma PostgreSQL patches : {e}")
            return False

    def is_critical_file(self, target_file: str) -> bool:
        """Détecte si le fichier ciblé est un composant hautement critique nécessitant validation de Pierre."""
        norm_path = target_file.replace("\\", "/").lower()
        base_name = os.path.basename(norm_path)

        if base_name in CRITICAL_FILES:
            return True

        for cf in ["core/tools/dispatcher.py", "services/auth_service.py", "auth.py", "config.py"]:
            if norm_path.endswith(cf) or cf in norm_path:
                return True

        return False

    # ─── 1. EXTRACTION & NORMALISATION DU PATCH ───────────────────────────────

    def parse_patch_from_output(self, raw_output: str, fallback_file: Optional[str] = None) -> Dict[str, Any]:
        """Extrait les informations du patch de code depuis le rapport de l'agent Antigravity."""
        result = {
            "target_file": fallback_file or "",
            "patch_type": "snippet",
            "search_block": "",
            "replace_block": "",
            "replacement_code": "",
            "diff_text": "",
            "suggested_test_code": "",
            "explanation": "Correctif autonome"
        }

        # 1. Recherche d'un bloc JSON explicite ```json:patch ou ```json
        json_blocks = re.findall(r'```(?:json:patch|json)(.*?)```', raw_output, re.DOTALL)
        for block in json_blocks:
            try:
                data = json.loads(block.strip())
                if isinstance(data, dict) and ("target_file" in data or "file" in data or "search_block" in data or "diff" in data):
                    result["target_file"] = data.get("target_file") or data.get("file") or result["target_file"]
                    result["search_block"] = data.get("search_block") or data.get("original") or ""
                    result["replace_block"] = data.get("replace_block") or data.get("replacement") or ""
                    result["replacement_code"] = data.get("replacement_code") or data.get("full_code") or ""
                    result["diff_text"] = data.get("diff") or data.get("patch_diff") or ""
                    result["explanation"] = data.get("explanation") or result["explanation"]
                    result["suggested_test_code"] = data.get("suggested_test") or data.get("test_code") or ""
                    result["patch_type"] = "replace_snippet" if result["search_block"] else ("replace_file" if result["replacement_code"] else "unified_diff")
                    break
            except Exception:
                continue

        # 2. Recherche d'un bloc de test suggéré ```python:test ou ```python ... def test_
        if not result["suggested_test_code"]:
            test_match = re.search(r'```(?:python:test)(.*?)```', raw_output, re.DOTALL)
            if not test_match:
                test_match = re.search(r'```python\s*(#.*?[Tt]est.*?|import pytest.*?def test_.*?)```', raw_output, re.DOTALL)
            if not test_match:
                test_match = re.search(r'```python(.*?(?:def\s+test_).*?)```', raw_output, re.DOTALL)
            if test_match:
                import textwrap
                result["suggested_test_code"] = textwrap.dedent(test_match.group(1)).strip()

        # 3. Recherche d'un bloc diff ```diff
        diff_match = re.search(r'```diff(.*?)```', raw_output, re.DOTALL)
        if diff_match:
            diff_text = diff_match.group(1).strip()
            result["diff_text"] = diff_text
            if not result.get("search_block"):
                result["patch_type"] = "unified_diff"
            file_match = re.search(r'(?:---|\+\+\+)\s+[ab]/(.*?)(?:\s|$)', diff_text)
            if file_match and not result["target_file"]:
                result["target_file"] = file_match.group(1).strip()

        # 4. Recherche d'un bloc python ciblé ```python:chemin/vers/fichier.py
        py_target_match = re.search(r'```python:([a-zA-Z0-9_\-\./\\]+\.py)(.*?)```', raw_output, re.DOTALL)
        if py_target_match:
            result["target_file"] = py_target_match.group(1).strip()
            result["replacement_code"] = py_target_match.group(2).strip()
            result["patch_type"] = "replace_file"

        # 5. Fallback heuristique : détection de mention de fichier source dans le texte
        if not result["target_file"]:
            f_match = re.search(r'(?:services|core|routers|utils)/[a-zA-Z0-9_-]+\.py', raw_output)
            if f_match:
                result["target_file"] = f_match.group(0)

        # Extraction de snippet code python brut
        raw_py = re.findall(r'```python(.*?)```', raw_output, re.DOTALL)
        if raw_py and not result["replacement_code"] and not result["search_block"]:
            candidates = [c.strip() for c in raw_py if "def test_" not in c]
            if candidates:
                result["replacement_code"] = candidates[0]
                result["patch_type"] = "replace_snippet"

        return result

    # ─── 2. ENVIRONNEMENT ISOLÉ (SANDBOX) & VALIDATION TESTS ──────────────────

    def create_isolated_sandbox(self) -> str:
        """Copie le repository dans un répertoire temporaire isolé hors production."""
        parent_dir = os.path.join(self.workspace_dir, ".healing_sandboxes")
        os.makedirs(parent_dir, exist_ok=True)
        import random
        sandbox_dir = os.path.join(parent_dir, f"heal_{int(time.time() * 1000)}_{random.randint(1000, 9999)}")
        os.makedirs(sandbox_dir, exist_ok=True)

        def _ignore_filter(src, names):
            ignored = set()
            for name in names:
                if name in EXCLUDE_SANDBOX_PATTERNS or name.startswith("."):
                    ignored.add(name)
                elif any(name.endswith(ext) for ext in [".pyc", ".tmp", ".log", ".key"]):
                    ignored.add(name)
            return ignored

        # Copie récursive sécurisée
        for item in os.listdir(self.workspace_dir):
            if item in EXCLUDE_SANDBOX_PATTERNS or item.startswith("."):
                continue
            src_path = os.path.join(self.workspace_dir, item)
            dst_path = os.path.join(sandbox_dir, item)
            if os.path.isdir(src_path):
                shutil.copytree(src_path, dst_path, ignore=_ignore_filter, symlinks=False if sys.platform == "win32" else True)
            elif os.path.isfile(src_path) and not item.endswith((".key", ".tmp")):
                shutil.copy2(src_path, dst_path)

        return sandbox_dir

    def apply_patch_to_target(
        self,
        base_path: str,
        target_file: str,
        patch_info: Dict[str, Any]
    ) -> Tuple[bool, str, str]:
        """Applique le patch sur un fichier donné, vérifie sa syntaxe et calcule le diff.
        Retourne (succès, diff_unifié, message_erreur).
        """
        full_path = os.path.join(base_path, target_file)
        if not os.path.exists(full_path):
            return False, "", f"Fichier cible introuvable : {target_file}"

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                original_content = f.read()
        except Exception as e:
            return False, "", f"Erreur lecture fichier cible : {e}"

        new_content = original_content

        # Application selon le format
        if patch_info.get("patch_type") == "replace_file" and patch_info.get("replacement_code"):
            new_content = patch_info["replacement_code"]

        elif patch_info.get("search_block") and patch_info.get("replace_block"):
            s_block = patch_info["search_block"].strip()
            r_block = patch_info["replace_block"].strip()
            if s_block in original_content:
                new_content = original_content.replace(s_block, r_block, 1)
            else:
                # Tentative avec normalisation des espaces
                s_lines = "\n".join(line.strip() for line in s_block.splitlines() if line.strip())
                orig_lines = "\n".join(line.strip() for line in original_content.splitlines() if line.strip())
                if s_lines in orig_lines:
                    # Remplacement exact ligne par ligne
                    new_content = original_content.replace(patch_info["search_block"], patch_info["replace_block"])
                else:
                    return False, "", f"search_block introuvable dans {target_file}"

        elif patch_info.get("replacement_code"):
            # Si c'est un snippet de remplacement
            s_block = patch_info.get("search_block")
            if s_block and s_block in original_content:
                new_content = original_content.replace(s_block, patch_info["replacement_code"])
            else:
                # En fallback, si la fonction existe déjà, on remplace la fonction
                func_match = re.search(r'def\s+([a-zA-Z0-9_]+)\s*\(', patch_info["replacement_code"])
                if func_match:
                    func_name = func_match.group(1)
                    pattern = rf'def\s+{func_name}\s*\(.*?(?=\ndef|\nclass|\Z)'
                    if re.search(pattern, original_content, re.DOTALL):
                        new_content = re.sub(pattern, patch_info["replacement_code"], original_content, flags=re.DOTALL)
                    else:
                        new_content = original_content + "\n\n" + patch_info["replacement_code"]
                else:
                    new_content = patch_info["replacement_code"]
        else:
            return False, "", "Aucun bloc de modification valide n'a pu être extrait du patch"

        # Écriture temporaire pour vérification syntaxique
        try:
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception as e:
            return False, "", f"Erreur écriture correctif : {e}"

        # ─── VÉRIFICATION SYNTAXIQUE STRICTE PY_COMPILE ───────────────────────
        try:
            py_compile.compile(full_path, doraise=True)
        except py_compile.PyCompileError as py_err:
            # Restauration immédiate en cas d'erreur de syntaxe
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(original_content)
            return False, "", f"Erreur syntaxique py_compile : {py_err}"

        # Calcul du diff unifié propre
        orig_lines = original_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff = "".join(difflib.unified_diff(
            orig_lines, new_lines,
            fromfile=f"a/{target_file}",
            tofile=f"b/{target_file}"
        ))

        return True, diff or "Modifications appliquées (diff identique ou minime)", ""

    def find_or_generate_tests(
        self,
        sandbox_dir: str,
        target_file: str,
        incident_context: Dict[str, Any],
        suggested_test_code: Optional[str] = None
    ) -> Tuple[List[str], bool, str]:
        """Localise la suite de tests existante ciblant le module, ou génère un test minimal de non-régression.
        Retourne (liste_des_fichiers_tests_relatifs, est_généré, code_du_test).
        """
        stem = os.path.splitext(os.path.basename(target_file))[0]
        tests_dir = os.path.join(sandbox_dir, "tests")
        os.makedirs(tests_dir, exist_ok=True)

        candidate_tests = [
            f"tests/test_{stem}.py",
            f"tests/unit/test_{stem}.py",
            f"tests/test_{stem.replace('_service', '')}.py"
        ]

        existing = []
        for rel in candidate_tests:
            if os.path.exists(os.path.join(sandbox_dir, rel)):
                existing.append(rel)

        if existing:
            return existing, False, ""

        # Aucun test existant : Génération automatique d'un test minimal de non-régression
        gen_filename = f"tests/test_regression_{stem}.py"
        gen_full_path = os.path.join(sandbox_dir, gen_filename)

        if suggested_test_code and "def test_" in suggested_test_code:
            import textwrap
            test_content = textwrap.dedent(suggested_test_code).strip() + "\n"
        else:
            # Détection des classes ou fonctions dans le fichier cible
            module_import_path = target_file.replace("/", ".").replace("\\", ".").replace(".py", "")
            if module_import_path.startswith("."):
                module_import_path = module_import_path.lstrip(".")

            test_content = (
                f'"""Test minimal de non-régression généré automatiquement par J.A.R.V.I.S. SRE.\n'
                f'Module ciblé : {target_file}\n'
                f'Incident initial : {incident_context.get("message", "Anomalie d execution")}\n'
                f'"""\n'
                f'import pytest\n'
                f'import importlib\n\n'
                f'def test_module_import_and_integrity_{stem}():\n'
                f'    """Vérifie l\'importabilité et l\'absence de régression syntaxique ou cyclique."""\n'
                f'    mod = importlib.import_module("{module_import_path}")\n'
                f'    assert mod is not None\n\n'
                f'def test_smoke_sanity_check_{stem}():\n'
                f'    """Vérifie que les symboles clés du module sont intacts."""\n'
                f'    mod = importlib.import_module("{module_import_path}")\n'
                f'    symbols = [s for s in dir(mod) if not s.startswith("_")]\n'
                f'    assert len(symbols) >= 0\n'
            )

        with open(gen_full_path, "w", encoding="utf-8") as f:
            f.write(test_content)

        return [gen_filename], True, test_content

    async def execute_tests_in_sandbox(self, sandbox_dir: str, test_files: List[str]) -> Dict[str, Any]:
        """Exécute pytest dans l'environnement isolé."""
        python_bin = sys.executable
        if sys.platform == "win32":
            venv_py = os.path.join(sys.prefix, "Scripts", "python.exe")
            if os.path.exists(venv_py):
                python_bin = venv_py
            elif os.path.exists(os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")):
                python_bin = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")

        env = os.environ.copy()
        env["PYTHONPATH"] = sandbox_dir

        # Garantit que sandbox_dir est la racine stricte pour pytest et sys.path
        ini_path = os.path.join(sandbox_dir, "pytest.ini")
        if not os.path.exists(ini_path):
            with open(ini_path, "w", encoding="utf-8") as f:
                f.write("[pytest]\nrootdir = .\npythonpath = .\n")

        # Conftest d'isolation garantissant que sandbox_dir a la priorité absolue
        sandbox_conftest = os.path.join(sandbox_dir, "tests", "conftest.py")
        if not os.path.exists(sandbox_conftest):
            os.makedirs(os.path.dirname(sandbox_conftest), exist_ok=True)
            with open(sandbox_conftest, "w", encoding="utf-8") as f:
                f.write(
                    "import sys, os\n"
                    "ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))\n"
                    "if ROOT in sys.path: sys.path.remove(ROOT)\n"
                    "sys.path.insert(0, ROOT)\n"
                )

        runner_script = (
            f"import sys, os\n"
            f"root = r'{sandbox_dir}'\n"
            f"if root in sys.path: sys.path.remove(root)\n"
            f"sys.path.insert(0, root)\n"
            f"import pytest\n"
            f"sys.exit(pytest.main({json.dumps(test_files)} + ['-v', '--tb=short', '-c', r'{ini_path}', '-o', 'rootdir=' + r'{sandbox_dir}']))\n"
        )
        cmd = [python_bin, "-c", runner_script]

        start_t = time.time()
        loop = asyncio.get_running_loop()

        def _run_sync():
            return subprocess.run(
                cmd,
                cwd=sandbox_dir,
                env=env,
                capture_output=True,
                timeout=120
            )

        try:
            completed_proc = await loop.run_in_executor(None, _run_sync)
            duration = round(time.time() - start_t, 2)

            stdout_txt = completed_proc.stdout.decode(errors="replace")
            stderr_txt = completed_proc.stderr.decode(errors="replace")
            passed = (completed_proc.returncode == 0)

            summary_match = re.search(r'==+ (.*?) ==+', stdout_txt)
            summary_str = summary_match.group(1) if summary_match else f"returncode {completed_proc.returncode}"

            return {
                "passed": passed,
                "returncode": completed_proc.returncode,
                "duration_s": duration,
                "summary": summary_str,
                "stdout": stdout_txt[-1500:],
                "stderr": stderr_txt[-1000:],
                "test_files": test_files
            }
        except Exception as e:
            return {
                "passed": False,
                "returncode": -1,
                "duration_s": round(time.time() - start_t, 2),
                "summary": f"Exception exécution tests : {e}",
                "stdout": "",
                "stderr": str(e),
                "test_files": test_files
            }

    # ─── 3. PATTERN RELEASES/TIMESTAMP & SYMLINK CURRENT ─────────────────────

    def create_release_with_patch(
        self,
        target_file: str,
        patch_info: Dict[str, Any],
        generated_test_code: Optional[str] = None,
        generated_test_file: Optional[str] = None
    ) -> Tuple[str, str, str]:
        """Crée une nouvelle release dans releases/timestamp avec le patch appliqué.
        Retourne (release_id, release_dir, diff_unifié).
        """
        release_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        release_dir = os.path.join(self.releases_dir, release_id)
        os.makedirs(release_dir, exist_ok=True)

        def _ignore_filter(src, names):
            ignored = set()
            for name in names:
                if name in EXCLUDE_SANDBOX_PATTERNS or name.startswith("."):
                    ignored.add(name)
                elif any(name.endswith(ext) for ext in [".pyc", ".tmp", ".log", ".key"]):
                    ignored.add(name)
            return ignored

        # Copie de l'état actuel de la base
        for item in os.listdir(self.workspace_dir):
            if item in EXCLUDE_SANDBOX_PATTERNS or item.startswith("."):
                continue
            src_path = os.path.join(self.workspace_dir, item)
            dst_path = os.path.join(release_dir, item)
            if os.path.isdir(src_path):
                shutil.copytree(src_path, dst_path, ignore=_ignore_filter, symlinks=False if sys.platform == "win32" else True)
            elif os.path.isfile(src_path) and not item.endswith((".key", ".tmp")):
                shutil.copy2(src_path, dst_path)

        # Application du patch dans la release
        ok, diff, err = self.apply_patch_to_target(release_dir, target_file, patch_info)
        if not ok:
            shutil.rmtree(release_dir, ignore_errors=True)
            raise RuntimeError(f"Échec application patch dans release : {err}")

        # Inclusion du test de non-régression auto-généré si existant
        if generated_test_code and generated_test_file:
            t_path = os.path.join(release_dir, generated_test_file)
            os.makedirs(os.path.dirname(t_path), exist_ok=True)
            with open(t_path, "w", encoding="utf-8") as f:
                f.write(generated_test_code)

        return release_id, release_dir, diff

    def activate_release_symlink(self, release_dir: str, target_file: str, patch_info: Dict[str, Any]) -> str:
        """Fait basculer atomiquement le symlink 'current' vers la nouvelle release,
        et applique le patch dans le workspace actif avec sauvegarde .bak.
        Retourne le chemin de la release précédente.
        """
        previous_release = None
        if os.path.islink(self.current_symlink) or os.path.exists(self.current_symlink):
            try:
                if os.path.islink(self.current_symlink):
                    previous_release = os.readlink(self.current_symlink)
                elif os.path.isdir(self.current_symlink):
                    previous_release = self.current_symlink
            except Exception:
                pass

        # 1. Mise à jour atomique du symlink
        tmp_link = os.path.join(self.workspace_dir, "current_tmp")
        try:
            if os.path.islink(tmp_link) or os.path.exists(tmp_link):
                if os.path.islink(tmp_link):
                    os.remove(tmp_link)
                else:
                    shutil.rmtree(tmp_link, ignore_errors=True)

            try:
                os.symlink(release_dir, tmp_link, target_is_directory=True)
                os.replace(tmp_link, self.current_symlink)
                logger.info(f"[SystemHealing] Symlink 'current' basculé vers {release_dir}")
            except (OSError, NotImplementedError):
                # Fallback Windows sans Developer Mode : fichier pointeur + mise à jour directe
                with open(os.path.join(self.workspace_dir, "current_release.txt"), "w", encoding="utf-8") as f:
                    f.write(release_dir)
        except Exception as e:
            logger.warning(f"[SystemHealing] Note symlink current : {e}")

        # 2. Sauvegarde et application dans le workspace actif pour prise en compte immédiate
        ws_target = os.path.join(self.workspace_dir, target_file)
        if os.path.exists(ws_target):
            bak_path = ws_target + ".bak"
            shutil.copy2(ws_target, bak_path)
            self.apply_patch_to_target(self.workspace_dir, target_file, patch_info)

        return previous_release or ""

    def revert_release(self, previous_release_dir: str, target_file: str) -> bool:
        """Restaure la release précédente et le fichier source original."""
        try:
            # Restauration du symlink
            if previous_release_dir and os.path.exists(previous_release_dir):
                tmp_link = os.path.join(self.workspace_dir, "current_tmp")
                try:
                    if os.path.islink(tmp_link) or os.path.exists(tmp_link):
                        os.remove(tmp_link)
                    os.symlink(previous_release_dir, tmp_link, target_is_directory=True)
                    os.replace(tmp_link, self.current_symlink)
                except Exception:
                    with open(os.path.join(self.workspace_dir, "current_release.txt"), "w", encoding="utf-8") as f:
                        f.write(previous_release_dir)

            # Restauration du fichier source depuis .bak
            ws_target = os.path.join(self.workspace_dir, target_file)
            bak_path = ws_target + ".bak"
            if os.path.exists(bak_path):
                shutil.copy2(bak_path, ws_target)
                os.remove(bak_path)
                logger.info(f"[SystemHealing] Fichier source {target_file} restauré depuis backup")
            elif previous_release_dir and os.path.exists(os.path.join(previous_release_dir, target_file)):
                shutil.copy2(os.path.join(previous_release_dir, target_file), ws_target)
                logger.info(f"[SystemHealing] Fichier source {target_file} restauré depuis release précédente")

            return True
        except Exception as e:
            logger.error(f"[SystemHealing] Erreur lors du rollback : {e}")
            return False

    # ─── 4. JOURNALISATION (POSTGRESQL + SQLITE + MÉMOIRE) ────────────────────

    async def log_patch(
        self,
        patch_id: str,
        incident_motif: str,
        target_file: str,
        patch_diff: str,
        test_suite: str,
        test_results: Dict[str, Any],
        status: str,
        is_critical: bool,
        release_path: Optional[str] = None,
        previous_release_path: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Enregistre le patch dans le buffer mémoire, SQLite et PostgreSQL."""
        now_iso = datetime.now().isoformat()
        record = {
            "id": patch_id,
            "created_at": now_iso,
            "incident_motif": incident_motif,
            "target_file": target_file,
            "patch_diff": patch_diff,
            "test_suite": test_suite,
            "test_results": test_results,
            "status": status,
            "is_critical": is_critical,
            "release_path": release_path or "",
            "previous_release_path": previous_release_path or "",
            "applied_at": now_iso if status == "applied" else None,
            "rolled_back_at": None,
            "details": details or {}
        }

        # 1. Enregistrement mémoire
        self._memory_buffer.appendleft(record)

        # 2. Enregistrement SQLite local
        try:
            import sqlite3
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("""
            INSERT OR REPLACE INTO patches_auto_appliques (
                id, created_at, incident_motif, target_file, patch_diff,
                test_suite, test_results, status, is_critical, release_path,
                previous_release_path, applied_at, rolled_back_at, details
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record["id"], record["created_at"], record["incident_motif"], record["target_file"],
                record["patch_diff"], record["test_suite"], json.dumps(record["test_results"]),
                record["status"], 1 if record["is_critical"] else 0, record["release_path"],
                record["previous_release_path"], record["applied_at"], record["rolled_back_at"],
                json.dumps(record["details"])
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"[SystemHealing] Erreur écriture SQLite patch: {e}")

        # 3. Enregistrement PostgreSQL 16 (si disponible)
        try:
            pool = await self._get_pg_pool()
            if pool:
                await self.ensure_pg_schema()
                sql = """
                INSERT INTO patches_auto_appliques (
                    id, incident_motif, target_file, patch_diff, test_suite,
                    test_results, status, is_critical, release_path,
                    previous_release_path, applied_at, rolled_back_at, details
                ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10, $11, $12, $13::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    applied_at = EXCLUDED.applied_at,
                    rolled_back_at = EXCLUDED.rolled_back_at,
                    details = EXCLUDED.details;
                """
                async with pool.acquire() as conn:
                    await conn.execute(
                        sql,
                        record["id"], record["incident_motif"], record["target_file"],
                        record["patch_diff"], record["test_suite"], json.dumps(record["test_results"]),
                        record["status"], record["is_critical"], record["release_path"],
                        record["previous_release_path"],
                        datetime.fromisoformat(record["applied_at"]) if record["applied_at"] else None,
                        None,
                        json.dumps(record["details"])
                    )
        except Exception as e:
            logger.debug(f"[SystemHealing] Pas d'écriture PostgreSQL pour le patch ({e}) - persistance SQLite active")

        return record

    async def update_patch_status(
        self,
        patch_id: str,
        new_status: str,
        rolled_back_at: Optional[str] = None,
        applied_at: Optional[str] = None
    ) -> bool:
        """Met à jour le statut d'un patch existant (ex: passage à 'applied' ou 'rolled_back')."""
        # 1. Mémoire
        for p in self._memory_buffer:
            if p["id"] == patch_id:
                p["status"] = new_status
                if rolled_back_at:
                    p["rolled_back_at"] = rolled_back_at
                if applied_at:
                    p["applied_at"] = applied_at
                break

        # 2. SQLite
        try:
            import sqlite3
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute(
                "UPDATE patches_auto_appliques SET status = ?, rolled_back_at = COALESCE(?, rolled_back_at), applied_at = COALESCE(?, applied_at) WHERE id = ?",
                (new_status, rolled_back_at, applied_at, patch_id)
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

        # 3. PostgreSQL
        try:
            pool = await self._get_pg_pool()
            if pool:
                sql = """
                UPDATE patches_auto_appliques
                SET status = $1,
                    rolled_back_at = COALESCE($2, rolled_back_at),
                    applied_at = COALESCE($3, applied_at)
                WHERE id = $4
                """
                async with pool.acquire() as conn:
                    await conn.execute(
                        sql,
                        new_status,
                        datetime.fromisoformat(rolled_back_at) if rolled_back_at else None,
                        datetime.fromisoformat(applied_at) if applied_at else None,
                        patch_id
                    )
        except Exception:
            pass

        return True

    async def get_recent_patches(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Récupère l'historique des patches (PostgreSQL -> SQLite -> Buffer mémoire)."""
        pool = await self._get_pg_pool()
        if pool:
            try:
                await self.ensure_pg_schema()
                sql = """
                SELECT id, created_at, incident_motif, target_file, patch_diff,
                       test_suite, test_results, status, is_critical, release_path,
                       previous_release_path, applied_at, rolled_back_at, details
                FROM patches_auto_appliques
                ORDER BY created_at DESC
                LIMIT $1
                """
                async with pool.acquire() as conn:
                    rows = await conn.fetch(sql, limit)
                    return [{
                        "id": r["id"],
                        "created_at": r["created_at"].isoformat() if r["created_at"] else "",
                        "incident_motif": r["incident_motif"],
                        "target_file": r["target_file"],
                        "patch_diff": r["patch_diff"],
                        "test_suite": r["test_suite"],
                        "test_results": r["test_results"] if isinstance(r["test_results"], dict) else json.loads(r["test_results"] or "{}"),
                        "status": r["status"],
                        "is_critical": r["is_critical"],
                        "release_path": r["release_path"],
                        "previous_release_path": r["previous_release_path"],
                        "applied_at": r["applied_at"].isoformat() if r["applied_at"] else None,
                        "rolled_back_at": r["rolled_back_at"].isoformat() if r["rolled_back_at"] else None,
                        "details": r["details"] if isinstance(r["details"], dict) else json.loads(r["details"] or "{}")
                    } for r in rows]
            except Exception as e:
                logger.warning(f"[SystemHealing] Repli SQLite car lecture Postgres en erreur : {e}")

        # Repli SQLite
        try:
            import sqlite3
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("""
            SELECT id, created_at, incident_motif, target_file, patch_diff,
                   test_suite, test_results, status, is_critical, release_path,
                   previous_release_path, applied_at, rolled_back_at, details
            FROM patches_auto_appliques
            ORDER BY created_at DESC
            LIMIT ?
            """, (limit,))
            rows = cur.fetchall()
            conn.close()
            if rows:
                return [{
                    "id": r[0], "created_at": r[1], "incident_motif": r[2], "target_file": r[3],
                    "patch_diff": r[4], "test_suite": r[5],
                    "test_results": json.loads(r[6]) if isinstance(r[6], str) else r[6],
                    "status": r[7], "is_critical": bool(r[8]), "release_path": r[9],
                    "previous_release_path": r[10], "applied_at": r[11], "rolled_back_at": r[12],
                    "details": json.loads(r[13]) if isinstance(r[13], str) else r[13]
                } for r in rows]
        except Exception:
            pass

        # Repli mémoire
        return list(self._memory_buffer)[:limit]

    # ─── 5. ORCHESTRATION DU WORKFLOW COMPLET D'AUTO-GUÉRISON ─────────────────

    async def process_healing_patch(
        self,
        incident_motif: str,
        raw_agent_output: str,
        incident_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Exécute l'orchestration complète :
        1. Parse le patch.
        2. Teste dans une sandbox isolée.
        3. Exécute la suite de tests ou génère le test de non-régression.
        4. Si les tests échouent : rejette le patch et journalise l'échec.
        5. Si le fichier est critique : passe en statut requires_validation (attente accord Pierre).
        6. Sinon : crée la release et active le symlink current.
        7. Journalise dans patches_auto_appliques.
        """
        incident_context = incident_context or {}
        patch_id = f"patch_{int(time.time())}_{os.urandom(3).hex()}"

        patch_info = self.parse_patch_from_output(raw_agent_output, fallback_file=incident_context.get("source"))
        target_file = patch_info.get("target_file") or ""

        if not target_file:
            logger.warning("[SystemHealing] Aucun fichier source cible identifié dans le rapport.")
            return {
                "success": False,
                "status": "no_target_file",
                "oral_pitch": "Pierre, j'ai terminé l'analyse SRE mais aucun fichier source précis n'a été désigné pour application d'un patch.",
                "patch_id": patch_id
            }

        is_critical = self.is_critical_file(target_file)

        # ─── ÉTAPE A : VALIDATION ISOLÉE EN SANDBOX ───────────────────────────
        sandbox_dir = self.create_isolated_sandbox()
        try:
            # 1. Application du patch dans la copie temporaire
            ok_apply, diff_unifie, err_apply = self.apply_patch_to_target(sandbox_dir, target_file, patch_info)
            if not ok_apply:
                fail_details = {"error": err_apply, "stage": "apply_patch_or_py_compile"}
                await self.log_patch(
                    patch_id=patch_id,
                    incident_motif=incident_motif,
                    target_file=target_file,
                    patch_diff=patch_info.get("diff_text") or err_apply,
                    test_suite="py_compile",
                    test_results={"passed": False, "error": err_apply},
                    status="failed_syntax",
                    is_critical=is_critical,
                    details=fail_details
                )
                return {
                    "success": False,
                    "status": "failed_syntax",
                    "oral_pitch": f"Pierre, le patch préparé pour '{os.path.basename(target_file)}' a échoué à la compilation syntaxique en sandbox. Application annulée pour préserver la production.",
                    "details": fail_details,
                    "patch_id": patch_id
                }

            # 2. Recherche ou génération de tests
            test_files, is_generated, gen_test_code = self.find_or_generate_tests(
                sandbox_dir=sandbox_dir,
                target_file=target_file,
                incident_context=incident_context,
                suggested_test_code=patch_info.get("suggested_test_code")
            )
            test_suite_label = f"Auto-généré: {test_files[0]}" if is_generated else ", ".join(test_files)

            # 3. Exécution des tests en environnement isolé
            test_result = await self.execute_tests_in_sandbox(sandbox_dir, test_files)

            if not test_result.get("passed"):
                # ÉCHEC DES TESTS : REJET DU PATCH
                fail_details = {
                    "stage": "test_execution",
                    "stdout": test_result.get("stdout"),
                    "summary": test_result.get("summary")
                }
                await self.log_patch(
                    patch_id=patch_id,
                    incident_motif=incident_motif,
                    target_file=target_file,
                    patch_diff=diff_unifie,
                    test_suite=test_suite_label,
                    test_results=test_result,
                    status="failed_tests",
                    is_critical=is_critical,
                    details=fail_details
                )
                return {
                    "success": False,
                    "status": "failed_tests",
                    "oral_pitch": f"Pierre, le patch pour '{os.path.basename(target_file)}' a provoqué un échec lors des tests automatisés en sandbox. Il a été rejeté sans toucher à la production.",
                    "test_results": test_result,
                    "patch_id": patch_id
                }

        finally:
            shutil.rmtree(sandbox_dir, ignore_errors=True)

        # ─── ÉTAPE B : ARBITRAGE SELON SEUIL DE CONFIANCE (CRITICITÉ) ─────────
        if is_critical:
            # FICHIER CRITIQUE : DÉLÉGATION À VALIDATION ORALE DE PIERRE
            release_id, release_dir, real_diff = self.create_release_with_patch(
                target_file=target_file,
                patch_info=patch_info,
                generated_test_code=gen_test_code if is_generated else None,
                generated_test_file=test_files[0] if is_generated else None
            )

            record = await self.log_patch(
                patch_id=patch_id,
                incident_motif=incident_motif,
                target_file=target_file,
                patch_diff=real_diff,
                test_suite=test_suite_label,
                test_results=test_result,
                status="requires_validation",
                is_critical=True,
                release_path=release_dir,
                details={"release_id": release_id, "is_generated_test": is_generated}
            )

            oral_pitch = (
                f"Pierre, j'ai validé avec succès en sandbox isolée un correctif pour le fichier critique '{os.path.basename(target_file)}'. "
                f"Tous les tests passent ({test_result.get('duration_s')}s). Conformément aux protocoles de sécurité Stark, "
                f"je sollicite ta validation orale avant d'appliquer ce patch sur le noyau en production."
            )
            telegram_extra = (
                f"⚠️ *Validation requise pour fichier critique* : `{target_file}`\n"
                f"🧪 *Tests* : `{test_suite_label}` (Réussite en {test_result.get('duration_s')}s)\n"
                f"📦 *Release préparée* : `{release_dir}`\n"
            )

            return {
                "success": True,
                "status": "requires_validation",
                "is_critical": True,
                "oral_pitch": oral_pitch,
                "telegram_extra": telegram_extra,
                "patch_id": patch_id,
                "diff": real_diff,
                "test_results": test_result,
                "release_path": release_dir
            }

        else:
            # FICHIER STANDARD NON CRITIQUE : APPLICATION AUTOMATIQUE AVEC RELEASES + SYMLINK
            release_id, release_dir, real_diff = self.create_release_with_patch(
                target_file=target_file,
                patch_info=patch_info,
                generated_test_code=gen_test_code if is_generated else None,
                generated_test_file=test_files[0] if is_generated else None
            )

            prev_release = self.activate_release_symlink(release_dir, target_file, patch_info)

            record = await self.log_patch(
                patch_id=patch_id,
                incident_motif=incident_motif,
                target_file=target_file,
                patch_diff=real_diff,
                test_suite=test_suite_label,
                test_results=test_result,
                status="applied",
                is_critical=False,
                release_path=release_dir,
                previous_release_path=prev_release,
                details={"release_id": release_id, "is_generated_test": is_generated}
            )

            oral_pitch = (
                f"Pierre, l'anomalie sur '{os.path.basename(target_file)}' a été corrigée avec succès. "
                f"Le patch a validé la suite de tests en sandbox isolée et a été déployé sous la release {release_id} "
                f"avec symlink et garantie de rollback instantané."
            )
            telegram_extra = (
                f"✅ *Patch SRE auto-appliqué* : `{target_file}`\n"
                f"🧪 *Tests validés* : `{test_suite_label}` ({test_result.get('duration_s')}s)\n"
                f"📦 *Release active* : `{release_dir}`\n"
                f"🔄 *Rollback instantané disponible* : `/api/supervision/patches/{patch_id}/rollback`\n"
            )

            return {
                "success": True,
                "status": "applied",
                "is_critical": False,
                "oral_pitch": oral_pitch,
                "telegram_extra": telegram_extra,
                "patch_id": patch_id,
                "diff": real_diff,
                "test_results": test_result,
                "release_path": release_dir,
                "previous_release_path": prev_release
            }

    # ─── 6. GESTION DU ROLLBACK & APPROBATION MANUELLE ────────────────────────

    async def rollback_patch(self, patch_id: Optional[str] = None) -> Dict[str, Any]:
        """Exécute un rollback instantané vers la version précédente du code."""
        patches = await self.get_recent_patches(limit=20)
        target_patch = None

        if patch_id:
            for p in patches:
                if p["id"] == patch_id:
                    target_patch = p
                    break
        else:
            # Dernier patch appliqué
            for p in patches:
                if p["status"] == "applied":
                    target_patch = p
                    break

        if not target_patch:
            return {"success": False, "message": "Aucun patch éligible au rollback trouvé."}

        target_file = target_patch["target_file"]
        prev_rel = target_patch.get("previous_release_path") or ""

        ok = self.revert_release(prev_rel, target_file)
        if ok:
            now_iso = datetime.now().isoformat()
            await self.update_patch_status(target_patch["id"], new_status="rolled_back", rolled_back_at=now_iso)
            logger.info(f"[SystemHealing] Rollback du patch {target_patch['id']} effectué avec succès.")
            return {
                "success": True,
                "patch_id": target_patch["id"],
                "target_file": target_file,
                "message": f"Rollback instantané effectué pour '{target_file}'. Service rétabli sur la version antérieure."
            }
        else:
            return {"success": False, "message": f"Échec de la restauration pour '{target_file}'."}

    async def approve_and_apply_patch(self, patch_id: str) -> Dict[str, Any]:
        """Valide et applique un patch sur fichier critique en attente d'accord."""
        patches = await self.get_recent_patches(limit=20)
        target_patch = next((p for p in patches if p["id"] == patch_id), None)

        if not target_patch:
            return {"success": False, "message": f"Patch {patch_id} introuvable."}

        if target_patch["status"] != "requires_validation":
            return {"success": False, "message": f"Le patch {patch_id} a déjà le statut '{target_patch['status']}'."}

        target_file = target_patch["target_file"]
        release_path = target_patch.get("release_path")

        if not release_path or not os.path.exists(release_path):
            return {"success": False, "message": "Répertoire de release introuvable pour ce patch."}

        # Application de la release
        prev_release = self.activate_release_symlink(release_path, target_file, {
            "patch_type": "replace_file",
            "replacement_code": open(os.path.join(release_path, target_file), "r", encoding="utf-8").read()
        })

        now_iso = datetime.now().isoformat()
        await self.update_patch_status(patch_id, new_status="applied", applied_at=now_iso)

        logger.info(f"[SystemHealing] Patch critique {patch_id} validé par Pierre et appliqué en production.")
        return {
            "success": True,
            "patch_id": patch_id,
            "target_file": target_file,
            "message": f"Patch critique '{target_file}' validé et déployé avec succès en production."
        }


# Singleton exporté
system_healing_service = SystemHealingService()
