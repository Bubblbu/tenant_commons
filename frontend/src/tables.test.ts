import { describe, expect, it } from 'vitest';
import { blockRowsHtml, buildingRow, buildingRowsHtml, networkRowsHtml, neighbourhoodRowsHtml, ownerRowsHtml } from './tables';
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
      '<tr data-bid="7" data-owner="example-holdings" data-network="example-group" data-block="3" data-area="West End" ' +
        'data-chinatown="" data-village="" ' +
        'data-value-land="5000000" data-value-bldg="800000" data-value-ratio="0.16" data-units="40" ' +
        'data-year-built="1965" data-search="12 oak &amp; elm st west end 40 example &quot;holdings&quot; example group sro" ' +
        'data-housing-type="sro" data-n-issues="">' +
        '<td class="select-cell"><input type="checkbox" class="row-select" data-type="building" data-target="7"></td>' +
        '<td>12 Oak &amp; Elm St</td><td data-sort-value="West End">West End</td>' +
        '<td data-sort-value="40">40</td>' +
        '<td>Example &quot;Holdings&quot;</td><td>Example Group</td>' +
        '<td data-sort-value="1965">1965</td><td data-sort-value="sro">sro</td></tr>',
    );
  });

  it('leaves the network cell blank when it names the owner again', () => {
    const row = buildingRow(rec({ owner_name: 'GLR PROPERTIES LTD.', network_name: 'Glr Properties Ltd' }));
    expect(row).toContain('<td>GLR PROPERTIES LTD.</td><td></td>');
  });

  it('leaves missing values empty and keeps them out of the search text', () => {
    const row = buildingRow(rec({ b_id: 9, address: 'X', local_area: null, block_id: null, units: null, year_built: null }));
    expect(row).toContain('data-block="" data-area=""');
    expect(row).toContain('data-units="" data-year-built=""');
    expect(row).toContain('data-search="x o"');
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
