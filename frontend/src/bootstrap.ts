/**
 * Entry point: load the artifacts once, build the map, render the sidebar
 * rows and legend, then hand everything to wiring. Order matters —
 * wiring queries the table rows and neighbourhood filter inputs once, so
 * those render first. The basemap and boundaries draw as soon as their own
 * artifacts arrive; blocks, buildings and the panels (inert under
 * body.loading) wait for the building records.
 */
import 'leaflet/dist/leaflet.css';
// Folium's page loaded Bootstrap; the sidebar's font, box-sizing and spacing
// come from its reboot layer (no Bootstrap classes or JS are used).
import 'bootstrap/dist/css/bootstrap-reboot.min.css';
import './provenance.css';
import './popup.css';
import * as L from 'leaflet';
import { initAboutModal } from './about';
import { initDisplayOptions } from './display-options';
import { BASEMAPS, DEFAULT_BASEMAP, DEFAULT_CENTER, DEFAULT_ZOOM, MAX_ZOOM } from './config';
import { renderCoverage } from './coverage';
import { loadBuildingArtifacts, loadMapArtifacts } from './data';
import { initDeepLinks } from './deep-link';
import { buildOptions, initLandlordPicker, type LandlordFilter } from './landlord-picker';
import { areaBounds, selectionBounds } from './initial-view';
import {
  createBlocksLayer,
  createBoundaryRenderer,
  createBuildingLayers,
  createNeighbourhoodsLayer,
  createOverlayLayers,
} from './layers';
import { initLegendToggle, renderLegend } from './legend';
import { markerStyle } from './markers';
import { overlayLook } from './overlays';
import { initPopupTabs, renderPopup } from './popup/index';
import { belowPopup } from './popup/below';
import { initTipDismiss } from './provenance';
import { applyStoredWidths, pagePanes } from './pane-resize';
import { initClearButton } from './search-clear';
import { initTableSearch } from './table-search';
import { renderTables } from './tables';
import { initViewToggle } from './view-toggle';
import { startWiring } from './wiring';
import { decodeFilterState, encodeFilterState } from './wiring/filter-state';

function showLoadError(err: unknown): void {
  console.error('Failed to initialise the map', err);
  const el = document.createElement('div');
  el.id = 'load-error';
  el.textContent = `Map failed to load: ${err instanceof Error ? err.message : String(err)}`;
  document.body.appendChild(el);
}

