import { describe, expect, it } from 'vitest';
import type { Building, Network } from './contract.gen';
import { FLAT_COLUMNS, flatten } from './flat';

const network: Network = {
  id: 'net:cressey', name: 'Cressey Development Group', name_source: 'claim', tier: 'confirmed',
  evidence: { registry: 7, vtu_research: 9 }, entities: ['A', 'B'],
  totals: { buildings: 10, units: 609, open_issues: 2, properties_on_title: 10 },
};

const york: Building = {
  id: 1, origin: 'building', address: '2145 york ave', name: 'Yorkshire Apartments', also_known_as: [],
  local_area: 'Kitsilano', block_id: 5, lat: 49.27, lon: -123.15, in_chinatown: false, in_village_plan: false,
  units: 43, units_basis: 'inventory', year_built: 1979, listed_in: ['rental_inventory'],
  value: { land: 8721000, building: 11437000, land_share: 0.43, land_share_pctl: 20 },
  issues: { count: 1, url: 'http://app.vancouver.ca/x' },
  parties: [
    { role: 'owner', name: 'Yorkshire Place Apts. Ltd.', entity_key: 'yorkshire-place-apts-ltd', kind: null,
      interest: null, pids: ['007-273-924'], same_as: null,
      sources: [{ type: 'registry', as_of: '2024-05-03', url: null }, { type: 'licence', as_of: null, url: null }] },
    { role: 'manager', name: 'Cascadia Apartment Rentals', entity_key: 'cascadia-apartment-rentals', kind: null,
      interest: null, pids: [], same_as: null, sources: [{ type: 'listing', as_of: '2026-09-30', url: 'https://c.example' }] },
  ],
  network_id: 'net:cressey', registry_search: { status: 'filed', date: null },
  coop: null, sro: { rooms: 10, occupancy: 'open', owner_sector: 'private', operator_sector: null }, rezoning: null,
};

describe('flatten', () => {
  it('gives the tables the fields they read, with nulls not sentinels', () => {
    const f = flatten(york, { 'net:cressey': network });
    expect(f).toMatchObject({
      b_id: 1, source: 'building', address: '2145 york ave', building_name: 'Yorkshire Apartments',
      owner_key: 'yorkshire-place-apts-ltd', owner_name: 'Yorkshire Place Apts. Ltd.', owner_source: 'registry',
      network_key: 'net:cressey', network_name: 'Cressey Development Group', network_source: 'claims',
      network_evidence: { registry: 7, vtu_research: 9 }, network_name_source: 'claim',
      managed_by: 'Cascadia Apartment Rentals', housing_type: 'sro', n_issues: 1,
      value_land: 8721000, value_bldg: 11437000, registry_no_filing: null,
    });
    expect(f.bldg_land_ratio).toBeCloseTo(11437000 / 8721000);
  });

  it('marks an owner-less building with nulls', () => {
    const f = flatten({ ...york, parties: [], network_id: null, registry_search: { status: 'no_filing', date: '2026-10-06' } }, {});
    expect(f.owner_key).toBeNull();
    expect(f.network_key).toBeNull();
    expect(f.registry_no_filing).toBe('2026-10-06');
  });

  it('has one plain column per field for the CSV', () => {
    const f = flatten(york, { 'net:cressey': network });
    for (const col of FLAT_COLUMNS) {
      const v = f[col];
      expect(v === null || ['string', 'number', 'boolean'].includes(typeof v), col).toBe(true);
    }
  });
});
