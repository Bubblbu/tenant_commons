import type { BlockStyler } from './block-style';
import type { MarkerStyler } from './marker-style';
import type { LiveTables } from './tables-live';
import type { MapIndex } from './types';

export interface Selection {
  owner(key: string, on: boolean): void;
  network(key: string, on: boolean): void;
  hood(key: string, on: boolean): void;
  blockMarkers(blockId: string, on: boolean): void;
  /** Reset's "untick every row" loop (dispatches change so counts follow). */
  clearAll(): void;
}

/** Wires row checkboxes and row hover for all five tables. */
export function initSelection(index: MapIndex, markers: MarkerStyler, blocks: BlockStyler, tables: LiveTables, doc: Document): Selection {
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

  function blockMarkers(blockId: string, selected: boolean): void {
    const ids = index.blockBuildings[String(blockId)] || [];
    ids.forEach((bid) => {
      const marker = index.buildings[String(bid)];
      if (!marker) return;
      markers.adjustSelection(marker, selected ? 1 : -1);
    });
  }

  function handleSelectionChange(evt: Event): void {
    const cb = evt.target as HTMLInputElement;
    if (!cb.classList.contains('row-select')) return;
    const row = cb.closest('tr');
    if (row) row.classList.toggle('selected', cb.checked);
    const typ = cb.dataset.type;
    const key = String(cb.dataset.target);
    if (typ === 'building') {
      markers.adjustSelection(index.buildings[key], cb.checked ? 1 : -1);
    } else if (typ === 'block') {
      blocks.adjustSelection(index.blocks[key], cb.checked ? 1 : -1);
      blockMarkers(key, cb.checked);
    } else if (typ === 'owner') {
      owner(key, cb.checked);
    } else if (typ === 'network') {
      network(key, cb.checked);
    } else if (typ === 'neighbourhood') {
      hood(key.toLowerCase().trim(), cb.checked);
    }
    tables.updateSummaryBar();
    tables.updateGroupTableSummaries();
  }

  doc.querySelectorAll('.row-select').forEach((cb) => {
    cb.addEventListener('change', handleSelectionChange);
  });

  doc.querySelectorAll('#blocks-table tbody tr').forEach((row) => {
    const id = String(row.getAttribute('data-block'));
    row.addEventListener('mouseenter', () => blocks.hover(id, true));
    row.addEventListener('mouseleave', () => blocks.hover(id, false));
  });

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

  return { owner, network, hood, blockMarkers, clearAll };
}
