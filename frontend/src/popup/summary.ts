/** Summary tab — the tenant's first look (spec 2026-10-08 §6). */
import type { Building, Party } from '../contract.gen';
import { escapeHtml } from '../html';
import { evidenceParts, provenanceIcon } from '../provenance';
import { classificationHeadline } from './classification';
import { LABELS } from './labels';
import { linked, plural, sourceText } from './format';
import type { PopupContext } from './index';

const NOT_ON_RECORD = '<span class="popup-muted">Not on record</span>';
const row = (k: string, v: string) => `<div class="popup-row"><span class="popup-k">${k}</span> <span>${v}</span></div>`;
const tier = (label: string, weak = false) => ` <span class="popup-tier${weak ? ' weak' : ''}">${escapeHtml(label)}</span>`;
const icon = (p: Party, ctx: PopupContext) => provenanceIcon(p.sources.map((s) => sourceText(s, ctx.licenceYear)).join('; '));
const first = (b: Building, role: Party['role']) => b.parties.find((p) => p.role === role) ?? null;

function badges(b: Building): string {
  const out: string[] = [];
  if (b.sro) {
    out.push('SRO');
    if (b.sro.occupancy) out.push(LABELS.occupancy[b.sro.occupancy]);
  }
  if (b.coop) out.push('Co-op');
  // The City counts co-ops as non-market; a co-op's badge says Co-op only.
  if (b.housing.non_market && !b.coop) out.push('Non-market');
  if (b.housing.non_market?.seniors) out.push('Seniors');
  return out.length ? `<div class="popup-badges">${out.map((t) => `<span class="popup-badge">${escapeHtml(t)}</span>`).join('')}</div>` : '';
}

function ownedBy(b: Building, ctx: PopupContext): string {
  const net = b.network_id ? ctx.networks[b.network_id] : undefined;
  if (net && net.tier === 'confirmed') {
    const ev = `Grouped from ${evidenceParts(net.evidence).join(', ')}.`;
    return `<strong>${escapeHtml(net.name)}</strong>${tier('confirmed')}${provenanceIcon(ev)}`;
  }
  const owner = first(b, 'owner');
  if (!owner) return NOT_ON_RECORD;
  const licenceOnly = owner.sources.every((s) => s.type === 'licence');
  return `<strong>${escapeHtml(owner.name)}</strong>${licenceOnly ? tier('licence only', true) : ''}${icon(owner, ctx)}`;
}

function managedBy(b: Building, ctx: PopupContext): string {
  const m = first(b, 'manager');
  if (!m) return NOT_ON_RECORD;
  const url = m.sources.find((s) => s.type === 'listing' && s.url)?.url ?? null;
  return `<strong>${linked(m.name, url)}</strong>${icon(m, ctx)}`;
}

function portfolio(b: Building, ctx: PopupContext): string {
  const net = b.network_id ? ctx.networks[b.network_id] : undefined;
  if (!net) return '';
  if (net.totals.buildings <= 1) return `<div class="popup-muted">Only building we know of for this owner</div>`;
  return `<div class="popup-muted">${escapeHtml(`${net.name} holds ${plural(net.totals.buildings, 'building', 'buildings')} · ${plural(net.totals.units, 'unit', 'units')} on the map`)}</div>`;
}

function rezoningAlert(b: Building): string {
  const z = b.rezoning;
  if (!z || (z.status !== 'approved' && z.status !== 'rezoning')) return '';
  const when = z.detail ? ` (${escapeHtml(z.detail.replace(/^Approved\s+/, ''))})` : '';
  const link = z.url ? ` · ${linked('Shape Your City', z.url)}` : '';
  return `<div class="popup-alert"><strong>${escapeHtml(LABELS.rezoning[z.status])}</strong>${when} — the site may be redeveloped${link}</div>`;
}

/** The City's plain facts about the building: licence type, purpose-built list, zoning, age, size. */
function housingFacts(b: Building): string {
  const h = b.housing;
  const parts = [
    ...h.licence_types.map((t) => `${t} (2024 City licence)`),
    h.purpose_built ? "on the City's purpose-built rental list" : '',
    h.zoning ? `zoned ${h.zoning}` : '',
    b.year_built ? `built ${b.year_built}` : '',
    b.units ? plural(b.units, 'unit', 'units') : '',
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

export function renderSummary(b: Building, ctx: PopupContext): string {
  const licensee = first(b, 'licensee');
  const licensed = licensee && licensee.same_as === null
    ? row('Licensed to', `${escapeHtml(licensee.name)}${icon(licensee, ctx)}`) : '';
  const issues = b.issues
    ? `<div class="popup-issues">${linked(plural(b.issues.count, 'outstanding City issue', 'outstanding City issues'), b.issues.url)}</div>` : '';
  return badges(b) + classificationHeadline(b) + housingFacts(b) + nonMarketLine(b) + rezoningAlert(b) + row('Owned by', ownedBy(b, ctx)) + row('Managed by', managedBy(b, ctx)) +
    licensed + portfolio(b, ctx) + issues;
}
