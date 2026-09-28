import { initPaneResize as initPaneGutters } from './pane-resize';
import { createBlockStyler } from './wiring/block-style';
import { buildMapIndex } from './wiring/indexes';
import { createMarkerStyler, createRestack } from './wiring/marker-style';
import { buildMetricControls } from './wiring/metric-controls';
import { initSelection } from './wiring/selection';
import { createStatus, initCsvExport, watchMap } from './wiring/status-export';
import { initLiveTables } from './wiring/tables-live';

export function startWiring(ctx) {
  let filterConfig = {};
  let markerMetadata = [];
  let buildingData = {};
  // wireUp() legitimately fails a few times at startup (Folium's layers
  // aren't attached to window/the map yet — see the "not ready" throws
  // below) and silently retries, which is fine. But a *permanent* bug (e.g.
  // a reference used before it's declared) throws every single time too,
  // and was retrying forever with nothing printed anywhere — this counter
  // gives up and logs loudly after a few seconds instead of hanging forever.
  let wireUpAttempts = 0;

  function assignLoadedData(filters, metadata, buildings) {
    filterConfig = filters || {};
    markerMetadata = Array.isArray(metadata) ? metadata : [];
    buildingData = buildings || {};
  }
  function wireUp() {
    try {
      const layerBlocks = ctx.layers.blocks;
      const layerBuildings = ctx.layers.buildings;
      const layerNeighbourhoods = ctx.layers.neighbourhoods;
      const layerVillages = ctx.layers.villages;
      const layerChinatown = ctx.layers.chinatown;
      const mapInstance = ctx.map;

      if (!layerBlocks || typeof layerBlocks.eachLayer !== 'function') {
        throw new Error('Blocks layer not ready');
      }

      const index = buildMapIndex(ctx);
      const restack = createRestack(index);
      const blocks = createBlockStyler(index, document, restack.schedule);
      const markers = createMarkerStyler(index, restack.schedule);
      const status = createStatus(index, mapInstance, filterConfig, document);
      watchMap(mapInstance, status, () => markers.applyZoom(mapInstance.getZoom()));
      const tables = initLiveTables(index, document);
      const selection = initSelection(index, markers, blocks, tables, document);
      initCsvExport(index, mapInstance, buildingData, document);
      let showHousingTypeChecked = false;
      let showIssuesChecked = false;
      // Declared here (not down with the other filter-panel DOM refs) because
      // applyHousingTypeFilter()/updateLegendVisibility() — both called
      // early during wireUp() — read these. Referencing a `const` before its
      // declaration line throws (temporal dead zone), and since that throw
      // happened inside wireUp()'s top-level try/catch, it was being
      // silently swallowed and retried forever — filters and tab-switching
      // never finished wiring up as a result.
      const vizShowHousingTypeChk = document.getElementById('viz-show-housing-type');
      const vizShowIssuesChk = document.getElementById('viz-show-issues');


      // Housing type (SRO/co-op) and rental-issues toggles only restyle
      // existing markers (stroke color, extra rings) — they never add,
      // remove or hide a marker. (Only show buildings with issues, in the
      // Filters panel, is the one that actually hides markers — see
      // applyFilters().)
      function applyHousingTypeFilter() {
        showHousingTypeChecked = vizShowHousingTypeChk ? vizShowHousingTypeChk.checked !== false : false;
        showIssuesChecked = vizShowIssuesChk ? vizShowIssuesChk.checked !== false : false;
        markers.setHousingFlags(showHousingTypeChecked, showIssuesChecked);
        applyFilters();
        updateLegendVisibility();
        markers.restyleHousing();
      }

      function toggleLayerVisibility(layer, show) {
        if (!mapInstance || !layer) return;
        const hasLayer = mapInstance.hasLayer(layer);
        if (show && !hasLayer) {
          layer.addTo(mapInstance);
        } else if (!show && hasLayer) {
          mapInstance.removeLayer(layer);
        }
      }

      // Every layer is still unfiltered at this point in wireUp(), so this
      // paints against the full dataset's min/max; applyFilters() calls
      // blocks.recomputeScale() again once neighbourhood/other filters are
      // known, narrowing it to whatever's actually visible.
      blocks.recomputeScale();

      restack.sendBlocksToBack();

      Object.values(index.buildings).forEach(function(marker) {
        markers.ensureBase(marker);
        markers.refreshAppearance(marker);
      });

      restack.now();

      applyZoomScaling();

      const hoodInputs = Array.from(document.querySelectorAll('.filter-neighbourhood-option'));
      const housingChips = Array.from(document.querySelectorAll('.housing-chip'));
      const sectionCounts = ['area', 'ownership', 'building', 'value'].reduce(function(acc, sec) {
        acc[sec] = {
          count: document.getElementById('filter-count-' + sec),
          clear: document.getElementById('filter-clear-' + sec),
        };
        return acc;
      }, {});
      const resetBtn = document.getElementById('filter-reset');
      const colorBlocksChk = document.getElementById('viz-color-blocks');
      const showBuildingsChk = document.getElementById('viz-show-buildings');
      const vizBlocksChk = document.getElementById('viz-show-blocks');
      const showEmptyBlocksChk = document.getElementById('viz-show-empty-blocks');
      const vizNeighbourhoodsChk = document.getElementById('viz-show-neighbourhoods');
      const vizVillagesChk = document.getElementById('viz-show-villages');
      const vizChinatownChk = document.getElementById('viz-show-chinatown');
      const landlordFilter = ctx.landlordFilter;
      const onlyIssuesChk = document.getElementById('filter-only-issues');
      const onlyOwnedChk = document.getElementById('filter-only-owned');
      const onlyUnitsChk = document.getElementById('filter-only-units');
      const legendContainerEl = document.getElementById('legend-map');
      const legendBlocksEl = document.getElementById('legend-blocks-section');
      const legendBuildingDetailsEl = document.getElementById('legend-building-details-section');
      const legendBoundariesEl = document.getElementById('legend-boundaries-section');

      function setLegendDisplay(el, show) {
        if (!el) return;
        el.style.display = show ? 'block' : 'none';
      }

      function boundaryVisibility() {
        const neighbourhoods = vizNeighbourhoodsChk ? vizNeighbourhoodsChk.checked : true;
        return {
          neighbourhoods: neighbourhoods,
          chinatown: neighbourhoods && (vizChinatownChk ? vizChinatownChk.checked : true),
          villages: neighbourhoods && (vizVillagesChk ? vizVillagesChk.checked : false),
        };
      }

      function syncBoundaryLayers() {
        const v = boundaryVisibility();
        toggleLayerVisibility(layerNeighbourhoods, v.neighbourhoods);
        toggleLayerVisibility(layerChinatown, v.chinatown);
        toggleLayerVisibility(layerVillages, v.villages);
      }

      function updateLegendVisibility() {
        const blocksVisible = vizBlocksChk ? vizBlocksChk.checked !== false : true;
        const showBlocksLegend = blocksVisible && blocks.colorScalingEnabled();
        if (legendContainerEl) {
          const sidebarEl = document.getElementById('sidebar-container');
          if (sidebarEl && sidebarEl.offsetWidth) {
            const leftPos = sidebarEl.offsetWidth + 30;
            legendContainerEl.style.left = leftPos + 'px';
          }
        }
        setLegendDisplay(legendBlocksEl, showBlocksLegend);
        // Static reference info (ring colors) — only relevant once at least
        // one Buildings ring toggle (Housing type / Rental issues) is actually on.
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

      function applyBlockColorScaling(enabled) {
        blocks.setColorScaling(enabled);
        updateLegendVisibility();
      }

      function applyZoomScaling() {
        if (!mapInstance || typeof mapInstance.getZoom !== 'function') return;
        markers.applyZoom(mapInstance.getZoom());
      }

      // Below the mobile breakpoint (see index.html's @media rule), the
      // sidebar/filters panels become fixed-position off-canvas drawers
      // instead of in-flow flex columns. This just toggles the `.open`
      // class the CSS keys off of; above the breakpoint the class is inert
      // (no matching rule), so no width/media check is needed here.
      function initMobilePanels() {
        const sidebar = document.getElementById('sidebar-container');
        const filters = document.getElementById('filters-panel');
        const openSidebarBtn = document.getElementById('mobile-toggle-sidebar');
        const openFiltersBtn = document.getElementById('mobile-toggle-filters');

        function closeAll() {
          if (sidebar) sidebar.classList.remove('open');
          if (filters) filters.classList.remove('open');
          if (openSidebarBtn) openSidebarBtn.setAttribute('aria-expanded', 'false');
          if (openFiltersBtn) openFiltersBtn.setAttribute('aria-expanded', 'false');
        }

        // Only one drawer open at a time — opening one closes the other.
        function openPanel(panel, btn) {
          closeAll();
          if (panel) panel.classList.add('open');
          if (btn) btn.setAttribute('aria-expanded', 'true');
        }

        if (openSidebarBtn) {
          openSidebarBtn.addEventListener('click', function() {
            if (sidebar && sidebar.classList.contains('open')) closeAll();
            else openPanel(sidebar, openSidebarBtn);
          });
        }
        if (openFiltersBtn) {
          openFiltersBtn.addEventListener('click', function() {
            if (filters && filters.classList.contains('open')) closeAll();
            else openPanel(filters, openFiltersBtn);
          });
        }
        document.querySelectorAll('.mobile-panel-close').forEach(function(btn) {
          btn.addEventListener('click', closeAll);
        });
      }

      function initPaneResize() {
        const gutter = function(pane) { return document.querySelector('.pane-gutter[data-pane="' + pane + '"]'); };
        const dataGutter = gutter('data');
        const filtersGutter = gutter('filters');
        const dataPanel = document.getElementById('sidebar-container');
        const filtersPanel = document.getElementById('filters-panel');
        if (!dataGutter || !filtersGutter || !dataPanel || !filtersPanel) return;
        initPaneGutters([
          { gutter: dataGutter, side: 'left', panel: dataPanel, storageKey: 'tc-data-width', min: 280, max: 1000, defaultWidth: 480 },
          { gutter: filtersGutter, side: 'right', panel: filtersPanel, storageKey: 'tc-filters-width', min: 240, max: 520, defaultWidth: 300 },
        ], {
          onResize: updateLegendVisibility,
          onResizeEnd: function() {
            if (mapInstance && typeof mapInstance.invalidateSize === 'function') {
              mapInstance.invalidateSize({ animate: false });
            }
            updateLegendVisibility();
          },
        });
      }

      // Sliders fire 'input' many times per second while dragging. applyFilters() walks
      // every building/block/landlord row, so calling it synchronously per event is what
      // makes dragging a filter slider feel sluggish. Coalesce to at most once per
      // animation frame instead — the label text still updates immediately below, only
      // the expensive full-row-scan pass gets throttled.
      let applyFiltersScheduled = false;
      function scheduleApplyFilters() {
        if (applyFiltersScheduled) return;
        applyFiltersScheduled = true;
        window.requestAnimationFrame(function() {
          applyFiltersScheduled = false;
          applyFilters();
        });
      }

      const metrics = buildMetricControls(filterConfig, document, scheduleApplyFilters);
      status.updateDataset();
      updateLegendVisibility();

      // How many filters each Filter by section has on, shown beside its heading.
      function updateSectionCounts(hoods, housing, thresholds) {
        const activeMetrics = { building: 0, value: 0 };
        Object.keys(thresholds).forEach(function(metric) {
          const t = thresholds[metric];
          if (t.min !== null || t.max !== null) activeMetrics[metrics.controls[metric].section] += 1;
        });
        const counts = {
          area: hoods,
          ownership: (landlordFilter ? landlordFilter.count() : 0) + (onlyOwnedChk && onlyOwnedChk.checked ? 1 : 0),
          building: housing + (onlyIssuesChk && onlyIssuesChk.checked ? 1 : 0) +
            (onlyUnitsChk && onlyUnitsChk.checked ? 1 : 0) + activeMetrics.building,
          value: activeMetrics.value,
        };
        Object.keys(sectionCounts).forEach(function(sec) {
          const els = sectionCounts[sec];
          const n = counts[sec] || 0;
          if (els.count) {
            els.count.hidden = n === 0;
            els.count.textContent = String(n);
          }
          if (els.clear) els.clear.hidden = n === 0;
        });
      }

      function applyFilters() {
        metrics.updateAllLabels();
        const selectedHoods = hoodInputs
          .filter(function(inp) { return inp.checked; })
          .map(function(inp) { return (inp.value || '').toLowerCase().trim(); });
        // No area ticked means every area.
        const restrictHoods = selectedHoods.length > 0;
        const selectedHousing = housingChips
          .filter(function(chip) { return chip.getAttribute('aria-pressed') === 'true'; })
          .map(function(chip) { return chip.getAttribute('data-housing'); });
        // Chinatown/Villages Plan are two more checkboxes in the same list
        // (see legend.ts's specialAreaTagsHtml) but aren't a row's own
        // local_area — a building/block can be in a real neighbourhood *and*
        // one of these overlays at once — so a row matches the selection if
        // its area is selected OR it's flagged for a selected special area.
        function areaSelectionMatches(area, inChinatown, inVillage) {
          if (selectedHoods.includes(area)) return true;
          if (inChinatown && selectedHoods.includes('chinatown')) return true;
          if (inVillage && selectedHoods.includes('village-plan')) return true;
          return false;
        }
        const thresholds = {};
        metrics.keys.forEach(function(metric) {
          const ctrl = metrics.controls[metric];
          const summary = ctrl.summary;
          let minVal = ctrl.currentMin;
          let maxVal = ctrl.currentMax;
          const tolerance = summary.step ? summary.step * 0.5 : 0;
          thresholds[metric] = {
            min: (minVal <= summary.min + tolerance) ? null : minVal,
            max: (maxVal >= summary.max - tolerance) ? null : maxVal,
            summary: summary,
          };
        });
        // Live histograms (see metric-controls.ts's renderMetricControl): each
        // metric's bars are recomputed below from the rows that pass every
        // OTHER active filter — neighbourhood, search, issues-only, and every
        // other metric's own slider — but not this metric's own threshold.
        // That answers "how many more would I get if I loosened just this
        // slider" (the usual faceted-search convention) rather than a
        // metric's own bars shrinking toward whatever range it's already
        // dragged to. Bin edges and the slider's min/max range stay fixed;
        // only bar heights (counts) are live.
        const binCounts = {};
        metrics.keys.forEach(function(metric) {
          binCounts[metric] = metrics.controls[metric].bars.map(function() { return 0; });
        });

        const visibleBids = new Set();
        tables.buildingRows.forEach(function(row) {
          const bid = row.getAttribute('data-bid');
          const marker = index.buildings[bid];

          // Every filter except the per-metric thresholds — shared by the
          // final `matches` below and by each metric's "exclude own filter"
          // histogram recount.
          let baseMatches = true;
          const rowArea = (row.getAttribute('data-area') || '').toLowerCase().trim();
          if (restrictHoods) {
            baseMatches = areaSelectionMatches(
              rowArea,
              row.getAttribute('data-chinatown') === '1',
              row.getAttribute('data-village') === '1',
            );
          }
          if (baseMatches && landlordFilter && landlordFilter.isActive()) {
            baseMatches = landlordFilter.matches({
              owner: row.getAttribute('data-owner') || '',
              network: row.getAttribute('data-network') || '',
              manager: row.getAttribute('data-manager') || '',
            });
          }
          if (baseMatches && onlyIssuesChk && onlyIssuesChk.checked) {
            const rawIssues = row.getAttribute('data-n-issues');
            const nIssues = rawIssues === null || rawIssues === '' ? NaN : parseFloat(rawIssues);
            baseMatches = Number.isFinite(nIssues) && nIssues > 0;
          }
          if (baseMatches && selectedHousing.length) {
            // "co-op, sro" is both.
            const types = (row.getAttribute('data-housing-type') || '').split(',').map(function(t) { return t.trim(); });
            baseMatches = selectedHousing.some(function(t) { return types.indexOf(t) !== -1; });
          }
          if (baseMatches && onlyUnitsChk && onlyUnitsChk.checked) {
            // Otherwise the Units slider lets buildings with no count through (see below).
            baseMatches = (row.getAttribute('data-units') || '') !== '';
          }
          if (baseMatches && onlyOwnedChk && onlyOwnedChk.checked) {
            baseMatches = row.getAttribute('data-has-owner') === '1';
          }

          // Rows with no value for a metric (e.g. SRO/co-op records with no
          // building match have no units/year built) are skipped per-metric
          // — treated as passing that one threshold — rather than hidden by
          // a NaN comparison.
          let matches = baseMatches;
          const metricPass = {};
          const metricValue = {};
          if (baseMatches && metrics.keys.length) {
            for (let i = 0; i < metrics.keys.length; i += 1) {
              const metric = metrics.keys[i];
              const threshold = thresholds[metric];
              const attrName = 'data-' + threshold.summary.attr;
              const rawValue = row.getAttribute(attrName);
              const value = rawValue === null || rawValue === '' ? NaN : parseFloat(rawValue);
              metricValue[metric] = value;
              if (Number.isNaN(value)) {
                metricPass[metric] = true;
                continue;
              }
              const pass = !((threshold.min !== null && value < threshold.min) ||
                (threshold.max !== null && value > threshold.max));
              metricPass[metric] = pass;
              if (!pass) matches = false;
            }
          }

          if (baseMatches) {
            for (let i = 0; i < metrics.keys.length; i += 1) {
              const metric = metrics.keys[i];
              const value = metricValue[metric];
              if (value === undefined || Number.isNaN(value)) continue;
              let othersPass = true;
              for (let j = 0; j < metrics.keys.length; j += 1) {
                if (j !== i && !metricPass[metrics.keys[j]]) { othersPass = false; break; }
              }
              if (!othersPass) continue;
              const bins = thresholds[metric].summary.bins || [];
              for (let b = 0; b < bins.length; b += 1) {
                const isLast = b === bins.length - 1;
                if (value >= bins[b].start && (isLast ? value <= bins[b].end : value < bins[b].end)) {
                  binCounts[metric][b] += 1;
                  break;
                }
              }
            }
          }

          row.classList.toggle('hidden', !matches);
          const checkbox = row.__checkbox;
          if (!matches) {
            if (checkbox && checkbox.checked) {
              const current = marker ? (marker._selectionRefs || 0) : 0;
              checkbox.checked = false;
              if (marker && current > 0) markers.adjustSelection(marker, -current);
            }
          }

          const wasFiltered = marker ? marker._isFiltered : null;
          markers.setVisible(marker, matches);
          // refreshAppearance() re-applies the highlight state via another
          // setStyle call — only worth doing when this tick actually flipped
          // the marker's filtered state.
          if (marker && wasFiltered !== marker._isFiltered) {
            markers.refreshAppearance(marker);
          }

          if (matches) {
            visibleBids.add(String(bid));
          }
        });

        metrics.keys.forEach(function(k) { metrics.setBarCounts(k, binCounts[k]); });

        const hideEmptyBlocks = showEmptyBlocksChk ? !showEmptyBlocksChk.checked : true;
        Object.keys(index.blocks).forEach(function(blockId) {
          var ids = index.blockBuildings[blockId] || [];
          var isEmpty = ids.length === 0;
          var row = tables.blockRowById[blockId];
          // The neighbourhood filter always has to be checked against the
          // block's own local_area (data-area), never inferred solely from
          // which of its member buildings are visible: the block<->building
          // spatial join has a known data bug where a handful of blocks pick
          // up member buildings from other, sometimes distant, neighbourhoods
          // (e.g. a "Fairview" block claiming a Marpole or Strathcona
          // building) — relying on hasVisible alone let a block from one
          // neighbourhood stay on-screen just because one of its mismatched
          // buildings belonged to whichever neighbourhood *was* selected,
          // which is what made toggling one neighbourhood appear to affect
          // blocks "across the whole city".
          var blockArea = row ? (row.getAttribute('data-area') || '').toLowerCase().trim() : '';
          var hoodMatch = true;
          if (restrictHoods) {
            hoodMatch = areaSelectionMatches(
              blockArea,
              row ? row.getAttribute('data-chinatown') === '1' : false,
              row ? row.getAttribute('data-village') === '1' : false,
            );
          }
          var shouldHide;
          if (isEmpty) {
            // Empty blocks have no buildings to derive visibility from at all.
            shouldHide = hideEmptyBlocks || !hoodMatch;
          } else {
            var hasVisible = ids.some(function(id) { return visibleBids.has(String(id)); });
            shouldHide = !hasVisible || !hoodMatch;
          }
          var layer = index.blocks[blockId];
          if (row) {
            row.classList.toggle('hidden', shouldHide);
            const checkbox = row.__checkbox;
            if (shouldHide && checkbox && checkbox.checked) {
              checkbox.checked = false;
              if (layer) layer._selectionRefs = 0;
              selection.blockMarkers(blockId, false);
            }
          }
          blocks.setFiltered(blockId, shouldHide);
        });

        // Re-stretch the block color scale to whichever blocks are visible
        // now that this pass's filtering is settled (e.g. narrowing to a
        // single selected neighbourhood re-scales hue to that
        // neighbourhood's own min/max instead of the whole dataset's).
        blocks.recomputeScale();

        // Was a per-row `document.querySelector('...:not(.hidden)')` CSS scan over all
        // building rows for every one of ~1,500 landlords — O(landlords x buildings) via
        // the selector engine, on every slider tick. index.owners (built once at
        // load) plus the marker._isFiltered flag set just above give the same answer as
        // a plain array check with no DOM/CSS involved.
        tables.ownerRows.forEach(function(row) {
          var owner = row.getAttribute('data-owner');
          var markers = index.owners[owner] || [];
          var hasVisible = markers.some(function(m) { return !m._isFiltered; });
          row.classList.toggle('hidden', !hasVisible);
          const checkbox = row.__checkbox;
          if (!hasVisible && checkbox && checkbox.checked) {
            checkbox.checked = false;
            selection.owner(owner, false);
          }
        });

        tables.networkRows.forEach(function(row) {
          var network = row.getAttribute('data-network');
          var markers = index.networks[network] || [];
          var hasVisible = markers.some(function(m) { return !m._isFiltered; });
          row.classList.toggle('hidden', !hasVisible);
          const checkbox = row.__checkbox;
          if (!hasVisible && checkbox && checkbox.checked) {
            checkbox.checked = false;
            selection.network(network, false);
          }
        });

        tables.neighbourhoodRows.forEach(function(row) {
          var hoodKey = (row.getAttribute('data-area') || '').toLowerCase().trim();
          var markers = index.hoods[hoodKey] || [];
          var hasVisible = markers.some(function(m) { return !m._isFiltered; });
          row.classList.toggle('hidden', !hasVisible);
          const checkbox = row.__checkbox;
          if (!hasVisible && checkbox && checkbox.checked) {
            checkbox.checked = false;
            selection.hood(hoodKey, false);
          }
        });
        tables.refreshAfterFilter();

        status.updateDataset();
        status.updateMapView();
        tables.updateSummaryBar();
        tables.updateGroupTableSummaries();
        updateSectionCounts(selectedHoods.length, selectedHousing.length, thresholds);
        if (typeof ctx.onFilter === 'function') ctx.onFilter(visibleBids);
      }

      if (showEmptyBlocksChk) showEmptyBlocksChk.addEventListener('change', applyFilters);
      if (landlordFilter) landlordFilter.onChange(scheduleApplyFilters);
      if (onlyIssuesChk) onlyIssuesChk.addEventListener('change', applyFilters);
      if (onlyOwnedChk) onlyOwnedChk.addEventListener('change', applyFilters);
      if (onlyUnitsChk) onlyUnitsChk.addEventListener('change', applyFilters);
      hoodInputs.forEach(function(inp) { inp.addEventListener('change', applyFilters); });

      housingChips.forEach(function(chip) {
        chip.addEventListener('click', function() {
          chip.setAttribute('aria-pressed', chip.getAttribute('aria-pressed') === 'true' ? 'false' : 'true');
          applyFilters();
        });
      });

      // Per-section Clear: resets that section's controls only.
      const clearSection = {
        area: function() {
          hoodInputs.forEach(function(inp) { inp.checked = false; });
        },
        ownership: function() {
          if (landlordFilter) landlordFilter.clear();
          if (onlyOwnedChk) onlyOwnedChk.checked = false;
        },
        building: function() {
          housingChips.forEach(function(chip) { chip.setAttribute('aria-pressed', 'false'); });
          if (onlyIssuesChk) onlyIssuesChk.checked = false;
          if (onlyUnitsChk) onlyUnitsChk.checked = false;
          metrics.keys.forEach(function(metric) {
            if (metrics.controls[metric].section === 'building') metrics.reset(metric);
          });
        },
        value: function() {
          metrics.keys.forEach(function(metric) {
            if (metrics.controls[metric].section === 'value') metrics.reset(metric);
          });
        },
      };
      Object.keys(sectionCounts).forEach(function(sec) {
        const btn = sectionCounts[sec].clear;
        if (!btn) return;
        btn.addEventListener('click', function(e) {
          // Inside <summary> (Assessed value), don't also toggle the section.
          e.preventDefault();
          clearSection[sec]();
          applyFilters();
        });
      });

      let searchDebounce = null;

      initPaneResize();
      initMobilePanels();

      if (showBuildingsChk) {
        toggleLayerVisibility(layerBuildings, showBuildingsChk.checked !== false);
        showBuildingsChk.addEventListener('change', function() {
          toggleLayerVisibility(layerBuildings, showBuildingsChk.checked !== false);
          if (showBuildingsChk.checked) restack.now();
          updateLegendVisibility();
        });
      } else {
        toggleLayerVisibility(layerBuildings, true);
      }
      if (colorBlocksChk) {
        applyBlockColorScaling(colorBlocksChk.checked !== false);
        colorBlocksChk.addEventListener('change', function() {
          applyBlockColorScaling(colorBlocksChk.checked !== false);
        });
      } else {
        applyBlockColorScaling(true);
      }
      if (vizBlocksChk) {
        toggleLayerVisibility(layerBlocks, vizBlocksChk.checked !== false);
        vizBlocksChk.addEventListener('change', function() {
          toggleLayerVisibility(layerBlocks, vizBlocksChk.checked);
          if (vizBlocksChk.checked) { restack.sendBlocksToBack(); restack.now(); }
          updateLegendVisibility();
        });
      } else {
        toggleLayerVisibility(layerBlocks, true);
      }
      // Chinatown and Villages Plan sit under Neighbourhood boundaries in
      // Show on map: each is drawn only while it and the parent are ticked.
      syncBoundaryLayers();
      [vizNeighbourhoodsChk, vizChinatownChk, vizVillagesChk].forEach(function(chk) {
        if (!chk) return;
        chk.addEventListener('change', function() {
          syncBoundaryLayers();
          updateLegendVisibility();
        });
      });
      applyHousingTypeFilter();
      if (vizShowHousingTypeChk) vizShowHousingTypeChk.addEventListener('change', applyHousingTypeFilter);
      if (vizShowIssuesChk) vizShowIssuesChk.addEventListener('change', applyHousingTypeFilter);

      if (resetBtn) {
        resetBtn.addEventListener('click', function() {
          if (showEmptyBlocksChk) showEmptyBlocksChk.checked = false;
          hoodInputs.forEach(function(inp) { inp.checked = false; });
          housingChips.forEach(function(chip) { chip.setAttribute('aria-pressed', 'false'); });
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
          if (landlordFilter) landlordFilter.clear();
          if (onlyIssuesChk) {
            onlyIssuesChk.checked = false;
          }
          if (onlyOwnedChk) {
            onlyOwnedChk.checked = false;
          }
          if (onlyUnitsChk) onlyUnitsChk.checked = false;
          selection.clearAll();
          metrics.keys.forEach(metrics.reset);
          applyFilters();
          updateLegendVisibility();
        });
      }

      metrics.updateAllLabels();
      updateLegendVisibility();
      applyFilters();
    } catch (e) {
      wireUpAttempts += 1;
      if (wireUpAttempts > 50) {
        console.error('wireUp() failed after ' + wireUpAttempts + ' attempts, giving up:', e);
        return;
      }
      setTimeout(wireUp, 120);
    }
  }

  assignLoadedData(ctx.filterConfig, ctx.markers, ctx.buildingData);
  if (document.readyState === 'complete') {
    wireUp();
  } else {
    window.addEventListener('load', wireUp);
  }
}
