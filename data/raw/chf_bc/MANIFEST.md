# raw/chf_bc — CHF BC co-op housing list

- **Source:** the CHF BC website (a third party's own site, not the City or VTU).
- **Method:** scripted, `uv run python scripts/fetch_coops.py` (replayable from saved HTML with its `--html-file` option).
- **File:** `coops_vancouver.csv`.
- **Used by:** `tc_core` ingest (`raw_coops`) and the map's co-op overlay.
