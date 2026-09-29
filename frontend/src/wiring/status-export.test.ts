import { describe, expect, it } from 'vitest';
import { escapeCSV } from './status-export';

describe('escapeCSV', () => {
  it('leaves plain values alone and blanks missing ones', () => {
    expect(escapeCSV('West End')).toBe('West End');
    expect(escapeCSV(40)).toBe('40');
    expect(escapeCSV(null)).toBe('');
    expect(escapeCSV(undefined)).toBe('');
  });

  it('quotes commas, quotes and newlines', () => {
    expect(escapeCSV('101 Main St, Vancouver')).toBe('"101 Main St, Vancouver"');
    expect(escapeCSV('the "Tower"')).toBe('"the ""Tower"""');
    expect(escapeCSV('a\nb')).toBe('"a\nb"');
  });

  it('writes objects as JSON', () => {
    expect(escapeCSV(['a', 'b'])).toBe('"[""a"",""b""]"');
  });
});
