/**
 * The popup's "Highlight on map" toggle on a network: it ticks or unticks the
 * network's row in the Networks table, so the highlight is an ordinary
 * selection — counted in the summary bar, cleared by Reset. The map doesn't
 * move. Buttons show the row's state whenever a popup opens or a selection
 * changes.
 */
import type L from 'leaflet';

const ON = 'Stop highlighting';
const OFF = 'Highlight on map';

function rowBox(doc: Document, network: string): HTMLInputElement | undefined {
  // Compared as text: network ids hold ":" and other selector characters.
  return [...doc.querySelectorAll<HTMLInputElement>('#networks-table input.row-select')]
    .find((cb) => cb.getAttribute('data-target') === network);
}

function sync(doc: Document, btn: HTMLElement): void {
  const on = rowBox(doc, btn.dataset.network ?? '')?.checked === true;
  btn.setAttribute('aria-pressed', String(on));
  btn.textContent = on ? ON : OFF;
}

export function initNetworkHighlight(map: L.Map, doc: Document = document): void {
  const syncAll = (root: ParentNode) =>
    root.querySelectorAll<HTMLElement>('.network-highlight').forEach((btn) => sync(doc, btn));
  doc.addEventListener('click', (event) => {
    const btn = (event.target as Element | null)?.closest?.('.network-highlight') as HTMLElement | null;
    const box = btn ? rowBox(doc, btn.dataset.network ?? '') : undefined;
    if (!btn || !box) return;
    event.preventDefault();
    box.checked = !box.checked;
    box.dispatchEvent(new Event('change', { bubbles: true }));
  });
  // Any selection change (this button, the table, Reset) re-labels open popups.
  doc.addEventListener('change', (event) => {
    if ((event.target as Element | null)?.closest?.('#networks-table')) syncAll(doc);
  });
  map.on('popupopen', (e) => {
    const el = (e as L.PopupEvent).popup.getElement();
    if (el) syncAll(el);
  });
}
