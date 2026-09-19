# raw/vanmaps — VanMaps

- **Files:** `addresses.geojson`, exported from VanMaps 2024-03-11 (per the file date). Gives each civic address a primary/secondary flag, used to resolve secondary addresses to a building's primary address.
- **Method:** manual. The exact export steps were not recorded when the `vhd` pipeline was written. TODO: write them down the next time this is re-exported.
- **Used by:** `scripts/prepare_data.py --stage properties`.
