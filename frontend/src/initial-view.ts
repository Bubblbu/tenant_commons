/**
 * Where the map opens. A `?hood=` link that narrows Filters > Neighbourhoods
 * (e.g. just Chinatown) should open framed on those areas, not the whole
 * city. Pure: bounds are plain [[south, west], [north, east]] pairs, handed
 * to Leaflet's fitBounds by bootstrap.ts.
 */
import type { Geometry, Position } from 'geojson';
import type { BoundaryCollection } from './types';

export type LatLonBounds = [[number, number], [number, number]];

function extend(b: LatLonBounds | null, lat: number, lon: number): LatLonBounds {
  if (!b) return [[lat, lon], [lat, lon]];
  return [[Math.min(b[0][0], lat), Math.min(b[0][1], lon)], [Math.max(b[1][0], lat), Math.max(b[1][1], lon)]];
}

function union(a: LatLonBounds | null, b: LatLonBounds | null): LatLonBounds | null {
  if (!a || !b) return a ?? b;
  return extend(extend(a, b[0][0], b[0][1]), b[1][0], b[1][1]);
}

function positions(g: Geometry): Position[] {
  switch (g.type) {
    case 'Point': return [g.coordinates];
    case 'MultiPoint': case 'LineString': return g.coordinates;
    case 'MultiLineString': case 'Polygon': return g.coordinates.flat();
    case 'MultiPolygon': return g.coordinates.flat(2);
    case 'GeometryCollection': return g.geometries.flatMap(positions);
  }
}

/** Bounding box of a GeoJSON geometry (GeoJSON is [lon, lat]), or null if it has no coordinates. */
export function geometryBounds(g: Geometry | null | undefined): LatLonBounds | null {
  if (!g) return null;
  let b: LatLonBounds | null = null;
  for (const [lon, lat] of positions(g)) b = extend(b, lat, lon);
  return b;
}

function collectionBounds(fc: BoundaryCollection): LatLonBounds | null {
  return fc.features.reduce<LatLonBounds | null>((b, f) => union(b, geometryBounds(f.geometry)), null);
}

/**
 * Bounds per Filters > Neighbourhoods value: each neighbourhood by its
 * lowercased name (as legend.ts writes the checkbox values), plus the two
 * special areas under their filter keys.
 */
export function areaBounds(
  neighbourhoods: BoundaryCollection,
  chinatown: BoundaryCollection,
  villages: BoundaryCollection,
): Map<string, LatLonBounds> {
  const out = new Map<string, LatLonBounds>();
  for (const f of neighbourhoods.features) {
    const key = String(f.properties?.name ?? '').trim().toLowerCase();
    const b = geometryBounds(f.geometry);
    if (key && b) out.set(key, union(out.get(key) ?? null, b)!);
  }
  const ct = collectionBounds(chinatown);
  if (ct) out.set('chinatown', ct);
  const vp = collectionBounds(villages);
  if (vp) out.set('village-plan', vp);
  return out;
}

/**
 * Bounds to open on for the checked areas, or null to keep the default
 * citywide view: when everything (or nothing) is checked, or none of the
 * checked areas has a known boundary.
 */
export function selectionBounds(checked: string[], all: string[], areas: Map<string, LatLonBounds>): LatLonBounds | null {
  if (checked.length === 0 || checked.length === all.length) return null;
  return checked.reduce<LatLonBounds | null>((b, key) => union(b, areas.get(key) ?? null), null);
}
