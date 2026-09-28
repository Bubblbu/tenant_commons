import type * as L from 'leaflet';
import type { BuildingData, FilterConfig } from '../types';
import type { BuildingMarker, MapIndex } from './types';

export function escapeCSV(value: unknown): string {
  if (value === null || value === undefined) return '';
  let normalized: unknown = value;
  if (typeof normalized === 'object') {
    try {
      normalized = JSON.stringify(normalized);
    } catch {
      normalized = String(normalized);
    }
  }
  let text = String(normalized);
  if (/[",\n\r]/.test(text)) {
    text = '"' + text.replace(/"/g, '""') + '"';
  }
  return text;
}

// Shared by computeMapSummary (createStatus) and collectVisibleBuildingIds
// (initCsvExport): a building counts as "in view" when it isn't filtered,
// its marker is on the map, and its position falls inside the current
// pan/zoom bounds. Object.keys(index.buildings) order, same as the two
// call sites had before they were split.
function markersInView(index: MapIndex, map: L.Map): [string, BuildingMarker][] {
  if (!map || typeof map.getBounds !== 'function') return [];
  const bounds = map.getBounds();
  const result: [string, BuildingMarker][] = [];
  Object.keys(index.buildings).forEach((key) => {
    const marker = index.buildings[key];
    if (!marker || marker._isFiltered) return;
    if (typeof map.hasLayer === 'function' && !map.hasLayer(marker)) return;
    if (typeof marker.getLatLng !== 'function') return;
    const latLng = marker.getLatLng();
    if (!latLng || typeof bounds.contains !== 'function' || !bounds.contains(latLng)) return;
    result.push([key, marker]);
  });
  return result;
}

export interface Status {
  updateDataset(): void;
  updateMapView(): void;
}

interface DatasetTotals {
  buildings?: unknown;
  units?: unknown;
}

export function createStatus(index: MapIndex, map: L.Map, filterConfig: FilterConfig, doc: Document): Status {
  const statusCells = {
    total: {
      units: doc.getElementById('status-total-units'),
      buildings: doc.getElementById('status-total-buildings'),
    },
    view: {
      units: doc.getElementById('status-view-units'),
      buildings: doc.getElementById('status-view-buildings'),
    },
  };

  const datasetTotals = (filterConfig && (filterConfig.dataset_totals as DatasetTotals | null | undefined)) || null;
  const totalBuildings = datasetTotals && typeof datasetTotals.buildings === 'number' ? datasetTotals.buildings : null;
  const totalUnits = datasetTotals && typeof datasetTotals.units === 'number' ? datasetTotals.units : null;

  function setStatusCell(cell: HTMLElement | null, value: number | null | undefined): void {
    if (!cell) return;
    if (value === null || value === undefined || Number.isNaN(value)) {
      cell.textContent = '–';
      cell.setAttribute('data-value', 'none');
    } else {
      cell.textContent = Number(value).toLocaleString();
      cell.setAttribute('data-value', 'value');
    }
  }

  function updateDataset(): void {
    setStatusCell(statusCells.total.units, totalUnits);
    setStatusCell(statusCells.total.buildings, totalBuildings);
    setStatusCell(statusCells.view.units, null);
    setStatusCell(statusCells.view.buildings, null);
  }

  function computeMapSummary(): { buildings: number | null; units: number | null } {
    if (!map || typeof map.getBounds !== 'function') {
      return { buildings: null, units: null };
    }
    const inView = markersInView(index, map);
    let unitTotal = 0;
    inView.forEach(([, marker]) => {
      const unitsVal = Number(marker._units);
      if (Number.isFinite(unitsVal)) unitTotal += unitsVal;
    });
    return { buildings: inView.length, units: unitTotal };
  }

  function updateMapView(): void {
    const summary = computeMapSummary();
    setStatusCell(statusCells.view.units, summary.units);
    setStatusCell(statusCells.view.buildings, summary.buildings);
  }

  return { updateDataset, updateMapView };
}

/** Coalesced map moveend/zoomend/layeradd/layerremove handling, plus the start-up invalidateSize. */
export function watchMap(map: L.Map, status: Status, onZoom: () => void): void {
  // Toggling a FeatureGroup/GeoJSON layer on/off (e.g. "Show buildings",
  // "Show blocks") fires 'layeradd'/'layerremove' on the map once PER CHILD
  // layer — thousands of times for ~5,000 building markers or ~4,600 block
  // features — not once for the group. Running updateMapView()/onZoom() (each
  // an O(buildings) scan) synchronously on every one of those events is what
  // froze the page on toggle. Coalesce to at most once per animation frame.
  let scheduled = false;
  function schedule(): void {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(() => {
      scheduled = false;
      status.updateMapView();
      onZoom();
    });
  }
  if (map && typeof map.on === 'function') {
    map.on('moveend', schedule);
    map.on('zoomend', schedule);
    map.on('layeradd', schedule);
    map.on('layerremove', schedule);
  }
  if (map && typeof map.invalidateSize === 'function') {
    setTimeout(() => {
      map.invalidateSize({ animate: false });
      onZoom();
      status.updateMapView();
    }, 50);
  }
}

export function initCsvExport(index: MapIndex, map: L.Map, buildingData: BuildingData, doc: Document): void {
  const buildingRecords = (buildingData && buildingData.records) || {};
  const buildingColumnOrder = (buildingData && Array.isArray(buildingData.columns)) ? buildingData.columns.slice() : [];

  // "Currently visible" matches exactly what computeMapSummary() already
  // counts for the sidebar's "In view" stats row: passes the active
  // filters, on the map layer, and within the current pan/zoom bounds —
  // not just the filter state.
  function collectVisibleBuildingIds(): string[] {
    return markersInView(index, map).map(([key]) => key);
  }

  function exportVisibleBuildingsCsv(): void {
    const ids = collectVisibleBuildingIds();
    if (!ids.length) {
      window.alert('No buildings are currently visible to export.');
      return;
    }
    const columns = buildingColumnOrder.length
      ? buildingColumnOrder
      : Object.keys(buildingRecords[ids[0]] || {});
    const lines = [columns.map(escapeCSV).join(',')];
    ids.forEach((id) => {
      const record = buildingRecords[id] || {};
      lines.push(columns.map((col) => escapeCSV(record[col])).join(','));
    });
    const blob = new Blob([lines.join('\r\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = doc.createElement('a');
    const timestamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
    link.href = url;
    link.download = 'buildings-visible-' + timestamp + '.csv';
    doc.body.appendChild(link);
    link.click();
    doc.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  const exportVisibleBtn = doc.getElementById('export-visible-csv');
  if (exportVisibleBtn) {
    exportVisibleBtn.addEventListener('click', exportVisibleBuildingsCsv);
  }
}
