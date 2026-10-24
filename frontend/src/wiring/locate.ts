/**
 * The locate button in each Buildings-table row: centre the map on the
 * building at street level and open its popup. Selection (the row checkbox)
 * and hover are untouched. On phones the sidebar drawer covers the map, so it
 * closes first. Deep links (deep-link.ts) focus a building the same way.
 */
import type L from 'leaflet';
import type { MapIndex } from './types';

/** Street level: close enough to tell neighbouring buildings apart. */
export const LOCATE_ZOOM = 17;

/** Uncovers the map: the mobile drawers (display.ts initMobilePanels) cover it. */
export function closeDrawers(doc: Document = document): void {
  ['sidebar-container', 'filters-panel'].forEach((id) => doc.getElementById(id)?.classList.remove('open'));
  ['mobile-toggle-sidebar', 'mobile-toggle-filters'].forEach((id) =>
    doc.getElementById(id)?.setAttribute('aria-expanded', 'false'));
}

/** Street-level view of one building with its popup open; also used by deep links (deep-link.ts). */
export function focusMarker(marker: L.CircleMarker, map: L.Map, doc: Document = document): void {
  // No marker is drawn while Show on map > Buildings is off.
  const showBuildings = doc.getElementById('viz-show-buildings') as HTMLInputElement | null;
  if (showBuildings && !showBuildings.checked) {
    showBuildings.checked = true;
    showBuildings.dispatchEvent(new Event('change', { bubbles: true }));
  }
  closeDrawers(doc);
  map.setView(marker.getLatLng(), Math.max(map.getZoom(), LOCATE_ZOOM));
  marker.openPopup();
}

export function initLocate(index: MapIndex, map: L.Map, doc: Document = document): void {
  doc.addEventListener('click', (event) => {
    const btn = (event.target as Element | null)?.closest?.('.locate-btn') as HTMLElement | null;
    const marker = btn ? index.buildings[btn.dataset.locate ?? ''] : undefined;
    if (!btn || !marker) return;
    event.preventDefault();
    focusMarker(marker, map, doc);
  });
}
