import { describe, expect, it } from 'vitest';
import { housingTypes, markerRadius, markerStyle } from './markers';
import type { MarkerRecord } from './types';

const base: MarkerRecord = {
  b_id: 1, lat: 49.28, lon: -123.1, owner_key: 'x', block_id: 1, units: 40, year_built: 1970,
  local_area: 'West End', housing_type: '', source: 'building',
};

describe('markerRadius', () => {
  it('matches layout.py for a real building (449 units)', () => {
    // From the Folium-era marker metadata: base_radius 9.18345683964709.
    expect(markerRadius(449)).toBeCloseTo(9.18345683964709, 12);
  });

  it('caps at 600 units and floors missing or non-positive values at 3.2', () => {
    expect(markerRadius(600)).toBeCloseTo(9.5, 12);
    expect(markerRadius(5000)).toBeCloseTo(9.5, 12);
    expect(markerRadius(null)).toBe(3.2);
    expect(markerRadius(0)).toBe(3.2);
    expect(markerRadius(Number.NaN)).toBe(3.2);
  });
});

describe('housingTypes', () => {
  it('orders co-op before SRO, as layout.py did', () => {
    expect(housingTypes('co-op, sro')).toEqual(['coop', 'sro']);
    expect(housingTypes('sro')).toEqual(['sro']);
    expect(housingTypes('')).toEqual([]);
  });
});

describe('markerStyle', () => {
  it('colours every building the same neutral grey — no VTU membership signal', () => {
    expect(markerStyle(base)).toMatchObject({ base_color: '#9e9e9e', base_opacity: 0.6 });
  });

  it('gives a single-type building that type\'s ring as its own stroke', () => {
    expect(markerStyle({ ...base, housing_type: 'sro' })).toMatchObject({
      stroke_color: '#3182bd', stroke_weight: 2.2, primary_housing_type: 'sro', extra_rings: [],
    });
  });

  it('gives a dual building the co-op stroke plus one extra SRO ring', () => {
    expect(markerStyle({ ...base, housing_type: 'co-op, sro' })).toMatchObject({
      stroke_color: '#d97706', primary_housing_type: 'coop', extra_rings: [{ housing_type: 'sro' }],
    });
  });

  it('uses the thin white default stroke otherwise', () => {
    expect(markerStyle(base)).toMatchObject({
      stroke_color: '#ffffff', stroke_weight: 0.6, primary_housing_type: '', extra_rings: [],
    });
  });
});
