import { describe, expect, it } from 'vitest';
import {
  formatCurrencyCompact,
  licenceProvenance,
  networkProvenance,
  registryProvenance,
  renderPopup,
  safeUrl,
} from './popup';
import type { BuildingRecord } from './types';

const building: BuildingRecord = {
  b_id: 1, address: '522 E 8th Ave', housing_name: null,
  owner_name: 'ST. GEORGE ESTATES LTD.', owner_key: 'st-george-estates-ltd', owner_source: 'registry',
  registered_owners: ['ST. GEORGE ESTATES LTD.'], registry_pids: ['008-173-613'],
  registry_retrieved: '2026-05-28', licence_holder: 'Willow Lane Apartments Inc',
  network_key: 'glr-properties-ltd', network_name: 'GLR PROPERTIES LTD.', network_source: 'claims',
  network_name_source: 'default', network_entities: ['a', 'b', 'c', 'd', 'e', 'f'],
  network_buildings_on_map: 19, network_properties_on_title: 23,
  network_evidence: { registry: 36, vtu_research: 2 },
  units: 87.0, year_built: 1974.0, local_area: 'Mount Pleasant', value_land: 20100000, value_bldg: 950000,
  is_coop: false, is_sro: false,
};

describe('renderPopup', () => {
  it('leads with the ownership story', () => {
    const html = renderPopup(building);
    expect(html.indexOf('ST. GEORGE ESTATES LTD.')).toBeLessThan(html.indexOf('87 units'));
    expect(html).toContain('Licensed as Willow Lane Apartments Inc');
    expect(html).toContain('Part of the <strong>GLR PROPERTIES LTD.</strong> network');
    expect(html).toContain('19 buildings on map · 23 properties on title · 6 linked entities');
    expect(html).toContain('87 units · built 1974');
    expect(html).toContain('Assessed $20.1M land · $950K building');
  });

  it('carries no membership data (editorial choice, spec §7)', () => {
    // "VTU research" provenance is about ownership claims, not membership.
    expect(renderPopup(building)).not.toMatch(/member/i);
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
    const html = renderPopup({ b_id: 9, address: '300 Invented Rd', owner_name: '(Unknown)', units: null, year_built: null });
    expect(html).not.toMatch(/units|built|Assessed|network|null|undefined/);
  });

  it('shows the outstanding-issues count only when there is one', () => {
    expect(renderPopup(building)).not.toMatch(/issue/i);
    expect(renderPopup({ ...building, n_issues: 0 })).not.toMatch(/issue/i);
    expect(renderPopup({ ...building, n_issues: 1 })).toContain('1 outstanding issue<');
    expect(renderPopup({ ...building, n_issues: 3 })).toContain('3 outstanding issues');
  });

  it('links to the City details page for an issue, only when a safe URL is present', () => {
    const withUrl = renderPopup({
      ...building, n_issues: 2,
      issues_details: 'http://app.vancouver.ca/RPS_Net/Default.aspx?num=1234&street=DAVIE%20ST',
    });
    expect(withUrl).toContain(
      '<a href="http://app.vancouver.ca/RPS_Net/Default.aspx?num=1234&amp;street=DAVIE%20ST" target="_blank" rel="noopener">City details</a>',
    );
    expect(renderPopup({ ...building, n_issues: 2 })).not.toContain('<a');
    expect(renderPopup({ ...building, n_issues: 2, issues_details: 'javascript:alert(1)' })).not.toContain('<a');
  });

  it('escapes every value', () => {
    const html = renderPopup({ ...building, address: '<img src=x onerror=alert(1)>', owner_name: 'A & B' });
    expect(html).toContain('&lt;img src=x onerror=alert(1)&gt;');
    expect(html).toContain('A &amp; B');
    expect(html).not.toContain('<img');
  });
});

describe('ownership lines', () => {
  it('tags the registry owner with its PID and retrieval date', () => {
    expect(renderPopup(building)).toContain(
      'data-tip="BC Land Owner Transparency Registry: PID 008-173-613, record retrieved 2026-05-28"',
    );
  });

  it('skips the licence line when it only differs in case or punctuation', () => {
    expect(renderPopup({ ...building, licence_holder: 'St. George Estates Ltd' })).not.toContain('Licensed as');
  });

  it('tags a licence-sourced owner with the licence year and shows no licence line', () => {
    const html = renderPopup(
      { ...building, owner_source: 'licence', owner_name: 'Solo Rentals Ltd', licence_holder: 'Solo Rentals Ltd' },
      { licenceYear: 2026 },
    );
    expect(html).toContain('data-tip="City of Vancouver business licence, 2026"');
    expect(html).not.toContain('Licensed as');
  });

  it('counts co-owners', () => {
    expect(renderPopup({ ...building, registered_owners: ['ST. GEORGE ESTATES LTD.', 'OTHER LTD.'] }))
      .toContain('+1 co-owner<');
  });

  it('shows a licence network only when it spans more than one building', () => {
    const lic = {
      ...building, network_source: 'licence', network_name: 'Solo Rentals Ltd',
      network_entities: null, network_properties_on_title: null, network_evidence: null,
    };
    expect(renderPopup({ ...lic, network_buildings_on_map: 1 })).not.toContain('network');
    const html = renderPopup({ ...lic, network_buildings_on_map: 3 });
    expect(html).toContain('Part of the <strong>Solo Rentals Ltd</strong> network');
    expect(html).toContain('>3 buildings on map<');
    expect(html).toContain('data-tip="Grouped by business licence name"');
  });

  it('shows no provenance for an unknown owner', () => {
    const html = renderPopup({ b_id: 9, address: '999 Nowhere Rd', owner_name: '(Unknown)', owner_source: null, network_source: null });
    expect(html).toContain('(Unknown)');
    expect(html).not.toContain('class="prov"');
    expect(html).not.toContain('network');
  });

  it('escapes provenance text', () => {
    const html = renderPopup({ ...building, registry_pids: ['"><img src=x>'] });
    expect(html).not.toContain('<img');
    expect(html).toContain('&quot;&gt;&lt;img src=x&gt;');
  });
});

describe('provenance text', () => {
  it('lists up to three PIDs', () => {
    expect(registryProvenance(['1', '2', '3', '4', '5'], '')).toBe(
      'BC Land Owner Transparency Registry: PIDs 1, 2, 3 (+2 more)',
    );
  });

  it('omits the licence year when unknown', () => {
    expect(licenceProvenance(null)).toBe('City of Vancouver business licence');
  });

  it('summarizes network evidence and the naming rule', () => {
    expect(networkProvenance(building)).toBe(
      'Grouped from 36 provincial registry filings and 2 VTU research claims. Name: default (entity with the most properties).',
    );
    expect(networkProvenance({ ...building, network_evidence: { registry: 1, vtu_research: 0 }, network_name_source: 'claim' }))
      .toBe('Grouped from 1 provincial registry filing. Name: set by claim.');
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
