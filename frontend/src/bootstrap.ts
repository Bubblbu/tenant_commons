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
import * as L from 'leaflet';
import { BASEMAPS, DEFAULT_BASEMAP, DEFAULT_CENTER, DEFAULT_ZOOM } from './config';
import { loadArtifacts } from './data';
import { createBlocksLayer, createBuildingLayers, createNeighbourhoodsLayer } from './layers';
import { renderLegend } from './legend';
import { markerStyle } from './markers';
import { renderTables } from './tables';
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

  // Same order Folium added them: blocks, neighbourhoods, then buildings.
  const blocks = createBlocksLayer(artifacts.blocks).addTo(map);
  const neighbourhoods = createNeighbourhoodsLayer(artifacts.boundaries).addTo(map);
  const styled = artifacts.markers.map((m) => ({ ...m, ...markerStyle(m) }));
  const buildings = createBuildingLayers(styled);
  buildings.non.addTo(map);
  buildings.vtu.addTo(map);

  const b = artifacts.filterConfig.bounds;
  if (b) map.fitBounds([[b.lat_min, b.lon_min], [b.lat_max, b.lon_max]]);

  renderLegend(artifacts.filterConfig);
  renderTables(artifacts.buildingData, artifacts.blocks);

  startWiring({
    map,
    layers: { blocks, vtu: buildings.vtu, non: buildings.non, neighbourhoods },
    markersById: buildings.markersById,
    ringsById: buildings.ringsById,
    filterConfig: artifacts.filterConfig,
    markers: styled,
    buildingData: artifacts.buildingData,
  });
}

main().catch(showLoadError);
