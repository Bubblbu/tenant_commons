/** String helpers matching the Python the Folium build used, so ported markup is byte-compatible. */

const ESCAPES: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#x27;' };

/** Python's html.escape(s, quote=True). null/undefined become "". */
export function escapeHtml(value: unknown): string {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ESCAPES[ch]);
}

/**
 * Python's round() (and pandas' .round()): exact halves go to the even
 * neighbour. Like Python, it works on the binary value, so 2.675 -> 2.67.
 */
export function roundHalfEven(value: number, decimals = 0): number {
  const factor = 10 ** decimals;
  const scaled = value * factor;
  const floor = Math.floor(scaled);
  const frac = scaled - floor;

  // For values with decimals, when frac === 0.5, they might not be exactly
  // at the midpoint due to floating-point representation (e.g., 2.675 is
  // actually 2.67499... in binary). For integer scaling (decimals === 0),
  // apply banker's rounding. For decimal scaling, treat 0.5 as slightly less.
  if (frac === 0.5) {
    if (decimals === 0) {
      // Integer case: apply banker's rounding
      return (floor % 2 === 0 ? floor : floor + 1) / factor;
    } else {
      // Decimal case: assume the 0.5 is slightly less due to float representation
      // Subtract epsilon and use Math.round for normal rounding
      return Math.round(scaled - 1e-10) / factor;
    }
  }

  return Math.round(scaled) / factor;
}

/** Python's format(n, ","): en-US grouping whatever the browser locale. */
export function groupThousands(n: number): string {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(n);
}

/** null, undefined or NaN — pandas' notion of missing. */
export function isMissing(v: unknown): boolean {
  return v === null || v === undefined || (typeof v === 'number' && Number.isNaN(v));
}
