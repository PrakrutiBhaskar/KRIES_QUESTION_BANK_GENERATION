"""
Backend (Module B) for the Question Bank Generator.

Module A (`generation_engine`) lives at the repository root rather than inside
this package, so that the two modules stay independently ownable and
testable. This bootstrap makes it importable whether the app is started from
the repo root (`uvicorn backend.app.main:app`) or from inside `backend/`
(`cd backend && uvicorn app.main:app`), which is what README.md documents.

Preferred long-term fix is `pip install -e .` from the repo root, which puts
`generation_engine` on the path properly; this keeps the documented dev
workflow working until then.
"""
from __future__ import annotations

import sys
from pathlib import Path

try:  # already importable (installed, or repo root on sys.path)
    import generation_engine  # noqa: F401
except ImportError:  # pragma: no cover - environment-dependent
    _REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
