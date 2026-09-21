/**
 * Neighbourhood outlines and name labels, ported from layout.py
 * (add_neighbourhoods_layer). Folium placed labels at a shapely centroid;
 * this uses the City's own geo_point_2d when present, so positions can
 * differ slightly.
 */
import type { PathOptions } from 'leaflet';
import { escapeHtml } from './html';
import type { BoundaryProperties } from './types';

export const NEIGHBOURHOOD_STYLE: PathOptions = { color: '#ff8c00', weight: 2, opacity: 0.9, fill: false };

export function neighbourhoodLabelHtml(name: string): string {
  return (
    '<div style="color:#ff8c00;font-weight:700;font-size:12px;' +
    'text-shadow:-1px -1px 0 #fff,1px -1px 0 #fff,-1px 1px 0 #fff,1px 1px 0 #fff;' +
    'white-space:nowrap;pointer-events:none;">' +
    escapeHtml(name) +
    '</div>'
  );
}

export function labelPosition(
  props: BoundaryProperties | null | undefined,
  fallback: [number, number],
): [number, number] {
  const p = props?.geo_point_2d;
  return p && Number.isFinite(p.lat) && Number.isFinite(p.lon) ? [p.lat, p.lon] : fallback;
}
