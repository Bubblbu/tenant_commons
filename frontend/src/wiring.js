import { initPaneResize as initPaneGutters } from './pane-resize';
import { pinLast } from './tables';
import { createBlockStyler } from './wiring/block-style';
import { buildMapIndex } from './wiring/indexes';
import { createMarkerStyler, createRestack } from './wiring/marker-style';
import { buildMetricControls } from './wiring/metric-controls';

export function startWiring(ctx) {
  let filterConfig = {};
  let markerMetadata = [];
  let buildingData = {};
  let buildingRecords = {};
  let buildingColumnOrder = [];
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
    buildingRecords = (buildingData && buildingData.records) || {};
    buildingColumnOrder = (buildingData && Array.isArray(buildingData.columns)) ? buildingData.columns.slice() : [];
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


      function setOwnerSelection(ownerKey, selected) {
        var arr = index.owners[ownerKey] || [];
        arr.forEach(function(marker) {
          markers.adjustSelection(marker, selected ? +1 : -1);
        });
      }

      function setNetworkSelection(networkKey, selected) {
        var arr = index.networks[networkKey] || [];
        arr.forEach(function(marker) {
          markers.adjustSelection(marker, selected ? +1 : -1);
        });
      }

      function setHoodSelection(hoodKey, selected) {
        var arr = index.hoods[hoodKey] || [];
        arr.forEach(function(marker) {
          markers.adjustSelection(marker, selected ? +1 : -1);
        });
      }

      function setBlockSelectionMarkers(blockId, selected) {
        var ids = index.blockBuildings[String(blockId)] || [];
        ids.forEach(function(bid) {
          var marker = index.buildings[String(bid)];
          if (!marker) return;
          markers.adjustSelection(marker, selected ? +1 : -1);
        });
      }

      function collectSelectedBuildingIds() {
        const ids = [];
        Object.keys(index.buildings).forEach(function(key) {
          const marker = index.buildings[key];
          if (marker && !marker._isFiltered && (marker._selectionRefs || 0) > 0) {
            ids.push(String(key));
          }
        });
        return ids;
      }

      function escapeCSV(value) {
        if (value === null || value === undefined) return '';
        let normalized = value;
        if (typeof normalized === 'object') {
          try {
            normalized = JSON.stringify(normalized);
          } catch (err) {
            normalized = String(normalized);
          }
        }
        let text = String(normalized);
        if (/[",\n\r]/.test(text)) {
          text = '"' + text.replace(/"/g, '""') + '"';
        }
        return text;
      }

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

      function handleSelectionChange(evt) {
        var cb = evt.target;
        if (!cb.classList.contains('row-select')) return;
        var row = cb.closest('tr');
        if (row) row.classList.toggle('selected', cb.checked);
        var typ = cb.dataset.type;
        var key = cb.dataset.target;
        if (typ === 'building') {
          markers.adjustSelection(index.buildings[key], cb.checked ? +1 : -1);
        } else if (typ === 'block') {
          blocks.adjustSelection(index.blocks[key], cb.checked ? +1 : -1);
          setBlockSelectionMarkers(key, cb.checked);
        } else if (typ === 'owner') {
          setOwnerSelection(key, cb.checked);
        } else if (typ === 'network') {
          setNetworkSelection(key, cb.checked);
        } else if (typ === 'neighbourhood') {
          setHoodSelection(key.toLowerCase().trim(), cb.checked);
        }
        updateSummaryBar();
        updateGroupTableSummaries();
      }

      function getSortValue(row, index, type) {
        var cell = row.children[index];
        if (!cell) return type === 'number' ? NaN : '';
        var raw = cell.getAttribute('data-sort-value');
        if (raw === null) raw = cell.textContent || '';
        if (type === 'number') {
          var num = parseFloat(String(raw).replace(/[^0-9\\.-]/g, ''));
          return isNaN(num) ? NaN : num;
        }
        return String(raw).toLowerCase();
      }

      function sortByHeader(event) {
        // An explainer icon inside the header shows its tooltip; it doesn't sort.
        if (event.target && event.target.closest && event.target.closest('.prov')) return;
        var th = event.currentTarget;
        var sortType = th.dataset.sort || 'text';
        if (sortType === 'none') return;
        var table = th.closest('table');
        if (!table) return;
        var tbody = table.querySelector('tbody');
        if (!tbody) return;
        var headers = Array.from(th.parentNode.children);
        var columnIndex = headers.indexOf(th);
        var prev = th.dataset.sortDir || 'desc';
        var direction = prev === 'asc' ? 'desc' : 'asc';
        th.dataset.sortDir = direction;
        headers.forEach(function(header) {
          if (header !== th) header.removeAttribute('data-sort-dir');
        });
        var rows = Array.from(tbody.querySelectorAll('tr'));
        var rowsWithIndex = rows.map(function(row, idx) { return { row: row, idx: idx }; });
        rowsWithIndex.sort(function(a, b) {
          var va = getSortValue(a.row, columnIndex, sortType);
          var vb = getSortValue(b.row, columnIndex, sortType);
          var cmp;
          if (sortType === 'number') {
            var aNaN = isNaN(va);
            var bNaN = isNaN(vb);
            if (aNaN && bNaN) cmp = 0;
            else if (aNaN) cmp = 1;
            else if (bNaN) cmp = -1;
            else cmp = va - vb;
          } else {
            cmp = String(va).localeCompare(String(vb));
          }
          if (cmp === 0) cmp = a.idx - b.idx;
          return direction === 'asc' ? cmp : -cmp;
        });
        // "Not on record" (data-pin="last") stays at the bottom in either direction.
        pinLast(rowsWithIndex.map(function(item) { return item.row; })).forEach(function(row) {
          tbody.appendChild(row);
        });
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
      // Toggling a FeatureGroup/GeoJSON layer on/off (e.g. "Show buildings",
      // "Show blocks") fires 'layeradd'/'layerremove' on the map once PER CHILD
      // layer — thousands of times for ~5,000 building markers or ~4,600 block
      // features — not once for the group. Running updateMapStatus()/
      // applyZoomScaling() (each an O(buildings) scan) synchronously on every one
      // of those events is what froze the page on toggle. Coalesce to at most
      // once per animation frame, same pattern as scheduleApplyFilters() below.
      let mapStatusScheduled = false;
      function scheduleMapStatusUpdate() {
        if (mapStatusScheduled) return;
        mapStatusScheduled = true;
        window.requestAnimationFrame(function() {
          mapStatusScheduled = false;
          updateMapStatus();
          applyZoomScaling();
        });
      }
      if (mapInstance && typeof mapInstance.on === 'function') {
        mapInstance.on('moveend', scheduleMapStatusUpdate);
        mapInstance.on('zoomend', scheduleMapStatusUpdate);
        mapInstance.on('layeradd', scheduleMapStatusUpdate);
        mapInstance.on('layerremove', scheduleMapStatusUpdate);
      }
      if (mapInstance && typeof mapInstance.invalidateSize === 'function') {
        setTimeout(function() {
          mapInstance.invalidateSize({ animate: false });
          applyZoomScaling();
          updateMapStatus();
        }, 50);
      }

      const tabB = document.getElementById('tab-buildings');
      const tabK = document.getElementById('tab-blocks');
      const tabL = document.getElementById('tab-landlords');
      const tabN = document.getElementById('tab-neighbourhoods');
      const paneB = document.getElementById('pane-buildings');
      const paneK = document.getElementById('pane-blocks');
      const paneL = document.getElementById('pane-landlords');
      const paneN = document.getElementById('pane-neighbourhoods');
      function activate(which) {
        [tabB, tabK, tabL, tabN].forEach(btn => btn && btn.classList.remove('active'));
        [paneB, paneK, paneL, paneN].forEach(pane => pane && pane.classList.remove('active'));
        if (which === 'buildings') { if (tabB) tabB.classList.add('active'); if (paneB) paneB.classList.add('active'); }
        else if (which === 'blocks') { if (tabK) tabK.classList.add('active'); if (paneK) paneK.classList.add('active'); }
        else if (which === 'neighbourhoods') { if (tabN) tabN.classList.add('active'); if (paneN) paneN.classList.add('active'); }
        else { if (tabL) tabL.classList.add('active'); if (paneL) paneL.classList.add('active'); }
        refreshStaleGroupRows();
      }
      if (tabB) tabB.addEventListener('click', () => activate('buildings'));
      if (tabK) tabK.addEventListener('click', () => activate('blocks'));
      if (tabL) tabL.addEventListener('click', () => activate('landlords'));
      if (tabN) tabN.addEventListener('click', () => activate('neighbourhoods'));

      document.querySelectorAll('table.data thead th').forEach(function(th) {
        if ((th.dataset.sort || 'none') !== 'none') {
          th.addEventListener('click', sortByHeader);
        }
      });

      document.querySelectorAll('.row-select').forEach(function(cb) {
        cb.addEventListener('change', handleSelectionChange);
      });

      document.querySelectorAll('#blocks-table tbody tr').forEach(function(row) {
        var id = row.getAttribute('data-block');
        row.addEventListener('mouseenter', function() { blocks.hover(id, true); });
        row.addEventListener('mouseleave', function() { blocks.hover(id, false); });
      });

      document.querySelectorAll('#buildings-table tbody tr').forEach(function(row) {
        var bid = row.getAttribute('data-bid');
        row.addEventListener('mouseenter', function() { markers.hover([index.buildings[bid]], true); });
        row.addEventListener('mouseleave', function() { markers.hover([index.buildings[bid]], false); });
      });

      document.querySelectorAll('#owners-table tbody tr').forEach(function(row) {
        var key = row.getAttribute('data-owner');
        row.addEventListener('mouseenter', function() { markers.hover(index.owners[key] || [], true); });
        row.addEventListener('mouseleave', function() { markers.hover(index.owners[key] || [], false); });
      });

      document.querySelectorAll('#networks-table tbody tr').forEach(function(row) {
        var key = row.getAttribute('data-network');
        row.addEventListener('mouseenter', function() { markers.hover(index.networks[key] || [], true); });
        row.addEventListener('mouseleave', function() { markers.hover(index.networks[key] || [], false); });
      });

      document.querySelectorAll('#neighbourhoods-table tbody tr').forEach(function(row) {
        var hoodKey = (row.getAttribute('data-area') || '').toLowerCase().trim();
        row.addEventListener('mouseenter', function() { markers.hover(index.hoods[hoodKey] || [], true); });
        row.addEventListener('mouseleave', function() { markers.hover(index.hoods[hoodKey] || [], false); });
      });

      const hoodInputs = Array.from(document.querySelectorAll('.filter-neighbourhood-option'));

      // Cached once: applyFilters() runs on every slider tick, so re-querying the DOM
      // (and re-resolving each row's checkbox) on every call is the difference between
      // a smooth drag and a janky one at ~5,000 building rows. Row sets never change
      // after initial render — only their hidden/visible state does.
      const buildingRows = Array.from(document.querySelectorAll('#buildings-table tbody tr'));
      buildingRows.forEach(function(row) { row.__checkbox = row.querySelector('.row-select'); });

      // Column indices of the aggregate cells that get recomputed live from
      // currently-visible buildings on every applyFilters() pass (see
      // updateGroupRowValues below) — must match the <thead> order in sidebar.html.
      function cacheRowCells(rows, colMap) {
        rows.forEach(function(row) {
          row.__cells = {};
          Object.keys(colMap).forEach(function(key) {
            row.__cells[key] = row.children[colMap[key]] || null;
          });
        });
      }

      const ownerRows = Array.from(document.querySelectorAll('#owners-table tbody tr'));
      ownerRows.forEach(function(row) { row.__checkbox = row.querySelector('.row-select'); });
      cacheRowCells(ownerRows, { bldgs: 2, units: 3, avg: 4 });

      const networkRows = Array.from(document.querySelectorAll('#networks-table tbody tr'));
      networkRows.forEach(function(row) { row.__checkbox = row.querySelector('.row-select'); });
      cacheRowCells(networkRows, { bldgs: 2, units: 3, avg: 4 });

      const neighbourhoodRows = Array.from(document.querySelectorAll('#neighbourhoods-table tbody tr'));
      neighbourhoodRows.forEach(function(row) { row.__checkbox = row.querySelector('.row-select'); });
      cacheRowCells(neighbourhoodRows, { bldgs: 2, units: 3, avg: 4 });

      const blockRowById = {};
      const blockRows = Array.from(document.querySelectorAll('#blocks-table tbody tr'));
      cacheRowCells(blockRows, { bldgs: 2, units: 3, avg: 4, year: 5 });
      blockRows.forEach(function(row) {
        row.__checkbox = row.querySelector('.row-select');
        blockRowById[row.getAttribute('data-block')] = row;
      });
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
      const statusCells = {
        total: {
          units: document.getElementById('status-total-units'),
          buildings: document.getElementById('status-total-buildings'),
        },
        view: {
          units: document.getElementById('status-view-units'),
          buildings: document.getElementById('status-view-buildings'),
        },
      };
      const summaryLabelEl = document.getElementById('summary-buildings-label');
      const summaryUnitsEl = document.getElementById('summary-buildings-units');
      const summaryRowsEl = document.getElementById('summary-buildings-rows');
      const legendContainerEl = document.getElementById('legend-map');
      const legendBlocksEl = document.getElementById('legend-blocks-section');
      const legendBuildingDetailsEl = document.getElementById('legend-building-details-section');
      const legendBoundariesEl = document.getElementById('legend-boundaries-section');

      const datasetTotals = (filterConfig && filterConfig.dataset_totals) || null;
      const totalBuildings = datasetTotals && typeof datasetTotals.buildings === 'number' ? datasetTotals.buildings : null;
      const totalUnits = datasetTotals && typeof datasetTotals.units === 'number' ? datasetTotals.units : null;

      function setStatusCell(cell, value) {
        if (!cell) return;
        if (value === null || value === undefined || Number.isNaN(value)) {
          cell.textContent = '–';
          cell.setAttribute('data-value', 'none');
        } else {
          cell.textContent = Number(value).toLocaleString();
          cell.setAttribute('data-value', 'value');
        }
      }

      function updateDatasetStatus() {
        if (!statusCells) return;
        setStatusCell(statusCells.total.units, totalUnits);
        setStatusCell(statusCells.total.buildings, totalBuildings);
        setStatusCell(statusCells.view.units, null);
        setStatusCell(statusCells.view.buildings, null);
      }

      function computeMapSummary() {
        if (!mapInstance || typeof mapInstance.getBounds !== 'function') {
          return { buildings: null, units: null };
        }
        const bounds = mapInstance.getBounds();
        let buildingCount = 0;
        let unitTotal = 0;
        Object.keys(index.buildings).forEach(function(key) {
          const marker = index.buildings[key];
          if (!marker || marker._isFiltered) return;
          if (typeof mapInstance.hasLayer === 'function' && !mapInstance.hasLayer(marker)) return;
          if (typeof marker.getLatLng !== 'function') return;
          const latLng = marker.getLatLng();
          if (!latLng || typeof bounds.contains !== 'function' || !bounds.contains(latLng)) return;
          buildingCount += 1;
          const unitsVal = Number(marker._units);
          if (Number.isFinite(unitsVal)) unitTotal += unitsVal;
        });
        return {
          buildings: buildingCount,
          units: unitTotal,
        };
      }

      function updateMapStatus() {
        if (!statusCells) return;
        const summary = computeMapSummary();
        setStatusCell(statusCells.view.units, summary.units);
        setStatusCell(statusCells.view.buildings, summary.buildings);
      }

      function updateSummaryBar() {
        if (!summaryLabelEl || !summaryUnitsEl || !summaryRowsEl) return;
        const allRows = buildingRows;
        const selectedRows = allRows.filter(function(row) {
          const cb = row.__checkbox;
          return cb && cb.checked;
        });
        const targetRows = selectedRows.length ? selectedRows : allRows.filter(function(row) {
          return !row.classList.contains('hidden') && !row.classList.contains('search-hidden');
        });
        const label = selectedRows.length ? 'Totals (selected)' : 'Totals (visible)';
        let unitsSum = 0;
        targetRows.forEach(function(row) {
          const units = Number(row.getAttribute('data-units'));
          if (Number.isFinite(units)) unitsSum += units;
        });
        summaryLabelEl.textContent = label;
        summaryUnitsEl.textContent = unitsSum.toLocaleString();
        summaryRowsEl.textContent = (targetRows.length || 0).toLocaleString() + (targetRows.length === 1 ? ' row' : ' rows');
      }

      // Recomputes one Blocks/Landlords/Neighbourhoods row's Bldgs/Units/Avg
      // (and, for blocks, Median year) cells from only the buildings currently
      // passing the active filters — the row's own columns were previously baked
      // in at build time from the full dataset and never changed when a filter
      // (e.g. the unit-size slider) hid some of its buildings.
      // `items` is either an array of markers (landlords/neighbourhoods, via
      // index.owners/index.hoods) or an array of building-id strings
      // (blocks, via index.blockBuildings) — `resolveMarker` resolves the
      // latter without allocating an intermediate array on every call.
      // `includeYear` skips the years array/sort entirely for landlord and
      // neighbourhood rows, which never display a median-year column — with
      // ~1,500 landlord rows re-evaluated per slider-drag frame, that sort was
      // pure waste for a value nothing ever reads.
      function computeLiveGroupMetrics(items, resolveMarker, includeYear) {
        let bldgs = 0;
        let units = 0;
        const years = includeYear ? [] : null;
        items.forEach(function(item) {
          const marker = resolveMarker ? resolveMarker(item) : item;
          if (!marker || marker._isFiltered) return;
          bldgs += 1;
          const u = Number(marker._units);
          if (Number.isFinite(u)) units += u;
          if (includeYear && marker._yearBuilt !== null && marker._yearBuilt !== undefined) {
            years.push(marker._yearBuilt);
          }
        });
        let medianYear = null;
        if (includeYear && years.length) {
          years.sort(function(a, b) { return a - b; });
          const mid = Math.floor(years.length / 2);
          medianYear = years.length % 2 ? years[mid] : Math.round((years[mid - 1] + years[mid]) / 2);
        }
        return { bldgs: bldgs, units: units, avg: bldgs > 0 ? units / bldgs : 0, medianYear: medianYear };
      }

      function setCellValue(cell, sortValue, text) {
        if (!cell) return;
        cell.setAttribute('data-sort-value', String(sortValue));
        cell.textContent = text;
      }

      // Skips all DOM writes when nothing actually changed since the last call —
      // during a slider drag, most blocks/landlords/neighbourhoods are unaffected
      // by a given threshold nudge, and writing textContent/attributes on ~6,000
      // rows every animation frame (whether or not the numbers moved) was the
      // main cause of the drag feeling sluggish.
      function updateGroupRowValues(row, items, resolveMarker) {
        if (!row || !row.__cells) return;
        const includeYear = !!row.__cells.year;
        const m = computeLiveGroupMetrics(items, resolveMarker, includeYear);
        const prev = row.__lastMetrics;
        if (prev && prev.bldgs === m.bldgs && prev.units === m.units && prev.medianYear === m.medianYear) {
          return;
        }
        row.__lastMetrics = m;
        setCellValue(row.__cells.bldgs, m.bldgs, m.bldgs.toLocaleString());
        setCellValue(row.__cells.units, m.units, m.units.toLocaleString());
        setCellValue(row.__cells.avg, m.avg, m.avg.toFixed(1));
        if (includeYear) {
          setCellValue(row.__cells.year, m.medianYear === null ? '' : m.medianYear, m.medianYear === null ? '' : String(m.medianYear));
        }
        // Keep the row's own data attributes in sync too, since
        // updateGroupTableSummary()'s footer totals sum from these.
        row.setAttribute('data-bldgs', String(m.bldgs));
        row.setAttribute('data-units', String(m.units));
      }

      // Recounting every Blocks/Landlords/Neighbourhoods row was most of a filter
      // pass's cost, but only one sidebar tab is on screen at a time. A pass
      // recounts the visible tab's rows and marks the others stale;
      // activate() recounts a stale tab when it's opened.
      const staleGroupRows = { blocks: false, landlords: false, neighbourhoods: false };
      const groupPanes = { blocks: paneK, landlords: paneL, neighbourhoods: paneN };
      function blockBuilding(id) { return index.buildings[id]; }
      function refreshGroupRows(which) {
        if (which === 'blocks') {
          blockRows.forEach(function(row) {
            updateGroupRowValues(row, index.blockBuildings[row.getAttribute('data-block')] || [], blockBuilding);
          });
        } else if (which === 'landlords') {
          ownerRows.forEach(function(row) { updateGroupRowValues(row, index.owners[row.getAttribute('data-owner')] || []); });
          networkRows.forEach(function(row) { updateGroupRowValues(row, index.networks[row.getAttribute('data-network')] || []); });
        } else if (which === 'neighbourhoods') {
          neighbourhoodRows.forEach(function(row) {
            updateGroupRowValues(row, index.hoods[(row.getAttribute('data-area') || '').toLowerCase().trim()] || []);
          });
        }
      }
      // After a filter pass: recount what's on screen, defer the rest.
      function refreshGroupRowsAfterFilter() {
        Object.keys(staleGroupRows).forEach(function(which) {
          const pane = groupPanes[which];
          if (pane && pane.classList.contains('active')) {
            refreshGroupRows(which);
            staleGroupRows[which] = false;
          } else {
            staleGroupRows[which] = true;
          }
        });
      }
      function refreshStaleGroupRows() {
        let any = false;
        Object.keys(staleGroupRows).forEach(function(which) {
          const pane = groupPanes[which];
          if (!staleGroupRows[which] || !pane || !pane.classList.contains('active')) return;
          refreshGroupRows(which);
          staleGroupRows[which] = false;
          any = true;
        });
        if (any) updateGroupTableSummaries();
      }

      // Shared footer-summary logic for the Blocks/Landlords/Neighbourhoods tabs,
      // which all use the same Bldgs/Units/Avg Units per Bldg column shape
      // (unlike Buildings, whose footer tracks Units for the building row
      // rather than a per-group aggregate).
      function updateGroupTableSummary(rows, ids) {
        const labelEl = document.getElementById(ids.label);
        if (!labelEl) return;
        const selectedRows = rows.filter(function(row) {
          const cb = row.__checkbox;
          return cb && cb.checked;
        });
        const targetRows = selectedRows.length ? selectedRows : rows.filter(function(row) {
          return !row.classList.contains('hidden') && !row.classList.contains('search-hidden');
        });
        const label = selectedRows.length ? 'Totals (selected)' : 'Totals (visible)';
        let bldgsSum = 0;
        let unitsSum = 0;
        targetRows.forEach(function(row) {
          const bldgs = Number(row.getAttribute('data-bldgs'));
          const units = Number(row.getAttribute('data-units'));
          if (Number.isFinite(bldgs)) bldgsSum += bldgs;
          if (Number.isFinite(units)) unitsSum += units;
        });
        const avg = bldgsSum > 0 ? unitsSum / bldgsSum : 0;
        const rowCount = targetRows.length || 0;
        labelEl.textContent = label + ' — ' + rowCount.toLocaleString() + (rowCount === 1 ? ' row' : ' rows');
        const bldgsEl = document.getElementById(ids.bldgs);
        const unitsEl = document.getElementById(ids.units);
        const avgEl = document.getElementById(ids.avg);
        if (bldgsEl) bldgsEl.textContent = bldgsSum.toLocaleString();
        if (unitsEl) unitsEl.textContent = unitsSum.toLocaleString();
        if (avgEl) avgEl.textContent = avg.toFixed(1);
      }

      function updateGroupTableSummaries() {
        updateGroupTableSummary(blockRows, {
          label: 'summary-blocks-label', bldgs: 'summary-blocks-bldgs',
          units: 'summary-blocks-units', avg: 'summary-blocks-avg',
        });
        updateGroupTableSummary(ownerRows, {
          label: 'summary-owners-label', bldgs: 'summary-owners-bldgs',
          units: 'summary-owners-units', avg: 'summary-owners-avg',
        });
        updateGroupTableSummary(networkRows, {
          label: 'summary-networks-label', bldgs: 'summary-networks-bldgs',
          units: 'summary-networks-units', avg: 'summary-networks-avg',
        });
        updateGroupTableSummary(neighbourhoodRows, {
          label: 'summary-neighbourhoods-label', bldgs: 'summary-neighbourhoods-bldgs',
          units: 'summary-neighbourhoods-units', avg: 'summary-neighbourhoods-avg',
        });
      }

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
      updateDatasetStatus();
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
        buildingRows.forEach(function(row) {
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
          var row = blockRowById[blockId];
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
              setBlockSelectionMarkers(blockId, false);
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
        ownerRows.forEach(function(row) {
          var owner = row.getAttribute('data-owner');
          var markers = index.owners[owner] || [];
          var hasVisible = markers.some(function(m) { return !m._isFiltered; });
          row.classList.toggle('hidden', !hasVisible);
          const checkbox = row.__checkbox;
          if (!hasVisible && checkbox && checkbox.checked) {
            checkbox.checked = false;
            setOwnerSelection(owner, false);
          }
        });

        networkRows.forEach(function(row) {
          var network = row.getAttribute('data-network');
          var markers = index.networks[network] || [];
          var hasVisible = markers.some(function(m) { return !m._isFiltered; });
          row.classList.toggle('hidden', !hasVisible);
          const checkbox = row.__checkbox;
          if (!hasVisible && checkbox && checkbox.checked) {
            checkbox.checked = false;
            setNetworkSelection(network, false);
          }
        });

        neighbourhoodRows.forEach(function(row) {
          var hoodKey = (row.getAttribute('data-area') || '').toLowerCase().trim();
          var markers = index.hoods[hoodKey] || [];
          var hasVisible = markers.some(function(m) { return !m._isFiltered; });
          row.classList.toggle('hidden', !hasVisible);
          const checkbox = row.__checkbox;
          if (!hasVisible && checkbox && checkbox.checked) {
            checkbox.checked = false;
            setHoodSelection(hoodKey, false);
          }
        });
        refreshGroupRowsAfterFilter();

        updateDatasetStatus();
        updateMapStatus();
        updateSummaryBar();
        updateGroupTableSummaries();
        updateSectionCounts(selectedHoods.length, selectedHousing.length, thresholds);
        if (typeof ctx.onFilter === 'function') ctx.onFilter(visibleBids);
      }

      if (showEmptyBlocksChk) showEmptyBlocksChk.addEventListener('change', applyFilters);
      if (landlordFilter) landlordFilter.onChange(scheduleApplyFilters);
      // The sidebar table search (table-search.ts) only hides table rows, so
      // just the footer totals need refreshing — no map/filter pass.
      document.addEventListener('tablesearch', function() {
        updateSummaryBar();
        updateGroupTableSummaries();
      });
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
          document.querySelectorAll('.row-select').forEach(function(cb) {
            if (cb.checked) {
              cb.checked = false;
              cb.dispatchEvent(new Event('change', { bubbles: true }));
            }
          });
          metrics.keys.forEach(metrics.reset);
          applyFilters();
          updateLegendVisibility();
        });
      }

      // "Currently visible" matches exactly what computeMapSummary() already counts
      // for the sidebar's "In view" stats row: passes the active filters, on the map
      // layer, and within the current pan/zoom bounds — not just the filter state.
      function collectVisibleBuildingIds() {
        const ids = [];
        if (!mapInstance || typeof mapInstance.getBounds !== 'function') return ids;
        const bounds = mapInstance.getBounds();
        Object.keys(index.buildings).forEach(function(key) {
          const marker = index.buildings[key];
          if (!marker || marker._isFiltered) return;
          if (typeof mapInstance.hasLayer === 'function' && !mapInstance.hasLayer(marker)) return;
          if (typeof marker.getLatLng !== 'function') return;
          const latLng = marker.getLatLng();
          if (!latLng || typeof bounds.contains !== 'function' || !bounds.contains(latLng)) return;
          ids.push(key);
        });
        return ids;
      }

      function exportVisibleBuildingsCsv() {
        const ids = collectVisibleBuildingIds();
        if (!ids.length) {
          window.alert('No buildings are currently visible to export.');
          return;
        }
        const columns = buildingColumnOrder.length
          ? buildingColumnOrder
          : Object.keys(buildingRecords[ids[0]] || {});
        const lines = [columns.map(escapeCSV).join(',')];
        ids.forEach(function(id) {
          const record = buildingRecords[id] || {};
          lines.push(columns.map(function(col) { return escapeCSV(record[col]); }).join(','));
        });
        const blob = new Blob([lines.join('\r\n')], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        const timestamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
        link.href = url;
        link.download = 'buildings-visible-' + timestamp + '.csv';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      }

      const exportVisibleBtn = document.getElementById('export-visible-csv');
      if (exportVisibleBtn) {
        exportVisibleBtn.addEventListener('click', exportVisibleBuildingsCsv);
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
