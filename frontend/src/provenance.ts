/**
 * Provenance text and the "i" icon, shared by the popup and the tables. Public
 * provenance is source types and counts only — never claim notes (spec
 * 2026-09-23-ownership-layers-design.md, CLAUDE.md sensitivity model).
 */
import { escapeHtml, isMissing } from './html';
import type { BuildingRecord } from './types';

const str = (v: unknown): string => (isMissing(v) ? '' : String(v).trim());
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

const REGISTRY = 'BC Land Owner Transparency Registry';

/** What each ownership layer means, for the table-header icons. */
export const EXPLAINERS = {
  network:
    'Buildings grouped under one real owner. Legally separate companies and people are linked by ' +
    'confirmed ownership claims (provincial registry filings, VTU research). Where there are no ' +
    'claims, buildings are grouped by business-licence name.',
  owner:
    "The owner on title for the building's parcels, from the BC Land Owner Transparency Registry. " +
    "Where there is no registry record, it's the business-licence holder.",
} as const;

export function registryProvenance(pids: string[], retrieved: string): string {
  const shown = pids.slice(0, 3).join(', ');
  const more = pids.length > 3 ? ` (+${pids.length - 3} more)` : '';
  const pidText = pids.length ? `: ${pids.length === 1 ? 'PID' : 'PIDs'} ${shown}${more}` : '';
  const when = retrieved ? `, record retrieved ${retrieved}` : '';
  return `${REGISTRY}${pidText}${when}`;
}

export function licenceProvenance(year: number | null | undefined): string {
  return year ? `City of Vancouver business licence, ${year}` : 'City of Vancouver business licence';
}

export function networkProvenance(r: BuildingRecord): string {
  if (str(r.network_source) !== 'claims') return 'Grouped by business licence name';
  const ev = (r.network_evidence ?? {}) as Record<string, unknown>;
  const registry = num(ev.registry) ?? 0;
  const research = num(ev.vtu_research) ?? 0;
  const parts = [
    registry ? plural(registry, 'provincial registry filing', 'provincial registry filings') : '',
    research ? plural(research, 'VTU research claim', 'VTU research claims') : '',
  ].filter(Boolean);
  const grouped = parts.length ? `Grouped from ${parts.join(' and ')}.` : 'Grouped from ownership claims.';
  const name = str(r.network_name_source) === 'claim'
    ? 'Name: set by claim.'
    : 'Name: default (entity with the most properties).';
  return `${grouped} ${name}`;
}

/** Source of an Owners-table row, from its buildings' owner_source values ('' if none is known). */
export function ownerRowProvenance(sources: unknown[], year: number | null | undefined): string {
  const registry = sources.filter((s) => s === 'registry').length;
  const licence = sources.filter((s) => s === 'licence').length;
  if (registry && licence) {
    return `${REGISTRY} (${plural(registry, 'building', 'buildings')}); ` +
      `${licenceProvenance(year)} (${plural(licence, 'building', 'buildings')})`;
  }
  if (registry) return REGISTRY;
  if (licence) return licenceProvenance(year);
  return '';
}

/**
 * Where a header tooltip goes: start at the icon, but kept (with `pad`) inside
 * the visible area clipLeft..clipRight, narrowed if that area is small.
 * `left` is relative to the header cell, which is the tooltip's containing block.
 */
export function tipPlacement(
  iconLeft: number, cellLeft: number, clipLeft: number, clipRight: number, maxWidth = 240, pad = 12,
): { left: number; width: number } {
  const width = Math.max(0, Math.min(maxWidth, clipRight - clipLeft - 2 * pad));
  const x = Math.min(Math.max(iconLeft, clipLeft + pad), clipRight - pad - width);
  return { left: x - cellLeft, width };
}

/**
 * A clicked icon keeps focus, and so its tooltip, after the mouse moves on —
 * leaving it overlapping the next one hovered. Blur it when a mouse leaves it;
 * touch taps are left alone (on phones, focus is how the tooltip shows).
 */
export function initTipDismiss(doc: Document = document): void {
  doc.addEventListener('pointerout', (event) => {
    const target = event.target as HTMLElement | null;
    if ((event as PointerEvent).pointerType === 'mouse' && target?.classList?.contains('prov')) target.blur();
  });
}

/** Small "i" marker; its text shows on hover or on focus (a tap on touch screens). */
export function provenanceIcon(text: string, label = 'Source'): string {
  const t = escapeHtml(text);
  return `<span class="prov" tabindex="0" role="note" aria-label="${escapeHtml(label)}: ${t}" data-tip="${t}">i</span>`;
}
