"""sync_deploy.py — Point d'entrée racine rétrocompatible vers ops/deploy/sync_deploy.py."""
import os
import sys
import runpy

_TARGET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ops", "deploy", "sync_deploy.py")
if __name__ == "__main__":
    runpy.run_path(_TARGET, run_name="__main__")
