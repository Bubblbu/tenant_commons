/**
 * Filters > Landlords: type to get suggestions (landlords, ownership groups,
 * property managers) drawn from the building records, pick one to add it as a
 * tile. A building passes when it matches any tile; no tiles, no filter.
 * Typed text alone never filters — it only drives the suggestions.
 */
import { escapeHtml, isMissing, sameName } from './html';
import type { BuildingRecord } from './types';

export type PickKind = 'owner' | 'network' | 'manager';

export interface PickOption {
  kind: PickKind;
  key: string;
  label: string;
  buildings: number;
  /** Extra context in the suggestion list, e.g. "3 landlords". */
  detail: string;
}

/** A building row's landlord keys, as tables.ts writes them. */
export interface RowKeys {
  owner: string;
  network: string;
  manager: string;
}

export const KIND_LABEL: Record<PickKind, string> = { owner: 'Landlord', network: 'Group', manager: 'Manager' };

const text = (v: unknown): string => (isMissing(v) ? '' : String(v).trim());
const onRecord = (key: string): boolean => key !== '' && key !== 'unknown';

/** The key tables.ts writes to data-manager: managers have no export key, so the lowercased name. */
export const managerKey = (name: unknown): string => text(name).toLowerCase();

interface Tally {
  labels: Map<string, number>;
  buildings: number;
  owners: Set<string>;
}

function tally(map: Map<string, Tally>, key: string, label: string, owner: string): void {
  let t = map.get(key);
  if (!t) {
    t = { labels: new Map(), buildings: 0, owners: new Set() };
    map.set(key, t);
  }
  t.labels.set(label, (t.labels.get(label) ?? 0) + 1);
  t.buildings += 1;
  if (onRecord(owner)) t.owners.add(owner);
}

/** Commonest spelling, ties by code point — same rule as the landlord tables. */
function commonest(labels: Map<string, number>): string {
  return [...labels].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0))[0][0];
}

/**
 * Every pickable landlord, group and manager. A group whose only landlord goes
 * by the same name is left out: picking it would be the same as picking the landlord.
 */
export function buildOptions(records: BuildingRecord[]): PickOption[] {
  const owners = new Map<string, Tally>();
  const networks = new Map<string, Tally>();
  const managers = new Map<string, Tally>();
  for (const r of records) {
    const owner = text(r.owner_key);
    if (!onRecord(owner)) {
      const manager = text(r.managed_by);
      if (manager) tally(managers, managerKey(manager), manager, '');
      continue;
    }
    tally(owners, owner, text(r.owner_name) || owner, owner);
    const network = text(r.network_key);
    if (onRecord(network)) tally(networks, network, text(r.network_name) || network, owner);
    const manager = text(r.managed_by);
    if (manager) tally(managers, managerKey(manager), manager, owner);
  }
  const options: PickOption[] = [];
  const ownerLabels = new Map<string, string>();
  for (const [key, t] of owners) {
    const label = commonest(t.labels);
    ownerLabels.set(key, label);
    options.push({ kind: 'owner', key, label, buildings: t.buildings, detail: '' });
  }
  for (const [key, t] of networks) {
    const label = commonest(t.labels);
    const [only] = [...t.owners];
    if (t.owners.size === 1 && sameName(label, ownerLabels.get(only) ?? '')) continue;
    const detail = t.owners.size > 1 ? `${t.owners.size} landlords` : '';
    options.push({ kind: 'network', key, label, buildings: t.buildings, detail });
  }
  for (const [key, t] of managers) {
    options.push({ kind: 'manager', key, label: commonest(t.labels), buildings: t.buildings, detail: '' });
  }
  return options;
}

const sameOption = (a: PickOption, b: PickOption): boolean => a.kind === b.kind && a.key === b.key;

/**
 * Options whose name contains every typed term, already-picked ones left out.
 * Names starting with the query rank first, then more buildings first. An
 * empty query suggests the largest landlords.
 */
export function suggest(options: PickOption[], query: string, picked: PickOption[], limit = 8): PickOption[] {
  const q = query.trim().toLowerCase();
  const terms = q.split(/\s+/).filter((t) => t !== '');
  const kindOrder: Record<PickKind, number> = { network: 0, owner: 1, manager: 2 };
  return options
    .filter((o) => !picked.some((p) => sameOption(p, o)))
    .filter((o) => {
      const name = o.label.toLowerCase();
      return terms.every((t) => name.includes(t));
    })
    .map((o) => ({ o, prefix: q !== '' && o.label.toLowerCase().startsWith(q) ? 0 : 1 }))
    .sort((a, b) =>
      a.prefix - b.prefix ||
      b.o.buildings - a.o.buildings ||
      kindOrder[a.o.kind] - kindOrder[b.o.kind] ||
      (a.o.label < b.o.label ? -1 : a.o.label > b.o.label ? 1 : 0))
    .slice(0, limit)
    .map(({ o }) => o);
}

