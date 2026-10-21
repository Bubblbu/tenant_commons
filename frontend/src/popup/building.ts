/** Building tab — value and redevelopment pressure, civic records (spec 2026-10-08 §6). */
import type { Building } from '../contract.gen';
import { escapeHtml } from '../html';
import { provenanceIcon } from '../provenance';
import { LABELS } from './labels';
import { formatCurrencyCompact, linked, plural, sourceText } from './format';
import type { PopupContext } from './index';

const section = (title: string, body: string) => `<div class="popup-lbl">${title}</div>${body}`;
const row = (k: string, v: string) => `<div class="popup-row"><span class="popup-k">${k}</span> <span>${v}</span></div>`;
const LAND_SHARE_NOTE =
  'Share of the assessed value that is land. Where land is worth far more than the building on it, ' +
  'redeveloping the site pays more than keeping the building — a sign of redevelopment pressure.';

function value(b: Building, ctx: PopupContext): string {
  const v = b.value;
  if (!v) return '';
  const pct = Math.round(v.land_share * 1000) / 10;
  const median = ctx.landShareMedian === null ? ''
    : `<div class="median" style="left:${Math.round(ctx.landShareMedian * 100)}%"></div>`;
  const label = ctx.landShareMedian === null ? ''
    : `<div class="median-row"><span class="median-label" style="left:${Math.round(ctx.landShareMedian * 100)}%">city median</span></div>`;
  return section('Assessed value',
    `<div class="value-bar"><div class="fill" style="width:${pct}%"></div>${median}</div>${label}` +
    `<div class="popup-muted">Land <b>${formatCurrencyCompact(v.land)}</b> (${Math.round(v.land_share * 100)}%) · ` +
    `Building <b>${formatCurrencyCompact(v.building)}</b>${provenanceIcon(LAND_SHARE_NOTE)}</div>` +
    `<div class="popup-muted">${escapeHtml(`Land share higher than ${v.land_share_pctl}% of rental buildings on the map`)}</div>`);
}

const MONTH = /^(?:Approved\s+)?([A-Z][a-z]+)\w*\s+(\d{1,2}),\s+(\d{4})$/;
function rezoning(b: Building): string {
  const z = b.rezoning;
  if (!z) return '';
  const m = z.detail?.match(MONTH);
  const when = m ? ` · ${m[1].slice(0, 3)} ${m[2]}, ${m[3]}` : z.detail && z.detail !== 'Application in Process' ? ` · ${z.detail}` : '';
  const status = { approved: 'Approved', rezoning: 'In progress', upcoming: 'Upcoming' }[z.status];
  return section('Rezoning',
    row('Status', escapeHtml(status + when)) + row('Type', escapeHtml(LABELS.rezoningCategory(z.category))) +
    (z.url ? row('Details', linked('Shape Your City', z.url)) : ''));
}

function sro(b: Building): string {
  const s = b.sro;
  if (!s) return '';
  const sectors = [s.owner_sector && `${LABELS.sector[s.owner_sector]} owner`, s.operator_sector && `${LABELS.sector[s.operator_sector]} operator`]
    .filter(Boolean).join(' · ');
  const cap = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);
  return section('SRO',
    (s.rooms !== null ? row('Rooms', `${s.rooms} registered`) : '') +
    (s.occupancy ? row('Status', LABELS.occupancy[s.occupancy]) : '') +
    (sectors ? row('Sectors', escapeHtml(cap(sectors))) : ''));
}

function coop(b: Building): string {
  const c = b.coop;
  if (!c) return '';
  return section('Co-op',
    (c.ownership_model ? row('Model', LABELS.coopModel[c.ownership_model]) : '') +
    (c.status ? row('Waitlist', LABELS.coopStatus[c.status].replace('Waitlist ', '')) : '') +
    (c.url ? row('More', linked('CHF BC listing', c.url)) : ''));
}

/** The City's plain facts about the building: licence type, purpose-built list, zoning (age and size are in the header). */
function housingFacts(b: Building): string {
  const h = b.housing;
  const parts = [
    ...h.licence_types.map((t) => `${t} (2024 City licence)`),
    h.purpose_built ? "on the City's purpose-built rental list" : '',
    h.zoning ? `zoned ${h.zoning}` : '',
  ].filter(Boolean);
  return parts.length ? `<div class="popup-muted popup-housing">${escapeHtml(parts.join(' · '))}</div>` : '';
}

/** Who runs non-market housing and who its units are for (the City's clientele counts). A co-op
 * runs itself, so it shows only the unit mix. */
function nonMarketLine(b: Building): string {
  const nm = b.housing.non_market;
  if (!nm) return '';
  const parts = [
    b.coop ? '' : nm.operators.length ? `Non-market housing operated by ${nm.operators.join(' and ')}` : 'Non-market housing',
    nm.seniors_units ? plural(nm.seniors_units, 'seniors unit', 'seniors units') : '',
    nm.family_units ? `${plural(nm.family_units, 'family-size unit', 'family-size units')} (2+ bedrooms)` : '',
    nm.other_units ? plural(nm.other_units, 'unit for singles', 'units for singles') : '',
  ].filter(Boolean);
  return parts.length ? `<div class="popup-housing">${escapeHtml(parts.join(' · '))}</div>` : '';
}

function housing(b: Building): string {
  const body = housingFacts(b) + nonMarketLine(b);
  return body ? section('Housing', body) : '';
}

export function renderBuilding(b: Building, ctx: PopupContext): string {
  const aka = b.also_known_as.length ? `<div class="popup-muted">${escapeHtml(`Also known as ${b.also_known_as.join(', ')}`)}</div>` : '';
  const issues = b.issues
    ? section('City issues', `<div class="popup-issues">${linked(`${b.issues.count.toLocaleString('en-US')} outstanding · details`, b.issues.url)}</div>`)
    : '';
  const listed = b.listed_in.map((s) => sourceText({ type: s, as_of: null, url: null }, ctx.licenceYear)).join(' · ');
  const records = listed ? section('Records', `<div class="popup-muted">${escapeHtml(`Listed in ${listed}`)}</div>`) : '';
  return aka + housing(b) + value(b, ctx) + rezoning(b) + sro(b) + coop(b) + issues + records;
}
