/**
 * The About modal: a static info panel (project context, prototype status,
 * support links). Content lives in index.html as plain markup — it's not
 * data-driven, so there's nothing to render, only open/close to wire.
 */
import type * as L from 'leaflet';

export function initAboutModal(map: L.Map, doc: Document = document): void {
  const toggle = doc.getElementById('about-toggle-btn');
  const modal = doc.getElementById('about-modal');
  const closeBtn = doc.getElementById('about-modal-close');
  const backdrop = modal?.querySelector('.about-modal-backdrop');
  if (!toggle || !modal) return;

  // Reparent the toggle into the map container so it's anchored to the map's
  // own box (bottom-left, the one corner Leaflet's default controls leave
  // free), not the viewport — a viewport-fixed corner would land on top of
  // the sidebar/filters columns on desktop, where they're in-flow, not
  // off-canvas the way they are on mobile.
  map.getContainer().appendChild(toggle);

  function open(): void {
    modal!.hidden = false;
    toggle!.setAttribute('aria-expanded', 'true');
    doc.addEventListener('keydown', onKeydown);
  }
  function close(): void {
    modal!.hidden = true;
    toggle!.setAttribute('aria-expanded', 'false');
    doc.removeEventListener('keydown', onKeydown);
    toggle!.focus();
  }
  function onKeydown(e: KeyboardEvent): void {
    if (e.key === 'Escape') close();
  }

  toggle.addEventListener('click', open);
  closeBtn?.addEventListener('click', close);
  backdrop?.addEventListener('click', close);
}
