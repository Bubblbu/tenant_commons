import { describe, expect, it } from 'vitest';
import { formatCurrencyCompact, linked, monthYear, safeUrl } from './format';

describe('format helpers', () => {
  it('compacts currency', () => {
    expect(formatCurrencyCompact(20186619)).toBe('$20.2M');
    expect(formatCurrencyCompact(950000)).toBe('$950K');
    expect(formatCurrencyCompact(640)).toBe('$640');
  });

  it('links only http(s) URLs', () => {
    expect(safeUrl('https://example.org/x')).toBe('https://example.org/x');
    expect(safeUrl('javascript:alert(1)')).toBeNull();
    expect(safeUrl('not a url')).toBeNull();
    expect(safeUrl(null)).toBeNull();
    expect(linked('<b>x</b>', 'javascript:alert(1)')).toBe('&lt;b&gt;x&lt;/b&gt;');
  });

  it('formats an ISO date as month and year', () => {
    expect(monthYear('2026-09-30')).toBe('Sep 2026');
  });
});
