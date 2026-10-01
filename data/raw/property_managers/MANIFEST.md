# raw/property_managers — property-manager listing snapshots

- **Layout:** `<manager-slug>/<YYYY-MM-DD>.json`, one file per manager per fetch date. The file date is the snapshot date.
- **Method:** manual for Tribe; `scripts/fetch_dorset_listings.py` for Dorset, `scripts/fetch_wall_listings.py` for Wall, `scripts/fetch_metcap_listings.py` for MetCap. Ingested by `tc_core/ingest/manager_listings.py` into `raw_manager_listings` (persistent: first/last seen per listing).
- **Stored in the database:** listing id, name, address, URL, status and unit count only, and only for listings in Vancouver (raw files keep the whole portfolio). The files also carry staff contact details; those never leave the raw file.
- **Never commit fetch URLs:** some feeds need an access token in the URL. Keep it out of files and git.

## Sources

| Slug | Manager | Feed | Notes |
|---|---|---|---|
| `tribe` | Tribe Rentals (licences as "Tribe Rental Management") | theliftsystem.com `/v2/search`, client 118, city 3201 (Vancouver), limit 50 | Search endpoint: may omit buildings with no vacancies. First snapshot 2026-09-24: 25 properties. |
| `dorset` | Dorset Realty Group (licences as "Dorset Realty Group Canada Ltd") | Scraped HTML cards from dorsetrealty.com/properties/residential/ (public, no token) | Lists every building, vacant or fully rented, with a status badge (stored as `status`). First snapshot 2026-09-30: 50 properties, 39 in Vancouver, 7 with vacancies. |
| `wall` | Wall Financial Corporation (owner-operator, not a third-party manager: don't add to `property_managers.toml`) | Webflow cards on wallfinancialcorporation.com/rental (city, status, units available) plus each property page's schema.org block (street address, coordinates, units). Public, no token | First snapshot 2026-09-30: 18 properties (incl. 2 in development), 10 listed in Vancouver. The site lists St. George's (1415 St Georges Ave, North Vancouver) under Vancouver. |
| `metcap` | MetCap Living (manages for owners; in `property_managers.toml`; holds no Vancouver rental licence) | Server-rendered cards on metcap.com/province-search-results?lang=en&province=117&city=Vancouver (address, name, coordinates). Public, no token, no staff contacts on cards | First snapshot 2026-09-30: 23 Vancouver properties, all named. |
