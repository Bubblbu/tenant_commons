/**
 * Sidebar table rows, ported from sica_mapping/data/tables.py. Attributes,
 * columns, sort keys and rounding follow the Python, because wiring/ reads
 * these rows as its filter model: data-* attributes, fixed column indices
 * (wiring/tables-live.ts cacheRowCells) and .row-select checkboxes. Known cosmetic
 * differences, neither affecting sorting or filtering: numeric sort values
 * render as JS numbers (15, not Python's 15.0), and tied rows may order
 * differently. Must render before startWiring(); it queries the rows once.
 */
import { formatAddress } from './address';
import { escapeHtml, isMissing, roundHalfEven, sameName } from './html';
import { managerKey } from './landlord-picker';
import { EXPLAINERS, networkProvenance, ownerRowProvenance, provenanceIcon, tipPlacement } from './provenance';
import type { BlocksCollection, BuildingData, BuildingRecord } from './types';

export interface FilterFields {
  bid: string;
  /** lowercased, trimmed local_area */
  area: string;
  chinatown: boolean;
  village: boolean;
  owner: string;
  network: string;
  manager: string;
  housingTypes: string[];
  nIssues: number | null;
  hasOwner: boolean;
  /** Keyed by a metric summary's attr: 'units', 'year-built', 'value-land', 'value-bldg', 'value-ratio'. */
  metrics: Record<string, number | null>;
}

const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
/** Python int() of a present number, else "". */
const intStr = (v: unknown): string => {
  const n = num(v);
  return n === null ? '' : String(Math.trunc(n));
};
const text = (v: unknown): string => (isMissing(v) ? '' : String(v));

/** pandas sort_values(ascending=False): larger first, missing last. Stable. */
function descMissingLast(a: number | null, b: number | null): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return b - a;
}

/** A building with no known landlord: shown as "Not on record" and never ranked as a landlord. */
const notOnRecord = (key: unknown): boolean => isMissing(key);

/** Date the registry was searched without a filing (null in the flat view when a registry owner exists). */
const noFilingSearched = (r: BuildingRecord): string => text(r.registry_no_filing);

/** Group key of a not-on-record building that was searched in the registry without a filing. */
export const SEARCHED_KEY = 'unknown-searched';

/**
 * The owner or network key a building is grouped, filtered and selected by:
 * the export's key, except that not-on-record buildings (null key) split into
 * SEARCHED_KEY (registry searched, no filing) and "unknown" (not yet searched)
 * — the tables' own group keys, not data.
 */
export function groupKey(key: unknown, r: BuildingRecord): string {
  if (!notOnRecord(key)) return String(key);
  return noFilingSearched(r) ? SEARCHED_KEY : 'unknown';
}
const isNotOnRecordGroup = (key: string): boolean => key === 'unknown' || key === SEARCHED_KEY;

const truncOrNull = (v: unknown): number | null => {
  const n = num(v);
  return n === null ? null : Math.trunc(n);
};
const roundOrNull = (v: unknown, digits = 0): number | null => {
  const n = num(v);
  return n === null ? null : roundHalfEven(n, digits);
};
const attr = (v: number | null): string => (v === null ? '' : String(v));

/** What the filters read about a building. The row's data-* attributes are rendered from this. */
export function filterFields(r: BuildingRecord): FilterFields {
  return {
    bid: String(Math.trunc(Number(r.b_id))),
    area: text(r.local_area).toLowerCase().trim(),
    chinatown: r.in_chinatown === true,
    village: r.in_village_plan === true,
    owner: groupKey(r.owner_key, r),
    network: groupKey(r.network_key, r),
    manager: managerKey(r.managed_by),
    housingTypes: text(r.housing_type).split(',').map((t) => t.trim()).filter((t) => t !== ''),
    nIssues: truncOrNull(r.n_issues),
    hasOwner: !notOnRecord(r.owner_key),
    metrics: {
      units: truncOrNull(r.units),
      'year-built': truncOrNull(r.year_built),
      'value-land': roundOrNull(r.value_land),
      'value-bldg': roundOrNull(r.value_bldg),
      'value-ratio': roundOrNull(r.bldg_land_ratio, 3),
    },
  };
}

/**
 * Sorted rows with the data-pin="last" rows moved to the end, in their
 * built order rather than the sort's (wiring sorting): the "Not on record"
 * rows stay put, searched before not yet searched, in either direction.
 */
