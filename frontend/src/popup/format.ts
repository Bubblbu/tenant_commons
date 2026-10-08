/** Small formatting helpers shared by the popup tabs. */
import type { Source } from '../contract.gen';
import { escapeHtml } from '../html';
import { SRO_INVENTORY, licenceProvenance, listingProvenance } from '../provenance';

/** The URL if it is http(s), else null — never link javascript: or other schemes. */
export function safeUrl(v: unknown): string | null {
  if (typeof v !== 'string') return null;
  try {
    const u = new URL(v);
    return u.protocol === 'http:' || u.protocol === 'https:' ? u.href : null;
  } catch {
    return null;
  }
}

export function formatCurrencyCompact(v: number): string {
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${Math.round(v / 1e3).toLocaleString('en-US')}K`;
  return `$${Math.round(v)}`;
}

export const plural = (n: number, one: string, many: string): string => `${n.toLocaleString('en-US')} ${n === 1 ? one : many}`;

export function linked(text: string, url: string | null | undefined): string {
  const href = safeUrl(url);
  return href ? `<a href="${escapeHtml(href)}" target="_blank" rel="noopener">${escapeHtml(text)} ↗</a>` : escapeHtml(text);
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
/** "2026-09-30" -> "Sep 2026". */
export const monthYear = (iso: string): string => `${MONTHS[Number(iso.slice(5, 7)) - 1]} ${iso.slice(0, 4)}`;

/** Public provenance text for one source: types and dates only. */
export function sourceText(s: Source, licenceYear: number | null): string {
  switch (s.type) {
    case 'registry': return s.as_of ? `BC Land Owner Transparency Registry, record retrieved ${s.as_of}` : 'BC Land Owner Transparency Registry';
    case 'licence': return licenceProvenance(licenceYear);
    case 'sro_inventory': return SRO_INVENTORY;
    case 'listing': return listingProvenance(s.as_of ?? '');
    case 'vtu_research': return 'VTU research';
    case 'claim_registry': return 'Provincial registry filing';
    case 'rental_inventory': return 'City of Vancouver rental inventory (FOI)';
    case 'non_market_list': return 'City of Vancouver non-market housing list';
    case 'chf_bc': return 'Co-operative Housing Federation of BC';
    case 'rezoning': return 'City of Vancouver rezoning applications';
  }
}
