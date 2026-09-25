/**
 * Sidebar table search: hides rows whose visible text doesn't contain every
 * search term. View-only — it never touches the map or the filter panel, and
 * uses its own `search-hidden` class so it composes with wiring.js's `hidden`
 * (filter) class instead of fighting over it. Fires `tablesearch` on the
 * document afterwards so wiring.js can refresh the footer totals.
 */

/** Whitespace-separated, lowercased terms; empty query → no terms. */
export function searchTerms(query: string): string[] {
  return query.toLowerCase().split(/\s+/).filter((t) => t !== '');
}

/** True when every term appears somewhere in the row's text (case-insensitive). */
export function rowMatches(rowText: string, terms: string[]): boolean {
  const haystack = rowText.toLowerCase();
  return terms.every((t) => haystack.includes(t));
}

export function applyTableSearch(tables: HTMLTableElement[], query: string): void {
  const terms = searchTerms(query);
  for (const table of tables) {
    for (const row of Array.from(table.tBodies[0]?.rows ?? [])) {
      row.classList.toggle('search-hidden', terms.length > 0 && !rowMatches(row.textContent ?? '', terms));
    }
  }
  document.dispatchEvent(new Event('tablesearch'));
}

export function initTableSearch(input: HTMLInputElement, tables: HTMLTableElement[]): void {
  input.addEventListener('input', () => applyTableSearch(tables, input.value));
}
