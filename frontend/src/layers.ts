/** Every Leaflet constructor lives here (and in bootstrap.ts); the modules it uses are pure and unit-tested. */
import type { PathOptions } from 'leaflet';
import * as L from 'leaflet';
import { blockPopupHtml, blockStyle, maxTotalUnits } from './blocks';
import { CHINATOWN_LABEL, CHINATOWN_STYLE, chinatownLabelHtml } from './chinatown';
import { RING_OPACITY, RING_SPACING, RING_WEIGHT, ringColor, type StyledMarker } from './markers';
import { NEIGHBOURHOOD_STYLE, labelPosition, neighbourhoodLabelHtml } from './neighbourhoods';
import type { BlocksCollection, BoundaryCollection, BoundaryProperties, VillagesCollection } from './types';
import { VILLAGE_STYLE, villageLabelHtml } from './villages';

export function createBlocksLayer(fc: BlocksCollection): L.GeoJSON {
  const maxUnits = maxTotalUnits(fc);
  return L.geoJSON(fc, {
    style: (feature) => blockStyle(feature?.properties, maxUnits),
    onEachFeature: (feature, layer) => {
      layer.bindPopup(() => blockPopupHtml(feature.properties ?? {}));
    },
  });
}

/**
 * One outline + one name label per feature — the shape shared by
 * neighbourhoods, villages and the Chinatown boundary. `labelName` picks
 * the label text off each feature's properties (or ignores them, for a
 * fixed label like Chinatown's).
 */
function createBoundaryLayer(
  fc: BoundaryCollection,
  style: PathOptions,
  labelHtml: (name: string) => string,
  labelName: (props: BoundaryProperties | null | undefined) => string,
): L.FeatureGroup {
  const group = L.featureGroup();
  for (const feature of fc.features) {
    const outline = L.geoJSON(feature, { style: () => style }).addTo(group);
    const centre = outline.getBounds().getCenter();
    L.marker(labelPosition(feature.properties, [centre.lat, centre.lng]), {
      // className 'empty', as Folium's DivIcon: no default white box.
      icon: L.divIcon({ html: labelHtml(labelName(feature.properties)), iconSize: [0, 0], className: 'empty' }),
      interactive: false,
      keyboard: false,
    }).addTo(group);
  }
  return group;
}

const nameProperty = (props: BoundaryProperties | null | undefined) => String(props?.name ?? '');

export function createNeighbourhoodsLayer(fc: BoundaryCollection): L.FeatureGroup {
  return createBoundaryLayer(fc, NEIGHBOURHOOD_STYLE, neighbourhoodLabelHtml, nameProperty);
}

export function createVillagesLayer(fc: VillagesCollection): L.FeatureGroup {
  return createBoundaryLayer(fc, VILLAGE_STYLE, villageLabelHtml, nameProperty);
}

/** The source file carries no per-feature name, so every feature gets the same fixed label. */
export function createChinatownLayer(fc: BoundaryCollection): L.FeatureGroup {
  return createBoundaryLayer(fc, CHINATOWN_STYLE, chinatownLabelHtml, () => CHINATOWN_LABEL);
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
