import { describe, expect, it } from 'vitest';
import type { PickOption } from '../landlord-picker';
import type { FilterFields } from '../tables';
import { blockVisibility, filterBuildings, type MetricSpec } from './filter';
import type { FilterState } from './filter-state';

const none: FilterState = {
  hoods: [], housing: [], landlords: [], onlyIssues: false, onlyOwned: false, onlyUnits: false, thresholds: {},
  ownerTypes: [], legalForms: [], market: [], includeInferred: true,
};
const f = (bid: string, o: Partial<FilterFields> = {}): FilterFields => ({
  bid, area: 'west end', areas: [], owner: '', network: '', manager: '',
  housingTypes: [], nIssues: null, hasOwner: false, metrics: { units: 10 },
  ownerTypes: [], legalForms: [], ownerInferred: false, market: '', marketInferred: false, ...o,
});
const unitsSpec: MetricSpec = { key: 'units', attr: 'units', bins: [{ start: 0, end: 10 }, { start: 10, end: 20 }] };
const ids = (s: Set<string>) => [...s].sort();

describe('filterBuildings', () => {
  it('shows everything when nothing is set', () => {
    expect(ids(filterBuildings([f('1'), f('2')], none, []).visible)).toEqual(['1', '2']);
  });

  it('matches an area, or any overlay area of the row, when areas are ticked', () => {
    const fields = [
      f('1'), f('2', { area: 'downtown', areas: ['chinatown'] }), f('3', { area: 'downtown' }),
      f('4', { area: 'strathcona', areas: ['chinatown', 'deod'] }),
    ];
    expect(ids(filterBuildings(fields, { ...none, hoods: ['west end'] }, []).visible)).toEqual(['1']);
    expect(ids(filterBuildings(fields, { ...none, hoods: ['chinatown'] }, []).visible)).toEqual(['2', '4']);
    expect(ids(filterBuildings(fields, { ...none, hoods: ['deod'] }, []).visible)).toEqual(['4']);
    expect(ids(filterBuildings(fields, { ...none, hoods: ['deod', 'west end'] }, []).visible)).toEqual(['1', '4']);
  });

  it('matches landlord tiles by owner, network or manager key', () => {
    const tile = (kind: PickOption['kind'], key: string): PickOption => ({ kind, key, label: key, buildings: 1, detail: '' });
    const fields = [f('1', { owner: 'a' }), f('2', { network: 'n' }), f('3', { manager: 'm' }), f('4')];
    const state = { ...none, landlords: [tile('owner', 'a'), tile('network', 'n'), tile('manager', 'm')] };
    expect(ids(filterBuildings(fields, state, []).visible)).toEqual(['1', '2', '3']);
  });

  it('applies the only-* toggles and housing types', () => {
    const fields = [
      f('1', { nIssues: 2, hasOwner: true, housingTypes: ['co-op', 'sro'] }),
      f('2', { nIssues: 0, metrics: { units: null } }),
    ];
    expect(ids(filterBuildings(fields, { ...none, onlyIssues: true }, []).visible)).toEqual(['1']);
    expect(ids(filterBuildings(fields, { ...none, onlyOwned: true }, []).visible)).toEqual(['1']);
    expect(ids(filterBuildings(fields, { ...none, onlyUnits: true }, []).visible)).toEqual(['1']);
    expect(ids(filterBuildings(fields, { ...none, housing: ['sro'] }, []).visible)).toEqual(['1']);
  });

  it('lets a building with no value pass a threshold', () => {
    const fields = [f('1', { metrics: { units: 5 } }), f('2', { metrics: { units: 15 } }), f('3', { metrics: { units: null } })];
    const state = { ...none, thresholds: { units: { min: 10, max: null } } };
    expect(ids(filterBuildings(fields, state, [unitsSpec]).visible)).toEqual(['2', '3']);
  });

  it("counts each metric's bins without its own threshold, with the last bin inclusive", () => {
    const year: MetricSpec = { key: 'year', attr: 'year-built', bins: [{ start: 1900, end: 1950 }, { start: 1950, end: 2000 }] };
    const fields = [
      f('1', { metrics: { units: 5, 'year-built': 1920 } }),
      f('2', { metrics: { units: 15, 'year-built': 2000 } }), // 2000 is the last bin's end: counted
      f('3', { metrics: { units: 20, 'year-built': 1960 } }), // 20 is the last units bin's end: counted
    ];
    const state = { ...none, thresholds: { units: { min: 10, max: null } } };
    const r = filterBuildings(fields, state, [unitsSpec, year]);
    expect(r.binCounts.units).toEqual([1, 2]); // own threshold ignored: 5 | 15, 20
    expect(r.binCounts.year).toEqual([0, 2]); // only 2 and 3 pass the units threshold
  });
});

