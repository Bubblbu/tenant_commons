/**
 * Neighbourhood filter tags and the block legend, ported from layout.py
 * (legends_html). Fills the containers index.html left empty. Must run
 * before wiring.js starts: it queries .filter-neighbourhood-option once.
 */
import { LEGEND_LEFT_OFFSET } from './config';
import { escapeHtml, groupThousands } from './html';
import type { FilterConfig, NeighbourhoodSummary } from './types';

export function hoodTagsHtml(hoods: NeighbourhoodSummary[] | undefined): string {
  if (!hoods || hoods.length === 0) return '<em class="filter-none">No neighbourhood data</em>';
  return hoods
    .map((n) => {
      const name = String(n.name ?? '');
      const count = groupThousands(Math.trunc(Number(n.count) || 0));
      const units = groupThousands(Math.trunc(Number(n.units) || 0));
      return (
        `<label class="filter-tag"><input type="checkbox" class="filter-neighbourhood-option" ` +
        `value="${escapeHtml(name.toLowerCase())}" checked> ${escapeHtml(name)} ` +
        `<span class="filter-tag-count">(${count} bldgs · ${units} units)</span></label>`
      );
    })
    .join('');
}

export function blockLegendMax(fc: FilterConfig): number {
  const raw = fc.blocks_total_units_max ?? fc.blocks_member_building_max;
  const n = Math.trunc(Number(raw));
  return Number.isFinite(n) && n > 0 ? n : 0;
}

/** Six ticks, 0 to max. (Python used banker's rounding; wiring.js repaints these with Math.round at start-up anyway.) */
export function blockTicks(max: number): string[] {
  if (max === 0) return Array(6).fill('0');
  return [0, 0.2, 0.4, 0.6, 0.8, 1].map((f) => groupThousands(f === 1 ? max : Math.round(max * f)));
}

export function renderLegend(fc: FilterConfig, doc: Document = document): void {
  const hoods = doc.getElementById('filter-neighbourhoods');
  if (hoods) hoods.innerHTML = hoodTagsHtml(fc.neighbourhoods);
  const max = blockLegendMax(fc);
  const scale = doc.getElementById('block-legend-scale');
  if (scale) scale.innerHTML = blockTicks(max).map((t) => `<span>${escapeHtml(t)}</span>`).join('');
  const note = doc.getElementById('block-legend-note');
  if (note) note.textContent = `Color scaled to 0–${groupThousands(max)} units (visible blocks).`;
  const legend = doc.getElementById('legend-map');
  if (legend) legend.style.left = `${LEGEND_LEFT_OFFSET}px`;
}

const LEGEND_COLLAPSED_KEY = 'sica-legend-collapsed';

/** Whether the viewer previously collapsed the legend. Defaults to expanded if storage is unavailable (private browsing) or unset. */
function readStoredCollapsed(): boolean {
  try {
    return localStorage.getItem(LEGEND_COLLAPSED_KEY) === '1';
  } catch {
    return false;
  }
}

function writeStoredCollapsed(collapsed: boolean): void {
  try {
    if (collapsed) localStorage.setItem(LEGEND_COLLAPSED_KEY, '1');
    else localStorage.removeItem(LEGEND_COLLAPSED_KEY);
  } catch {
    // Storage blocked/unavailable: the toggle still works, it just won't be remembered.
  }
}

export function setLegendCollapsed(collapsed: boolean, doc: Document = document): void {
  const container = doc.getElementById('legend-map');
  const toggle = doc.getElementById('legend-toggle-btn');
  if (container) container.classList.toggle('collapsed', collapsed);
  if (toggle) toggle.setAttribute('aria-expanded', String(!collapsed));
}

/** Wires the legend's collapse toggle. Call once, after renderLegend(). */
export function initLegendToggle(doc: Document = document): void {
  const toggle = doc.getElementById('legend-toggle-btn');
  if (!toggle) return;
  setLegendCollapsed(readStoredCollapsed(), doc);
  toggle.addEventListener('click', () => {
    const collapsed = !doc.getElementById('legend-map')?.classList.contains('collapsed');
    setLegendCollapsed(collapsed, doc);
    writeStoredCollapsed(collapsed);
  });
}
