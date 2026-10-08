#!/usr/bin/env python3
"""Write frontend/src/contract.schema.json from tc_core.contract.

Run after changing tc_core/contract.py, then `npm run gen:types` in frontend/.
tests/test_contract.py fails while the committed file is stale.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from tc_core.contract import json_schema  # noqa: E402

OUT = REPO_ROOT / "frontend" / "src" / "contract.schema.json"

if __name__ == "__main__":
    OUT.write_text(json.dumps(json_schema(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO_ROOT)}")
