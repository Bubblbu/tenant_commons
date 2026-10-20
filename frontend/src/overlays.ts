/**
 * Overlay areas — config.toml's [[overlay_areas]] (Chinatown, DEOD, the
 * Village Plan Areas): outlines and labels from overlay_areas.geojson, one
 * Show on map toggle and legend row each. Which areas exist, their names
 * and order come from filter_config.json's special_areas; how each is drawn
 * lives here, so an area added in config.toml shows up with a fallback
 * colour and no frontend change.
 */
import type { PathOptions } from 'leaflet';
import { escapeHtml } from './html';
import type { SpecialAreaSummary } from './types';
import { MAP_THEME } from './wiring/map-theme';

export interface OverlayLook {
  color: string;
  dashed: boolean;
  /** Ticked in Show on map at start-up (and after Reset). */
  shown: boolean;
}

/** Areas drawn other than solid and shown at start-up. */
const LOOKS: Record<string, Partial<OverlayLook>> = {
  // Hand-traced and citywide: dashed, and off until asked for.
  'village-plan': { dashed: true, shown: false },
};

/** `index` is the area's position in special_areas, for a stable fallback colour. */
export function overlayLook(key: string, index: number): OverlayLook {
  const themed = (MAP_THEME.boundary.overlays as Record<string, string>)[key];
  const fallback = MAP_THEME.boundary.overlayFallback;
  return { color: themed ?? fallback[index % fallback.length], dashed: false, shown: true, ...LOOKS[key] };
}

export function overlayPathOptions(look: OverlayLook): PathOptions {
  return { color: look.color, weight: 2, opacity: 0.85, fill: false, ...(look.dashed ? { dashArray: '6 4' } : {}) };
}

export function overlayLabelHtml(name: string, color: string): string {
  const halo = MAP_THEME.boundary.labelHalo;
  return (
    `<div style="color:${color};font-weight:700;font-size:11px;` +
    `text-shadow:-1px -1px 0 ${halo},1px -1px 0 ${halo},-1px 1px 0 ${halo},1px 1px 0 ${halo};` +
    'white-space:nowrap;pointer-events:none;">' +
    escapeHtml(name) +
    '</div>'
  );
}

/** Only areas with an outline to draw get a toggle or a legend row. */
const drawn = (areas: SpecialAreaSummary[] | undefined, drawable: Set<string>) =>
  (areas ?? []).map((a, i) => ({ a, look: overlayLook(a.key, i) })).filter(({ a }) => drawable.has(a.key));

/** Show on map checkboxes, indented under Neighbourhood boundaries. */
export function overlayTogglesHtml(areas: SpecialAreaSummary[] | undefined, drawable: Set<string>): string {
  return drawn(areas, drawable)
    .map(({ a, look }) =>
      `<label><input type="checkbox" class="viz-show-overlay" data-area="${escapeHtml(a.key)}"` +
      `${look.shown ? ' checked' : ''}> ${escapeHtml(a.name)}</label>`)
    .join('');
}

export function overlayLegendRowsHtml(areas: SpecialAreaSummary[] | undefined, drawable: Set<string>): string {
  return drawn(areas, drawable)
    .map(({ a, look }) =>
      `<div class="legend-key-row"><span class="legend-swatch" style="background:transparent;` +
      `border:2px ${look.dashed ? 'dashed' : 'solid'} ${look.color};"></span> ${escapeHtml(a.name)}</div>`)
    .join('');
}
