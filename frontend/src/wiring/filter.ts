/**
 * The filter pass as pure functions: which buildings and blocks pass the
 * current FilterState, and the live histogram counts. filter-pass.ts applies
 * the result to the map and tables.
 */
import { selectionMatches } from '../landlord-picker';
import type { FilterFields } from '../tables';
import type { FilterState } from './filter-state';

export interface MetricSpec { key: string; attr: string; bins: { start: number; end: number }[] }
export interface FilterResult { visible: Set<string>; binCounts: Record<string, number[]> }
export interface BlockFields { id: string; area: string; areas: string[]; buildingIds: string[] }

/**
 * No area ticked means every area. Overlay areas (Chinatown, DEOD, the
 * Villages Plan) are keys a building carries alongside its own local_area,
 * so a row matches if its area is ticked OR any of its overlay areas is.
 */
export function areaMatches(hoods: string[], area: string, areas: string[]): boolean {
  if (hoods.length === 0) return true;
  if (hoods.includes(area)) return true;
  return areas.some((key) => hoods.includes(key));
}

/** Every filter except the per-metric thresholds. */
function baseMatches(f: FilterFields, s: FilterState): boolean {
  if (!areaMatches(s.hoods, f.area, f.areas)) return false;
  if (s.landlords.length > 0 && !selectionMatches(s.landlords, f)) return false;
  if (s.onlyIssues && !(f.nIssues !== null && f.nIssues > 0)) return false;
  if (s.housing.length > 0 && !s.housing.some((t) => f.housingTypes.includes(t))) return false;
  // Otherwise the Units slider lets buildings with no count through (see below).
  if (s.onlyUnits && f.metrics.units == null) return false;
  if (s.onlyOwned && !f.hasOwner) return false;
  return true;
}

export function filterBuildings(fields: FilterFields[], state: FilterState, metrics: MetricSpec[]): FilterResult {
  const visible = new Set<string>();
  const binCounts: Record<string, number[]> = {};
  for (const m of metrics) binCounts[m.key] = m.bins.map(() => 0);

  for (const f of fields) {
    if (!baseMatches(f, state)) continue;
    // A building with no value for a metric (e.g. an SRO record with no unit
    // count) passes that metric's threshold rather than failing a NaN test.
    const values = metrics.map((m) => f.metrics[m.attr] ?? null);
    const pass = metrics.map((m, i) => {
      const v = values[i];
      const t = state.thresholds[m.key];
      if (v === null || !t) return true;
      return !((t.min !== null && v < t.min) || (t.max !== null && v > t.max));
    });
    if (pass.every(Boolean)) visible.add(f.bid);

    // Live histograms: each metric's bars count buildings passing every OTHER
    // filter but not its own threshold — "how many more if I loosen just this
    // slider". Bin edges stay fixed; the last bin includes its end.
    metrics.forEach((m, i) => {
      const v = values[i];
      if (v === null) return;
      if (!pass.every((p, j) => j === i || p)) return;
      const bins = m.bins;
      for (let b = 0; b < bins.length; b += 1) {
        const isLast = b === bins.length - 1;
        if (v >= bins[b].start && (isLast ? v <= bins[b].end : v < bins[b].end)) {
          binCounts[m.key][b] += 1;
          break;
        }
      }
    });
  }
  return { visible, binCounts };
}

/**
 * A block's area match always uses the block's own local_area, never its
 * member buildings': the block/building spatial join has a known bug where a
 * few blocks claim buildings from other, sometimes distant, neighbourhoods.
 * A non-empty block shows if any of its buildings is visible; an empty block
 * only when "Include empty blocks" is on.
 */
export function blockVisibility(blocks: BlockFields[], visible: Set<string>, hoods: string[], showEmpty: boolean): Set<string> {
  const hidden = new Set<string>();
  for (const b of blocks) {
    const hoodMatch = areaMatches(hoods, b.area, b.areas);
    const hide = b.buildingIds.length === 0
      ? !showEmpty || !hoodMatch
      : !b.buildingIds.some((id) => visible.has(id)) || !hoodMatch;
    if (hide) hidden.add(b.id);
  }
  return hidden;
}
