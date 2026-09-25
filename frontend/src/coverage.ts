/**
 * Filters > Map Summary > Coverage: how much of the map has a landlord on
 * record, and where that ownership comes from. Counts the same rows as the
 * summary's Total (source "building"; SRO/co-op overlay rows are extra
 * records for buildings already counted), restricted to the buildings that
 * pass the current filters.
 */
import { escapeHtml, isMissing } from './html';
import type { BuildingRecord } from './types';

export interface Coverage {
  buildings: number;
  units: number;
  withOwner: number;
  withOwnerUnits: number;
  /** Buildings with an owner, by where the owner came from (owner_source). */
  bySource: Record<string, number>;
  /** Buildings whose landlord group was assembled from ownership claims. */
  grouped: number;
}

/** Owner sources in bar order, each with its segment class. */
const SOURCE_LABELS: [string, string][] = [
  ['registry', 'Land title registry'],
  ['licence', 'Business licence'],
  ['sro_list', 'SRO inventory'],
];

export const hasOwner = (r: BuildingRecord): boolean => !isMissing(r.owner_key) && r.owner_key !== 'unknown';

export function computeCoverage(records: BuildingRecord[]): Coverage {
  const c: Coverage = { buildings: 0, units: 0, withOwner: 0, withOwnerUnits: 0, bySource: {}, grouped: 0 };
  for (const r of records) {
    if (r.source !== 'building') continue;
    const units = typeof r.units === 'number' && Number.isFinite(r.units) ? r.units : 0;
    c.buildings += 1;
    c.units += units;
    if (!hasOwner(r)) continue;
    c.withOwner += 1;
    c.withOwnerUnits += units;
    const src = isMissing(r.owner_source) ? 'other' : String(r.owner_source);
    c.bySource[src] = (c.bySource[src] ?? 0) + 1;
    if (r.network_source === 'claims') c.grouped += 1;
  }
  return c;
}

const pct = (n: number, d: number): string => (d > 0 ? `${Math.round((n / d) * 100)}%` : '–');
const fmt = (n: number): string => Math.round(n).toLocaleString('en-CA');
const width = (n: number, d: number): string => `${((n / d) * 100).toFixed(2)}%`;

export function coverageHtml(c: Coverage): string {
  if (c.buildings === 0) {
    return '<details class="coverage"><summary><span class="coverage-title">Landlord coverage</span>' +
      '<span class="coverage-headline">no buildings match</span></summary></details>';
  }
  const missing = c.buildings - c.withOwner;
  const missingUnits = c.units - c.withOwnerUnits;
  const known = new Set(SOURCE_LABELS.map(([k]) => k));
  const parts = [
    ...SOURCE_LABELS,
    ...Object.keys(c.bySource).filter((k) => !known.has(k)).map((k): [string, string] => [k, k === 'other' ? 'Other' : k]),
  ]
    .filter(([k]) => c.bySource[k])
    .map(([k, label]) => ({ cls: known.has(k) ? `seg-${k}` : 'seg-other', label, n: c.bySource[k] }));
  parts.push({ cls: 'seg-missing', label: 'Landlord missing', n: missing });

  const bar = parts
    .filter((p) => p.n > 0)
    .map((p) => `<span class="coverage-seg ${p.cls}" style="width:${width(p.n, c.buildings)}" title="${escapeHtml(p.label)}: ${fmt(p.n)}"></span>`)
    .join('');
  const items = parts
    .map(
      (p) =>
        `<li${p.cls === 'seg-missing' ? ' class="coverage-missing"' : ''}>` +
        `<span class="coverage-swatch ${p.cls}"></span><span class="coverage-label">${escapeHtml(p.label)}</span>` +
        `<span class="coverage-n">${fmt(p.n)}</span><span class="coverage-pct">${pct(p.n, c.buildings)}</span></li>`,
    )
    .join('');
  return (
    '<details class="coverage">' +
    '<summary><span class="coverage-title">Landlord coverage</span>' +
    `<span class="coverage-headline">${pct(c.withOwner, c.buildings)} of ${fmt(c.buildings)} bldgs</span></summary>` +
    '<div class="coverage-body">' +
    `<div class="coverage-bar" role="img" aria-label="${fmt(c.withOwner)} of ${fmt(c.buildings)} buildings have a landlord on record">${bar}</div>` +
    `<ul class="coverage-list">${items}</ul>` +
    '<dl class="coverage-facts">' +
    `<dt>Units with a landlord</dt><dd>${pct(c.withOwnerUnits, c.units)} <span class="coverage-pct">· ${fmt(missingUnits)} missing</span></dd>` +
    `<dt>In a landlord network</dt><dd>${fmt(c.grouped)} <span class="coverage-pct">· ${pct(c.grouped, c.buildings)}</span></dd>` +
    '</dl></div></details>'
  );
}

/** Re-renders in place, keeping the card open if the user had opened it. */
export function renderCoverage(records: BuildingRecord[], doc: Document = document): void {
  const el = doc.getElementById('map-coverage');
  if (!el) return;
  const wasOpen = el.querySelector('details')?.open ?? false;
  el.innerHTML = coverageHtml(computeCoverage(records));
  const details = el.querySelector('details');
  if (details && wasOpen) details.open = true;
}
