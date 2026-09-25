/**
 * Entry point: load the artifacts once, build the map, render the sidebar
 * rows and legend, then hand everything to wiring.js. Order matters —
 * wiring.js queries the table rows and neighbourhood filter inputs once, so
 * those render first.
 */
import 'leaflet/dist/leaflet.css';
// Folium's page loaded Bootstrap; the sidebar's font, box-sizing and spacing
// come from its reboot layer (no Bootstrap classes or JS are used).
import 'bootstrap/dist/css/bootstrap-reboot.min.css';
import './provenance.css';
import './popup.css';
import * as L from 'leaflet';
import { initAboutModal } from './about';
import { BASEMAPS, DEFAULT_BASEMAP, DEFAULT_CENTER, DEFAULT_ZOOM } from './config';
import { renderCoverage } from './coverage';
import { loadArtifacts } from './data';
import { initHoodUrlSync } from './hood-url';
import { buildOptions, initLandlordPicker, type LandlordFilter } from './landlord-picker';
import { areaBounds, selectionBounds } from './initial-view';
import {
  createBlocksLayer,
  createBoundaryRenderer,
  createBuildingLayers,
  createChinatownLayer,
  createNeighbourhoodsLayer,
  createVillagesLayer,
} from './layers';
import { initLegendToggle, renderLegend } from './legend';
import { markerStyle } from './markers';
import { renderPopup } from './popup';
import { initTipDismiss } from './provenance';
import { initClearButton } from './search-clear';
import { initTableSearch } from './table-search';
import { renderTables } from './tables';
import { initViewToggle } from './view-toggle';
import { startWiring } from './wiring.js';

function showLoadError(err: unknown): void {
  console.error('Failed to initialise the map', err);
  const el = document.createElement('div');
  el.id = 'load-error';
  el.textContent = `Map failed to load: ${err instanceof Error ? err.message : String(err)}`;
  document.body.appendChild(el);
}

async function main(): Promise<void> {
  const artifacts = await loadArtifacts();

  const map = L.map('map', { preferCanvas: true }).setView(DEFAULT_CENTER, DEFAULT_ZOOM);
  const basemap = BASEMAPS[DEFAULT_BASEMAP];
  L.tileLayer(basemap.tiles, { attribution: basemap.attribution }).addTo(map);
  if (basemap.labels) L.tileLayer(basemap.labels, { attribution: basemap.attribution }).addTo(map);

  // Blocks, then buildings, share the default canvas; boundaries draw in their own pane above both.
  const boundaryRenderer = createBoundaryRenderer(map);
  const blocks = createBlocksLayer(artifacts.blocks).addTo(map);
  const neighbourhoods = createNeighbourhoodsLayer(artifacts.boundaries, boundaryRenderer).addTo(map);
  const villages = createVillagesLayer(artifacts.villages, boundaryRenderer);
  const chinatown = createChinatownLayer(artifacts.chinatown, boundaryRenderer).addTo(map);
  const styled = artifacts.markers.map((m) => ({ ...m, ...markerStyle(m) }));
  const records = artifacts.buildingData.records;
  // Lazy: the markup is built on first open, from the one record the table and filters also read.
  const buildings = createBuildingLayers(styled, (marker, m) => {
    marker.bindPopup(
      () => renderPopup(records[String(m.b_id)] ?? { b_id: m.b_id }, { licenceYear: artifacts.filterConfig.licence_year ?? null }),
      { maxWidth: 320 },
    );
  });
  buildings.buildings.addTo(map);

  const b = artifacts.filterConfig.bounds;
  if (b) map.fitBounds([[b.lat_min, b.lon_min], [b.lat_max, b.lon_max]]);

  renderLegend(artifacts.filterConfig);
  initHoodUrlSync();
  // A ?hood= link that narrows the neighbourhoods opens framed on them.
  const hoodInputs = Array.from(document.querySelectorAll<HTMLInputElement>('.filter-neighbourhood-option'));
  const selected = selectionBounds(
    hoodInputs.filter((i) => i.checked).map((i) => i.value),
    hoodInputs.map((i) => i.value),
    areaBounds(artifacts.boundaries, artifacts.chinatown, artifacts.villages),
  );
  if (selected) map.fitBounds(selected, { padding: [20, 20] });
  initLegendToggle();
  initAboutModal(map);
  renderTables(artifacts.buildingData, artifacts.blocks, document, artifacts.filterConfig.licence_year ?? null);
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

  startWiring({
    map,
    layers: { blocks, buildings: buildings.buildings, neighbourhoods, villages, chinatown },
    markersById: buildings.markersById,
    ringsById: buildings.ringsById,
    filterConfig: artifacts.filterConfig,
    markers: styled,
    buildingData: artifacts.buildingData,
    landlordFilter,
    onFilter: (visibleBids) => renderCoverage([...visibleBids].map((bid) => records[bid]).filter((r) => r !== undefined)),
  });

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
}

main().catch(showLoadError);
