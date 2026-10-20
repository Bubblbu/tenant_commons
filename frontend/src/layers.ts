/** Every Leaflet constructor lives here (and in bootstrap.ts); the modules it uses are pure and unit-tested. */
import type { PathOptions } from 'leaflet';
import * as L from 'leaflet';
import { blockPopupHtml, blockStyle, maxTotalUnits } from './blocks';
import { RING_OPACITY, RING_SPACING, RING_WEIGHT, ringColor, type RingType, type StyledMarker } from './markers';
import { NEIGHBOURHOOD_STYLE, labelPosition, neighbourhoodLabelHtml } from './neighbourhoods';
import { overlayLabelHtml, overlayLook, overlayPathOptions } from './overlays';
import type { BlocksCollection, BoundaryCollection, BoundaryProperties, OverlayCollection, SpecialAreaSummary } from './types';

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
 * neighbourhoods and the overlay areas. `labelName` picks the label text
 * off each feature's properties.
 */
function createBoundaryLayer(
  fc: BoundaryCollection,
  style: PathOptions,
  labelHtml: (name: string) => string,
  labelName: (props: BoundaryProperties | null | undefined) => string,
  renderer: L.Renderer,
): L.FeatureGroup {
  const group = L.featureGroup();
  for (const feature of fc.features) {
    // Outline-only and popup-less, so non-interactive: clicks fall through to
    // the blocks/buildings canvas underneath.
    const outline = L.geoJSON(feature, { style: () => ({ ...style, renderer, interactive: false }) }).addTo(group);
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

export const BOUNDARY_PANE = 'boundaries';

/**
 * Blocks and building markers share the map's default canvas, where paint
 * order is insertion order — re-showing a layer or highlighting a block would
 * push it over the boundary outlines. Boundaries instead draw on their own
 * canvas in a pane above overlayPane (400) and below markerPane (600, where
 * the name labels live). The pane ignores pointer events: a canvas on top
 * would otherwise swallow every click meant for the canvas underneath.
 */
export function createBoundaryRenderer(map: L.Map): L.Canvas {
  const pane = map.createPane(BOUNDARY_PANE);
  pane.style.zIndex = '450';
  pane.style.pointerEvents = 'none';
  return L.canvas({ pane: BOUNDARY_PANE });
}

const nameProperty = (props: BoundaryProperties | null | undefined) => String(props?.name ?? '');

export function createNeighbourhoodsLayer(fc: BoundaryCollection, renderer: L.Renderer): L.FeatureGroup {
  return createBoundaryLayer(fc, NEIGHBOURHOOD_STYLE, neighbourhoodLabelHtml, nameProperty, renderer);
}

/** One layer per overlay area that has polygons, keyed by area, coloured by its place in `areas`. */
export function createOverlayLayers(
  fc: OverlayCollection,
  areas: SpecialAreaSummary[] | undefined,
  renderer: L.Renderer,
): Record<string, L.FeatureGroup> {
  const layers: Record<string, L.FeatureGroup> = {};
  (areas ?? []).forEach((area, i) => {
    const features = fc.features.filter((f) => f.properties?.area === area.key);
    if (features.length === 0) return;
    const look = overlayLook(area.key, i);
    layers[area.key] = createBoundaryLayer(
      { type: 'FeatureCollection', features } as BoundaryCollection,
      overlayPathOptions(look),
      (name) => overlayLabelHtml(name, look.color),
      nameProperty,
      renderer,
    );
  });
  return layers;
}

export interface BuildingLayers {
  buildings: L.FeatureGroup;
  markersById: Record<string, L.CircleMarker>;
  ringsById: Record<string, { housing_type: RingType; marker: L.CircleMarker }[]>;
}

/**
 * One group for every building marker. Markers go into the group first; the
 * caller adds it to the map afterwards.
 *
 * Two passes, not one: every base marker is added before any ring. A ring's
 * radius is always larger than its own building's base marker, so draw
 * order never affects a building's marker relative to its own ring — what
 * it does affect is *other* buildings' markers, which (with preferCanvas)
 * paint in insertion order. Interleaving them (as one pass does per
 * building) lets a later building's opaque base marker paint over an
 * earlier building's ring in dense areas; two passes keeps every ring above
 * every base marker, globally.
 */
export function createBuildingLayers(
  markers: StyledMarker[],
  bindPopup?: (marker: L.CircleMarker, m: StyledMarker) => void,
): BuildingLayers {
  const buildings = L.featureGroup();
  const markersById: BuildingLayers['markersById'] = {};
  const ringsById: BuildingLayers['ringsById'] = {};
  const pending: { key: string; lat: number; lon: number; rings: StyledMarker['extra_rings']; baseRadius: number }[] = [];
  for (const m of markers) {
    if (m.lat === null || m.lon === null) continue;
    const key = String(m.b_id);
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
    if (m.extra_rings.length) {
      pending.push({ key, lat: m.lat, lon: m.lon, rings: m.extra_rings, baseRadius: m.base_radius });
    }
  }
  for (const p of pending) {
    const rings = p.rings.map((ring, i) => {
      const marker = L.circleMarker([p.lat, p.lon], {
        radius: p.baseRadius + RING_SPACING * (i + 1),
        fill: false,
        color: ringColor(ring.housing_type),
        weight: RING_WEIGHT,
        opacity: RING_OPACITY,
        // A canvas CircleMarker hit-tests its whole disc even with fill off,
        // so an interactive ring (drawn above every base marker) would
        // swallow the click meant for the building's own popup.
        interactive: false,
      });
      buildings.addLayer(marker);
      return { housing_type: ring.housing_type, marker };
    });
    ringsById[p.key] = rings;
  }
  return { buildings, markersById, ringsById };
}
