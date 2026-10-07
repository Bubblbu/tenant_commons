# raw/samwise — BC Land Owner Transparency Registry export (PRIVATE)

- **File:** `samwise-export.csv`, produced by the separate `samwise` tool and dropped in by hand.
- **Method:** manual. Imported into claims with `scripts/import_lotr_claims.py`.
- **Do not share:** it holds ownership records from the registry.
- **Search log:** `searches/*.csv` (`pid,searched_on,result,note`; result `no_filing` or `filed`). Records searches, including those with no filing, which the export above can't hold. `manual.csv` is hand-kept; `samwise-searches-<date>.csv` are Samwise's own search exports, with two more columns (`result_count`, `searched_at`). Imported into `raw_lotr_searches` by the same script. The public map shows the date a building with no registry owner was searched without a filing; notes stay internal.
- **To search:** `todo/*.csv` (`pid,address,search_by,source,note`) lists PIDs still to run through Samwise, with why each matters. A row with no `pid` needs a lookup first (strata plan or address). Nothing imports this folder; once a search is run, log it in `searches/` as usual.
