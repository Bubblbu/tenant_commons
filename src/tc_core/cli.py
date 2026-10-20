"""`uv run dev` / `uv run deploy`: the frontend's npm scripts, run from the repo root.

Both run in frontend/ and pass any extra arguments through to npm, e.g.
`uv run dev --host`. Neither rebuilds the data — run
`uv run python scripts/rebuild_data.py` first when it changed.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _npm(script: str) -> None:
    args = sys.argv[1:]
    cmd = ["npm", "run", script, *(["--", *args] if args else [])]
    try:
        sys.exit(subprocess.call(cmd, cwd=FRONTEND))
    except KeyboardInterrupt:
        sys.exit(130)


def dev() -> None:
    """Vite dev server with hot reload."""
    _npm("dev")


def deploy() -> None:
    """vite build, then force-push dist/ as the `production` branch (GitHub Pages)."""
    _npm("deploy")
