/**
 * The building popup (spec 2026-10-08 §6): one header, three tabs. Leaflet
 * takes the popup as an HTML string, so tab switching is delegated from the
 * document (initPopupTabs) rather than bound per popup. The last tab opened
 * is remembered in memory for the page session, so an organizer clicking
 * through buildings stays on Ownership; a reload starts on Summary.
 */
import type { Building, Network } from '../contract.gen';
import { formatAddress } from '../address';
import { escapeHtml } from '../html';
import { renderBuilding } from './building';
import { renderOwnership } from './ownership';
import { renderSummary } from './summary';

export type TabId = 'summary' | 'ownership' | 'building';
const TABS: [TabId, string][] = [['summary', 'Summary'], ['ownership', 'Ownership'], ['building', 'Building']];

export interface PopupContext {
  networks: Record<string, Network>;
  licenceYear: number | null;
  landShareMedian: number | null;
}

let remembered: TabId = 'summary';
export const currentTab = (): TabId => remembered;
export const resetTabMemory = (): void => { remembered = 'summary'; };

const SHOWN_PIDS = 3;

/** The building's parcels: a few PIDs inline (for a registry search), the rest collapsed. */
function parcels(b: Building): string {
  if (!b.pids.length) return '';
  const label = b.pids.length === 1 ? 'PID' : 'PIDs';
  const shown = b.pids.slice(0, SHOWN_PIDS).join(', ');
  const rest = b.pids.slice(SHOWN_PIDS);
  const more = rest.length
    ? ` <details class="popup-inline"><summary>+${rest.length} more</summary>${escapeHtml(rest.join(', '))}</details>` : '';
  return `<div class="popup-muted popup-pids">${escapeHtml(`${label} ${shown}`)}${more}</div>`;
}

function header(b: Building): string {
  const units = b.units === null ? '' : `${b.units.toLocaleString('en-US')} ${b.sro && b.units_basis !== 'licence_fee' ? 'rooms' : 'units'}`;
  const sub = [b.name ?? '', b.local_area ?? '', units, b.year_built === null ? '' : `built ${b.year_built}`]
    .filter(Boolean).join(' · ');
  return `<div class="popup-address">${escapeHtml(formatAddress(b.address))}</div>` +
    (sub ? `<div class="popup-sub">${escapeHtml(sub)}</div>` : '') + parcels(b);
}

export function renderPopup(b: Building, ctx: PopupContext): string {
  const panels: Record<TabId, string> = {
    summary: renderSummary(b, ctx), ownership: renderOwnership(b, ctx), building: renderBuilding(b, ctx),
  };
  const tabs = TABS.map(([id, label]) => {
    const on = id === remembered;
    return `<button type="button" role="tab" class="tc-tab" data-tab="${id}" id="tc-tab-${id}" ` +
      `aria-controls="tc-panel-${id}" aria-selected="${on}" tabindex="${on ? 0 : -1}">${label}</button>`;
  }).join('');
  const bodies = TABS.map(([id]) =>
    `<div role="tabpanel" class="tc-panel" id="tc-panel-${id}" aria-labelledby="tc-tab-${id}"${id === remembered ? '' : ' hidden'}>${panels[id]}</div>`,
  ).join('');
  return `<div class="tc-popup">${header(b)}<div role="tablist" class="tc-tabs">${tabs}</div><div class="tc-panels">${bodies}</div></div>`;
}

function select(popup: Element, id: TabId, focus: boolean): void {
  remembered = id;
  popup.querySelectorAll<HTMLElement>('.tc-tab').forEach((t) => {
    const on = t.dataset.tab === id;
    t.setAttribute('aria-selected', String(on));
    t.tabIndex = on ? 0 : -1;
    if (on && focus) t.focus();
  });
  popup.querySelectorAll<HTMLElement>('.tc-panel').forEach((p) => { p.hidden = p.id !== `tc-panel-${id}`; });
}

const initialized = new WeakSet<Document>();

export function initPopupTabs(doc: Document): void {
  if (initialized.has(doc)) return;  // one set of delegated listeners per document
  initialized.add(doc);
  doc.addEventListener('click', (e) => {
    const tab = (e.target as Element | null)?.closest?.('.tc-tab') as HTMLElement | null;
    const popup = tab?.closest('.tc-popup');
    if (tab && popup) select(popup, tab.dataset.tab as TabId, false);
  });
  doc.addEventListener('keydown', (e) => {
    const tab = (e.target as Element | null)?.closest?.('.tc-tab') as HTMLElement | null;
    const popup = tab?.closest('.tc-popup');
    if (!tab || !popup || (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft')) return;
    const ids = TABS.map(([id]) => id);
    const step = e.key === 'ArrowRight' ? 1 : -1;
    const next = ids[(ids.indexOf(tab.dataset.tab as TabId) + step + ids.length) % ids.length];
    e.preventDefault();
    select(popup, next, true);
  });
}
