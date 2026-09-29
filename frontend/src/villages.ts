/**
 * City of Vancouver "Village Plan Area" outlines and name labels — a static
 * reference overlay, styled and shaped like neighbourhoods.ts's boundary
 * layer but visually distinct (neighbourhoods already uses solid orange,
 * the color the source reference map itself used for villages).
 */
import type { PathOptions } from 'leaflet';
import { escapeHtml } from './html';
import { MAP_THEME } from './wiring/map-theme';

export const VILLAGE_STYLE: PathOptions = { color: MAP_THEME.boundary.villages, weight: 2, opacity: 0.85, fill: false, dashArray: '6 4' };

export function villageLabelHtml(name: string): string {
  const c = MAP_THEME.boundary.villages;
  const halo = MAP_THEME.boundary.labelHalo;
  return (
    `<div style="color:${c};font-weight:700;font-size:11px;` +
    `text-shadow:-1px -1px 0 ${halo},1px -1px 0 ${halo},-1px 1px 0 ${halo},1px 1px 0 ${halo};` +
    'white-space:nowrap;pointer-events:none;">' +
    escapeHtml(name) +
    '</div>'
  );
}
