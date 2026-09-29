import type * as L from 'leaflet';
import { MAP_THEME } from './map-theme';
import type { BlockLayer, MapIndex } from './types';

export interface BlockStyler {
  /** recomputeBlockColorScale(), including the legend scale text. */
  recomputeScale(): void;
  setColorScaling(enabled: boolean): void;
  colorScalingEnabled(): boolean;
  setFiltered(blockId: string, filtered: boolean): void;
  adjustSelection(layer: BlockLayer | undefined, delta: number): void;
  hover(blockId: string, on: boolean): void;
}

export function createBlockStyler(index: MapIndex, doc: Document, scheduleRestack: () => void): BlockStyler {
  let blockColorScalingEnabled = true;
  let blockColorMin = 0;
  let blockColorMax = 0;

  function resetBlockStyle(layer: BlockLayer | undefined): void {
    if (!layer) return;
    const rawUnits = Number(layer._blockUnits);
    const units = Number.isFinite(rawUnits) ? rawUnits : 0;
    const buildingCount = Number(layer._blockBuildings) || 0;
    let base: L.PathOptions;
    if (buildingCount <= 0) {
      // Empty blocks (no buildings) carry no meaningful data — leave them
      // transparent rather than painting them into the color scale.
      base = { weight: 1, color: MAP_THEME.block.stroke, fillOpacity: 0, fillColor: 'transparent' };
    } else if (!blockColorScalingEnabled || blockColorMax <= 0) {
      base = { weight: 1, color: MAP_THEME.block.stroke, fillOpacity: 0.35, fillColor: MAP_THEME.block.unscaledFill };
    } else {
      // Scale relative to the currently-visible blocks' own min/max (set by
      // recomputeScale()), not fixed dataset-wide bounds — so e.g. filtering
      // to one neighbourhood re-stretches the hue range to that
      // neighbourhood's least/most-dense blocks instead of leaving
      // everything bunched at the low end of a city-wide scale.
      const span = blockColorMax - blockColorMin;
      const ratio = span > 0 ? Math.max(0, Math.min(1, (units - blockColorMin) / span)) : 1;
      const fill = (ratio <= 0.10) ? MAP_THEME.block.scale[0] :
                   (ratio <= 0.25) ? MAP_THEME.block.scale[1] :
                   (ratio <= 0.50) ? MAP_THEME.block.scale[2] :
                   (ratio <= 0.75) ? MAP_THEME.block.scale[3] :
                   (ratio <  1.00) ? MAP_THEME.block.scale[4] : MAP_THEME.block.scale[5];
      base = { weight: 1, color: MAP_THEME.block.stroke, fillOpacity: 0.7, fillColor: fill };
    }
    layer._baseStyle = base;
    layer.setStyle(base);
  }

  function updateBlockLegendScale(): void {
    const scaleEl = doc.getElementById('block-legend-scale');
    const noteEl = doc.getElementById('block-legend-note');
    if (!scaleEl && !noteEl) return;
    const min = blockColorMin;
    const max = blockColorMax;
    if (scaleEl) {
      const fractions = [0, 0.2, 0.4, 0.6, 0.8, 1.0];
      scaleEl.innerHTML = fractions.map((frac) => {
        const value = max > min ? Math.round(min + (max - min) * frac) : (frac === 1 ? max : min);
        return '<span>' + value.toLocaleString() + '</span>';
      }).join('');
    }
    if (noteEl) {
      if (max <= 0) {
        noteEl.textContent = 'No visible blocks with unit data.';
      } else if (max === min) {
        noteEl.textContent = 'All visible blocks have ' + max.toLocaleString() + ' units.';
      } else {
        noteEl.textContent = 'Color scaled to ' + min.toLocaleString() + '–' + max.toLocaleString() + ' units (visible blocks).';
      }
    }
  }

  // Recomputes the block color scale's min/max from whatever blocks are
  // currently visible (not filtered out by the neighbourhood picker or other
  // filters) and repaints them + the legend to match. Called once during
  // initial wireUp (when nothing is filtered yet, so it reflects the whole
  // dataset) and again at the end of every filter-pass.ts apply().
  function recomputeScale(): void {
    let min: number | null = null;
    let max = 0;
    index.blockLayers.forEach((layer) => {
      if (layer._isFiltered) return;
      if ((layer._blockBuildings || 0) <= 0) return;
      const units = Number(layer._blockUnits);
      if (!Number.isFinite(units)) return;
      if (min === null || units < min) min = units;
      if (units > max) max = units;
    });
    if (min === null) min = 0;
    blockColorMin = min;
    blockColorMax = max;
    index.blockLayers.forEach((layer) => {
      if (layer._isFiltered) return;
      resetBlockStyle(layer);
    });
    updateBlockLegendScale();
  }

  function setFiltered(blockId: string, filtered: boolean): void {
    const layer = index.blocks[blockId];
    if (!layer) return;
    // Called for every one of ~4,600 blocks on every filter tick; skip the
    // setStyle work when the filtered state isn't actually changing (same
    // reasoning as setVisible above).
    if (layer._isFiltered === filtered) return;
    layer._isFiltered = filtered;
    if (filtered) {
      layer._highlighted = false;
      layer._selectionRefs = 0;
      // Fully hidden, matching setVisible()'s treatment of filtered
      // buildings (weight:0/fillOpacity:0) rather than just dimming to a
      // faint grey outline.
      layer.setStyle({ weight: 0, color: undefined, fillOpacity: 0, fillColor: MAP_THEME.block.filteredFill });
    } else {
      resetBlockStyle(layer);
    }
  }

  function highlightBlock(layer: BlockLayer | undefined, on: boolean): void {
    if (!layer || layer._isFiltered) return;
    layer._highlighted = on;
    scheduleRestack();
    if (on) {
      const base = layer._baseStyle || {};
      layer.setStyle({
        weight: MAP_THEME.highlight.blockWeight,
        color: MAP_THEME.highlight.color,
        fillOpacity: Math.min(0.9, (base.fillOpacity || 0.35) + 0.1),
        fillColor: base.fillColor || (layer.options && layer.options.fillColor) || MAP_THEME.block.scale[0],
      });
    } else {
      resetBlockStyle(layer);
    }
  }

  function adjustSelection(layer: BlockLayer | undefined, delta: number): void {
    if (!layer) return;
    layer._selectionRefs = (layer._selectionRefs || 0) + delta;
    if (layer._selectionRefs < 0) layer._selectionRefs = 0;
    if (!layer._isFiltered) {
      highlightBlock(layer, layer._selectionRefs > 0);
    }
  }

  function hover(blockId: string, on: boolean): void {
    const layer = index.blocks[blockId];
    if (!layer || layer._isFiltered) return;
    if (on) {
      highlightBlock(layer, true);
    } else if ((layer._selectionRefs || 0) === 0) {
      highlightBlock(layer, false);
    }
  }

  function setColorScaling(enabled: boolean): void {
    blockColorScalingEnabled = enabled !== false;
    Object.keys(index.blocks).forEach((key) => {
      const layer = index.blocks[key];
      if (!layer) return;
      if (!layer._isFiltered) {
        resetBlockStyle(layer);
      }
    });
  }

  function colorScalingEnabled(): boolean {
    return blockColorScalingEnabled;
  }

  return { recomputeScale, setColorScaling, colorScalingEnabled, setFiltered, adjustSelection, hover };
}
