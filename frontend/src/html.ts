/** String helpers matching the Python the Folium build used, so ported markup is byte-compatible. */

const ESCAPES: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#x27;' };

/** Python's html.escape(s, quote=True). null/undefined become "". */
export function escapeHtml(value: unknown): string {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ESCAPES[ch]);
}

/**
 * Python's round() (and pandas' .round()): exact halves go to the even
 * neighbour, judged on the number's exact binary value — so 2.675 -> 2.67
 * (stored as 2.67499…) but 0.375 -> 0.38 (stored exactly). Scaling by
 * 10**decimals first would manufacture or erase a .5, so this reads the
 * exact decimal expansion instead: toFixed(100) is exact for the magnitudes
 * the map uses (|v| >= ~2^-47).
 */
export function roundHalfEven(value: number, decimals = 0): number {
  if (!Number.isFinite(value) || Math.abs(value) >= 1e21) return value;
  const [intPart, frac] = Math.abs(value).toFixed(100).split('.');
  let n = BigInt(intPart + frac.slice(0, decimals));
  const first = frac[decimals];
  const tail = frac.slice(decimals + 1);
  if (first > '5' || (first === '5' && /[1-9]/.test(tail)) || (first === '5' && n % 2n === 1n)) n += 1n;
  const result = Number(`${n}e-${decimals}`);
  return value < 0 ? -result : result;
}

/** Python's format(n, ","): en-US grouping whatever the browser locale. */
export function groupThousands(n: number): string {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(n);
}

/** Same name once case, spacing and punctuation are ignored ("GLR PROPERTIES LTD." ~ "Glr Properties Ltd"). */
export function sameName(a: string, b: string): boolean {
  const key = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, '');
  return key(a) === key(b);
}

/** null, undefined or NaN — pandas' notion of missing. */
export function isMissing(v: unknown): boolean {
  return v === null || v === undefined || (typeof v === 'number' && Number.isNaN(v));
}
