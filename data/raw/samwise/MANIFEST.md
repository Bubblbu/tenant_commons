# raw/samwise — BC Land Owner Transparency Registry export (PRIVATE)

- **File:** `samwise-export.csv`, produced by the separate `samwise` tool and dropped in by hand.
- **Method:** manual. Imported into claims with `scripts/import_lotr_claims.py`.
- **Do not share:** it holds ownership records from the registry.
- **Search log:** `searches/*.csv` (`pid,searched_on,result,note`; result `no_filing` or `filed`). Records searches, including those with no filing, which the export above can't hold. `manual.csv` is hand-kept until Samwise can export searches itself. Imported into `raw_lotr_searches` by the same script. Internal only.
