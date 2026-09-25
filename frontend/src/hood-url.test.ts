import { describe, expect, it } from 'vitest';
import { readHoodParam, writeHoodParam } from './hood-url';

const ALL = ['west end', 'downtown', 'kitsilano'];

describe('readHoodParam', () => {
  it('returns null when the URL has no hood param', () => {
    expect(readHoodParam(new URLSearchParams('foo=1'), ALL)).toBeNull();
  });

  it('returns the listed neighbourhoods', () => {
    expect(readHoodParam(new URLSearchParams('hood=west+end&hood=kitsilano'), ALL)).toEqual(['west end', 'kitsilano']);
  });

  it('matches case-insensitively, like the lowercased checkbox values', () => {
    expect(readHoodParam(new URLSearchParams('hood=West+End'), ALL)).toEqual(['west end']);
  });

  it('drops neighbourhoods that no longer exist', () => {
    expect(readHoodParam(new URLSearchParams('hood=west+end&hood=gone'), ALL)).toEqual(['west end']);
  });

  it('ignores a stale link whose neighbourhoods all no longer exist', () => {
    expect(readHoodParam(new URLSearchParams('hood=gone'), ALL)).toBeNull();
  });

  it('reads an older link\'s empty hood param as the default: none ticked, every area shown', () => {
    expect(readHoodParam(new URLSearchParams('hood='), ALL)).toBeNull();
  });

  it('reads an older link listing every area as none ticked', () => {
    expect(readHoodParam(new URLSearchParams('hood=west+end&hood=downtown&hood=kitsilano'), ALL)).toEqual([]);
  });
});

describe('writeHoodParam', () => {
  it('omits the param when every neighbourhood is selected', () => {
    const params = new URLSearchParams('hood=downtown&foo=1');
    writeHoodParam(params, [...ALL], ALL);
    expect(params.toString()).toBe('foo=1');
  });

  it('writes one hood param per selected neighbourhood', () => {
    const params = new URLSearchParams();
    writeHoodParam(params, ['west end', 'kitsilano'], ALL);
    expect(params.getAll('hood')).toEqual(['west end', 'kitsilano']);
  });

  it('omits the param when none are ticked (every area shown)', () => {
    const params = new URLSearchParams('hood=downtown&foo=1');
    writeHoodParam(params, [], ALL);
    expect(params.toString()).toBe('foo=1');
  });

  it('round-trips a narrowed selection through readHoodParam', () => {
    for (const checked of [['downtown'], ['west end', 'kitsilano']]) {
      const params = new URLSearchParams();
      writeHoodParam(params, checked, ALL);
      expect(readHoodParam(params, ALL)).toEqual(checked);
    }
  });
});
