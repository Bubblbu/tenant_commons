import { describe, expect, it } from 'vitest';
import { escapeHtml, groupThousands, isMissing, roundHalfEven } from './html';

describe('escapeHtml', () => {
  it("matches Python's html.escape(quote=True)", () => {
    expect(escapeHtml(`<a href="x">&'`)).toBe('&lt;a href=&quot;x&quot;&gt;&amp;&#x27;');
    expect(escapeHtml(null)).toBe('');
  });
});

describe('roundHalfEven', () => {
  it("rounds halves to even, like Python's round()", () => {
    expect(roundHalfEven(12.5)).toBe(12);
    expect(roundHalfEven(13.5)).toBe(14);
    expect(roundHalfEven(-2.5)).toBe(-2);
    expect(roundHalfEven(1.25, 1)).toBe(1.2);
    expect(roundHalfEven(2.675, 2)).toBe(2.67); // binary 2.67499…, as in Python
    expect(roundHalfEven(12.6)).toBe(13);
  });
  it('handles exact binary ties like Python', () => {
    expect(roundHalfEven(0.375, 2)).toBe(0.38);
    expect(roundHalfEven(0.875, 2)).toBe(0.88);
    expect(roundHalfEven(-0.375, 2)).toBe(-0.38);
    expect(roundHalfEven(0.335, 2)).toBe(0.34);
    expect(roundHalfEven(1966.5)).toBe(1966);
  });
});

describe('groupThousands / isMissing', () => {
  it('groups en-US style regardless of locale', () => {
    expect(groupThousands(1234567)).toBe('1,234,567');
  });
  it('treats null, undefined and NaN as missing, but not 0 or ""', () => {
    expect([null, undefined, Number.NaN].every(isMissing)).toBe(true);
    expect(isMissing(0) || isMissing('')).toBe(false);
  });
});
