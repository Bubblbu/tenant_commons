/** Building tab — value and redevelopment pressure, civic records (spec 2026-10-08 §6). */
import type { Building } from '../contract.gen';
import { escapeHtml } from '../html';
import { provenanceIcon } from '../provenance';
import { LABELS } from './labels';
import { formatCurrencyCompact, linked, sourceText } from './format';
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

export function renderBuilding(b: Building, ctx: PopupContext): string {
  const aka = b.also_known_as.length ? `<div class="popup-muted">${escapeHtml(`Also known as ${b.also_known_as.join(', ')}`)}</div>` : '';
  const issues = b.issues
    ? section('City issues', `<div class="popup-issues">${linked(`${b.issues.count.toLocaleString('en-US')} outstanding · details`, b.issues.url)}</div>`)
    : '';
  const listed = b.listed_in.map((s) => sourceText({ type: s, as_of: null, url: null }, ctx.licenceYear)).join(' · ');
  const records = listed ? section('Records', `<div class="popup-muted">${escapeHtml(`Listed in ${listed}`)}</div>`) : '';
  return aka + value(b, ctx) + rezoning(b) + sro(b) + coop(b) + issues + records;
}
