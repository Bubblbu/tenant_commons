/** Every Leaflet constructor lives here (and in bootstrap.ts); the modules it uses are pure and unit-tested. */
import * as L from 'leaflet';
import { blockPopupHtml, blockStyle, maxTotalUnits } from './blocks';
import { RING_OPACITY, RING_SPACING, RING_WEIGHT, ringColor, type StyledMarker } from './markers';
import { NEIGHBOURHOOD_STYLE, labelPosition, neighbourhoodLabelHtml } from './neighbourhoods';
import type { BlocksCollection, BoundaryCollection } from './types';

export function createBlocksLayer(fc: BlocksCollection): L.GeoJSON {
  const maxUnits = maxTotalUnits(fc);
  return L.geoJSON(fc, {
    style: (feature) => blockStyle(feature?.properties, maxUnits),
    onEachFeature: (feature, layer) => {
      layer.bindPopup(() => blockPopupHtml(feature.properties ?? {}));
    },
  });
}

export function createNeighbourhoodsLayer(fc: BoundaryCollection): L.FeatureGroup {
  const group = L.featureGroup();
  for (const feature of fc.features) {
    const outline = L.geoJSON(feature, { style: () => NEIGHBOURHOOD_STYLE }).addTo(group);
    const centre = outline.getBounds().getCenter();
    L.marker(labelPosition(feature.properties, [centre.lat, centre.lng]), {
      // className 'empty', as Folium's DivIcon: no default white box.
      icon: L.divIcon({ html: neighbourhoodLabelHtml(String(feature.properties?.name ?? '')), iconSize: [0, 0], className: 'empty' }),
      interactive: false,
      keyboard: false,
    }).addTo(group);
  }
  return group;
}

export interface BuildingLayers {
  buildings: L.FeatureGroup;
  markersById: Record<string, L.CircleMarker>;
  ringsById: Record<string, { housing_type: string; marker: L.CircleMarker }[]>;
}

/**
 * One group for every building marker. Markers go into the group first; the
 * caller adds it to the map afterwards.
 */
export function createBuildingLayers(
  markers: StyledMarker[],
  bindPopup?: (marker: L.CircleMarker, m: StyledMarker) => void,
): BuildingLayers {
  const buildings = L.featureGroup();
  const markersById: BuildingLayers['markersById'] = {};
  const ringsById: BuildingLayers['ringsById'] = {};
  for (const m of markers) {
    if (m.lat === null || m.lon === null) continue;
    const key = String(m.b_id);
    // Extra rings first, so they paint underneath the building as a halo.
    const rings = m.extra_rings.map((ring, i) => {
      const marker = L.circleMarker([m.lat as number, m.lon as number], {
        radius: m.base_radius + RING_SPACING * (i + 1),
        fill: false,
        color: ringColor(ring.housing_type),
        weight: RING_WEIGHT,
        opacity: RING_OPACITY,
      });
      buildings.addLayer(marker);
      return { housing_type: ring.housing_type, marker };
    });
    if (rings.length) ringsById[key] = rings;
    const marker = L.circleMarker([m.lat, m.lon], {
      radius: m.base_radius,
      fill: true,
      fillOpacity: m.base_opacity,
      color: m.stroke_color,
      weight: m.stroke_weight,
      fillColor: m.base_color,
    });
    bindPopup?.(marker, m);
    buildings.addLayer(marker);
    markersById[key] = marker;
  }
  return { buildings, markersById, ringsById };
}
