import type * as L from 'leaflet';
import { MAP_THEME } from './map-theme';
import type { BuildingMarker, MapIndex } from './types';

const BASE_ZOOM = 14;
// Thin light stroke so overlapping markers read as distinct dots instead of
// blurring into solid blobs at dense blocks (option 1). Per-marker overrides
// (housing-type rings) fall back to these via marker._strokeColor/_strokeWeight,
// set in buildMapIndex().
const MARKER_STROKE_COLOR = MAP_THEME.marker.stroke;
const MARKER_STROKE_WEIGHT = MAP_THEME.marker.strokeWeight;

export interface Restack {
  /** Coalesced to one restack per animation frame. */
  schedule(): void;
  now(): void;
  sendBlocksToBack(): void;
}

export function createRestack(index: MapIndex): Restack {
  function bringLayerToFront(layer: L.Path | undefined): void {
    if (layer) layer.bringToFront();
  }

  // Blocks and building markers share one canvas renderer (prefer_canvas=True
  // on the map, neither layer sets a custom pane/renderer), so paint order is
  // just insertion order into that shared canvas — not tied to which was added
  // to the map first. Toggling a layer off/on re-inserts it at the end (drawn
  // on top), so re-showing blocks after hiding them can push them in front of
  // buildings. Pin blocks behind buildings every time blocks become visible.
  function sendBlocksToBack(): void {
    index.blockLayers.forEach((layer) => {
      if (layer) layer.bringToBack();
    });
  }

  // Same shared-canvas insertion-order issue sendBlocksToBack() handles, for
  // everything above the blocks: toggling a layer re-inserts it at the end of
  // the draw order, and hovering/selecting changes what must sit on top. One
  // pass restores the full stack — unhighlighted blocks (left at the back),
  // highlighted blocks, building markers, housing-type rings (above every
  // marker, as createBuildingLayers() orders them), then highlighted markers.
  // Boundary outlines are on their own canvas above all of this (see
  // createBoundaryRenderer), so they never need restacking.
  function now(): void {
    const markers = Object.keys(index.buildings).map((key) => index.buildings[key]);
    index.blockLayers.forEach((layer) => { if (layer._highlighted) bringLayerToFront(layer); });
    markers.forEach((marker) => { if (!marker._highlighted) bringLayerToFront(marker); });
    markers.forEach((marker) => {
      (marker._extraRings || []).forEach((ring) => bringLayerToFront(ring.marker));
    });
    markers.forEach((marker) => { if (marker._highlighted) bringLayerToFront(marker); });
  }

  // highlightMarker()/highlightBlock() run in loops (owner/network hover,
  // filter ticks), so they coalesce to one restack per frame.
  let scheduled = false;
  function schedule(): void {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(() => {
      scheduled = false;
      now();
    });
  }

  return { schedule, now, sendBlocksToBack };
}

export interface MarkerStyler {
  ensureBase(marker: BuildingMarker): void;
  highlight(marker: BuildingMarker | undefined, on: boolean): void;
  adjustSelection(marker: BuildingMarker | undefined, delta: number): void;
  setVisible(marker: BuildingMarker | undefined, visible: boolean): void;
  /** updateMarkerColorAppearance: re-applies highlight state after a visibility flip. */
  refreshAppearance(marker: BuildingMarker): void;
  /** Hover on/off for a set of markers; leaves selected ones highlighted. */
  hover(markers: (BuildingMarker | undefined)[], on: boolean): void;
  applyZoom(zoom: number): void;
  /** Sets the Housing type / Rental issues display flags (read by stroke and ring logic). */
  setHousingFlags(showHousing: boolean, showIssues: boolean): void;
  /** The restyle loop at the end of applyHousingTypeFilter(). */
  restyleHousing(): void;
}

