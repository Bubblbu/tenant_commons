// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { buildingRow, filterFields } from './tables';
import type { BuildingRecord } from './types';

function renderedRow(r: BuildingRecord): HTMLTableRowElement {
  const t = document.createElement('template');
  t.innerHTML = `<table><tbody>${buildingRow(r)}</tbody></table>`;
  const row = t.content.querySelector('tr');
  if (!row) throw new Error('no row');
  return row;
}

const attrOf = (v: number | null) => (v === null ? '' : String(v));

describe('filterFields', () => {
  it('agrees with every data-* attribute the building row renders', () => {
    const r: BuildingRecord = {
      b_id: 7, local_area: ' West End ', owner_key: 'smith & sons', owner_name: 'Smith & Sons',
      network_key: 'nw<1>', network_name: 'N', managed_by: 'Tribe Management',
      housing_type: 'co-op, sro', n_issues: 2.7, units: 12.9, year_built: 1965,
      value_land: 1234567.5, value_bldg: null, bldg_land_ratio: 0.12345,
      in_chinatown: true, in_village_plan: false,
    };
    const f = filterFields(r);
    const row = renderedRow(r);
    const a = (name: string) => row.getAttribute(`data-${name}`);
    expect(a('bid')).toBe(f.bid);
    expect(a('area')?.toLowerCase().trim()).toBe(f.area);
    expect(a('owner')).toBe(f.owner);
    expect(a('network')).toBe(f.network);
    expect(a('manager')).toBe(f.manager);
    expect(a('chinatown')).toBe(f.chinatown ? '1' : '');
    expect(a('village')).toBe(f.village ? '1' : '');
    expect(a('has-owner')).toBe(f.hasOwner ? '1' : '');
    expect(a('n-issues')).toBe(attrOf(f.nIssues));
    expect((a('housing-type') ?? '').split(',').map((t) => t.trim()).filter(Boolean)).toEqual(f.housingTypes);
    for (const attr of ['units', 'year-built', 'value-land', 'value-bldg', 'value-ratio']) {
      expect(a(attr)).toBe(attrOf(f.metrics[attr]));
    }
    expect(f).toMatchObject({ owner: 'smith & sons', nIssues: 2, housingTypes: ['co-op', 'sro'] });
    expect(f.metrics).toMatchObject({ units: 12, 'year-built': 1965, 'value-bldg': null });
  });

  it('treats a bare record as missing everything', () => {
    const f = filterFields({ b_id: 3 });
    expect(f).toMatchObject({ area: '', owner: '', hasOwner: false, nIssues: null, housingTypes: [] });
    expect(renderedRow({ b_id: 3 }).getAttribute('data-units')).toBe('');
  });
});
