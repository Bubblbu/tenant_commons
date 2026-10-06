# Address matching

How a source address ("1266 W 12TH AVE Appolloni Court", "#800 - 1047 Barclay St")
becomes an `addr_key` that joins to a building. Code: [`src/tc_core/normalize.py`](../src/tc_core/normalize.py).
Every rule below has test cases built from real source rows in
[`tests/test_normalize.py`](../tests/test_normalize.py), so run
`uv run pytest tests/test_normalize.py -v` to see each one pass.

There are two layers, and the split between them is deliberate:

| Layer | Function | Runs on | May it guess? |
|---|---|---|---|
| Canonical spelling (C1–C8) | `addr_key_from_freeform()` / `normalize_street()` | **every** key on both sides of every join, including the City's address register | **No.** It only makes two spellings of the same address agree. |
| Candidates + matching (V1–V4, M1–M4) | `address_key_variants()`, `AddressMatcher` | source addresses, checked against a fixed set of known keys | Yes, but only by trying candidates against real known keys. It returns nothing rather than pick between two. |

A canonical rule that guessed wrong would quietly re-key the register itself, and
everything joined to it. A matcher rule that guesses wrong can only pick a key that
exists, and it refuses whenever more than one would fit.

## Canonical spelling rules (C1–C8)

| Rule | What it does | Example (input → key) |
|---|---|---|
| C1 ordinal | Adds st/nd/rd/th to a bare number before Ave/St (11th–13th get "th") | `1771 E 18 AVENUE` → `1771 e 18th ave`; `2535 W 8 Av` → `2535 w 8th ave` |
| C2 glued direction | Splits a direction stuck to the number | `131 W49th Avenue` → `131 w 49th ave`; `2005 E40 Ave` → `2005 e 40th ave` |
| C3 trailing direction | Moves a trailing E/W/N/S to the front, **unless the street already starts with a direction** | `962 16TH AVE E` → `962 e 16th ave`; but `2777 E KENT AVE N` stays `2777 e kent ave n` |
| C4 compass words | A trailing North/South/East/West becomes N/S/E/W | `2777 E KENT AV NORTH` → `2777 e kent ave n`; `2610 GRANDVIEW HIGHWAY S` → `2610 s grandview hwy` |
| C5 compound directions | Southwest/Southeast/Northwest/Northeast → SW/SE/NW/NE | `575 Southwest Marine Drive` → `575 sw marine dr` |
| C6 street types | Adds Crescent/Cr → `cres` and Crt → `ct` to the existing table (Street, Avenue, Av, Road, Drive, Boulevard, Place, Court, Highway) | `3381 Marquette Cr` → `3381 marquette cres` |
| C7 doubled type | Drops a second street type at the end (an FOI 2024 extract artifact) | `309 E CORDOVA ST St` → `309 e cordova st` |
| C8 dashes | Reads an en dash, em dash, or garbled en dash (`â€“`) as a hyphen | `3120â€“3184 Knight St` → `3120-3184 knight st` |

Earlier rules still apply: lowercase, periods removed, repeated spaces collapsed, and
the FOI list's trailing `*` footnote stripped.

**The missing "th" problem** is mostly a membership problem. Across the current data,
bare numbers ("E 18 Ave") appear in 217 NationBuilder addresses and only 5 City or
listing rows. Glued numbers ("W49th") appear in 73 membership rows and 3 others.
C1 and C2 fix both.

## Candidates (`address_key_variants`, V1–V4)

These produce an ordered list of candidate keys, most literal first.

| Rule | Example → candidates |
|---|---|
| V1 civic range → A, then B | `429 - 433 W Pender St` → `429 w pender st`, `433 w pender st` |
| V1 shortened end expanded | `3335-45 Sophia St` → `3335 sophia st`, `3345 sophia st` |
| V1 `&` / `and` lists | `7430 & 7460 Heather St` → `7430 heather st`, `7460 heather st` |
| V2 unit prefix → B only | `303-1210 Jervis St` → `1210 jervis st` (never `303 jervis st`) |
| V3 several addresses → the first | `3306 E 5th Ave / 3350 E 5th Ave` → `3306 e 5th ave` |
| V4 spelled-out leading direction | `1865 East 10th Avenue` → `1865 e 10th ave` |

### Range or unit? (V1 vs V2)

`A-B Street` is read as a **range** only when all three hold:

- B > A (after expanding a shortened end like "3335-45").
- Same parity: both odd or both even, i.e. the same side of the street.
- B − A ≤ 200.

An `&` or `and` between the numbers always means two civic numbers. **Everything else
is a unit number in front of civic number B**: a `#`, letters (`PH1-1500`), B < A, an
odd/even mix (`1205-1210 Jervis`), or a wider gap (`100-2950 Heather`).

A unit reading never tries A. Otherwise "303-1210 Jervis St" could land on 303 Jervis,
which is a different building. That mistake is the expensive one, so ambiguous cases
lean towards "unit".

