/**
 * Show-on-map toggles (layer visibility, block color scaling, boundaries,
 * housing/issues rings), the legend, mobile drawers and pane gutters.
 * Everything here is presentation, not filtering — see filter-pass.ts for
 * what actually hides a building or block.
 */
import type * as L from 'leaflet';
import { initPaneResize as initPaneGutters } from '../pane-resize';
import type { BlockStyler } from './block-style';
import type { MarkerStyler, Restack } from './marker-style';
import type { WiringContext } from './types';

export interface Display {
  updateLegend(): void;
  /** Reset's display part: layer toggles, block shading, boundaries, housing rings. */
  reset(): void;
}

/** Wires Show-on-map toggles, legend, pane gutters and mobile drawers; applies initial toggle state. */
export function initDisplay(
  ctx: WiringContext,
  markers: MarkerStyler,
  blocks: BlockStyler,
  restack: Restack,
  applyFilters: () => void,
  doc: Document,
): Display {
  const mapInstance = ctx.map;
  const layerBuildings = ctx.layers.buildings;
  const layerBlocks = ctx.layers.blocks;
  const layerNeighbourhoods = ctx.layers.neighbourhoods;
  const layerVillages = ctx.layers.villages;
  const layerChinatown = ctx.layers.chinatown;

  let showHousingTypeChecked = false;
  let showIssuesChecked = false;
  // Declared here (not down with the other filter-panel DOM refs) because
  // applyHousingTypeFilter()/updateLegendVisibility() — both called early
  // during start-up — read these. Referencing a `const` before its
  // declaration line throws (temporal dead zone), and since that throw used
  // to happen inside wireUp()'s top-level try/catch, it was being silently
  // swallowed and retried forever — filters and tab-switching never finished
  // wiring up as a result.
  const vizShowHousingTypeChk = doc.getElementById('viz-show-housing-type') as HTMLInputElement | null;
  const vizShowIssuesChk = doc.getElementById('viz-show-issues') as HTMLInputElement | null;

  const colorBlocksChk = doc.getElementById('viz-color-blocks') as HTMLInputElement | null;
  const showBuildingsChk = doc.getElementById('viz-show-buildings') as HTMLInputElement | null;
  const vizBlocksChk = doc.getElementById('viz-show-blocks') as HTMLInputElement | null;
  const vizNeighbourhoodsChk = doc.getElementById('viz-show-neighbourhoods') as HTMLInputElement | null;
  const vizVillagesChk = doc.getElementById('viz-show-villages') as HTMLInputElement | null;
  const vizChinatownChk = doc.getElementById('viz-show-chinatown') as HTMLInputElement | null;
  const legendContainerEl = doc.getElementById('legend-map');
  const legendBlocksEl = doc.getElementById('legend-blocks-section');
  const legendBuildingDetailsEl = doc.getElementById('legend-building-details-section');
  const legendBoundariesEl = doc.getElementById('legend-boundaries-section');

  function toggleLayerVisibility(layer: L.Layer | undefined, show: boolean): void {
    if (!mapInstance || !layer) return;
    const hasLayer = mapInstance.hasLayer(layer);
    if (show && !hasLayer) {
      layer.addTo(mapInstance);
    } else if (!show && hasLayer) {
      mapInstance.removeLayer(layer);
    }
  }

  function boundaryVisibility(): { neighbourhoods: boolean; chinatown: boolean; villages: boolean } {
    const neighbourhoods = vizNeighbourhoodsChk ? vizNeighbourhoodsChk.checked : true;
    return {
      neighbourhoods,
      chinatown: neighbourhoods && (vizChinatownChk ? vizChinatownChk.checked : true),
      villages: neighbourhoods && (vizVillagesChk ? vizVillagesChk.checked : false),
    };
  }

  function syncBoundaryLayers(): void {
    const v = boundaryVisibility();
    toggleLayerVisibility(layerNeighbourhoods, v.neighbourhoods);
    toggleLayerVisibility(layerChinatown, v.chinatown);
    toggleLayerVisibility(layerVillages, v.villages);
  }

  function setLegendDisplay(el: HTMLElement | null, show: boolean): void {
    if (!el) return;
    el.style.display = show ? 'block' : 'none';
  }

  function updateLegendVisibility(): void {
    const blocksVisible = vizBlocksChk ? vizBlocksChk.checked !== false : true;
    const showBlocksLegend = blocksVisible && blocks.colorScalingEnabled();
    if (legendContainerEl) {
      const sidebarEl = doc.getElementById('sidebar-container');
      if (sidebarEl && sidebarEl.offsetWidth) {
        const leftPos = sidebarEl.offsetWidth + 30;
        legendContainerEl.style.left = leftPos + 'px';
      }
    }
    setLegendDisplay(legendBlocksEl, showBlocksLegend);
    // Static reference info (ring colors) — only relevant once at least one
    // Buildings ring toggle (Housing type / Rental issues) is actually on.
    const showBuildingDetailsLegend = showHousingTypeChecked || showIssuesChecked;
    setLegendDisplay(legendBuildingDetailsEl, showBuildingDetailsLegend);
    const boundaries = boundaryVisibility();
    const showBoundariesLegend = boundaries.neighbourhoods || boundaries.chinatown || boundaries.villages;
    setLegendDisplay(legendBoundariesEl, showBoundariesLegend);
    if (legendContainerEl) {
      const shouldShow = (showBlocksLegend && legendBlocksEl) ||
        (showBuildingDetailsLegend && legendBuildingDetailsEl) ||
        (showBoundariesLegend && legendBoundariesEl);
      legendContainerEl.style.display = shouldShow ? 'flex' : 'none';
    }
  }

  function applyBlockColorScaling(enabled: boolean): void {
    blocks.setColorScaling(enabled);
    updateLegendVisibility();
  }

  // Housing type (SRO/co-op) and rental-issues toggles only restyle existing
  // markers (stroke color, extra rings) — they never add, remove or hide a
  // marker. (Only show buildings with issues, in the Filters panel, is the
  // one that actually hides markers — see filter-pass.ts's apply().)
  function applyHousingTypeFilter(): void {
    showHousingTypeChecked = vizShowHousingTypeChk ? vizShowHousingTypeChk.checked !== false : false;
    showIssuesChecked = vizShowIssuesChk ? vizShowIssuesChk.checked !== false : false;
    markers.setHousingFlags(showHousingTypeChecked, showIssuesChecked);
    applyFilters();
    updateLegendVisibility();
    markers.restyleHousing();
  }

  // Below the mobile breakpoint (see index.html's @media rule), the
  // sidebar/filters panels become fixed-position off-canvas drawers instead
  // of in-flow flex columns. This just toggles the `.open` class the CSS
  // keys off of; above the breakpoint the class is inert (no matching
  // rule), so no width/media check is needed here.
  function initMobilePanels(): void {
    const sidebar = doc.getElementById('sidebar-container');
    const filters = doc.getElementById('filters-panel');
    const openSidebarBtn = doc.getElementById('mobile-toggle-sidebar');
    const openFiltersBtn = doc.getElementById('mobile-toggle-filters');

    function closeAll(): void {
      if (sidebar) sidebar.classList.remove('open');
      if (filters) filters.classList.remove('open');
      if (openSidebarBtn) openSidebarBtn.setAttribute('aria-expanded', 'false');
      if (openFiltersBtn) openFiltersBtn.setAttribute('aria-expanded', 'false');
    }

    // Only one drawer open at a time — opening one closes the other.
    function openPanel(panel: HTMLElement | null, btn: HTMLElement | null): void {
      closeAll();
      if (panel) panel.classList.add('open');
      if (btn) btn.setAttribute('aria-expanded', 'true');
    }

    if (openSidebarBtn) {
      openSidebarBtn.addEventListener('click', () => {
        if (sidebar && sidebar.classList.contains('open')) closeAll();
        else openPanel(sidebar, openSidebarBtn);
      });
    }
    if (openFiltersBtn) {
      openFiltersBtn.addEventListener('click', () => {
        if (filters && filters.classList.contains('open')) closeAll();
        else openPanel(filters, openFiltersBtn);
      });
    }
    doc.querySelectorAll('.mobile-panel-close').forEach((btn) => {
      btn.addEventListener('click', closeAll);
    });
  }

  function initPaneResize(): void {
    const gutter = (pane: string) => doc.querySelector<HTMLElement>('.pane-gutter[data-pane="' + pane + '"]');
    const dataGutter = gutter('data');
    const filtersGutter = gutter('filters');
    const dataPanel = doc.getElementById('sidebar-container');
    const filtersPanel = doc.getElementById('filters-panel');
    if (!dataGutter || !filtersGutter || !dataPanel || !filtersPanel) return;
    initPaneGutters([
      { gutter: dataGutter, side: 'left', panel: dataPanel, storageKey: 'tc-data-width', min: 280, max: 1000, defaultWidth: 480 },
      { gutter: filtersGutter, side: 'right', panel: filtersPanel, storageKey: 'tc-filters-width', min: 240, max: 520, defaultWidth: 300 },
    ], {
      onResize: updateLegendVisibility,
      onResizeEnd: () => {
        if (mapInstance && typeof mapInstance.invalidateSize === 'function') {
          mapInstance.invalidateSize({ animate: false });
        }
        updateLegendVisibility();
      },
    });
  }

  initPaneResize();
  initMobilePanels();

  if (showBuildingsChk) {
    toggleLayerVisibility(layerBuildings, showBuildingsChk.checked !== false);
    showBuildingsChk.addEventListener('change', () => {
      toggleLayerVisibility(layerBuildings, showBuildingsChk.checked !== false);
      if (showBuildingsChk.checked) restack.now();
      updateLegendVisibility();
    });
  } else {
    toggleLayerVisibility(layerBuildings, true);
  }
  if (colorBlocksChk) {
    applyBlockColorScaling(colorBlocksChk.checked !== false);
    colorBlocksChk.addEventListener('change', () => {
      applyBlockColorScaling(colorBlocksChk.checked !== false);
    });
  } else {
    applyBlockColorScaling(true);
  }
  if (vizBlocksChk) {
    toggleLayerVisibility(layerBlocks, vizBlocksChk.checked !== false);
    vizBlocksChk.addEventListener('change', () => {
      toggleLayerVisibility(layerBlocks, vizBlocksChk.checked);
      if (vizBlocksChk.checked) { restack.sendBlocksToBack(); restack.now(); }
      updateLegendVisibility();
    });
  } else {
    toggleLayerVisibility(layerBlocks, true);
  }
  // Chinatown and Villages Plan sit under Neighbourhood boundaries in Show
  // on map: each is drawn only while it and the parent are ticked.
  syncBoundaryLayers();
  [vizNeighbourhoodsChk, vizChinatownChk, vizVillagesChk].forEach((chk) => {
    if (!chk) return;
    chk.addEventListener('change', () => {
      syncBoundaryLayers();
      updateLegendVisibility();
    });
  });
  applyHousingTypeFilter();
  if (vizShowHousingTypeChk) vizShowHousingTypeChk.addEventListener('change', applyHousingTypeFilter);
  if (vizShowIssuesChk) vizShowIssuesChk.addEventListener('change', applyHousingTypeFilter);

  function reset(): void {
    if (colorBlocksChk) {
      colorBlocksChk.checked = true;
      applyBlockColorScaling(true);
    }
    if (showBuildingsChk) {
      showBuildingsChk.checked = true;
      toggleLayerVisibility(layerBuildings, true);
      restack.now();
    }
    if (vizBlocksChk) {
      vizBlocksChk.checked = true;
      toggleLayerVisibility(layerBlocks, true);
      restack.sendBlocksToBack();
      restack.now();
    }
    if (vizNeighbourhoodsChk) vizNeighbourhoodsChk.checked = true;
    if (vizVillagesChk) vizVillagesChk.checked = false;
    if (vizChinatownChk) vizChinatownChk.checked = true;
    syncBoundaryLayers();
    if (vizShowHousingTypeChk) vizShowHousingTypeChk.checked = false;
    if (vizShowIssuesChk) vizShowIssuesChk.checked = false;
    applyHousingTypeFilter();
  }

  return { updateLegend: updateLegendVisibility, reset };
}
