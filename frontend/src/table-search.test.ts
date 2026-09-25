import { describe, expect, it } from 'vitest';
import { rowMatches, searchTerms } from './table-search';

describe('searchTerms', () => {
  it('lowercases and splits on whitespace', () => {
    expect(searchTerms('  Davie   ST ')).toEqual(['davie', 'st']);
  });

  it('returns no terms for a blank query', () => {
    expect(searchTerms('   ')).toEqual([]);
  });
});

describe('rowMatches', () => {
  const row = '1234 Davie StWest End42Hollyburn Properties1968Apartment';

  it('matches case-insensitively', () => {
    expect(rowMatches(row, searchTerms('hollyburn'))).toBe(true);
  });

  it('requires every term, in any order', () => {
    expect(rowMatches(row, searchTerms('west davie'))).toBe(true);
    expect(rowMatches(row, searchTerms('davie kitsilano'))).toBe(false);
  });

  it('matches everything when there are no terms', () => {
    expect(rowMatches(row, [])).toBe(true);
  });
});
