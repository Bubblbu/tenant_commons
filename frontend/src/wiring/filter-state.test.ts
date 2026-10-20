import { describe, expect, it } from 'vitest';
import type { MetricSection } from './metric-controls';
import { clearSection, decodeFilterState, defaultFilterState, encodeFilterState, normalizeThreshold, sectionCounts } from './filter-state';

const ALL = ['west end', 'downtown', 'kitsilano'];

describe('decodeFilterState', () => {
  it('returns {} when the URL has no hood param', () => {
    expect(decodeFilterState(new URLSearchParams('foo=1'), ALL)).toEqual({});
  });

  it('returns the listed neighbourhoods', () => {
    expect(decodeFilterState(new URLSearchParams('hood=west+end&hood=kitsilano'), ALL)).toEqual({ hoods: ['west end', 'kitsilano'] });
  });

  it('matches case-insensitively, like the lowercased checkbox values', () => {
    expect(decodeFilterState(new URLSearchParams('hood=West+End'), ALL)).toEqual({ hoods: ['west end'] });
  });

  it('drops neighbourhoods that no longer exist', () => {
    expect(decodeFilterState(new URLSearchParams('hood=west+end&hood=gone'), ALL)).toEqual({ hoods: ['west end'] });
  });

  it('ignores a stale link whose neighbourhoods all no longer exist', () => {
    expect(decodeFilterState(new URLSearchParams('hood=gone'), ALL)).toEqual({});
  });

  it('reads an older link\'s empty hood param as the default: none ticked, every area shown', () => {
    expect(decodeFilterState(new URLSearchParams('hood='), ALL)).toEqual({});
  });

  it('reads an older link listing every area as none ticked', () => {
    expect(decodeFilterState(new URLSearchParams('hood=west+end&hood=downtown&hood=kitsilano'), ALL)).toEqual({ hoods: [] });
  });
});

describe('encodeFilterState', () => {
  it('omits the param when every neighbourhood is selected', () => {
    const params = new URLSearchParams('hood=downtown&foo=1');
    encodeFilterState({ ...defaultFilterState(), hoods: [...ALL] }, params, ALL);
    expect(params.toString()).toBe('foo=1');
  });

  it('writes one hood param per selected neighbourhood', () => {
    const params = new URLSearchParams();
    encodeFilterState({ ...defaultFilterState(), hoods: ['west end', 'kitsilano'] }, params, ALL);
    expect(params.getAll('hood')).toEqual(['west end', 'kitsilano']);
  });

  it('omits the param when none are ticked (every area shown)', () => {
    const params = new URLSearchParams('hood=downtown&foo=1');
    encodeFilterState({ ...defaultFilterState(), hoods: [] }, params, ALL);
    expect(params.toString()).toBe('foo=1');
  });

  it('round-trips a narrowed selection through decodeFilterState', () => {
    for (const checked of [['downtown'], ['west end', 'kitsilano']]) {
      const params = new URLSearchParams();
      encodeFilterState({ ...defaultFilterState(), hoods: checked }, params, ALL);
      expect(decodeFilterState(params, ALL)).toEqual({ hoods: checked });
    }
  });
});

const sections: Record<string, MetricSection> = { units: 'building', value_land: 'value', portfolio_units: 'portfolio' };

describe('normalizeThreshold', () => {
  it('reads a handle within half a step of its end as no bound', () => {
    const s = { min: 0, max: 100, step: 1, attr: 'units' };
    expect(normalizeThreshold(s, 0.4, 99.6)).toEqual({ min: null, max: null });
    expect(normalizeThreshold(s, 20, 80)).toEqual({ min: 20, max: 80 });
  });
});

describe('clearSection', () => {
  const busy = {
    ...defaultFilterState(),
    hoods: ['west end'], housing: ['sro'], onlyIssues: true, onlyOwned: true, onlyUnits: true,
    landlords: [{ kind: 'owner' as const, key: 'a', label: 'A', buildings: 1, detail: '' }],
    thresholds: { units: { min: 5, max: null }, value_land: { min: null, max: 9 }, portfolio_units: { min: 50, max: null } },
  };

  it('clears only the named section', () => {
    expect(clearSection(busy, 'area', sections)).toEqual({ ...busy, hoods: [] });
    // Landlord: the picker, "Landlord on record" and the portfolio sliders.
    expect(clearSection(busy, 'landlord', sections)).toEqual({
      ...busy, landlords: [], onlyOwned: false,
      thresholds: { units: { min: 5, max: null }, value_land: { min: null, max: 9 } },
    });
    expect(clearSection(busy, 'building', sections)).toEqual({
      ...busy, housing: [], onlyIssues: false, onlyUnits: false,
      thresholds: { value_land: { min: null, max: 9 }, portfolio_units: { min: 50, max: null } },
    });
    expect(clearSection(busy, 'value', sections)).toEqual({
      ...busy, thresholds: { units: { min: 5, max: null }, portfolio_units: { min: 50, max: null } },
    });
  });

  it('counts active filters per section', () => {
    expect(sectionCounts(busy, sections)).toEqual({ area: 1, landlord: 3, type: 0, building: 4, value: 1 });
    expect(sectionCounts(defaultFilterState(), sections)).toEqual({ area: 0, landlord: 0, type: 0, building: 0, value: 0 });
    const classified = { ...busy, ownerTypes: ['private'], legalForms: ['trust'], includeInferred: false };
    expect(sectionCounts(classified, sections).type).toBe(3);
    expect(clearSection(classified, 'type', sections)).toEqual(busy);
    // Rents sit in Building.
    const rents = { ...defaultFilterState(), market: ['non_market'] };
    expect(sectionCounts(rents, sections)).toMatchObject({ type: 0, building: 1 });
    expect(clearSection(rents, 'type', sections).market).toEqual(['non_market']);
    expect(clearSection(rents, 'building', sections).market).toEqual([]);
  });
});

describe('URL codec', () => {
  it('round-trips the ticked areas', () => {
    const all = ['west end', 'downtown', 'chinatown'];
    const params = new URLSearchParams();
    encodeFilterState({ ...defaultFilterState(), hoods: ['downtown', 'chinatown'] }, params, all);
    expect(decodeFilterState(params, all)).toEqual({ hoods: ['downtown', 'chinatown'] });
  });
});
