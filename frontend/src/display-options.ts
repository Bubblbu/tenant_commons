/**
 * Map Display Options: an option indented under a layer (.display-children
 * with data-parent="<layer checkbox id>") only means something while that
 * layer is on, so it is disabled and greyed out while the layer is off.
 * Reset sets .checked without a change event, so it resyncs on its click.
 */
export function initDisplayOptions(doc: Document = document): void {
  const groups = Array.from(doc.querySelectorAll<HTMLElement>('.display-children[data-parent]'));
  const syncAll = () => {
    for (const group of groups) {
      const parent = doc.getElementById(group.dataset.parent ?? '');
      if (!(parent instanceof HTMLInputElement)) continue;
      group.classList.toggle('disabled', !parent.checked);
      group.querySelectorAll('input').forEach((input) => {
        input.disabled = !parent.checked;
      });
    }
  };
  for (const group of groups) doc.getElementById(group.dataset.parent ?? '')?.addEventListener('change', syncAll);
  // Deferred so wiring.js's own reset handler has set the checkboxes first.
  doc.getElementById('filter-reset')?.addEventListener('click', () => setTimeout(syncAll));
  syncAll();
}