export function pinLast<T extends { getAttribute(name: string): string | null }>(sorted: T[], built: T[] = sorted): T[] {
  const pinned = (r: T) => r.getAttribute('data-pin') === 'last';
  return [...sorted.filter((r) => !pinned(r)), ...built.filter(pinned)];
}

/** Python's str ordering (code points), not localeCompare. */
function byCodePoint(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

export function buildingRow(r: BuildingRecord): string {
  const f = filterFields(r);
  const bid = f.bid;
  const block = intStr(r.block_id);
  const units = attr(f.metrics.units);
  const year = attr(f.metrics['year-built']);
  const nIssues = attr(f.nIssues);
  const valLand = attr(f.metrics['value-land']);
  const valBldg = attr(f.metrics['value-bldg']);
  const ratioVal = attr(f.metrics['value-ratio']);
  const area = text(r.local_area);
  const housing = text(r.housing_type);
  const onRecord = f.hasOwner;
  const owner = onRecord ? text(r.owner_name) : '';
  const networkName = onRecord && !notOnRecord(r.network_key) ? text(r.network_name) : '';
  const network = sameName(networkName, owner) ? '' : networkName;
  const manager = text(r.managed_by);
  const sub = (line: string) => (line ? `<div class="cell-sub">${escapeHtml(line)}</div>` : '');
  const managerLine = sub(manager ? `Managed by ${manager}` : '');
  const searched = noFilingSearched(r);
  const searchLine = sub(searched ? `No registry filing · searched ${searched}` : '');
  const landlordCell = onRecord
    ? `<td>${escapeHtml(owner)}${sub(network ? `Group: ${network}` : '')}${searchLine}${managerLine}</td>`
    : `<td class="not-on-record">Not on record${searchLine}${managerLine}</td>`;
  const names = [text(r.building_name), ...(Array.isArray(r.other_names) ? r.other_names.map(text) : [])];
  const search = [text(r.address), ...names, area, units, owner, network, manager, housing]
    .filter((v) => v !== '')
    .map((v) => v.toLowerCase())
    .join(' ');
  const a = escapeHtml(area);
  const h = escapeHtml(housing);
  const chinatown = f.chinatown ? '1' : '';
  const village = f.village ? '1' : '';
  return (
    `<tr data-bid="${bid}" data-owner="${escapeHtml(f.owner)}" ` +
    `data-network="${escapeHtml(f.network)}" data-manager="${escapeHtml(f.manager)}" ` +
    `data-block="${block}" ` +
    `data-area="${a}" data-chinatown="${chinatown}" data-village="${village}" ` +
    `data-value-land="${valLand}" data-value-bldg="${valBldg}" ` +
    `data-value-ratio="${ratioVal}" data-units="${units}" ` +
    `data-year-built="${year}" data-search="${escapeHtml(search)}" ` +
    `data-housing-type="${h}" data-n-issues="${nIssues}" data-has-owner="${onRecord ? '1' : ''}">` +
    `<td class="select-cell"><input type="checkbox" class="row-select" ` +
    `data-type="building" data-target="${bid}"></td>` +
    `<td>${escapeHtml(formatAddress(r.address))}</td>` +
    `<td>${escapeHtml(text(r.building_name))}</td>` +
    `<td data-sort-value="${a}">${a}</td>` +
    `<td data-sort-value="${units}">${units}</td>` +
    landlordCell +
    `<td data-sort-value="${year}">${year}</td>` +
    `<td data-sort-value="${nIssues}">${nIssues}</td>` +
    `</tr>`
  );
}

export function buildingRowsHtml(records: BuildingRecord[]): string {
  return [...records]
    .sort((x, y) => descMissingLast(num(x.units), num(y.units)))
    .map(buildingRow)
    .join('\n');
}

const avgUnits = (total: number, bldgs: number): number => (bldgs > 0 ? roundHalfEven(total / bldgs, 1) : 0);

export function blockRowsHtml(fc: BlocksCollection): string {
  const rows = fc.features.map((f) => f.properties ?? ({} as BlocksCollection['features'][number]['properties']));
  return rows
    .map((p) => ({ p, label: text(p.block_label) }))
    .sort((x, y) => {
      const ux = x.label.startsWith('(Unknown)') ? 1 : 0;
      const uy = y.label.startsWith('(Unknown)') ? 1 : 0;
      return ux - uy || byCodePoint(x.label, y.label);
    })
    .map(({ p, label }) => {
      const id = Math.trunc(Number(p.block_id));
      const bldgs = Math.trunc(num(p.buildings) ?? 0);
      const totalRaw = num(p.total_units) ?? 0;
      const total = Math.trunc(totalRaw);
      const avg = avgUnits(totalRaw, bldgs);
      const median = num(p.median_year_built);
      const year = median === null ? '' : String(roundHalfEven(median));
      const l = escapeHtml(label);
      const chinatown = p.in_chinatown === true ? '1' : '';
      const village = p.in_village_plan === true ? '1' : '';
      return (
        `<tr data-block="${id}" data-area="${escapeHtml(text(p.local_area))}" ` +
        `data-chinatown="${chinatown}" data-village="${village}" ` +
        `data-bldgs="${bldgs}" data-units="${total}">` +
        `<td class="select-cell"><input type="checkbox" class="row-select" ` +
        `data-type="block" data-target="${id}"></td>` +
        `<td data-sort-value="${l}">${l}</td>` +
        `<td data-sort-value="${bldgs}">${bldgs}</td>` +
        `<td data-sort-value="${total}">${total}</td>` +
        `<td data-sort-value="${avg}">${avg.toFixed(1)}</td>` +
        `<td data-sort-value="${year}">${year}</td>` +
        `</tr>`
      );
    })
    .join('\n');
}

interface Group {
  label: string;
  key: string;
  buildings: number;
  totalUnits: number;
  records: BuildingRecord[];
}

/**
 * Group by key (count address, sum units), then sort by units, buildings desc.
 * One row per key: spellings of the same key ("Chartwell Construction Ltd" /
 * "CHARTWELL CONSTRUCTION LTD.") merge, labelled by the commonest spelling
 * (ties: code-point order), since wiring/indexes.ts indexes markers by key alone.
 */
function aggregate(records: BuildingRecord[], labelOf: (r: BuildingRecord) => string, keyOf: (r: BuildingRecord) => string): Group[] {
  const groups = new Map<string, Group & { labels: Map<string, number> }>();
  for (const r of records) {
    const label = labelOf(r);
    const key = keyOf(r);
    let g = groups.get(key);
    if (!g) {
      g = { label, key, buildings: 0, totalUnits: 0, records: [], labels: new Map() };
      groups.set(key, g);
    }
    g.records.push(r);
    g.labels.set(label, (g.labels.get(label) ?? 0) + 1);
    if (!isMissing(r.address)) g.buildings += 1;
    g.totalUnits += num(r.units) ?? 0;
  }
  for (const g of groups.values()) {
    g.label = [...g.labels].sort((a, b) => b[1] - a[1] || byCodePoint(a[0], b[0]))[0][0];
  }
  return [...groups.values()]
    .sort((a, b) => byCodePoint(a.label, b.label) || byCodePoint(a.key, b.key)) // groupby's key order
    .sort((a, b) => b.totalUnits - a.totalUnits || b.buildings - a.buildings);
}

function groupRow(
  g: Group, type: 'owner' | 'network' | 'neighbourhood', target: string, first: string, dataKey: string, icon = '',
  pinned = false,
): string {
  const units = Math.trunc(g.totalUnits);
  const avg = avgUnits(g.totalUnits, g.buildings);
  const pin = pinned ? 'data-pin="last" class="not-on-record" ' : '';
  const label = !pinned ? first
    : target === SEARCHED_KEY ? 'Not on record · searched, no registry filing' : 'Not on record · not yet searched';
  return (
    `<tr ${dataKey}="${target}" ${pin}` +
    `data-bldgs="${g.buildings}" data-units="${units}">` +
    `<td class="select-cell"><input type="checkbox" class="row-select" ` +
    `data-type="${type}" data-target="${target}"></td>` +
    `<td data-sort-value="${pinned ? '' : first}">${label}${icon}</td>` +
    `<td data-sort-value="${g.buildings}">${g.buildings}</td>` +
    `<td data-sort-value="${units}">${units}</td>` +
    `<td data-sort-value="${avg}">${avg.toFixed(1)}</td>` +
    `</tr>`
  );
}

/** Landlord groups with the two "Not on record" groups (searched first) moved to the end. */
function landlordGroups(records: BuildingRecord[], nameOf: (r: BuildingRecord) => unknown, keyOf: (r: BuildingRecord) => unknown): Group[] {
  const groups = aggregate(
    records,
    (r) => (notOnRecord(keyOf(r)) ? '' : text(nameOf(r))),
    (r) => groupKey(keyOf(r), r),
  );
  return [
    ...groups.filter((g) => !isNotOnRecordGroup(g.key)),
    ...groups.filter((g) => g.key === SEARCHED_KEY),
    ...groups.filter((g) => g.key === 'unknown'),
  ];
}

/** A row's provenance icon, or '' when there is nothing to say. */
const iconFor = (text: string) => (text ? provenanceIcon(text) : '');

export function ownerRowsHtml(records: BuildingRecord[], licenceYear: number | null = null): string {
  return landlordGroups(records, (r) => r.owner_name, (r) => r.owner_key)
    .map((g) => {
      if (isNotOnRecordGroup(g.key)) return groupRow(g, 'owner', g.key, '', 'data-owner', '', true);
      return groupRow(
        g, 'owner', escapeHtml(g.key), escapeHtml(g.label), 'data-owner',
        iconFor(ownerRowProvenance(g.records.map((r) => r.owner_source), licenceYear)),
      );
    })
    .join('\n');
}

export function networkRowsHtml(records: BuildingRecord[]): string {
  return landlordGroups(records, (r) => r.network_name, (r) => r.network_key)
    .map((g) => {
      if (isNotOnRecordGroup(g.key)) return groupRow(g, 'network', g.key, '', 'data-network', '', true);
      const sample = g.records[0];
      const icon = sample.network_source === 'claims' || sample.network_source === 'name_match'
        ? provenanceIcon(networkProvenance(sample))
        : '';
      const landlords = new Set(g.records.map((r) => r.owner_key).filter((k) => !notOnRecord(k))).size;
      const members = landlords > 1 ? `<span class="cell-sub-inline"> · ${landlords} landlords</span>` : '';
      return groupRow(g, 'network', escapeHtml(g.key), escapeHtml(g.label), 'data-network', members + icon);
    })
    .join('\n');
}

export function neighbourhoodRowsHtml(records: BuildingRecord[]): string {
  return aggregate(
    records,
    (r) => (isMissing(r.local_area) ? '(Unknown)' : String(r.local_area)),
    (r) => (isMissing(r.local_area) ? '(Unknown)' : String(r.local_area)),
  )
    .map((g) => {
      const area = escapeHtml(g.label);
      return groupRow(g, 'neighbourhood', area, area, 'data-area');
    })
    .join('\n');
}

/**
 * Adds the explainer icon to every header marked data-explain="owner|network".
 * Header cells are sticky (so they contain the tooltip) and tables can be wider
 * than the screen, so the tooltip is placed inside the visible table area each
 * time it opens.
 */
export function addHeaderExplainers(doc: Document = document): void {
  doc.querySelectorAll<HTMLElement>('table.data th[data-explain]').forEach((th) => {
    const text = EXPLAINERS[th.dataset.explain as keyof typeof EXPLAINERS];
    if (!text || th.querySelector('.prov')) return;
    th.insertAdjacentHTML('beforeend', provenanceIcon(text, 'About'));
    const icon = th.querySelector<HTMLElement>('.prov');
    if (!icon) return;
    const place = () => {
      const clip = (icon.closest('.table-wrap') ?? doc.documentElement).getBoundingClientRect();
      const viewWidth = doc.defaultView?.innerWidth ?? clip.right;
      const { left, width } = tipPlacement(
        icon.getBoundingClientRect().left, th.getBoundingClientRect().left,
        Math.max(clip.left, 0), Math.min(clip.right, viewWidth),
      );
      icon.style.setProperty('--tip-left', `${left}px`);
      icon.style.setProperty('--tip-width', `${width}px`);
    };
    icon.addEventListener('mouseenter', place);
    icon.addEventListener('focus', place);
  });
}

export function renderTables(
  data: BuildingData, blocks: BlocksCollection, doc: Document = document, licenceYear: number | null = null,
): void {
  const records = Object.values(data.records);
  const fill = (tableId: string, html: string) => {
    const tbody = doc.querySelector(`#${tableId} tbody`);
    if (tbody) tbody.innerHTML = html;
  };
  fill('buildings-table', buildingRowsHtml(records));
  fill('blocks-table', blockRowsHtml(blocks));
  fill('owners-table', ownerRowsHtml(records, licenceYear));
  fill('networks-table', networkRowsHtml(records));
  fill('neighbourhoods-table', neighbourhoodRowsHtml(records));
  addHeaderExplainers(doc);
}
