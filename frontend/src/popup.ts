/**
 * The building popup, redesigned per spec §7: leads with ownership (the
 * project's differentiator), sections appear only when their data does,
 * every value goes through one escape helper. VTU membership data is never
 * exported to the public artifacts at all (spec §11/§12 — see export.py),
 * so there is nothing for the popup to read here even by omission.
 */
import { escapeHtml, isMissing, sameName } from './html';
import { formatAddress } from './address';
import { SRO_INVENTORY, licenceProvenance, networkProvenance, provenanceIcon, registryProvenance } from './provenance';
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
const strList = (v: unknown): string[] => (Array.isArray(v) ? v.map(str).filter(Boolean) : []);

export interface PopupContext {
  /** Business-licence data year (filter_config.licence_year). */
  licenceYear?: number | null;
}

const provenance = (text: string) => provenanceIcon(text);

function ownershipLines(r: BuildingRecord, ctx: PopupContext): string[] {
  const lines: string[] = [];
  const onRecord = !isMissing(r.owner_key) && r.owner_key !== 'unknown' && str(r.owner_name) !== '(Unknown)';
  const owner = onRecord ? str(r.owner_name) : '';
  const ownerSource = str(r.owner_source);
  const manager = str(r.managed_by);
  const managerLine = () =>
    div('', escapeHtml(`Managed by ${manager}`) + provenance(licenceProvenance(ctx.licenceYear)));
  if (!owner) {
    lines.push(div('popup-owner popup-muted', 'Landlord not on record'));
    if (manager) lines.push(managerLine());
    return lines;
  }
  {
    let html = escapeHtml(owner);
    if (ownerSource === 'registry') html += provenance(registryProvenance(strList(r.registry_pids), str(r.registry_retrieved)));
    else if (ownerSource === 'licence') html += provenance(licenceProvenance(ctx.licenceYear));
    else if (ownerSource === 'sro_list') html += provenance(SRO_INVENTORY);
    const coOwners = strList(r.registered_owners).length - 1;
    if (coOwners > 0) html += ` <span class="popup-muted">${escapeHtml(`+${plural(coOwners, 'co-owner', 'co-owners')}`)}</span>`;
    lines.push(div('popup-owner', html));
  }
  const licence = str(r.licence_holder);
  if (manager) lines.push(managerLine());
  else if (ownerSource === 'registry' && licence && licence !== '(Unknown)' && !sameName(licence, owner)) {
    lines.push(div('', escapeHtml(`Licensed as ${licence}`) + provenance(licenceProvenance(ctx.licenceYear))));
  }
  const netSource = str(r.network_source);
  const onMap = num(r.network_buildings_on_map);
  if (netSource === 'claims' || (netSource === 'licence' && onMap !== null && onMap > 1)) {
    lines.push(div('', `Part of the <strong>${escapeHtml(str(r.network_name))}</strong> ownership group${provenance(networkProvenance(r))}`));
    const onTitle = num(r.network_properties_on_title);
    const entities = strList(r.network_entities).length;
    const counts = [
      onMap === null ? '' : `${plural(Math.trunc(onMap), 'building', 'buildings')} on map`,
      onTitle === null ? '' : `${plural(Math.trunc(onTitle), 'property', 'properties')} on title`,
      entities ? plural(entities, 'linked entity', 'linked entities') : '',
    ].filter(Boolean).join(' · ');
    if (counts) lines.push(div('popup-muted', escapeHtml(counts)));
  }
  return lines;
}

export function renderPopup(r: BuildingRecord, ctx: PopupContext = {}): string {
  const head = [div('popup-address', escapeHtml(formatAddress(r.address)))];
  const name = str(r.building_name) || str(r.housing_name);
  if (name) head.push(div('popup-name', escapeHtml(name)));
  const otherNames = strList(r.other_names);
  if (otherNames.length) head.push(div('popup-muted', escapeHtml(`Also known as ${otherNames.join(', ')}`)));

  const ownership = ownershipLines(r, ctx);

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
  const issues = num(r.n_issues);
  if (issues !== null && issues > 0) {
    let issuesHtml = escapeHtml(plural(Math.trunc(issues), 'outstanding issue', 'outstanding issues'));
    const issuesUrl = safeUrl(r.issues_details);
    if (issuesUrl) issuesHtml += ` · <a href="${escapeHtml(issuesUrl)}" target="_blank" rel="noopener">City details</a>`;
    facts.push(div('popup-issues', issuesHtml));
  }

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
  return div('tc-popup', sections.join(''));
}
