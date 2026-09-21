import { describe, expect, it } from 'vitest';
import { blockRowsHtml, buildingRow, buildingRowsHtml, landlordRowsHtml, neighbourhoodRowsHtml } from './tables';
import type { BlocksCollection, BuildingRecord } from './types';

const rec = (over: Partial<BuildingRecord>): BuildingRecord => ({
  b_id: 1, address: 'A', local_area: 'West End', block_id: 1, units: 10, member_count: 0,
  member_share_pct: 0, year_built: 1970, owner_group: 'O', owner_key: 'o', member_count_all: 0,
  value_land: 1, value_bldg: 1, bldg_land_ratio: 1, has_vtu_member: false, latest_membership_year: null,
  housing_type: '', ...over,
});

describe('buildingRow', () => {
  it("reproduces rows_buildings' markup exactly", () => {
    const row = buildingRow(rec({
      b_id: 7, address: '12 Oak & Elm St', block_id: 3.0, units: 40.0, member_count: 1,
      member_share_pct: 6, year_built: 1965.0, owner_group: 'Example "Holdings"',
      owner_key: 'example-holdings', member_count_all: 2, value_land: 5000000.4, value_bldg: 800000.0,
      bldg_land_ratio: 0.16, has_vtu_member: true, latest_membership_year: 2025.0, housing_type: 'sro',
    }));
    expect(row).toBe(
      '<tr data-bid="7" data-owner="example-holdings" data-block="3" data-area="West End" ' +
        'data-value-land="5000000" data-value-bldg="800000" data-value-ratio="0.16" data-units="40" ' +
        'data-year-built="1965" data-has-vtu-member="1" data-latest-membership-year="2025" ' +
        'data-member-total="2" data-search="12 oak &amp; elm st west end 3 40 1 example &quot;holdings&quot; sro" ' +
        'data-housing-type="sro">' +
        '<td class="select-cell"><input type="checkbox" class="row-select" data-type="building" data-target="7"></td>' +
        '<td>12 Oak &amp; Elm St</td><td data-sort-value="West End">West End</td>' +
        '<td data-sort-value="3">3</td><td data-sort-value="40">40</td><td data-sort-value="1">1</td>' +
        '<td data-sort-value="6">6%</td><td>Example &quot;Holdings&quot;</td>' +
        '<td data-sort-value="1965">1965</td><td data-sort-value="sro">sro</td></tr>',
    );
  });

  it('leaves missing values empty and keeps them out of the search text', () => {
    const row = buildingRow(rec({ b_id: 9, address: 'X', local_area: null, block_id: null, units: null, year_built: null }));
    expect(row).toContain('data-block="" data-area=""');
    expect(row).toContain('data-units="" data-year-built=""');
    expect(row).toContain('data-search="x 0 o"');
  });
});

describe('buildingRowsHtml', () => {
  it('sorts by members then units, descending, with missing units last', () => {
    const html = buildingRowsHtml([
      rec({ b_id: 1, member_count: 0, units: 5 }),
      rec({ b_id: 2, member_count: 1, units: null }),
      rec({ b_id: 3, member_count: 1, units: 50 }),
      rec({ b_id: 4, member_count: 0, units: 90 }),
    ]);
    expect([...html.matchAll(/data-bid="(\d+)"/g)].map((m) => m[1])).toEqual(['3', '2', '4', '1']);
  });
});

describe('blockRowsHtml', () => {
  it('sorts labelled blocks before (Unknown) ones and rounds like pandas', () => {
    const fc = { type: 'FeatureCollection', schema_version: 1, features: [
      { type: 'Feature', geometry: null, properties: { block_id: 5, block_label: '(Unknown)-01', local_area: null, buildings: 0, total_units: 0, median_year_built: null, member_buildings: 0 } },
      { type: 'Feature', geometry: null, properties: { block_id: 6, block_label: 'West End-02', local_area: 'West End', buildings: 2, total_units: 25, median_year_built: 1966.5, member_buildings: 1 } },
    ] } as unknown as BlocksCollection;
    const html = blockRowsHtml(fc);
    expect([...html.matchAll(/data-block="(\d+)"/g)].map((m) => m[1])).toEqual(['6', '5']);
    expect(html).toContain('<td data-sort-value="12.5">12.5</td>'); // avg units
    expect(html).toContain('<td data-sort-value="1966">1966</td>'); // 1966.5 -> 1966 (half to even)
  });
});

describe('group tables', () => {
  const records = [
    rec({ b_id: 1, owner_group: 'B Co', owner_key: 'b', units: 10, has_vtu_member: true, local_area: 'West End' }),
    rec({ b_id: 2, owner_group: 'A Co', owner_key: 'a', units: 30, local_area: null }),
    rec({ b_id: 3, owner_group: 'B Co', owner_key: 'b', units: 5, local_area: 'West End' }),
  ];

  it('groups landlords by owner, sorted by total units', () => {
    const html = landlordRowsHtml(records);
    expect([...html.matchAll(/data-owner="([^"]+)"/g)].map((m) => m[1])).toEqual(['a', 'b']);
    expect(html).toContain('data-owner="b" data-bldgs="2" data-units="15" data-vtu-bldgs="1"');
  });

  it('groups neighbourhoods, putting missing areas under (Unknown)', () => {
    const html = neighbourhoodRowsHtml(records);
    expect([...html.matchAll(/<tr data-area="([^"]+)"/g)].map((m) => m[1])).toEqual(['(Unknown)', 'West End']);
  });
});