describe('blockVisibility', () => {
  const b = (id: string, o: Partial<{ area: string; areas: string[]; buildingIds: string[] }> = {}) =>
    ({ id, area: 'west end', areas: [] as string[], buildingIds: ['1'], ...o });

  it('hides a block whose buildings are all filtered out', () => {
    expect(ids(blockVisibility([b('A'), b('B', { buildingIds: ['2'] })], new Set(['1']), [], false))).toEqual(['B']);
  });

  it('shows an empty block only when asked, and only in a ticked area', () => {
    const empty = b('E', { buildingIds: [] });
    expect(ids(blockVisibility([empty], new Set(), [], false))).toEqual(['E']);
    expect(ids(blockVisibility([empty], new Set(), [], true))).toEqual([]);
    expect(ids(blockVisibility([empty], new Set(), ['downtown'], true))).toEqual(['E']);
  });

  it("matches the block's own area, not its buildings'", () => {
    const strathcona = b('S', { area: 'strathcona', buildingIds: ['10'] }); // building 10 is Downtown
    expect(ids(blockVisibility([strathcona], new Set(['10']), ['downtown'], false))).toEqual(['S']);
  });

  it('hides a block with no area while an area filter is on', () => {
    expect(ids(blockVisibility([b('X', { area: '' })], new Set(['1']), ['west end'], false))).toEqual(['X']);
  });
});

describe('classification filters', () => {
  const pass = (o: Partial<FilterFields>, s: Partial<FilterState>) =>
    filterBuildings([f('1', o)], { ...none, ...s }, []).visible.size === 1;

  it('mixed matches any of its parts', () => {
    expect(pass({ ownerTypes: ['non_profit', 'private'] }, { ownerTypes: ['private'] })).toBe(true);
    expect(pass({ ownerTypes: ['non_profit', 'private'] }, { ownerTypes: ['government'] })).toBe(false);
  });

  it('unknown building passes only when no type is ticked', () => {
    expect(pass({ ownerTypes: [] }, {})).toBe(true);
    expect(pass({ ownerTypes: [] }, { ownerTypes: ['private'] })).toBe(false);
    expect(pass({ market: '' }, { market: ['market'] })).toBe(false);
  });

  it('legal form narrows private owners', () => {
    expect(pass({ ownerTypes: ['private'], legalForms: ['numbered_company'] },
      { ownerTypes: ['private'], legalForms: ['numbered_company'] })).toBe(true);
    expect(pass({ ownerTypes: ['private'], legalForms: ['company'] },
      { ownerTypes: ['private'], legalForms: ['numbered_company'] })).toBe(false);
  });

  it('legal form leaves the other chosen owner types alone', () => {
    const state = { ownerTypes: ['private', 'non_profit'], legalForms: ['company'] };
    expect(pass({ ownerTypes: ['non_profit'] }, state)).toBe(true);
    expect(pass({ ownerTypes: ['private'], legalForms: ['numbered_company'] }, state)).toBe(false);
    expect(pass({ ownerTypes: ['non_profit', 'private'], legalForms: ['numbered_company'] }, state)).toBe(true);
  });

  it('include inferred off drops inferred owner types and market values', () => {
    expect(pass({ ownerTypes: ['private'], ownerInferred: true }, { ownerTypes: ['private'], includeInferred: false })).toBe(false);
    expect(pass({ market: 'market', marketInferred: true }, { market: ['market'], includeInferred: false })).toBe(false);
    expect(pass({ market: 'non_market', marketInferred: false }, { market: ['non_market'], includeInferred: false })).toBe(true);
  });
});
