/**
 * Block choropleth and popup, ported from layout.py (add_blocks_layer) and
 * colors.py (greens_color). This is the initial paint only: wiring.js's
 * recomputeBlockColorScale() repaints every block against the visible
 * blocks' own range as soon as it starts.
 */
import type { PathOptions } from 'leaflet';
import { escapeHtml, groupThousands, isMissing, roundHalfEven } from './html';
import type { BlockProperties, BlocksCollection } from './types';
import { MAP_THEME } from './wiring/map-theme';

export function greensColor(s: number | null | undefined): string {
  const v = s === null || s === undefined ? 0 : Math.max(0, Math.min(Number(s), 1));
  if (v <= 0.1) return MAP_THEME.block.scale[0];
  if (v <= 0.25) return MAP_THEME.block.scale[1];
  if (v <= 0.5) return MAP_THEME.block.scale[2];
  if (v <= 0.75) return MAP_THEME.block.scale[3];
  if (v < 1.0) return MAP_THEME.block.scale[4];
  return MAP_THEME.block.scale[5];
}

export function maxTotalUnits(fc: BlocksCollection): number {
  let max = 0;
  for (const f of fc.features) {
    const units = Math.trunc(Number(f.properties?.total_units ?? 0)) || 0;
    if (units > max) max = units;
  }
  return max;
}

export function blockStyle(props: Partial<BlockProperties> | undefined, maxUnits: number): PathOptions {
  const buildings = Math.trunc(Number(props?.buildings ?? 0)) || 0;
  if (buildings <= 0) {
    // Empty blocks carry no data: transparent rather than painted into the scale.
    return { fillColor: 'transparent', color: MAP_THEME.block.stroke, weight: 1, fillOpacity: 0 };
  }
  const units = Number(props?.total_units ?? 0) || 0;
  const scaled = maxUnits > 0 ? Math.min(Math.max(units / maxUnits, 0), 1) : 0;
  return { fillColor: greensColor(scaled), color: MAP_THEME.block.stroke, weight: 1, fillOpacity: 0.7 };
}

const POPUP_FIELDS: [keyof BlockProperties, string][] = [
  ['block_label', 'Block'],
  ['buildings', 'Buildings'],
  ['total_units', '# Units'],
  ['median_year_built', 'Median year'],
];

function formatValue(field: keyof BlockProperties, value: unknown): string {
  if (isMissing(value)) return '';
  if (typeof value !== 'number') return String(value);
  // Folium's localize=True grouped years too ("1,965"); a year is not a quantity.
  // roundHalfEven matches tables.ts's rounding of the same field.
  if (field === 'median_year_built') return String(roundHalfEven(value));
  // en-US like the rest of the ported markup, not the browser's locale (a
  // German browser would render 1.234). Non-integers keep their decimals.
  return Number.isInteger(value) ? groupThousands(value) : value.toLocaleString('en-US');
}

/** The Folium GeoJsonPopup's content: one row per field, in the same order. */
export function blockPopupHtml(props: Partial<BlockProperties>): string {
  const rows = POPUP_FIELDS.map(
    ([field, alias]) => `<tr><th>${escapeHtml(alias)}</th><td>${escapeHtml(formatValue(field, props[field]))}</td></tr>`,
  ).join('');
  return `<table class="block-popup">${rows}</table>`;
}
