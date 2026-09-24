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

export const CHINATOWN_STYLE: PathOptions = { color: '#c0392b', weight: 2, opacity: 0.85, fill: false };
export const CHINATOWN_LABEL = 'Chinatown';

export function chinatownLabelHtml(name: string): string {
  return (
    '<div style="color:#c0392b;font-weight:700;font-size:11px;' +
    'text-shadow:-1px -1px 0 #fff,1px -1px 0 #fff,-1px 1px 0 #fff,1px 1px 0 #fff;' +
    'white-space:nowrap;pointer-events:none;">' +
    escapeHtml(name) +
    '</div>'
  );
}
