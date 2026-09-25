/**
 * Mirrors the Filter by > Area checkboxes into `?hood=` query params so a
 * filtered view can be shared as a link. One `hood` param per ticked value;
 * no param means none ticked, which shows every area (the default). Older
 * links used a lone empty `hood=` for "none"; with nothing ticked now meaning
 * everything, it reads as the default. Must run after renderLegend() and
 * before wiring.js starts, so wiring's first applyFilters() pass sees the
 * restored state.
 */

const PARAM = 'hood';

/** Checked values from the URL, or null to leave the defaults alone. */
export function readHoodParam(params: URLSearchParams, all: string[]): string[] | null {
  const raw = params.getAll(PARAM);
  if (raw.length === 0) return null;
  const wanted = new Set(raw.map((v) => v.trim().toLowerCase()));
  const checked = all.filter((v) => wanted.has(v));
  // Also covers a link whose neighbourhoods have all since disappeared.
  if (checked.length === 0) return null;
  // Every area ticked (older links spelled "all" out) is the same as none.
  if (checked.length === all.length) return [];
  return checked;
}

export function writeHoodParam(params: URLSearchParams, checked: string[], all: string[]): void {
  params.delete(PARAM);
  if (checked.length === all.length) return;
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
  // Area Clear and Reset set .checked directly, which fires no change
  // event; their click handlers (wiring.js) run before this deferred sync.
  for (const id of ['filter-clear-area', 'filter-reset']) {
    doc.getElementById(id)?.addEventListener('click', () => setTimeout(sync));
  }
}
