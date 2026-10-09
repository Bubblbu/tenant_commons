/**
 * The popup's "View in table" button on a network: filters to the network
 * (a Group tile in Filters > Landlords, replacing any other landlord tiles)
 * and shows the Buildings table. On phones it opens the data drawer.
 */
import type { LandlordFilter } from '../landlord-picker';

export function initNetworkTable(landlords: LandlordFilter | undefined, doc: Document = document): void {
  doc.addEventListener('click', (event) => {
    const btn = (event.target as Element | null)?.closest?.('.network-table') as HTMLElement | null;
    const option = btn ? landlords?.find('network', btn.dataset.network ?? '') : undefined;
    if (!btn || !landlords || !option) return;
    event.preventDefault();
    landlords.set([option]);
    doc.getElementById('tab-buildings')?.click();
    // The mobile drawers (display.ts initMobilePanels): data open, filters closed.
    doc.getElementById('filters-panel')?.classList.remove('open');
    doc.getElementById('mobile-toggle-filters')?.setAttribute('aria-expanded', 'false');
    doc.getElementById('sidebar-container')?.classList.add('open');
    doc.getElementById('mobile-toggle-sidebar')?.setAttribute('aria-expanded', 'true');
  });
}
