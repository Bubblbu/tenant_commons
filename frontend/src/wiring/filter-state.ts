import type { LandlordFilter, PickOption } from '../landlord-picker';
import type { MetricControls, MetricSection } from './metric-controls';
import type { MetricSummary } from './metric-format';

export interface Threshold { min: number | null; max: number | null }
export interface FilterState {
  /** lowercased area keys, incl. overlay area keys ('chinatown', 'deod', 'village-plan'); [] = every area */
  hoods: string[];
  housing: string[];
  landlords: PickOption[];
  onlyIssues: boolean;
  onlyOwned: boolean;
  onlyUnits: boolean;
  /** Owner types ('private', 'non_profit', ...); a mixed building matches any of its parts. */
  ownerTypes: string[];
  legalForms: string[];
  market: string[];
  /** Off: only owner types from evidence, not inference (rents always count inferred values). */
  includeInferred: boolean;
  /** Missing key or null bound = unbounded. */
  thresholds: Record<string, Threshold>;
}

/** The sidebar's Filter by sections. The portfolio sliders sit in Landlord; classification in Owner type. */
export type FilterSection = 'area' | 'landlord' | 'type' | 'building' | 'value';  // 'type' = Ownership type

export interface FilterControls {
  hoodInputs: HTMLInputElement[];
  housingChips: HTMLElement[];
  onlyIssues: HTMLInputElement | null;
  onlyOwned: HTMLInputElement | null;
  onlyUnits: HTMLInputElement | null;
  ownerTypeChips: HTMLElement[];
  legalFormChips: HTMLElement[];
  marketChips: HTMLElement[];
  includeInferred: HTMLInputElement | null;
  landlords?: LandlordFilter;
  metrics: MetricControls;
}

export function defaultFilterState(): FilterState {
  return {
    hoods: [], housing: [], landlords: [], onlyIssues: false, onlyOwned: false, onlyUnits: false, thresholds: {},
    ownerTypes: [], legalForms: [], market: [], includeInferred: true,
  };
}

/** A handle within half a step of its end of the range means "no bound". */
export function normalizeThreshold(summary: MetricSummary, currentMin: number, currentMax: number): Threshold {
  const tolerance = summary.step ? summary.step * 0.5 : 0;
  return {
    min: currentMin <= summary.min + tolerance ? null : currentMin,
    max: currentMax >= summary.max - tolerance ? null : currentMax,
  };
}

function withoutSection(thresholds: Record<string, Threshold>, section: MetricSection, metricSection: Record<string, MetricSection>) {
  return Object.fromEntries(Object.entries(thresholds).filter(([k]) => metricSection[k] !== section));
}

export function clearSection(state: FilterState, section: FilterSection, metricSection: Record<string, MetricSection>): FilterState {
  switch (section) {
    case 'area': return { ...state, hoods: [] };
    case 'landlord':
      return { ...state, landlords: [], onlyOwned: false, thresholds: withoutSection(state.thresholds, 'portfolio', metricSection) };
    case 'type': return { ...state, ownerTypes: [], legalForms: [], includeInferred: true };
    case 'building':
      return {
        ...state, housing: [], market: [], onlyIssues: false, onlyUnits: false,
        thresholds: withoutSection(state.thresholds, 'building', metricSection),
      };
    case 'value': return { ...state, thresholds: withoutSection(state.thresholds, 'value', metricSection) };
  }
}

/** How many filters each Filter by section has on, shown beside its heading. */
export function sectionCounts(state: FilterState, metricSection: Record<string, MetricSection>): Record<FilterSection, number> {
  const active: Record<MetricSection, number> = { building: 0, value: 0, portfolio: 0 };
  for (const [k, t] of Object.entries(state.thresholds)) {
    const section = metricSection[k];
    if (section && (t.min !== null || t.max !== null)) active[section] += 1;
  }
  return {
    area: state.hoods.length,
    landlord: state.landlords.length + (state.onlyOwned ? 1 : 0) + active.portfolio,
    type: state.ownerTypes.length + state.legalForms.length + (state.includeInferred ? 0 : 1),
    building: state.housing.length + state.market.length + (state.onlyIssues ? 1 : 0) + (state.onlyUnits ? 1 : 0) +
      active.building,
    value: active.value,
  };
}

const areaKey = (v: string): string => (v || '').toLowerCase().trim();

const pressed = (chips: HTMLElement[], attr: string): string[] =>
  chips.filter((chip) => chip.getAttribute('aria-pressed') === 'true').map((chip) => chip.getAttribute(attr) ?? '');

function press(chips: HTMLElement[], attr: string, values: string[]): void {
  chips.forEach((chip) => {
    chip.setAttribute('aria-pressed', values.includes(chip.getAttribute(attr) ?? '') ? 'true' : 'false');
  });
}

