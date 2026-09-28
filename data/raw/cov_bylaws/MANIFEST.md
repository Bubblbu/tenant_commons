# raw/cov_bylaws — City of Vancouver by-laws

- **File:** `4450c.PDF`, Licence By-law No. 4450, consolidated to 2026-07-14 (amended to By-law No. 14760).
- **Method:** manual browser download from vancouver.ca (scripted requests are blocked), 2026-09-25.
- **What's used:** Schedule A, Long Term Rental (PDF p. 78–79): $98 per dwelling unit, $71 per housekeeping
  unit, $47 per sleeping unit a year; $277 flat for non-profit housing; pool $1,108 (p. 84).
  Schedule B application fee $77; s. 6(3) prorates a new licence's annual fee by months remaining / 12.
- **Used by:** `tc_core/prepare/licence_fees.py::decode_fee` (constants copied by hand; re-check them when the
  licence data moves to a new folderyear or the by-law is re-consolidated).
