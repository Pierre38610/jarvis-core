"""Package backend.core : état partagé et outillage central J.A.R.V.I.S."""
import os
import sys

_CORE_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_CORE_DIR)
_ROOT_DIR = os.path.dirname(_BACKEND_DIR)
for _p in (_BACKEND_DIR, _ROOT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)
