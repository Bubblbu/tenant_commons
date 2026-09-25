import { describe, expect, it } from 'vitest';
import { blockRowsHtml, buildingRow, buildingRowsHtml, networkRowsHtml, neighbourhoodRowsHtml, ownerRowsHtml, pinLast } from './tables';
import type { BlocksCollection, BuildingRecord } from './types';

const rec = (over: Partial<BuildingRecord>): BuildingRecord => ({
  b_id: 1, address: 'A', local_area: 'West End', block_id: 1, units: 10,
  year_built: 1970, owner_name: 'O', owner_key: 'o', network_name: 'O', network_key: 'o',
  value_land: 1, value_bldg: 1, bldg_land_ratio: 1,
  housing_type: '', ...over,
});

describe('buildingRow', () => {
  it("reproduces rows_buildings' markup exactly", () => {
    const row = buildingRow(rec({
      b_id: 7, address: '12 Oak & Elm St', block_id: 3.0, units: 40.0,
      year_built: 1965.0, owner_name: 'Example "Holdings"', owner_key: 'example-holdings',
      network_name: 'Example Group', network_key: 'example-group',
      value_land: 5000000.4, value_bldg: 800000.0, bldg_land_ratio: 0.16, housing_type: 'sro',
    }));
    expect(row).toBe(
      '<tr data-bid="7" data-owner="example-holdings" data-network="example-group" data-manager="" data-block="3" data-area="West End" ' +
        'data-chinatown="" data-village="" ' +
        'data-value-land="5000000" data-value-bldg="800000" data-value-ratio="0.16" data-units="40" ' +
        'data-year-built="1965" data-search="12 oak &amp; elm st west end 40 example &quot;holdings&quot; example group sro" ' +
        'data-housing-type="sro" data-n-issues="" data-has-owner="1">' +
        '<td class="select-cell"><input type="checkbox" class="row-select" data-type="building" data-target="7"></td>' +
        '<td>12 Oak &amp; Elm St</td><td></td><td data-sort-value="West End">West End</td>' +
        '<td data-sort-value="40">40</td>' +
        '<td>Example &quot;Holdings&quot;<div class="cell-sub">Group: Example Group</div></td>' +
        '<td data-sort-value="1965">1965</td><td data-sort-value=""></td></tr>',
    );
  });

  it('omits the group line when the group names the landlord again', () => {
    const row = buildingRow(rec({ owner_name: 'GLR PROPERTIES LTD.', network_name: 'Glr Properties Ltd', year_built: 1970 }));
    expect(row).toContain('<td>GLR PROPERTIES LTD.</td><td data-sort-value="1970">');
  });

  it('names the property manager under the landlord, or under "Not on record"', () => {
    const none = buildingRow(rec({ owner_name: '(Unknown)', owner_key: 'unknown', managed_by: 'Tribe Rental Management' }));
    expect(none).toContain('<td class="not-on-record">Not on record<div class="cell-sub">Managed by Tribe Rental Management</div></td>');
    expect(none).toContain('tribe rental management');
    const owned = buildingRow(rec({ owner_name: 'GREENBRIER HOLDINGS LTD.', network_name: 'Greenbrier Holdings Ltd', managed_by: 'Tribe Rental Management' }));
    expect(owned).toContain('<td>GREENBRIER HOLDINGS LTD.<div class="cell-sub">Managed by Tribe Rental Management</div></td>');
  });

  it('shows the building name, and finds it by any of its names', () => {
    const row = buildingRow(rec({ building_name: 'Maple Apartments', other_names: ['The Maple Apts'] }));
    expect(row).toContain('<td>A</td><td>Maple Apartments</td>');
    expect(row).toMatch(/data-search="[^"]*maple apartments the maple apts/);
  });

  it('shows the address in readable form', () => {
    expect(buildingRow(rec({ address: '350 e 6th ave' }))).toContain('<td>350 E 6th Ave</td>');
  });

  it('shows a building with no known landlord as not on record, not as a landlord', () => {
    const row = buildingRow(rec({ owner_name: '(Unknown)', owner_key: 'unknown', network_name: '(Unknown)', network_key: 'unknown' }));
    expect(row).toContain('<td class="not-on-record">Not on record</td>');
    expect(row).not.toContain('Group:');
    expect(row).not.toMatch(/data-search="[^"]*unknown/);
  });

  it('leaves missing values empty and keeps them out of the search text', () => {
    const row = buildingRow(rec({ b_id: 9, address: 'X', local_area: null, block_id: null, units: null, year_built: null }));
    expect(row).toContain('data-block="" data-area=""');
    expect(row).toContain('data-units="" data-year-built=""');
    expect(row).toContain('data-search="x o"');
  });

  it('shows the number of open issues, blank when the building has no record', () => {
    expect(buildingRow(rec({ b_id: 20, n_issues: 3 }))).toMatch(/<td data-sort-value="3">3<\/td><\/tr>$/);
    expect(buildingRow(rec({ b_id: 21, n_issues: null }))).toMatch(/<td data-sort-value=""><\/td><\/tr>$/);
  });

  it('carries the outstanding-issues count for the "only show buildings with issues" filter', () => {
    expect(buildingRow(rec({ b_id: 10, n_issues: 3 }))).toContain('data-n-issues="3"');
    expect(buildingRow(rec({ b_id: 11, n_issues: 0 }))).toContain('data-n-issues="0"');
    expect(buildingRow(rec({ b_id: 12 }))).toContain('data-n-issues=""');
  });

  it('carries the Chinatown/Villages Plan boundary flags for the neighbourhood filter', () => {
    expect(buildingRow(rec({ b_id: 13, in_chinatown: true }))).toContain('data-chinatown="1" data-village=""');
    expect(buildingRow(rec({ b_id: 14, in_village_plan: true }))).toContain('data-chinatown="" data-village="1"');
    expect(buildingRow(rec({ b_id: 15 }))).toContain('data-chinatown="" data-village=""');
  });
});

