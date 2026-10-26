/**
 * Deep links into the map: `#pid=…&lat=…&lon=…&address=…`, as the
 * tenantcommons.ca address picker sends them from the City geocoder (format:
 * docs/DEEP_LINKS.md). A building whose address or PID matches opens its
 * popup; anything else opens the missing-building popup at lat/lon. No
 * guessing by distance: a wrong match would show a tenant someone else's
 * landlord.
 *
 * The hash keeps a tenant's address out of server logs, and is cleared once
 * read so it isn't shared along with the map.
 */
import L from 'leaflet';
import { formatAddress } from './address';
import { CONTACT_EMAIL, EXAMPLE_BUILDING_PID } from './config';
import type { Building } from './contract.gen';
import { escapeHtml } from './html';
import { closeDrawers, focusMarker, LOCATE_ZOOM } from './wiring/locate';

export interface DeepLink {
  pid: string | null;
  lat: number | null;
  lon: number | null;
  address: string | null;
}

const PID_RE = /^\d{9}$/;
// Generous Vancouver bounds: coordinates outside them aren't a City geocode.
const LAT_RANGE: [number, number] = [49.0, 49.5];
const LON_RANGE: [number, number] = [-123.5, -122.8];
const MAX_ADDRESS_LENGTH = 200;

function coord(raw: string | null, [min, max]: [number, number]): number | null {
  if (raw === null || raw.trim() === '') return null;
  const n = Number(raw);
  return Number.isFinite(n) && n >= min && n <= max ? n : null;
}

/** The link in a location hash, or null when the hash carries none. Invalid values read as absent. */
export function parseDeepLink(hash: string): DeepLink | null {
  const params = new URLSearchParams(hash.replace(/^#/, ''));
  const pid = (params.get('pid') ?? '').replace(/-/g, '').trim();
  const address = (params.get('address') ?? '').trim().slice(0, MAX_ADDRESS_LENGTH);
  const link: DeepLink = {
    pid: PID_RE.test(pid) ? pid : null,
    lat: coord(params.get('lat'), LAT_RANGE),
    lon: coord(params.get('lon'), LON_RANGE),
    address: address || null,
  };
  if (link.lat === null || link.lon === null) link.lat = link.lon = null;
  return link.pid || link.address || link.lat !== null ? link : null;
}

/**
 * Where the map opens for a link with coordinates: there, at street level.
 * Matching a building waits for the building records; opening on the city
 * first would load tiles only to jump away from them. null keeps the default.
 */
export function deepLinkView(hash: string): { center: [number, number]; zoom: number } | null {
  const link = parseDeepLink(hash);
  return link && link.lat !== null && link.lon !== null ? { center: [link.lat, link.lon], zoom: LOCATE_ZOOM } : null;
}

const WORDS: Record<string, string> = {
  avenue: 'ave', av: 'ave', street: 'st', road: 'rd', drive: 'dr', boulevard: 'blvd', place: 'pl',
  court: 'ct', crt: 'ct', crescent: 'cres', cr: 'cres', highway: 'hwy',
  east: 'e', west: 'w', north: 'n', south: 's',
};

/**
 * One spelling for the City's addresses ("1865 E 10TH AV") and the map's
 * ("1865 e 10th ave", or an overlay's "341 E Hastings St."). Not the
 * pipeline's full normalizer (normalize.py): the City's spelling is already
 * regular, so this only bridges the two conventions.
 */
export function addressKey(address: string): string {
  return address.toLowerCase().replace(/[.,]/g, ' ').split(/\s+/).filter(Boolean)
    .map((w) => WORDS[w] ?? w).join(' ');
}

export interface BuildingLookup {
  byAddress: Map<string, string>;
  /** Only PIDs a single building sits on: several buildings can share one parcel. */
  byPid: Map<string, string>;
}

export function buildLookup(records: Record<string, Building>): BuildingLookup {
  const byAddress = new Map<string, string>();
  const pidOwners = new Map<string, Set<string>>();
  for (const [bid, b] of Object.entries(records)) {
    byAddress.set(addressKey(b.address), bid);
    for (const pid of b.pids) {
      const key = pid.replace(/-/g, '');
      pidOwners.set(key, (pidOwners.get(key) ?? new Set()).add(bid));
    }
  }
  const byPid = new Map<string, string>();
  pidOwners.forEach((bids, pid) => { if (bids.size === 1) byPid.set(pid, [...bids][0]); });
  return { byAddress, byPid };
}

/** The b_id of the linked building: address first (exact), then a PID only one building has. */
export function findBuilding(link: DeepLink, lookup: BuildingLookup): string | null {
  const byAddress = link.address ? lookup.byAddress.get(addressKey(link.address)) : undefined;
  return byAddress ?? (link.pid ? lookup.byPid.get(link.pid) ?? null : null);
}

export function renderMissingPopup(link: DeepLink, examplePid: string | null = EXAMPLE_BUILDING_PID): string {
  const shown = link.address ? formatAddress(addressKey(link.address)) : '';
  const address = shown ? `<div class="popup-address">${escapeHtml(shown)}</div>` : '';
  // The subject names the building, so the email arrives with it.
  const subject = encodeURIComponent(shown ? `Missing building: ${shown}` : 'Missing building');
  const example = examplePid
    ? `<p>See what the map can show: <a href="#pid=${encodeURIComponent(examplePid)}">an example building</a>.</p>` : '';
  return `<div class="tc-popup tc-missing">${address}` +
    '<p><strong>We don\'t have this building on the map yet.</strong></p>' +
    '<p>The map currently covers mainly rental apartment buildings from the City\'s records. ' +
    'Smaller rentals, like houses, suites, duplexes and rented condos, and their smaller landlords ' +
    'are often missing.</p>' +
    '<p>We\'re working on a way for you to tell us about a building. Until then, email us:</p>' +
    `<p class="tc-missing-contact"><a href="mailto:${CONTACT_EMAIL}?subject=${subject}">${CONTACT_EMAIL}</a></p>` +
    `${example}</div>`;
}

export interface DeepLinkContext {
  map: L.Map;
  records: Record<string, Building>;
  markersById: Record<string, L.CircleMarker>;
  win?: Window;
}

/** Follows the link in the URL now, and any later one (the missing popup's example link). */
export function initDeepLinks(ctx: DeepLinkContext): void {
  const win = ctx.win ?? window;
  const lookup = buildLookup(ctx.records);
  const follow = (): void => {
    const link = parseDeepLink(win.location.hash);
    if (!link) return;
    const url = new URL(win.location.href);
    url.hash = '';
    win.history.replaceState(win.history.state, '', url.href.replace(/#$/, ''));
    const bid = findBuilding(link, lookup);
    const marker = bid === null ? undefined : ctx.markersById[bid];
    if (marker) {
      focusMarker(marker, ctx.map, win.document);
      return;
    }
    closeDrawers(win.document);
    const at = link.lat !== null && link.lon !== null ? L.latLng(link.lat, link.lon) : ctx.map.getCenter();
    if (link.lat !== null) ctx.map.setView(at, Math.max(ctx.map.getZoom(), LOCATE_ZOOM));
    L.popup({ maxWidth: 320 }).setLatLng(at).setContent(renderMissingPopup(link)).openOn(ctx.map);
  };
  follow();
  win.addEventListener('hashchange', follow);
}