export function createMarkerStyler(index: MapIndex, scheduleRestack: () => void): MarkerStyler {
  let currentZoomScale = 1;
  let showHousingTypeChecked = false;
  let showIssuesChecked = false;

  function computeZoomScale(zoom: number): number {
    if (!Number.isFinite(zoom)) return currentZoomScale;
    const scale = Math.pow(1.2, zoom - BASE_ZOOM);
    return Math.min(2.4, Math.max(0.35, scale));
  }

  function getScaledRadius(marker: BuildingMarker | undefined): number {
    const base = marker && marker._baseRadius ? marker._baseRadius : 6;
    return base * currentZoomScale;
  }

  function ensureBase(marker: BuildingMarker): void {
    if (!marker) return;
    const opts = (marker.options || {}) as Record<string, unknown>;
    if (marker._baseColor === undefined || marker._baseColor === null) {
      marker._baseColor = (opts.base_color !== undefined ? opts.base_color : (opts.fillColor || MAP_THEME.marker.fill)) as string;
    }
    if (marker._baseOpacity === undefined || marker._baseOpacity === null) {
      if (opts.base_opacity !== undefined && opts.base_opacity !== null) {
        marker._baseOpacity = opts.base_opacity as number;
      } else if (typeof opts.fillOpacity === 'number') {
        marker._baseOpacity = opts.fillOpacity;
      } else {
        marker._baseOpacity = 0.35;
      }
    }
    if (marker._baseRadius === undefined || marker._baseRadius === null) {
      const optRadius = (opts.base_radius !== undefined && opts.base_radius !== null)
        ? opts.base_radius
        : (opts.radius !== undefined ? opts.radius : 6);
      marker._baseRadius = typeof optRadius === 'number' ? optRadius : 6;
    }
    if (marker._selectionRefs === undefined) {
      marker._selectionRefs = 0;
    }
    if (marker._isFiltered === undefined) {
      marker._isFiltered = false;
    }
    if (marker._strokeColor === undefined || marker._strokeColor === null) {
      marker._strokeColor = (opts.color as string) || MARKER_STROKE_COLOR;
    }
    if (marker._strokeWeight === undefined || marker._strokeWeight === null) {
      marker._strokeWeight = (typeof opts.weight === 'number') ? opts.weight : MARKER_STROKE_WEIGHT;
    }
  }

  // A building matching exactly one housing type has its OWN stroke
  // overridden to that type's ring color (see add_buildings_layers in
  // layout.py) — no separate marker. So unchecking "Show housing type" for
  // that case means reverting the marker's own stroke back to the plain
  // default, not hiding/showing a child object.
  // marker._primaryHousingType (set in buildMapIndex) records which type
  // currently owns the stroke, so these two helpers are the single source of
  // truth for what color/weight a marker's stroke should currently render as
  // — used by every setStyle call site below instead of reading
  // marker._strokeColor/_strokeWeight directly.
  function effectiveStrokeColor(marker: BuildingMarker | undefined): string {
    if (!marker) return MARKER_STROKE_COLOR;
    if (marker._primaryHousingType && !showHousingTypeChecked) {
      return MARKER_STROKE_COLOR;
    }
    return marker._strokeColor || MARKER_STROKE_COLOR;
  }

  function effectiveStrokeWeight(marker: BuildingMarker | undefined): number {
    if (!marker) return MARKER_STROKE_WEIGHT;
    if (marker._primaryHousingType && !showHousingTypeChecked) {
      return MARKER_STROKE_WEIGHT;
    }
    return marker._strokeWeight || MARKER_STROKE_WEIGHT;
  }

  // Extra rings (a building that is both SRO and co-op, or has a housing type
  // plus outstanding issues) are separate child CircleMarkers, so — unlike
  // the single-type stroke override above — they're shown/hidden by resizing
  // to/from radius 0, mirroring how setVisible treats a fully-filtered
  // building marker. Called whenever a building's own visibility changes
  // (from within setVisible/applyZoom) AND whenever the Building Details
  // checkboxes change (from restyleHousing) — a no-op (single property
  // check) for the ~5,000 markers without extra rings.
  function syncMarkerAnnotations(marker: BuildingMarker | undefined): void {
    if (!marker) return;
    const buildingVisible = !marker._isFiltered;
    if (marker._extraRings) {
      marker._extraRings.forEach((r) => {
        if (!r || !r.marker) return;
        const typeShown = r.housingType === 'issues' ? showIssuesChecked : showHousingTypeChecked;
        const visible = buildingVisible && typeShown;
        r.marker.setStyle({ opacity: visible ? 0.9 : 0 });
        r.marker.setRadius(visible ? getScaledRadius(marker) + 3.0 : 0);
      });
    }
  }

  function restyleMarkerStroke(marker: BuildingMarker | undefined): void {
    if (!marker) return;
    marker.setStyle({ color: effectiveStrokeColor(marker), weight: effectiveStrokeWeight(marker) });
  }

  function highlight(marker: BuildingMarker | undefined, on: boolean): void {
    if (!marker) return;
    ensureBase(marker);
    if (marker._isFiltered) return;
    marker._highlighted = on;
    scheduleRestack();
    const baseOpacity = marker._baseOpacity || 0.35;
    const baseRadius = getScaledRadius(marker);
    const baseColor = marker._baseColor || (marker.options && marker.options.fillColor) || MAP_THEME.marker.fill;
    marker.setStyle(on ? {
      weight: MAP_THEME.highlight.markerWeight,
      color: MAP_THEME.highlight.color,
      fillOpacity: Math.min(0.95, baseOpacity + 0.20),
      fillColor: baseColor,
    } : {
      weight: effectiveStrokeWeight(marker),
      color: effectiveStrokeColor(marker),
      fillOpacity: baseOpacity,
      fillColor: baseColor,
    });
    const extra = Math.max(1.5, 1.5 * currentZoomScale);
    marker.setRadius(on ? baseRadius + extra : baseRadius);
    if (on) marker.bringToFront();
  }

  function adjustSelection(marker: BuildingMarker | undefined, delta: number): void {
    if (!marker) return;
    marker._selectionRefs = (marker._selectionRefs || 0) + delta;
    if (marker._selectionRefs < 0) marker._selectionRefs = 0;
    if (!marker._isFiltered) {
      highlight(marker, marker._selectionRefs > 0);
    }
  }

  function setVisible(marker: BuildingMarker | undefined, visible: boolean): void {
    if (!marker) return;
    ensureBase(marker);
    // Called for every one of ~5,000 buildings on every filter/slider tick;
    // most buildings' visibility doesn't flip on a given tick, so skip the
    // setStyle/setRadius work (real canvas redraw cost) entirely when the
    // state isn't actually changing — this was the main source of slider-
    // drag jank.
    if (marker._isFiltered === !visible) return;
    marker._isFiltered = !visible;
    if (!visible) {
      marker._selectionRefs = 0;
      marker._highlighted = false;
      marker.setStyle({ weight: 0, color: undefined, fillOpacity: 0, fillColor: marker._baseColor });
      marker.setRadius(0);
    } else {
      const baseOpacity = marker._baseOpacity || 0.35;
      const baseRadius = getScaledRadius(marker);
      marker.setStyle({
        weight: effectiveStrokeWeight(marker),
        color: effectiveStrokeColor(marker),
        fillOpacity: baseOpacity,
        fillColor: marker._baseColor,
      });
      marker.setRadius(baseRadius);
      if ((marker._selectionRefs || 0) > 0) {
        highlight(marker, true);
      }
    }
    syncMarkerAnnotations(marker);
  }

  function refreshAppearance(marker: BuildingMarker): void {
    if (!marker) return;
    ensureBase(marker);
    if (marker._isFiltered) {
      return;
    }
    if ((marker._selectionRefs || 0) > 0) {
      highlight(marker, true);
    } else {
      highlight(marker, false);
    }
  }

  function hover(markers: (BuildingMarker | undefined)[], on: boolean): void {
    (markers || []).forEach((marker) => {
      if (!marker || marker._isFiltered) return;
      if (on) {
        highlight(marker, true);
      } else if ((marker._selectionRefs || 0) === 0) {
        highlight(marker, false);
      }
    });
  }

  function applyZoom(zoom: number): void {
    currentZoomScale = computeZoomScale(zoom);
    Object.keys(index.buildings).forEach((key) => {
      const marker = index.buildings[key];
      if (!marker || marker._isFiltered) return;
      const baseOpacity = marker._baseOpacity || 0.35;
      const scaledRadius = getScaledRadius(marker);
      marker.setRadius(scaledRadius);
      marker.setStyle({
        weight: effectiveStrokeWeight(marker),
        color: effectiveStrokeColor(marker),
        fillOpacity: baseOpacity,
        fillColor: marker._baseColor || (marker.options && marker.options.fillColor) || MAP_THEME.marker.fill,
      });
      if ((marker._selectionRefs || 0) > 0) {
        highlight(marker, true);
      }
      syncMarkerAnnotations(marker);
    });
  }

  function setHousingFlags(showHousing: boolean, showIssues: boolean): void {
    showHousingTypeChecked = showHousing;
    showIssuesChecked = showIssues;
  }

  function restyleHousing(): void {
    Object.keys(index.buildings).forEach((key) => {
      const marker = index.buildings[key];
      if (!marker) return;
      if (marker._primaryHousingType) restyleMarkerStroke(marker);
      if (marker._extraRings) syncMarkerAnnotations(marker);
    });
  }

  return {
    ensureBase, highlight, adjustSelection, setVisible, refreshAppearance, hover,
    applyZoom, setHousingFlags, restyleHousing,
  };
}
