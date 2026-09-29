/**
 * The Chinatown boundary already used by tc_core.prepare.properties to flag
 * buildings (data/curated/chinatown_boundary.geojson) — reused, unmodified,
 * as a second map reference overlay. Styled and shaped like villages.ts's
 * layer, but the source file carries no `name` property (a single
 * unlabelled polygon), so the label is fixed rather than read off the
 * feature.
 */
import type { PathOptions } from 'leaflet';
import { escapeHtml } from './html';
import { MAP_THEME } from './wiring/map-theme';

export const CHINATOWN_STYLE: PathOptions = { color: MAP_THEME.boundary.chinatown, weight: 2, opacity: 0.85, fill: false };
export const CHINATOWN_LABEL = 'Chinatown';

export function chinatownLabelHtml(name: string): string {
  const c = MAP_THEME.boundary.chinatown;
  const halo = MAP_THEME.boundary.labelHalo;
  return (
    `<div style="color:${c};font-weight:700;font-size:11px;` +
    `text-shadow:-1px -1px 0 ${halo},1px -1px 0 ${halo},-1px 1px 0 ${halo},1px 1px 0 ${halo};` +
    'white-space:nowrap;pointer-events:none;">' +
    escapeHtml(name) +
    '</div>'
  );
}
