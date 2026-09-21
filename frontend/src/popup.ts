/**
 * The building popup, redesigned per spec §7: leads with ownership (the
 * project's differentiator), sections appear only when their data does,
 * every value goes through one escape helper. Membership is deliberately
 * absent — an editorial choice, NOT a privacy control: membership remains
 * in the artifacts and in marker colour (spec §12).
 */
import { escapeHtml, isMissing } from './html';
import type { BuildingRecord } from './types';

const str = (v: unknown): string => (isMissing(v) ? '' : String(v).trim());
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);

export function formatCurrencyCompact(v: number): string {
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${Math.round(v / 1e3).toLocaleString('en-US')}K`;
  return `$${Math.round(v)}`;
}

/** The URL if it is http(s), else null — never link javascript: or other schemes. */
export function safeUrl(v: unknown): string | null {
  if (typeof v !== 'string') return null;
  try {
    const u = new URL(v);
    return u.protocol === 'http:' || u.protocol === 'https:' ? u.href : null;
  } catch {
    return null;
  }
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
const div = (cls: string, html: string) => `<div${cls ? ` class="${cls}"` : ''}>${html}</div>`;

export function renderPopup(r: BuildingRecord): string {
  const head = [div('popup-address', escapeHtml(str(r.address)))];
  if (str(r.housing_name)) head.push(div('popup-name', escapeHtml(str(r.housing_name))));

  const ownership: string[] = [];
  if (str(r.owner_group)) ownership.push(div('popup-owner', escapeHtml(str(r.owner_group))));
  if (str(r.portfolio_name)) {
    const count = num(r.portfolio_building_count);
    const entities = Array.isArray(r.portfolio_entities) ? r.portfolio_entities.length : 0;
    const size = count === null ? 'Portfolio' : `Portfolio: ${plural(Math.trunc(count), 'building', 'buildings')}`;
    ownership.push(div('', escapeHtml(`${size}, ${plural(entities, 'linked entity', 'linked entities')}`)));
  }

  const facts: string[] = [];
  const units = num(r.units);
  const year = num(r.year_built);
  const sizeLine = [
    units === null ? '' : `${Math.trunc(units).toLocaleString('en-US')} units`,
    year === null ? '' : `built ${Math.trunc(year)}`,
  ].filter(Boolean).join(' · ');
  if (sizeLine) facts.push(div('', escapeHtml(sizeLine)));
  if (str(r.local_area)) facts.push(div('', escapeHtml(str(r.local_area))));
  const land = num(r.value_land);
  const bldg = num(r.value_bldg);
  const assessed = [
    land === null ? '' : `${formatCurrencyCompact(land)} land`,
    bldg === null ? '' : `${formatCurrencyCompact(bldg)} building`,
  ].filter(Boolean).join(' · ');
  if (assessed) facts.push(div('', escapeHtml(`Assessed ${assessed}`)));

  const housing: string[] = [];
  if (r.is_coop === true) {
    let line = 'Co-op';
    if (str(r.coop_status)) line += ` · ${str(r.coop_status)}`;
    if (str(r.coop_ownership_model)) line += ` (${str(r.coop_ownership_model)})`;
    let html = escapeHtml(line);
    const url = safeUrl(r.coop_url);
    if (url) html += ` · <a href="${escapeHtml(url)}" target="_blank" rel="noopener">more info</a>`;
    housing.push(div('', html));
  }
  if (r.is_sro === true) {
    const parts = ['SRO/SRA'];
    if (str(r.sro_owner)) parts.push(`Owner ${str(r.sro_owner)}`);
    if (str(r.sro_operator)) parts.push(`Operator ${str(r.sro_operator)}`);
    if (str(r.sro_occupancy_status)) parts.push(str(r.sro_occupancy_status));
    if (str(r.sro_registered_rooms)) parts.push(`${str(r.sro_registered_rooms)} rooms`);
    housing.push(div('', escapeHtml(parts.join(' · '))));
  }

  const sections = [head, ownership, facts, housing]
    .filter((s) => s.length)
    .map((s) => div('popup-section', s.join('')));
  return div('sica-popup', sections.join(''));
}
