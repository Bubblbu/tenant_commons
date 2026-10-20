import { describe, expect, it } from 'vitest';
import { areaBounds, geometryBounds, selectionBounds, type LatLonBounds } from './initial-view';
import type { BoundaryCollection, OverlayCollection } from './types';

const square = (lon0: number, lat0: number, lon1: number, lat1: number) => ({
  type: 'Polygon' as const,
  coordinates: [[[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]],
});

const fc = (...features: { name?: string; area?: string; geometry: ReturnType<typeof square> }[]): BoundaryCollection => ({
  type: 'FeatureCollection',
  features: features.map((f) => ({ type: 'Feature', properties: { name: f.name, ...(f.area ? { area: f.area } : {}) }, geometry: f.geometry })),
});

describe('geometryBounds', () => {
  it('swaps GeoJSON [lon, lat] into [[south, west], [north, east]]', () => {
    expect(geometryBounds(square(-123.2, 49.2, -123.1, 49.3))).toEqual([[49.2, -123.2], [49.3, -123.1]]);
  });

  it('covers every polygon of a MultiPolygon', () => {
    const g = { type: 'MultiPolygon' as const, coordinates: [square(0, 0, 1, 1).coordinates, square(2, 2, 3, 3).coordinates] };
    expect(geometryBounds(g)).toEqual([[0, 0], [3, 3]]);
  });

  it('returns null for a missing geometry', () => {
    expect(geometryBounds(null)).toBeNull();
  });
});

describe('areaBounds', () => {
  it('keys neighbourhoods by lowercased name and the overlay areas by their key', () => {
    const areas = areaBounds(
      fc({ name: 'West End', geometry: square(0, 0, 1, 1) }),
      fc(
        { area: 'chinatown', name: 'Chinatown', geometry: square(5, 5, 6, 6) },
        { area: 'village-plan', name: 'A', geometry: square(7, 7, 8, 8) },
        { area: 'village-plan', name: 'B', geometry: square(9, 9, 10, 10) },
      ) as unknown as OverlayCollection,
    );
    expect(areas.get('west end')).toEqual([[0, 0], [1, 1]]);
    expect(areas.get('chinatown')).toEqual([[5, 5], [6, 6]]);
    expect(areas.get('village-plan')).toEqual([[7, 7], [10, 10]]);
  });
});

describe('selectionBounds', () => {
  const areas = new Map<string, LatLonBounds>([
    ['west end', [[0, 0], [1, 1]]],
    ['chinatown', [[5, 5], [6, 6]]],
  ]);
  const all = ['west end', 'chinatown', 'downtown'];

  it('frames a single checked area', () => {
    expect(selectionBounds(['chinatown'], all, areas)).toEqual([[5, 5], [6, 6]]);
  });

  it('spans every checked area', () => {
    expect(selectionBounds(['west end', 'chinatown'], all, areas)).toEqual([[0, 0], [6, 6]]);
  });

  it('keeps the default view when everything or nothing is checked', () => {
    expect(selectionBounds(all, all, areas)).toBeNull();
    expect(selectionBounds([], all, areas)).toBeNull();
  });

  it('skips checked areas without a boundary, falling back when none has one', () => {
    expect(selectionBounds(['chinatown', 'downtown'], all, areas)).toEqual([[5, 5], [6, 6]]);
    expect(selectionBounds(['downtown'], all, areas)).toBeNull();
  });
});