export function findFilterControls(doc: Document, landlords: LandlordFilter | undefined, metrics: MetricControls): FilterControls {
  const checkbox = (id: string) => doc.getElementById(id) as HTMLInputElement | null;
  return {
    hoodInputs: Array.from(doc.querySelectorAll<HTMLInputElement>('.filter-neighbourhood-option')),
    housingChips: Array.from(doc.querySelectorAll<HTMLElement>('.housing-chip')),
    onlyIssues: checkbox('filter-only-issues'),
    onlyOwned: checkbox('filter-only-owned'),
    onlyUnits: checkbox('filter-only-units'),
    ownerTypeChips: Array.from(doc.querySelectorAll<HTMLElement>('.owner-type-chip')),
    legalFormChips: Array.from(doc.querySelectorAll<HTMLElement>('.legal-form-chip')),
    marketChips: Array.from(doc.querySelectorAll<HTMLElement>('.market-chip')),
    includeInferred: checkbox('filter-include-inferred'),
    landlords,
    metrics,
  };
}

/** Reads the controls. Call metrics.updateAllLabels() first so currentMin/currentMax are fresh. */
export function readFilterState(c: FilterControls): FilterState {
  const thresholds: Record<string, Threshold> = {};
  for (const key of c.metrics.keys) {
    const ctrl = c.metrics.controls[key];
    thresholds[key] = normalizeThreshold(ctrl.summary, ctrl.currentMin, ctrl.currentMax);
  }
  return {
    hoods: c.hoodInputs.filter((i) => i.checked).map((i) => areaKey(i.value)),
    housing: c.housingChips
      .filter((chip) => chip.getAttribute('aria-pressed') === 'true')
      .map((chip) => chip.getAttribute('data-housing') ?? ''),
    landlords: c.landlords ? c.landlords.picked() : [],
    onlyIssues: !!c.onlyIssues?.checked,
    onlyOwned: !!c.onlyOwned?.checked,
    onlyUnits: !!c.onlyUnits?.checked,
    ownerTypes: pressed(c.ownerTypeChips, 'data-owner-type'),
    legalForms: pressed(c.legalFormChips, 'data-legal-form'),
    market: pressed(c.marketChips, 'data-market'),
    includeInferred: c.includeInferred ? c.includeInferred.checked : true,
    thresholds,
  };
}

export function writeFilterState(c: FilterControls, state: FilterState): void {
  const hoods = new Set(state.hoods);
  c.hoodInputs.forEach((i) => { i.checked = hoods.has(areaKey(i.value)); });
  c.housingChips.forEach((chip) => {
    chip.setAttribute('aria-pressed', state.housing.includes(chip.getAttribute('data-housing') ?? '') ? 'true' : 'false');
  });
  if (c.onlyIssues) c.onlyIssues.checked = state.onlyIssues;
  if (c.onlyOwned) c.onlyOwned.checked = state.onlyOwned;
  if (c.onlyUnits) c.onlyUnits.checked = state.onlyUnits;
  press(c.ownerTypeChips, 'data-owner-type', state.ownerTypes);
  // Legal form narrows private owners, so it only applies once Private is chosen.
  const privateChosen = state.ownerTypes.includes('private');
  press(c.legalFormChips, 'data-legal-form', privateChosen ? state.legalForms : []);
  c.legalFormChips.forEach((chip) => chip.toggleAttribute('disabled', !privateChosen));
  press(c.marketChips, 'data-market', state.market);
  if (c.includeInferred) c.includeInferred.checked = state.includeInferred;
  c.landlords?.set(state.landlords);
  for (const key of c.metrics.keys) {
    const t = state.thresholds[key];
    c.metrics.setRange(key, t ? t.min : null, t ? t.max : null);
  }
}

const HOOD_PARAM = 'hood';

/**
 * Ticked areas from a shared link: one `hood` param per area. No param — or
 * every area, or only areas that no longer exist — means the default (none
 * ticked, every area shown). Older links' lone empty `hood=` reads as default.
 */
export function decodeFilterState(params: URLSearchParams, allHoods: string[]): Partial<FilterState> {
  const raw = params.getAll(HOOD_PARAM);
  if (raw.length === 0) return {};
  const wanted = new Set(raw.map(areaKey));
  const hoods = allHoods.filter((v) => wanted.has(v));
  if (hoods.length === 0) return {};
  if (hoods.length === allHoods.length) return { hoods: [] };
  return { hoods };
}

export function encodeFilterState(state: FilterState, params: URLSearchParams, allHoods: string[]): void {
  params.delete(HOOD_PARAM);
  if (state.hoods.length === allHoods.length) return;
  for (const v of state.hoods) params.append(HOOD_PARAM, v);
}
