# raw/cov_foi — City of Vancouver FOI releases

- **Method:** manual. The City releases a PDF; the table in it is extracted to CSV by hand.
- **Files:**
  - `FOI_2023-186-release_rental_market.pdf` (original, 2023-04-25) and `all_rentals.2023-186.csv` (extracted from it with `tabula`, pages 3–56; the extraction is not reproduced by this repo).
  - `2024-698-release.pdf` (original) and `2024-698_extracted_data.csv` (extracted by hand).
  - `sra_housing_combined.csv`, `rezoning_applications.csv`: **origin unverified** (see docs/DATA_SOURCES.md).
- **Used by:** `scripts/prepare_data.py --stage foi` (the two FOI extracts); `tc_core` ingest (`raw_sro`, `raw_rezoning`).
- **Do not hand-edit** the extracted CSVs; re-extract from the PDF instead.
