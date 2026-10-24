"""sync_deploy.py — Point d'entrée racine rétrocompatible vers ops/deploy/sync_deploy.py."""
import os
import sys

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

from ops.deploy.sync_deploy import (
    sync_and_verify_versions,
    deploy_to_vps,
    git_commit_and_push,
    get_candidate_keys,
    main,
)

if __name__ == "__main__":
    main()
