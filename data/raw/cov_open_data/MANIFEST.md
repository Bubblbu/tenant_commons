# raw/cov_open_data — Vancouver Open Data

- **Source:** https://opendata.vancouver.ca (Explore API v2.1 exports)
- **Method:** scripted, `uv run python scripts/fetch_cov_open_data.py` (`--only <id>` for one dataset)
- **License:** Open Government Licence – Vancouver (confirm per dataset before publishing derived data)
- **Refresh:** ad hoc. `property-tax-report` is filtered to one `report_year` (`--tax-report-year`).

| File | Fetched | Size |
|---|---|---|
| block-numbers.csv | 2026-09-18 | 800K |
| block-outlines.csv | 2026-09-18 | 11M |
| local-area-boundary.csv | 2026-09-18 | 56K |
| property-addresses.csv | 2026-09-18 | 18M |
| business-licences.geojson | 2026-09-18 | 136M |
| local-area-boundary.geojson | 2026-09-18 | 52K |
| non-market-housing.geojson | 2026-09-18 | 528K |
| property-addresses.geojson | 2026-09-18 | 33M |
| property-tax-report.geojson | 2026-09-18 | 202M |
| rental-standards-current-issues.geojson | 2026-09-18 | 192K |