async function main(): Promise<void> {
  // Both fetches start now; only the map's own files gate its first paint.
  const mapLoad = loadMapArtifacts();
  const buildingLoad = loadBuildingArtifacts();
  // A rejection before it is awaited would otherwise go unhandled.
  buildingLoad.catch(() => {});
  const artifacts = await mapLoad;
  document.body.classList.add('loading');
  // Before the map exists, so a remembered panel width doesn't resize (and
  // re-centre) it once the rest of the page is wired.
  const panes = pagePanes(document);
  if (panes) applyStoredWidths(panes);

  const map = L.map('map', { preferCanvas: true, maxZoom: MAX_ZOOM }).setView(DEFAULT_CENTER, DEFAULT_ZOOM);
  const basemap = BASEMAPS[DEFAULT_BASEMAP];
  L.tileLayer(basemap.tiles, {
    attribution: basemap.attribution,
    maxZoom: MAX_ZOOM,
    maxNativeZoom: basemap.maxNativeZoom,
  }).addTo(map);
  if (basemap.labels) L.tileLayer(basemap.labels, { attribution: basemap.attribution, maxZoom: MAX_ZOOM }).addTo(map);

  // Blocks, then buildings, share the default canvas; boundaries draw in their own pane above both.
  // Blocks and buildings go on the map with startWiring(), in the same task:
  // until it styles them they would paint every ring and an unscaled fill.
  const boundaryRenderer = createBoundaryRenderer(map);
  const blocks = createBlocksLayer(artifacts.blocks);
  const neighbourhoods = createNeighbourhoodsLayer(artifacts.boundaries, boundaryRenderer).addTo(map);
  const specialAreas = artifacts.filterConfig.special_areas;
  const overlays = createOverlayLayers(artifacts.overlays, specialAreas, boundaryRenderer);
  // Shown-by-default ones now; startWiring() then follows the Show on map toggles.
  (specialAreas ?? []).forEach((a, i) => {
    if (overlays[a.key] && overlayLook(a.key, i).shown) overlays[a.key].addTo(map);
  });

  renderLegend(artifacts.filterConfig, document, new Set(Object.keys(overlays)));
  const hoodValues = Array.from(document.querySelectorAll<HTMLInputElement>('.filter-neighbourhood-option')).map((i) => i.value);
  const restored = decodeFilterState(new URLSearchParams(window.location.search), hoodValues);
  // A ?hood= link that narrows the neighbourhoods opens framed on them.
  const selected = selectionBounds(restored.hoods ?? [], hoodValues, areaBounds(artifacts.boundaries, artifacts.overlays));
  // One call, and animate: false — an animated fitBounds this early races
  // watchMap()'s own start-up invalidateSize() (wiring/status-export.ts) and
  // can settle on the wrong center/zoom; there's no prior view worth
  // animating from anyway.
  const b = artifacts.filterConfig.bounds;
  if (selected) {
    map.fitBounds(selected, { padding: [20, 20], animate: false });
  } else if (b) {
    map.fitBounds([[b.lat_min, b.lon_min], [b.lat_max, b.lon_max]], { animate: false });
  }
  initLegendToggle();
  initAboutModal(map);

  const loaded = await buildingLoad;
  const styled = artifacts.markers.map((m) => ({ ...m, ...markerStyle(m) }));
  const popupCtx = {
    networks: loaded.networks,
    licenceYear: artifacts.filterConfig.licence_year ?? null,
    landShareMedian: artifacts.filterConfig.land_share_median ?? null,
  };
  // Lazy: the markup is built on first open, from the building as published.
  const buildings = createBuildingLayers(styled, (marker, m) => {
    // Below the pin, so switching tabs moves only the popup's bottom edge.
    marker.bindPopup(belowPopup({ maxWidth: 320 }).setContent(() => {
      const b = loaded.buildings[String(m.b_id)];
      return b ? renderPopup(b, popupCtx) : '';
    }));
  });
  initPopupTabs(document);
  // The flat view: the landlord picker and coverage panel read it too.
  const records = loaded.buildingData.records;
  renderTables(loaded.buildingData, document, artifacts.filterConfig.licence_year ?? null);
  initTipDismiss();

  const ownerSearch = document.getElementById('owner-search');
  const ownerSearchClear = document.getElementById('owner-search-clear');
  const ownerTiles = document.getElementById('owner-tiles');
  const ownerSuggestions = document.getElementById('owner-suggestions');
  let landlordFilter: LandlordFilter | undefined;
  if (ownerSearch instanceof HTMLInputElement && ownerTiles && ownerSuggestions) {
    landlordFilter = initLandlordPicker(buildOptions(Object.values(records)), {
      input: ownerSearch, tiles: ownerTiles, list: ownerSuggestions,
    });
    if (ownerSearchClear) initClearButton(ownerSearch, ownerSearchClear);
  }

  blocks.addTo(map);
  buildings.buildings.addTo(map);
  startWiring({
    map,
    layers: { blocks, buildings: buildings.buildings, neighbourhoods, overlays },
    markersById: buildings.markersById,
    ringsById: buildings.ringsById,
    filterConfig: artifacts.filterConfig,
    markers: styled,
    buildingData: loaded.buildingData,
    landlordFilter,
    onFilter: (visibleBids) => renderCoverage([...visibleBids].map((bid) => records[bid]).filter((r) => r !== undefined)),
    initialFilter: restored,
    onStateChange: (state) => {
      const url = new URL(window.location.href);
      encodeFilterState(state, url.searchParams, hoodValues);
      // Only when it changed: this runs on every slider frame, and Safari
      // throws after 100 replaceState calls in 30 seconds.
      if (url.href !== window.location.href) window.history.replaceState(window.history.state, '', url);
    },
  });

  initDisplayOptions();
  // After wiring, so a linked building's popup opens on a styled, filtered map.
  initDeepLinks({ map, records: loaded.buildings, markersById: buildings.markersById });

  const landlordViews = ['networks', 'owners'].map((v) => ({
    button: document.getElementById(`landlord-view-${v}`),
    panel: document.getElementById(`${v}-panel`),
  }));
  if (landlordViews.every((o) => o.button && o.panel)) {
    initViewToggle(landlordViews as { button: HTMLElement; panel: HTMLElement }[]);
  }

  const tableSearch = document.getElementById('table-search');
  const tableSearchClear = document.getElementById('table-search-clear');
  if (tableSearch instanceof HTMLInputElement) {
    const tables = Array.from(document.querySelectorAll<HTMLTableElement>('#sidebar-content table.data'));
    initTableSearch(tableSearch, tables);
    if (tableSearchClear) initClearButton(tableSearch, tableSearchClear);
  }
  document.body.classList.remove('loading');
}

main().catch(showLoadError);
