import { describe, expect, it } from 'vitest';
import { formatAddress } from './address';

describe('formatAddress', () => {
  it('capitalizes street names and types', () => {
    expect(formatAddress('1601 comox st')).toBe('1601 Comox St');
  });

  it('keeps compass directions upper case and ordinals lower case', () => {
    expect(formatAddress('350 e 6th ave')).toBe('350 E 6th Ave');
    expect(formatAddress('100 ne 21st st')).toBe('100 NE 21st St');
  });

  it('keeps unit prefixes and upper-cases civic-number suffixes', () => {
    expect(formatAddress('#200-581 cardero st')).toBe('#200-581 Cardero St');
    expect(formatAddress('1234a main st')).toBe('1234A Main St');
  });

  it('handles Mc names and hyphenated words', () => {
    expect(formatAddress('3410 mcintyre dr')).toBe('3410 McIntyre Dr');
    expect(formatAddress('10 saint-jean way')).toBe('10 Saint-Jean Way');
  });

  it('keeps a short prefix joined lower case, as in co-operative', () => {
    expect(formatAddress('2775 co-operative way')).toBe('2775 Co-operative Way');
  });

  it('leaves addresses that already carry capitals as published', () => {
    expect(formatAddress('1 Co-operative Way')).toBe('1 Co-operative Way');
    expect(formatAddress('MULTI Abbott St.')).toBe('MULTI Abbott St.');
  });

  it('returns an empty string for missing input', () => {
    expect(formatAddress('')).toBe('');
    expect(formatAddress(null)).toBe('');
  });
});
