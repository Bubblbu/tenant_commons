/**
 * Mirrors the Filters > Neighbourhoods checkboxes into `?hood=` query params
 * so a filtered view can be shared as a link. One `hood` param per checked
 * value; no param means all checked (the default), and a single empty
 * `hood=` means none. Must run after renderLegend() and before wiring.js
 * starts, so wiring's first applyFilters() pass sees the restored state.
 */

const PARAM = 'hood';

/** Checked values from the URL, or null to leave the defaults alone. */
export function readHoodParam(params: URLSearchParams, all: string[]): string[] | null {
  const raw = params.getAll(PARAM);
  if (raw.length === 0) return null;
  const wanted = new Set(raw.map((v) => v.trim().toLowerCase()));
  const checked = all.filter((v) => wanted.has(v));
  // A link whose neighbourhoods have all since disappeared would otherwise
  // show an empty map; an explicit `hood=` still means none.
  if (checked.length === 0 && !wanted.has('')) return null;
  return checked;
}

export function writeHoodParam(params: URLSearchParams, checked: string[], all: string[]): void {
  params.delete(PARAM);
  if (checked.length === all.length) return;
  if (checked.length === 0) params.append(PARAM, '');
  for (const v of checked) params.append(PARAM, v);
}

export function initHoodUrlSync(doc: Document = document, win: Window = window): void {
  const inputs = Array.from(doc.querySelectorAll<HTMLInputElement>('.filter-neighbourhood-option'));
  if (inputs.length === 0) return;
  const all = inputs.map((i) => i.value);

  const restored = readHoodParam(new URLSearchParams(win.location.search), all);
  if (restored) {
    const on = new Set(restored);
    for (const i of inputs) i.checked = on.has(i.value);
  }

  const sync = () => {
    const url = new URL(win.location.href);
    writeHoodParam(url.searchParams, inputs.filter((i) => i.checked).map((i) => i.value), all);
    win.history.replaceState(win.history.state, '', url);
  };
  doc.getElementById('filter-neighbourhoods')?.addEventListener('change', sync);
  // Select all / Clear all / Reset set .checked directly, which fires no
  // change event; their click handlers (wiring.js) run before this deferred sync.
  for (const id of ['hood-select-all', 'hood-clear', 'filter-reset']) {
    doc.getElementById(id)?.addEventListener('click', () => setTimeout(sync));
  }
}
