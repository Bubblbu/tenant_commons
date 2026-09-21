import { describe, expect, it } from 'vitest';
import { formatCurrencyCompact, renderPopup, safeUrl } from './popup';
import type { BuildingRecord } from './types';

const building: BuildingRecord = {
  b_id: 1, address: '1234 Davie St', housing_name: null, owner_group: 'Hollyburn Properties',
  portfolio_name: 'Hollyburn Properties', portfolio_building_count: 23, portfolio_entities: ['a', 'b', 'c', 'd', 'e', 'f'],
  units: 87.0, year_built: 1974.0, local_area: 'West End', value_land: 20100000, value_bldg: 950000,
  is_coop: false, is_sro: false, member_count: 2, member_count_all: 3, has_vtu_member: true,
};

describe('renderPopup', () => {
  it('leads with the ownership story', () => {
    const html = renderPopup(building);
    expect(html.indexOf('Hollyburn Properties')).toBeLessThan(html.indexOf('87 units'));
    expect(html).toContain('Portfolio: 23 buildings, 6 linked entities');
    expect(html).toContain('87 units · built 1974');
    expect(html).toContain('Assessed $20.1M land · $950K building');
  });

  it('carries no membership data (editorial choice, spec §7)', () => {
    expect(renderPopup(building)).not.toMatch(/member|VTU/i);
  });

  it('shows co-op and SRO sections only when they apply', () => {
    expect(renderPopup(building)).not.toMatch(/Co-op|SRO/);
    const html = renderPopup({
      ...building, is_coop: true, coop_status: 'Active', coop_ownership_model: 'Leasehold',
      coop_url: 'https://example.org/c', is_sro: true, sro_owner: 'X Ltd', sro_operator: 'Y Soc',
      sro_occupancy_status: 'Open', sro_registered_rooms: '42',
    });
    expect(html).toContain('Co-op · Active (Leasehold)');
    expect(html).toContain('<a href="https://example.org/c" target="_blank" rel="noopener">more info</a>');
    expect(html).toContain('SRO/SRA · Owner X Ltd · Operator Y Soc · Open · 42 rooms');
  });

  it('omits missing facts rather than printing blanks', () => {
    const html = renderPopup({ b_id: 9, address: '300 Invented Rd', owner_group: '(Unknown)', units: null, year_built: null });
    expect(html).not.toMatch(/units|built|Assessed|Portfolio|null|undefined/);
  });

  it('escapes every value', () => {
    const html = renderPopup({ ...building, address: '<img src=x onerror=alert(1)>', owner_group: 'A & B' });
    expect(html).toContain('&lt;img src=x onerror=alert(1)&gt;');
    expect(html).toContain('A &amp; B');
    expect(html).not.toContain('<img');
  });
});

describe('helpers', () => {
  it('formats assessed values compactly', () => {
    expect(formatCurrencyCompact(20186619)).toBe('$20.2M');
    expect(formatCurrencyCompact(950000)).toBe('$950K');
    expect(formatCurrencyCompact(640)).toBe('$640');
  });

  it('only links http(s) URLs', () => {
    expect(safeUrl('https://example.org/x')).toBe('https://example.org/x');
    expect(safeUrl('javascript:alert(1)')).toBeNull();
    expect(safeUrl('not a url')).toBeNull();
    expect(safeUrl(null)).toBeNull();
  });
});