describe('buildingRowsHtml', () => {
  it('sorts by units, descending, with missing units last', () => {
    const html = buildingRowsHtml([
      rec({ b_id: 1, units: 5 }),
      rec({ b_id: 2, units: null }),
      rec({ b_id: 3, units: 50 }),
      rec({ b_id: 4, units: 90 }),
    ]);
    expect([...html.matchAll(/data-bid="(\d+)"/g)].map((m) => m[1])).toEqual(['4', '3', '1', '2']);
  });
});

describe('blockRowsHtml', () => {
  it('sorts labelled blocks before (Unknown) ones and rounds like pandas', () => {
    const fc = { type: 'FeatureCollection', schema_version: 1, features: [
      { type: 'Feature', geometry: null, properties: { block_id: 5, block_label: '(Unknown)-01', local_area: null, buildings: 0, total_units: 0, median_year_built: null } },
      { type: 'Feature', geometry: null, properties: { block_id: 6, block_label: 'West End-02', local_area: 'West End', buildings: 2, total_units: 25, median_year_built: 1966.5 } },
    ] } as unknown as BlocksCollection;
    const html = blockRowsHtml(fc);
    expect([...html.matchAll(/data-block="(\d+)"/g)].map((m) => m[1])).toEqual(['6', '5']);
    expect(html).toContain('<td data-sort-value="12.5">12.5</td>'); // avg units
    expect(html).toContain('<td data-sort-value="1966">1966</td>'); // 1966.5 -> 1966 (half to even)
  });

  it('carries the Chinatown/Villages Plan boundary flags', () => {
    const fc = { type: 'FeatureCollection', schema_version: 1, features: [
      { type: 'Feature', geometry: null, properties: { block_id: 1, block_label: 'B-01', local_area: null, buildings: 0, total_units: 0, median_year_built: null, in_chinatown: true, in_village_plan: false } },
    ] } as unknown as BlocksCollection;
    expect(blockRowsHtml(fc)).toContain('data-chinatown="1" data-village=""');
  });
});

