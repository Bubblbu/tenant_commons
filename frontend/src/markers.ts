/**
 * Marker styling, ported from sica_mapping/frontend/layout.py
 * (marker_radius, add_buildings_layers). Presentation, so it lives here: the
 * artifacts carry the data (units, housing_type), not the styling.
 * Field names match what wiring.js's applyMarkerMetadata() reads.
 */
import type { MarkerRecord } from './types';

const NEUTRAL_COLOR = '#9e9e9e';
const COOP_RING_COLOR = '#d97706';
const SRO_RING_COLOR = '#3182bd';
const RING_STROKE_WEIGHT = 2.2;
const DEFAULT_STROKE_COLOR = '#ffffff';
const DEFAULT_STROKE_WEIGHT = 0.6;

/** Extra rings (dual-type buildings): each one this much wider than the last. */
export const RING_SPACING = 3.0;
export const RING_WEIGHT = 2.0;
export const RING_OPACITY = 0.9;

export type HousingType = 'coop' | 'sro';

export interface MarkerStyle {
  base_color: string;
  base_opacity: number;
  base_radius: number;
  stroke_color: string;
  stroke_weight: number;
  primary_housing_type: HousingType | '';
  extra_rings: { housing_type: HousingType }[];
}

export type StyledMarker = MarkerRecord & MarkerStyle;

/** Log-scaled by units, capped at 600; 3.2 for missing or non-positive values. */
export function markerRadius(units: number | null | undefined): number {
  if (units === null || units === undefined || !Number.isFinite(units) || units <= 0) return 3.2;
  const capped = Math.min(Math.max(units, 1), 600);
  return 2.5 + 7.0 * (Math.log1p(capped) / Math.log1p(600));
}

/** "co-op, sro" -> ['coop', 'sro']. Co-op first: the first type owns the stroke. */
export function housingTypes(housingType: string): HousingType[] {
  const parts = housingType.split(',').map((p) => p.trim());
  const types: HousingType[] = [];
  if (parts.includes('co-op')) types.push('coop');
  if (parts.includes('sro')) types.push('sro');
  return types;
}

export function ringColor(t: HousingType): string {
  return t === 'coop' ? COOP_RING_COLOR : SRO_RING_COLOR;
}

export function markerStyle(r: MarkerRecord): MarkerStyle {
  const types = housingTypes(r.housing_type ?? '');
  return {
    base_color: NEUTRAL_COLOR,
    base_opacity: 0.6,
    base_radius: markerRadius(r.units),
    stroke_color: types.length ? ringColor(types[0]) : DEFAULT_STROKE_COLOR,
    stroke_weight: types.length ? RING_STROKE_WEIGHT : DEFAULT_STROKE_WEIGHT,
    primary_housing_type: types[0] ?? '',
    extra_rings: types.slice(1).map((t) => ({ housing_type: t })),
  };
}
