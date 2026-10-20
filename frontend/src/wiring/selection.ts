import type { MarkerStyler } from './marker-style';
import type { LiveTables } from './tables-live';
import type { MapIndex } from './types';

export interface Selection {
  owner(key: string, on: boolean): void;
  network(key: string, on: boolean): void;
  hood(key: string, on: boolean): void;
  /** Reset's "untick every row" loop (dispatches change so counts follow). */
  clearAll(): void;
  /** Brings every table's select-all box in line with its shown rows (after a filter pass). */
  syncSelectAll(): void;
}

/** Wires row checkboxes and row hover for all four tables. */
export function initSelection(index: MapIndex, markers: MarkerStyler, tables: LiveTables, doc: Document): Selection {
  function owner(ownerKey: string, selected: boolean): void {
    const arr = index.owners[ownerKey] || [];
    arr.forEach((marker) => { markers.adjustSelection(marker, selected ? 1 : -1); });
  }

  function network(networkKey: string, selected: boolean): void {
    const arr = index.networks[networkKey] || [];
    arr.forEach((marker) => { markers.adjustSelection(marker, selected ? 1 : -1); });
  }

  function hood(hoodKey: string, selected: boolean): void {
    const arr = index.hoods[hoodKey] || [];
    arr.forEach((marker) => { markers.adjustSelection(marker, selected ? 1 : -1); });
  }

  /** Applies one row checkbox's state to its row and the map (no summaries). */
  function applyRow(cb: HTMLInputElement): void {
    const row = cb.closest('tr');
    if (row) row.classList.toggle('selected', cb.checked);
    const typ = cb.dataset.type;
    const key = String(cb.dataset.target);
    if (typ === 'building') {
      markers.adjustSelection(index.buildings[key], cb.checked ? 1 : -1);
    } else if (typ === 'owner') {
      owner(key, cb.checked);
    } else if (typ === 'network') {
      network(key, cb.checked);
    } else if (typ === 'neighbourhood') {
      hood(key.toLowerCase().trim(), cb.checked);
    }
  }

  const rowShown = (cb: HTMLInputElement): boolean => {
    const row = cb.closest('tr');
    return !!row && !row.classList.contains('hidden') && !row.classList.contains('search-hidden');
  };
  const rowBoxes = (table: Element): HTMLInputElement[] =>
    Array.from(table.querySelectorAll<HTMLInputElement>('tbody input.row-select'));

  /** The header box: ticked when every shown row is, partial when some are. */
  function syncSelectAll(table: Element | null): void {
    const head = table?.querySelector<HTMLInputElement>('thead input.select-all');
    if (!table || !head) return;
    const shown = rowBoxes(table).filter(rowShown);
    const on = shown.filter((cb) => cb.checked).length;
    head.checked = shown.length > 0 && on === shown.length;
    head.indeterminate = on > 0 && on < shown.length;
  }

  function handleSelectionChange(evt: Event): void {
    const cb = evt.target as HTMLInputElement;
    if (!cb.classList.contains('row-select')) return;
    applyRow(cb);
    tables.updateSummaryBar();
    tables.updateGroupTableSummaries();
    syncSelectAll(cb.closest('table'));
  }

  /** Ticking selects every row the filters and search leave shown; unticking clears the table. */
  function handleSelectAll(evt: Event): void {
    const head = evt.target as HTMLInputElement;
    const table = head.closest('table');
    if (!table) return;
    rowBoxes(table)
      .filter((cb) => (head.checked ? rowShown(cb) && !cb.checked : cb.checked))
      .forEach((cb) => {
        cb.checked = head.checked;
        applyRow(cb);
      });
    tables.updateSummaryBar();
    tables.updateGroupTableSummaries();
    syncSelectAll(table);
  }

  doc.querySelectorAll('.row-select').forEach((cb) => {
    cb.addEventListener('change', handleSelectionChange);
  });
  doc.querySelectorAll('input.select-all').forEach((cb) => {
    cb.addEventListener('change', handleSelectAll);
  });
  function syncAllHeaders(): void {
    doc.querySelectorAll('input.select-all').forEach((cb) => syncSelectAll(cb.closest('table')));
  }
  // Search hides rows without a change event; keep the header boxes honest.
  doc.addEventListener('tablesearch', syncAllHeaders);

  doc.querySelectorAll('#buildings-table tbody tr').forEach((row) => {
    const bid = String(row.getAttribute('data-bid'));
    row.addEventListener('mouseenter', () => markers.hover([index.buildings[bid]], true));
    row.addEventListener('mouseleave', () => markers.hover([index.buildings[bid]], false));
  });

  doc.querySelectorAll('#owners-table tbody tr').forEach((row) => {
    const key = String(row.getAttribute('data-owner'));
    row.addEventListener('mouseenter', () => markers.hover(index.owners[key] || [], true));
    row.addEventListener('mouseleave', () => markers.hover(index.owners[key] || [], false));
  });

  doc.querySelectorAll('#networks-table tbody tr').forEach((row) => {
    const key = String(row.getAttribute('data-network'));
    row.addEventListener('mouseenter', () => markers.hover(index.networks[key] || [], true));
    row.addEventListener('mouseleave', () => markers.hover(index.networks[key] || [], false));
  });

  doc.querySelectorAll('#neighbourhoods-table tbody tr').forEach((row) => {
    const hoodKey = (row.getAttribute('data-area') || '').toLowerCase().trim();
    row.addEventListener('mouseenter', () => markers.hover(index.hoods[hoodKey] || [], true));
    row.addEventListener('mouseleave', () => markers.hover(index.hoods[hoodKey] || [], false));
  });

  function clearAll(): void {
    doc.querySelectorAll('.row-select').forEach((cb) => {
      const input = cb as HTMLInputElement;
      if (input.checked) {
        input.checked = false;
        input.dispatchEvent(new Event('change', { bubbles: true }));
      }
    });
  }

  return { owner, network, hood, clearAll, syncSelectAll: syncAllHeaders };
}