/** True when the row belongs to any picked tile, or nothing is picked. */
export function selectionMatches(picked: PickOption[], row: RowKeys): boolean {
  if (picked.length === 0) return true;
  return picked.some((p) => p.key !== '' && row[p.kind] === p.key);
}

export interface LandlordFilter {
  isActive(): boolean;
  /** Number of picked tiles. */
  count(): number;
  matches(row: RowKeys): boolean;
  /** Removes every tile and the typed text. */
  clear(): void;
  onChange(listener: () => void): void;
}

interface PickerElements {
  input: HTMLInputElement;
  tiles: HTMLElement;
  list: HTMLElement;
}

export function initLandlordPicker(options: PickOption[], els: PickerElements): LandlordFilter {
  const { input, tiles, list } = els;
  const picked: PickOption[] = [];
  const listeners: (() => void)[] = [];
  let shown: PickOption[] = [];
  let active = -1;

  const changed = () => listeners.forEach((l) => l());

  function renderTiles(): void {
    tiles.innerHTML = picked
      .map((p, i) =>
        `<li class="picker-tile" data-kind="${p.kind}">` +
        `<span class="picker-kind">${KIND_LABEL[p.kind]}</span>` +
        `<span class="picker-tile-label" title="${escapeHtml(p.label)}">${escapeHtml(p.label)}</span>` +
        `<button type="button" class="picker-remove" data-index="${i}" ` +
        `aria-label="Remove ${escapeHtml(p.label)}">&times;</button></li>`)
      .join('');
    tiles.hidden = picked.length === 0;
  }

  function close(): void {
    shown = [];
    active = -1;
    list.hidden = true;
    list.innerHTML = '';
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
  }

  function renderList(): void {
    shown = suggest(options, input.value, picked);
    if (shown.length === 0) {
      close();
      return;
    }
    active = Math.min(active, shown.length - 1);
    list.innerHTML = shown
      .map((o, i) => {
        const meta = [o.detail, `${o.buildings} bldg${o.buildings === 1 ? '' : 's'}`].filter(Boolean).join(' · ');
        return (
          `<li role="option" id="owner-suggestion-${i}" class="picker-option${i === active ? ' active' : ''}" ` +
          `data-index="${i}" aria-selected="${i === active}">` +
          `<span class="picker-kind" data-kind="${o.kind}">${KIND_LABEL[o.kind]}</span>` +
          `<span class="picker-option-body"><span class="picker-option-label">${escapeHtml(o.label)}</span>` +
          `<span class="picker-option-meta">${escapeHtml(meta)}</span></span></li>`
        );
      })
      .join('');
    list.hidden = false;
    input.setAttribute('aria-expanded', 'true');
    if (active >= 0) input.setAttribute('aria-activedescendant', `owner-suggestion-${active}`);
    else input.removeAttribute('aria-activedescendant');
  }

  function pick(o: PickOption): void {
    picked.push(o);
    input.value = '';
    input.dispatchEvent(new Event('input')); // resyncs the clear button and the list
    renderTiles();
    changed();
  }

  function remove(index: number): void {
    picked.splice(index, 1);
    renderTiles();
    if (document.activeElement === input) renderList();
    changed();
  }

  input.addEventListener('input', () => {
    active = -1;
    renderList();
  });
  input.addEventListener('focus', renderList);
  input.addEventListener('blur', close);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      if (list.hidden) renderList();
      if (shown.length === 0) return;
      e.preventDefault();
      const step = e.key === 'ArrowDown' ? 1 : -1;
      active = (active + step + shown.length) % shown.length;
      renderList();
    } else if (e.key === 'Enter') {
      if (shown.length === 0) return;
      e.preventDefault();
      pick(shown[Math.max(active, 0)]);
    } else if (e.key === 'Escape') {
      close();
    } else if (e.key === 'Backspace' && input.value === '' && picked.length > 0) {
      remove(picked.length - 1);
    }
  });
  // mousedown, not click: picking must happen before the input's blur closes the list.
  list.addEventListener('mousedown', (e) => {
    const item = (e.target as Element).closest<HTMLElement>('.picker-option');
    if (!item) return;
    e.preventDefault();
    pick(shown[Number(item.dataset.index)]);
  });
  tiles.addEventListener('click', (e) => {
    const button = (e.target as Element).closest<HTMLElement>('.picker-remove');
    if (!button) return;
    remove(Number(button.dataset.index));
    input.focus();
  });

  renderTiles();
  close();

  return {
    isActive: () => picked.length > 0,
    count: () => picked.length,
    matches: (row) => selectionMatches(picked, row),
    clear() {
      const had = picked.length > 0;
      picked.length = 0;
      input.value = '';
      input.dispatchEvent(new Event('input'));
      if (document.activeElement !== input) close();
      renderTiles();
      if (had) changed();
    },
    onChange: (listener) => listeners.push(listener),
  };
}
