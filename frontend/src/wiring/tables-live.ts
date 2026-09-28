import { pinLast } from '../tables';
import type { BuildingMarker, CachedRow, MapIndex } from './types';

export interface LiveTables {
  buildingRows: CachedRow[];
  ownerRows: CachedRow[];
  networkRows: CachedRow[];
  neighbourhoodRows: CachedRow[];
  blockRows: CachedRow[];
  blockRowById: Record<string, CachedRow>;
  updateSummaryBar(): void;
  updateGroupTableSummaries(): void;
  /** refreshGroupRowsAfterFilter: recount the visible tab, mark the rest stale. */
  refreshAfterFilter(): void;
}

interface GroupMetrics {
  bldgs: number;
  units: number;
  avg: number;
  medianYear: number | null;
}

/** Caches rows, wires tabs, header sorting, and the 'tablesearch' footer refresh. */
export function initLiveTables(index: MapIndex, doc: Document): LiveTables {
  const tabB = doc.getElementById('tab-buildings');
  const tabK = doc.getElementById('tab-blocks');
  const tabL = doc.getElementById('tab-landlords');
  const tabN = doc.getElementById('tab-neighbourhoods');
  const paneB = doc.getElementById('pane-buildings');
  const paneK = doc.getElementById('pane-blocks');
  const paneL = doc.getElementById('pane-landlords');
  const paneN = doc.getElementById('pane-neighbourhoods');

  function activate(which: string): void {
    [tabB, tabK, tabL, tabN].forEach((btn) => btn && btn.classList.remove('active'));
    [paneB, paneK, paneL, paneN].forEach((pane) => pane && pane.classList.remove('active'));
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

  function getSortValue(row: HTMLTableRowElement, colIndex: number, type: string): number | string {
    const cell = row.children[colIndex];
    if (!cell) return type === 'number' ? NaN : '';
    let raw: string | null = cell.getAttribute('data-sort-value');
    if (raw === null) raw = cell.textContent || '';
    if (type === 'number') {
      const num = parseFloat(String(raw).replace(/[^0-9\\.-]/g, ''));
      return isNaN(num) ? NaN : num;
    }
    return String(raw).toLowerCase();
  }

  function sortByHeader(event: Event): void {
    // An explainer icon inside the header shows its tooltip; it doesn't sort.
    const target = event.target as Element | null;
    if (target && target.closest && target.closest('.prov')) return;
    const th = event.currentTarget as HTMLElement;
    const sortType = th.dataset.sort || 'text';
    if (sortType === 'none') return;
    const table = th.closest('table');
    if (!table) return;
    const tbody = table.querySelector('tbody');
    if (!tbody) return;
    const headers = Array.from((th.parentNode as Element).children);
    const columnIndex = headers.indexOf(th);
    const prev = th.dataset.sortDir || 'desc';
    const direction = prev === 'asc' ? 'desc' : 'asc';
    th.dataset.sortDir = direction;
    headers.forEach((header) => {
      if (header !== th) header.removeAttribute('data-sort-dir');
    });
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const rowsWithIndex = rows.map((row, idx) => ({ row, idx }));
    rowsWithIndex.sort((a, b) => {
      const va = getSortValue(a.row, columnIndex, sortType);
      const vb = getSortValue(b.row, columnIndex, sortType);
      let cmp: number;
      if (sortType === 'number') {
        const aNaN = isNaN(va as number);
        const bNaN = isNaN(vb as number);
        if (aNaN && bNaN) cmp = 0;
        else if (aNaN) cmp = 1;
        else if (bNaN) cmp = -1;
        else cmp = (va as number) - (vb as number);
      } else {
        cmp = String(va).localeCompare(String(vb));
      }
      if (cmp === 0) cmp = a.idx - b.idx;
      return direction === 'asc' ? cmp : -cmp;
    });
    // "Not on record" (data-pin="last") stays at the bottom in either direction.
    pinLast(rowsWithIndex.map((item) => item.row)).forEach((row) => {
      tbody.appendChild(row);
    });
  }

  doc.querySelectorAll('table.data thead th').forEach((th) => {
    if (((th as HTMLElement).dataset.sort || 'none') !== 'none') {
      th.addEventListener('click', sortByHeader);
    }
  });

  // Cached once: a filter pass runs on every slider tick, so re-querying the DOM
  // (and re-resolving each row's checkbox) on every call is the difference between
  // a smooth drag and a janky one at ~5,000 building rows. Row sets never change
  // after initial render — only their hidden/visible state does.
  const buildingRows = Array.from(doc.querySelectorAll<CachedRow>('#buildings-table tbody tr'));
  buildingRows.forEach((row) => { row.__checkbox = row.querySelector('.row-select'); });

  // Column indices of the aggregate cells that get recomputed live from
  // currently-visible buildings on every filter pass (see updateGroupRowValues
  // below) — must match the <thead> order in sidebar.html.
  function cacheRowCells(rows: CachedRow[], colMap: Record<string, number>): void {
    rows.forEach((row) => {
      row.__cells = {};
      Object.keys(colMap).forEach((key) => {
        row.__cells![key] = row.children[colMap[key]] || null;
      });
    });
  }

  const ownerRows = Array.from(doc.querySelectorAll<CachedRow>('#owners-table tbody tr'));
  ownerRows.forEach((row) => { row.__checkbox = row.querySelector('.row-select'); });
  cacheRowCells(ownerRows, { bldgs: 2, units: 3, avg: 4 });

  const networkRows = Array.from(doc.querySelectorAll<CachedRow>('#networks-table tbody tr'));
  networkRows.forEach((row) => { row.__checkbox = row.querySelector('.row-select'); });
  cacheRowCells(networkRows, { bldgs: 2, units: 3, avg: 4 });

  const neighbourhoodRows = Array.from(doc.querySelectorAll<CachedRow>('#neighbourhoods-table tbody tr'));
  neighbourhoodRows.forEach((row) => { row.__checkbox = row.querySelector('.row-select'); });
  cacheRowCells(neighbourhoodRows, { bldgs: 2, units: 3, avg: 4 });

  const blockRowById: Record<string, CachedRow> = {};
  const blockRows = Array.from(doc.querySelectorAll<CachedRow>('#blocks-table tbody tr'));
  cacheRowCells(blockRows, { bldgs: 2, units: 3, avg: 4, year: 5 });
  blockRows.forEach((row) => {
    row.__checkbox = row.querySelector('.row-select');
    blockRowById[String(row.getAttribute('data-block'))] = row;
  });

  // Recomputes one Blocks/Landlords/Neighbourhoods row's Bldgs/Units/Avg
  // (and, for blocks, Median year) cells from only the buildings currently
  // passing the active filters — the row's own columns were previously baked
  // in at build time from the full dataset and never changed when a filter
  // (e.g. the unit-size slider) hid some of its buildings.
  // `items` is either an array of markers (landlords/neighbourhoods, via
  // index.owners/index.hoods) or an array of building-id strings (blocks, via
  // index.blockBuildings) — `resolveMarker` resolves the latter without
  // allocating an intermediate array on every call.
  // `includeYear` skips the years array/sort entirely for landlord and
  // neighbourhood rows, which never display a median-year column — with
  // ~1,500 landlord rows re-evaluated per slider-drag frame, that sort was
  // pure waste for a value nothing ever reads.
  function computeLiveGroupMetrics(
    items: unknown[],
    resolveMarker: ((item: unknown) => BuildingMarker | undefined) | undefined,
    includeYear: boolean,
  ): GroupMetrics {
    let bldgs = 0;
    let units = 0;
    const years: number[] | null = includeYear ? [] : null;
    items.forEach((item) => {
      const marker = resolveMarker ? resolveMarker(item) : (item as BuildingMarker);
      if (!marker || marker._isFiltered) return;
      bldgs += 1;
      const u = Number(marker._units);
      if (Number.isFinite(u)) units += u;
      if (includeYear && marker._yearBuilt !== null && marker._yearBuilt !== undefined) {
        (years as number[]).push(marker._yearBuilt);
      }
    });
    let medianYear: number | null = null;
    if (includeYear && years && years.length) {
      years.sort((a, b) => a - b);
      const mid = Math.floor(years.length / 2);
      medianYear = years.length % 2 ? years[mid] : Math.round((years[mid - 1] + years[mid]) / 2);
    }
    return { bldgs, units, avg: bldgs > 0 ? units / bldgs : 0, medianYear };
  }

  function setCellValue(cell: Element | null | undefined, sortValue: unknown, text: string): void {
    if (!cell) return;
    cell.setAttribute('data-sort-value', String(sortValue));
    cell.textContent = text;
  }

  // Skips all DOM writes when nothing actually changed since the last call —
  // during a slider drag, most blocks/landlords/neighbourhoods are unaffected
  // by a given threshold nudge, and writing textContent/attributes on ~6,000
  // rows every animation frame (whether or not the numbers moved) was the
  // main cause of the drag feeling sluggish.
  function updateGroupRowValues(
    row: CachedRow | undefined,
    items: unknown[],
    resolveMarker?: (item: unknown) => BuildingMarker | undefined,
  ): void {
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
  const staleGroupRows: Record<string, boolean> = { blocks: false, landlords: false, neighbourhoods: false };
  const groupPanes: Record<string, HTMLElement | null> = { blocks: paneK, landlords: paneL, neighbourhoods: paneN };
  function blockBuilding(id: unknown): BuildingMarker | undefined { return index.buildings[String(id)]; }
  function refreshGroupRows(which: string): void {
    if (which === 'blocks') {
      blockRows.forEach((row) => {
        updateGroupRowValues(row, index.blockBuildings[String(row.getAttribute('data-block'))] || [], blockBuilding);
      });
    } else if (which === 'landlords') {
      ownerRows.forEach((row) => { updateGroupRowValues(row, index.owners[String(row.getAttribute('data-owner'))] || []); });
      networkRows.forEach((row) => { updateGroupRowValues(row, index.networks[String(row.getAttribute('data-network'))] || []); });
    } else if (which === 'neighbourhoods') {
      neighbourhoodRows.forEach((row) => {
        updateGroupRowValues(row, index.hoods[(row.getAttribute('data-area') || '').toLowerCase().trim()] || []);
      });
    }
  }
  // After a filter pass: recount what's on screen, defer the rest.
  function refreshGroupRowsAfterFilter(): void {
    Object.keys(staleGroupRows).forEach((which) => {
      const pane = groupPanes[which];
      if (pane && pane.classList.contains('active')) {
        refreshGroupRows(which);
        staleGroupRows[which] = false;
      } else {
        staleGroupRows[which] = true;
      }
    });
  }
  function refreshStaleGroupRows(): void {
    let any = false;
    Object.keys(staleGroupRows).forEach((which) => {
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
  function updateGroupTableSummary(rows: CachedRow[], ids: { label: string; bldgs: string; units: string; avg: string }): void {
    const labelEl = doc.getElementById(ids.label);
    if (!labelEl) return;
    const selectedRows = rows.filter((row) => row.__checkbox && row.__checkbox.checked);
    const targetRows = selectedRows.length ? selectedRows : rows.filter((row) => !row.classList.contains('hidden') && !row.classList.contains('search-hidden'));
    const label = selectedRows.length ? 'Totals (selected)' : 'Totals (visible)';
    let bldgsSum = 0;
    let unitsSum = 0;
    targetRows.forEach((row) => {
      const bldgs = Number(row.getAttribute('data-bldgs'));
      const units = Number(row.getAttribute('data-units'));
      if (Number.isFinite(bldgs)) bldgsSum += bldgs;
      if (Number.isFinite(units)) unitsSum += units;
    });
    const avg = bldgsSum > 0 ? unitsSum / bldgsSum : 0;
    const rowCount = targetRows.length || 0;
    labelEl.textContent = label + ' — ' + rowCount.toLocaleString() + (rowCount === 1 ? ' row' : ' rows');
    const bldgsEl = doc.getElementById(ids.bldgs);
    const unitsEl = doc.getElementById(ids.units);
    const avgEl = doc.getElementById(ids.avg);
    if (bldgsEl) bldgsEl.textContent = bldgsSum.toLocaleString();
    if (unitsEl) unitsEl.textContent = unitsSum.toLocaleString();
    if (avgEl) avgEl.textContent = avg.toFixed(1);
  }

  function updateGroupTableSummaries(): void {
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

  const summaryLabelEl = doc.getElementById('summary-buildings-label');
  const summaryUnitsEl = doc.getElementById('summary-buildings-units');
  const summaryRowsEl = doc.getElementById('summary-buildings-rows');
  function updateSummaryBar(): void {
    if (!summaryLabelEl || !summaryUnitsEl || !summaryRowsEl) return;
    const allRows = buildingRows;
    const selectedRows = allRows.filter((row) => row.__checkbox && row.__checkbox.checked);
    const targetRows = selectedRows.length ? selectedRows : allRows.filter((row) => !row.classList.contains('hidden') && !row.classList.contains('search-hidden'));
    const label = selectedRows.length ? 'Totals (selected)' : 'Totals (visible)';
    let unitsSum = 0;
    targetRows.forEach((row) => {
      const units = Number(row.getAttribute('data-units'));
      if (Number.isFinite(units)) unitsSum += units;
    });
    summaryLabelEl.textContent = label;
    summaryUnitsEl.textContent = unitsSum.toLocaleString();
    summaryRowsEl.textContent = (targetRows.length || 0).toLocaleString() + (targetRows.length === 1 ? ' row' : ' rows');
  }

  // The sidebar table search (table-search.ts) only hides table rows, so
  // just the footer totals need refreshing — no map/filter pass.
  doc.addEventListener('tablesearch', () => {
    updateSummaryBar();
    updateGroupTableSummaries();
  });

  return {
    buildingRows, ownerRows, networkRows, neighbourhoodRows, blockRows, blockRowById,
    updateSummaryBar, updateGroupTableSummaries,
    refreshAfterFilter: refreshGroupRowsAfterFilter,
  };
}
