"""Point d'entrée racine conservé pour compatibilité ascendante (ex: uvicorn App:app, tests, systemd).
Délègue directement vers backend.App.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.join(_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.App import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.App:app", host="0.0.0.0", port=8000, reload=True)
