import { groupKey } from '../tables';
import { MAP_THEME } from './map-theme';
import type { BlockLayer, BuildingMarker, MapIndex, WiringContext } from './types';

/**
 * Lookup tables built once at start-up from the map's live layers and the
 * loaded marker metadata (formerly window.blocksIndex/buildingIndex/etc.).
 */
export function buildMapIndex(ctx: WiringContext): MapIndex {
  const layerBlocks = ctx.layers.blocks;
  if (!layerBlocks || typeof layerBlocks.eachLayer !== 'function') {
    throw new Error('Blocks layer not ready');
  }

  const blocks: Record<string, BlockLayer> = {};
  const blockLayers: BlockLayer[] = [];
  layerBlocks.eachLayer((layer) => {
    const l = layer as unknown as BlockLayer;
    if (l && l.feature && l.feature.properties) {
      const props = l.feature.properties || {};
      const rawId = props.block_id;
      if (rawId === undefined || rawId === null) return;
      const id = String(rawId);
      blocks[id] = l;
      l._selectionRefs = 0;
      l._isFiltered = false;
      let unitTotal = Number(props.total_units);
      if (!Number.isFinite(unitTotal)) unitTotal = 0;
      l._blockUnits = unitTotal;
      const buildingCount = Number(props.buildings);
      l._blockBuildings = Number.isFinite(buildingCount) ? buildingCount : 0;
      blockLayers.push(l);
    }
  });

  const buildings: Record<string, BuildingMarker> = {};
  const blockBuildings: Record<string, string[]> = {};
  const owners: Record<string, BuildingMarker[]> = {};
  const networks: Record<string, BuildingMarker[]> = {};
  const hoods: Record<string, BuildingMarker[]> = {};

  const markerMetadata = Array.isArray(ctx.markers) ? ctx.markers : [];
  markerMetadata.forEach((meta) => {
    if (!meta) return;
    const marker = ctx.markersById[String(meta.b_id)] as BuildingMarker | undefined;
    if (!marker) return;

    const key = String(meta.b_id);
    buildings[key] = marker;

    marker._baseColor = (typeof meta.base_color === 'string' && meta.base_color) || marker._baseColor || (marker.options && marker.options.fillColor) || MAP_THEME.marker.fill;
    marker._baseOpacity = (typeof meta.base_opacity === 'number') ? meta.base_opacity : (marker._baseOpacity || (marker.options && marker.options.fillOpacity) || 0.35);
    marker._baseRadius = (typeof meta.base_radius === 'number') ? meta.base_radius : (marker._baseRadius || (marker.options && marker.options.radius) || 6);
    marker._selectionRefs = 0;
    marker._isFiltered = false;
    if (!marker.options) marker.options = {};
    (marker.options as Record<string, unknown>).base_color = marker._baseColor;
    const unitsMeta = Number(meta.units);
    marker._units = Number.isFinite(unitsMeta) ? unitsMeta : 0;
    const yearMeta = Number(meta.year_built);
    marker._yearBuilt = Number.isFinite(yearMeta) ? yearMeta : null;

    // Housing-type ring bookkeeping — see data.overlays.match_overlays
    // and add_buildings_layers in layout.py.
    marker._strokeColor = (typeof meta.stroke_color === 'string' && meta.stroke_color) || marker._strokeColor || MAP_THEME.marker.stroke;
    marker._strokeWeight = (typeof meta.stroke_weight === 'number') ? meta.stroke_weight : (marker._strokeWeight || MAP_THEME.marker.strokeWeight);
    marker._housingType = meta.housing_type || '';
    marker._primaryHousingType = meta.primary_housing_type || '';
    marker._extraRings = null;
    const rings = ctx.ringsById[String(meta.b_id)];
    if (rings && rings.length) {
      marker._extraRings = rings.map((r) => ({ housingType: r.housing_type, marker: r.marker }));
    }

    // Keyed as the landlord tables group them, so a "searched, no registry
    // filing" row selects its own buildings and not the other not-on-record ones.
    const rec = ctx.buildingData?.records[key];
    const grouped = (k: string | null) => (k && rec ? groupKey(k, rec) : k);
    const ownerKey = grouped(meta.owner_key);
    if (ownerKey) {
      if (!owners[ownerKey]) owners[ownerKey] = [];
      if (owners[ownerKey].indexOf(marker) === -1) owners[ownerKey].push(marker);
    }

    const networkKey = grouped(meta.network_key);
    if (networkKey) {
      if (!networks[networkKey]) networks[networkKey] = [];
      if (networks[networkKey].indexOf(marker) === -1) networks[networkKey].push(marker);
    }

    const hoodKey = String(meta.local_area || '').toLowerCase().trim();
    if (hoodKey) {
      if (!hoods[hoodKey]) hoods[hoodKey] = [];
      if (hoods[hoodKey].indexOf(marker) === -1) hoods[hoodKey].push(marker);
    }

    if (meta.block_id !== undefined && meta.block_id !== null) {
      const blockKey = String(meta.block_id);
      if (!blockBuildings[blockKey]) blockBuildings[blockKey] = [];
      if (blockBuildings[blockKey].indexOf(key) === -1) blockBuildings[blockKey].push(key);
    }
  });

  if (!Object.keys(buildings).length) {
    throw new Error('Building markers not ready');
  }

  return { buildings, blocks, blockLayers, blockBuildings, owners, networks, hoods };
}
