// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import type { Building } from './contract.gen';
import { addressKey, buildLookup, findBuilding, parseDeepLink, renderMissingPopup, type DeepLink } from './deep-link';

// Matching reads only address and pids.
const rec = (address: string, pids: string[] = []): Building => ({ address, pids }) as unknown as Building;
const RECORDS: Record<string, Building> = {
  1: rec('1600 beach ave', ['029-334-772']),
  2: rec('350 keefer st', ['008-737-371']),
  3: rec('705 jackson ave', ['008-737-371']), // same parcel as 2
  4: rec('341 E Hastings St.', ['015-584-771']), // an overlay's own spelling
  5: rec('2855 e kent ave n'),
};
const LOOKUP = buildLookup(RECORDS);
const link = (l: Partial<DeepLink>): DeepLink => ({ pid: null, lat: null, lon: null, address: null, ...l });

describe('parseDeepLink', () => {
  it('reads what the address picker sends', () => {
    expect(parseDeepLink('#pid=029334772&lat=49.261643&lon=-123.06691&address=1865%20E%2010TH%20AV')).toEqual({
      pid: '029334772', lat: 49.261643, lon: -123.06691, address: '1865 E 10TH AV',
    });
  });

  it('is null without a link', () => {
    expect(parseDeepLink('')).toBeNull();
    expect(parseDeepLink('#')).toBeNull();
    expect(parseDeepLink('#something=else')).toBeNull();
  });

  it('accepts a dashed PID and drops a malformed one', () => {
    expect(parseDeepLink('#pid=029-334-772')!.pid).toBe('029334772');
    expect(parseDeepLink('#pid=LMS10&address=1160%20W%208TH%20AV')!.pid).toBeNull();
  });

  it('drops coordinates outside Vancouver, or half a pair', () => {
    expect(parseDeepLink('#lat=0&lon=0&address=x')).toMatchObject({ lat: null, lon: null });
    expect(parseDeepLink('#lat=49.26&address=x')).toMatchObject({ lat: null, lon: null });
    expect(parseDeepLink('#lat=49.26&lon=abc&address=x')).toMatchObject({ lat: null, lon: null });
  });
});

describe('addressKey', () => {
  it('bridges the City\'s spelling and the map\'s', () => {
    expect(addressKey('1865 E 10TH AV')).toBe(addressKey('1865 e 10th ave'));
    expect(addressKey('341 E HASTINGS ST')).toBe(addressKey('341 E Hastings St.'));
    expect(addressKey('2855 East Kent Avenue North')).toBe(addressKey('2855 e kent ave n'));
  });
});

describe('findBuilding', () => {
  it('matches the address', () => {
    expect(findBuilding(link({ address: '1600 BEACH AV' }), LOOKUP)).toBe('1');
    expect(findBuilding(link({ address: '341 E HASTINGS ST' }), LOOKUP)).toBe('4');
    expect(findBuilding(link({ address: '2855 E KENT AV N' }), LOOKUP)).toBe('5');
  });

  it('falls back to a PID when the address differs', () => {
    expect(findBuilding(link({ pid: '029334772', address: '1610 BEACH AV' }), LOOKUP)).toBe('1');
  });

  it('prefers the address on a parcel several buildings share', () => {
    expect(findBuilding(link({ pid: '008737371', address: '705 JACKSON AV' }), LOOKUP)).toBe('3');
  });

  it('never guesses between buildings sharing a parcel', () => {
    expect(findBuilding(link({ pid: '008737371', address: '360 KEEFER ST' }), LOOKUP)).toBeNull();
  });

  it('is null for a building not on the map', () => {
    expect(findBuilding(link({ pid: '018280846', lat: 49.26, lon: -123.07, address: '1865 E 10TH AV' }), LOOKUP)).toBeNull();
  });
});

describe('renderMissingPopup', () => {
  it('names the address and says the building is missing', () => {
    const html = renderMissingPopup(link({ address: '1865 E 10TH AV' }), null);
    expect(html).toContain('1865 E 10th Ave');
    expect(html).toContain("We don't have this building on the map yet.");
    expect(html).not.toContain('example building');
  });

  it('explains that the map covers mainly rental apartment buildings', () => {
    const html = renderMissingPopup(link({ address: '1865 E 10TH AV' }), null);
    expect(html).toContain('mainly rental apartment buildings');
    expect(html).toContain('smaller landlords');
  });

  it('puts the email address on a line of its own', () => {
    const d = document.createElement('div');
    d.innerHTML = renderMissingPopup(link({ address: '1865 E 10TH AV' }), null);
    const contact = d.querySelector('.tc-missing-contact')!;
    expect(contact.textContent!.trim()).toBe('info@tenantcommons.ca');
  });

  it('gives the email address, with the building in the subject', () => {
    const html = renderMissingPopup(link({ address: '1865 E 10TH AV' }), null);
    expect(html).toContain('href="mailto:info@tenantcommons.ca?subject=Missing%20building%3A%201865%20E%2010th%20Ave"');
    expect(html).toContain('>info@tenantcommons.ca</a>');
  });

  it('links the example building when one is set', () => {
    expect(renderMissingPopup(link({}), '029334772')).toContain('href="#pid=029334772"');
  });

  it('escapes the address, which anyone can put in a link', () => {
    const html = renderMissingPopup(link({ address: '<img src=x onerror=alert(1)>' }), null);
    expect(html).not.toContain('<img');
    expect(html).toContain('&lt;img');
  });
});
