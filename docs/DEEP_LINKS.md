# Deep links into the map

A public interface, like the export contract: other sites and apps (the tenantcommons.ca address picker, Samwise, the RTB project, a QR code) open the map on one building with a link. Change it only in step with them.

```
https://map.tenantcommons.ca/#pid=029334772&lat=49.261643&lon=-123.066910&address=1865%20E%2010TH%20AV
```

| param | value |
|---|---|
| `pid` | the parcel's PID, 9 digits; dashes are ignored. The City geocoder's `siteId`. |
| `lat`, `lon` | WGS84 decimal degrees. Both or neither. |
| `address` | the address as the City spells it (`1865 E 10TH AV`), URL-encoded |

Every parameter is optional, and invalid values (a non-PID `siteId` such as a strata plan `LMS10`, coordinates outside Vancouver) are ignored. Send everything you have.

**Hash, not query string.** The `#` part never reaches a server, so a tenant's home address stays out of logs and referrer headers. The map clears the hash from the address bar once it has read it.

## What the map does

Implemented in `frontend/src/deep-link.ts`.

1. **Address match:** a building whose address, in one spelling (case, punctuation, `AV`/`Avenue` → `ave`, `East` → `e`), equals `address` opens its popup.
2. **PID match:** otherwise, the building on parcel `pid` opens its popup. Only when exactly one building sits on that parcel; some parcels hold several.
3. **Otherwise:** a missing-building popup at `lat`/`lon` (or the current view's centre without them) says the building isn't on the map yet, gives the contact email (`CONTACT_EMAIL`, subject naming the building), and links to an example building (`EXAMPLE_BUILDING_PID` in `frontend/src/config.ts`) when one is set.

With `lat`/`lon` the map opens there at street level straight away; matching waits for the building records, which load after the basemap. Without them it opens on the whole city until the match is made.

There's no matching by distance: a wrong match would show a tenant someone else's landlord. The map also follows a link that changes the hash while it's open.

## The City geocoder

The address picker gets these values from the City of Vancouver's geocoder (`maps.vancouver.ca/server/rest/services/Locator/locator_address/GeocodeServer`, `findAddressCandidates` with `outSR=4326&outFields=*`); `siteId` is inside the JSON string `attributes.User_fld`. For strata parcels `siteId` is the strata plan (`LMS10`, `EPS3195`), not a PID, so those buildings match by address.