describe('group tables', () => {
  const records = [
    rec({ b_id: 1, owner_name: 'B Co', owner_key: 'b', network_name: 'Net', network_key: 'net', units: 10, local_area: 'West End' }),
    rec({ b_id: 2, owner_name: 'A Co', owner_key: 'a', network_name: 'Net', network_key: 'net', units: 30, local_area: null }),
    rec({ b_id: 3, owner_name: 'B Co', owner_key: 'b', network_name: 'Other', network_key: 'other', units: 5, local_area: 'West End' }),
  ];

  it('groups owners, sorted by total units', () => {
    const html = ownerRowsHtml(records);
    expect([...html.matchAll(/data-owner="([^"]+)"/g)].map((m) => m[1])).toEqual(['a', 'b']);
    expect(html).toContain('data-owner="b" data-bldgs="2" data-units="15"');
    expect(html).toContain('data-type="owner" data-target="b"');
  });

  it('merges spellings of one key into a single row, labelled by the commonest spelling', () => {
    const html = ownerRowsHtml([
      rec({ b_id: 1, owner_name: 'Chartwell Construction Ltd', owner_key: 'chartwell-construction-ltd', units: 10 }),
      rec({ b_id: 2, owner_name: 'CHARTWELL CONSTRUCTION LTD.', owner_key: 'chartwell-construction-ltd', units: 20 }),
      rec({ b_id: 3, owner_name: 'CHARTWELL CONSTRUCTION LTD.', owner_key: 'chartwell-construction-ltd', units: 5 }),
    ]);
    expect([...html.matchAll(/<tr /g)]).toHaveLength(1);
    expect(html).toContain('data-bldgs="3" data-units="35"');
    expect(html).toContain('>CHARTWELL CONSTRUCTION LTD.</td>');
  });

  it('tags each network row with where its grouping comes from', () => {
    const html = networkRowsHtml([
      rec({ b_id: 1, network_name: 'GLR', network_key: 'net:glr', network_source: 'claims',
        network_name_source: 'default', network_evidence: { registry: 3, vtu_research: 0 } }),
      rec({ b_id: 2, network_name: 'Solo', network_key: 'solo', network_source: 'licence' }),
      rec({ b_id: 3, network_name: '(Unknown)', network_key: 'unknown', network_source: null }),
    ]);
    expect(html).toContain('data-tip="Grouped from 3 provincial registry filings. Name: default (entity with the most properties)."');
    expect(html).toContain('data-tip="Grouped by business licence name"');
    expect(html).toContain('>Not on record</td>');
  });

  it('pins buildings with no known landlord to one greyed row at the bottom of both views', () => {
    const recs = [
      rec({ b_id: 1, owner_name: '(Unknown)', owner_key: 'unknown', network_name: '(Unknown)', network_key: 'unknown', units: 500 }),
      rec({ b_id: 2, owner_name: 'A Co', owner_key: 'a', network_name: 'A Co', network_key: 'a', units: 10 }),
    ];
    for (const html of [ownerRowsHtml(recs), networkRowsHtml(recs)]) {
      const rows = html.split('\n');
      expect(rows).toHaveLength(2);
      expect(rows[1]).toContain('data-pin="last" class="not-on-record"');
      expect(rows[1]).toContain('<td data-sort-value="">Not on record</td>');
    }
  });

  it('says how many landlords an ownership group folds together', () => {
    const html = networkRowsHtml(records);
    expect(html).toContain('<td data-sort-value="Net">Net<span class="cell-sub-inline"> · 2 landlords</span></td>');
    expect(html).toContain('<td data-sort-value="Other">Other</td>');
  });

  it('tags each owner row with its source, keeping the name as the sort value', () => {
    const html = ownerRowsHtml([
      rec({ b_id: 1, owner_name: 'St. "George"', owner_key: 'st-george', owner_source: 'registry' }),
      rec({ b_id: 2, owner_name: 'Solo', owner_key: 'solo', owner_source: 'licence' }),
    ], 2026);
    expect(html).toContain('<td data-sort-value="St. &quot;George&quot;">St. &quot;George&quot;<span class="prov"');
    expect(html).toContain('data-tip="BC Land Owner Transparency Registry"');
    expect(html).toContain('data-tip="City of Vancouver business licence, 2026"');
  });

  it('groups networks, sorted by total units', () => {
    const html = networkRowsHtml(records);
    expect([...html.matchAll(/data-network="([^"]+)"/g)].map((m) => m[1])).toEqual(['net', 'other']);
    expect(html).toContain('data-network="net" data-bldgs="2" data-units="40"');
    expect(html).toContain('data-type="network" data-target="net"');
  });

  it('groups neighbourhoods, putting missing areas under (Unknown)', () => {
    const html = neighbourhoodRowsHtml(records);
    expect([...html.matchAll(/<tr data-area="([^"]+)"/g)].map((m) => m[1])).toEqual(['(Unknown)', 'West End']);
  });
});

describe('pinLast', () => {
  const row = (id: string, pin = '') => ({ id, getAttribute: (n: string) => (n === 'data-pin' ? pin || null : null) });

  it('moves pinned rows to the end, keeping both groups in order', () => {
    const rows = [row('x', 'last'), row('a'), row('b'), row('y', 'last'), row('c')];
    expect(pinLast(rows).map((r) => r.id)).toEqual(['a', 'b', 'c', 'x', 'y']);
  });
});
