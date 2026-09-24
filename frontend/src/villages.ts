/**
 * City of Vancouver "Village Plan Area" outlines and name labels — a static
 * reference overlay, styled and shaped like neighbourhoods.ts's boundary
 * layer but visually distinct (neighbourhoods already uses solid orange,
 * the color the source reference map itself used for villages).
 */
import type { PathOptions } from 'leaflet';
import { escapeHtml } from './html';

export const VILLAGE_STYLE: PathOptions = { color: '#7b3fa0', weight: 2, opacity: 0.85, fill: false, dashArray: '6 4' };

export function villageLabelHtml(name: string): string {
  return (
    '<div style="color:#7b3fa0;font-weight:700;font-size:11px;' +
    'text-shadow:-1px -1px 0 #fff,1px -1px 0 #fff,-1px 1px 0 #fff,1px 1px 0 #fff;' +
    'white-space:nowrap;pointer-events:none;">' +
    escapeHtml(name) +
    '</div>'
  );
}
