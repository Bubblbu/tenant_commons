# raw/property_managers — property-manager listing snapshots

- **Layout:** `<manager-slug>/<YYYY-MM-DD>.json`, one file per manager per fetch date. The file date is the snapshot date.
- **Method:** manual for now (later: per-manager scrapers). Ingested by `tc_core/ingest/manager_listings.py` into `raw_manager_listings` (persistent: first/last seen per listing).
- **Stored in the database:** listing id, name, address, URL only. The files also carry staff contact details; those never leave the raw file.
- **Never commit fetch URLs:** some feeds need an access token in the URL. Keep it out of files and git.

## Sources

| Slug | Manager | Feed | Notes |
|---|---|---|---|
| `tribe` | Tribe Rentals (licences as "Tribe Rental Management") | theliftsystem.com `/v2/search`, client 118, city 3201 (Vancouver), limit 50 | Search endpoint: may omit buildings with no vacancies. First snapshot 2026-09-24: 25 properties. |