**How confident is this?** There's no purely textual way to be certain. A tenant in
unit 1206 at 1210 Jervis would write "1206-1210 Jervis", which looks exactly like a
range. So the shape is checked against the City's address register (does A exist on
that street? does B?). Measured on 2026-10-06 across every source's "A-B" addresses:

| Register says | Read as range | Read as unit |
|---|---|---|
| A exists (range, or a unit whose number is also a civic number) | 54 + 85 (both exist) | 1 + 1 |
| Only B exists (unit, or a range filed under B) | 13 | 4 |
| Neither / street not found | 91 | 2 |

- All 4 real unit prefixes in the data are read as units. Each has a `#` or a gap of
  over 200.
- 2 real ranges are read as units: `8427-8482 Cambie St` (odd/even mix) and
  `2108-2408 Cassiar St` (gap of 300). Both still match through B or M3/M4, or stay
  unmatched. They can't land on the wrong building.
- Unit prefixes are rare in the sources: 4 co-op rows. NationBuilder keeps the unit
  in a separate field, so membership addresses have none.

## Matching (`AddressMatcher`, M1–M4)

`AddressMatcher(known_keys, aliases=None).match(address)` returns a known key or
`None`. It tries tiers in order, and the first hit wins:

| Tier | What it does | Example |
|---|---|---|
| M1 exact | Any candidate is a known key, or an alias of one (a building's secondary address) | `1010 Beach Avenue` → `1000 beach ave` via alias |
| M2 building name dropped | Cuts everything after the first street type that follows a street name, or after Broadway/Kingsway. A stray type after Broadway/Kingsway is cut too: `1265 Kingsway Ave` → `1265 kingsway` | `1266 W 12TH AVE Appolloni Court` → `1266 w 12th ave`; `1095 BUTE ST St James Court` → `1095 bute st`; `1209 E BROADWAY Plaza` → `1209 e broadway` |
| M3 street type ignored | Matches without the final street type, **only if exactly one known key fits** | `2215 E HASTINGS` → `2215 e hastings st`; `404 Hawks St.` → `404 hawks ave` |
| M4 inside a range | When neither end of a range is known, takes the one known civic number between them on the same side | `1102 - 1138 E Georgia St` → `1120 e georgia st` |

### Cases it refuses (it returns `None`)

- `200 Main` when both `200 main st` and `200 main ave` exist (M3 is ambiguous).
- `100 Main Mall`: "Mall" isn't a cut point, so it never shortens to `100 main`. This
  protects UBC addresses.
- `1415 St Georges Ave`: a leading "St" (Saint) is never a cut point.
- `303-1210 Jervis St` when only `303 jervis st` is known (see V2).

## Where it's used

| Call site | Known keys | Aliases |
|---|---|---|
| `prepare/buildings.py`: FOI inventory, non-market list, rental licences, rental-standards issues | property addresses (`properties.csv`) | — |
| `ingest/overlays.py`: co-ops, SRO/SRA, rezoning | buildings | secondary addresses |
| `ingest/building_names.py`, `ingest/listing_buildings.py` | buildings (and, for placing a listing, the City's address points) | secondary addresses |
| `ingest/membership.py` | buildings | secondary addresses: a member at "488 W 41st Ave" belongs to the building at 458 W 41st Ave on the same parcel |

Everything else (`metrics/portfolios.py`, `prepare/properties.py`, `merge.py`,
`scripts/export_pid_address_map.py`) still uses the plain `addr_key_from_freeform()`
and gets the canonical rules C1–C8 only.

## Effect (rebuild of 2026-10-06)

| | Before | After |
|---|---|---|
| Buildings | 5,415 | 5,469 (5 of the new ones come from listings added the same day) |
| FOI inventory / non-market buildings | 4,638 / 510 | 4,676 / 543 |
| Licence-only buildings | 253 | 231: licences that duplicated an inventory building now land on it |
| Members linked to a building | 1,790 | 2,384: about 300 from C1/C2 and the matcher, about 290 from secondary-address aliases |
| Buildings flagged co-op / SRO / rezoning | 93 / 68 / 43 | 98 / 70 / 91 |

Unmatched source rows by source: FOI 332 → 141, non-market 59 → 24, licences 44 → 11,
co-ops 72 → 31, SRO 108 → 104, rezoning 333 → 284, listings 15 → 14.

## Not handled (what's left)

- **Civic number not in the register** (~140 FOI rows, e.g. `1901 NELSON ST`). The
  address parses fine, but the City's address list has no such point. Fixing these
  needs a different kind of match, such as nearest civic number on the street or
  coordinates, not better parsing.
- **Outside the City**: UBC/UEL listings (`Wesbrook Mall`, `University Blvd`) and most
  unmatched membership addresses.
- **Typos** (`Namaimo`, `Montclam`, `Artbutus`). A fuzzy match restricted to the same
  civic number would catch these. Not built, because a wrong guess attaches data to
  the wrong building.
- **Truncated or garbled source text** (`3120–3184 Knight Stre`, `1588 E HASTINGS Bohème Living`).
- **SRO, co-op and rezoning records with no building in the pipeline.** These are
  genuine non-matches; they go to `overlay_housing` or the rezoning unmatched list.
