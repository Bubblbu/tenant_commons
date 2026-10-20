/** Popup test buildings: the spec's four real cases plus an overlay record. */
import type { Building, Network, Party } from '../contract.gen';
import type { PopupContext } from './index';

const party = (p: Partial<Party> & Pick<Party, 'role' | 'name'>): Party => ({
  entity_key: p.name.toLowerCase(), kind: null, interest: null, pids: [], same_as: null, sources: [], ...p,
});
const base = (b: Partial<Building> & Pick<Building, 'id' | 'address'>): Building => ({
  origin: 'building', name: null, also_known_as: [], pids: [], local_area: null, lat: 49.2, lon: -123.1,
  areas: [], units: null, units_basis: null, year_built: null, listed_in: [],
  value: null, issues: null, parties: [], network_id: null, registry_search: { status: 'not_searched', date: null },
  coop: null, sro: null, rezoning: null, ...b,
});

export const NETWORKS: Record<string, Network> = {
  'net:cressey': { id: 'net:cressey', name: 'Cressey Development Group', name_source: 'claim', tier: 'confirmed',
    evidence: { registry: 7, city_records: 0, vtu_research: 9 },
    entities: [
      { name: 'Cressey, Norman Edward', also_named: ['Norman Cressey'], kind: 'person', buildings: 0 },
      { name: 'Cressey, Scott Edward', also_named: [], kind: 'person', buildings: 0 },
      { name: 'Victoria Place Apts. Ltd.', also_named: [], kind: 'company', buildings: 2 },
      { name: 'Yorkshire Place Apts. Ltd.', also_named: ['Yorkshire Place Apt Ltd'], kind: 'company', buildings: 1 },
      ...Array.from({ length: 14 }, (_, i) => ({ name: `Cressey Holding ${i} Ltd`, also_named: [], kind: 'company' as const, buildings: 0 })),
    ],
    totals: { buildings: 10, units: 609, open_issues: 2, properties_on_title: 10 } },
  'net:lotus': { id: 'net:lotus', name: 'Lotus Capital', name_source: 'claim', tier: 'confirmed',
    evidence: { registry: 55, city_records: 0, vtu_research: 8 },
    entities: [{ name: 'A Ltd', also_named: [], kind: 'company', buildings: 1 }],
    totals: { buildings: 10, units: 500, open_issues: 3, properties_on_title: 11 } },
  'bc-housing': { id: 'bc-housing', name: 'BC Housing', name_source: 'default', tier: 'name_match',
    evidence: { registry: 0, city_records: 0, vtu_research: 0 }, entities: [],
    totals: { buildings: 33, units: 2000, open_issues: 90, properties_on_title: null } },
  'feliz-enterprises-ltd': { id: 'feliz-enterprises-ltd', name: 'Feliz Enterprises Ltd', name_source: 'default',
    tier: 'name_match', evidence: { registry: 0, city_records: 0, vtu_research: 0 }, entities: [],
    totals: { buildings: 1, units: 265, open_issues: 0, properties_on_title: null } },
};

export const YORK = base({
  id: 1, address: '2145 york ave', name: 'Yorkshire Apartments', pids: ['007-273-924'], local_area: 'Kitsilano', units: 43,
  units_basis: 'inventory', year_built: 1979, listed_in: ['rental_inventory'],
  value: { land: 8721000, building: 11437000, land_share: 0.433, land_share_pctl: 12 },
  issues: { count: 1, url: 'http://app.vancouver.ca/RPS_Net/x' }, network_id: 'net:cressey',
  registry_search: { status: 'filed', date: null },
  parties: [
    party({ role: 'owner', name: 'Yorkshire Place Apts. Ltd.', pids: ['007-273-924'],
      sources: [{ type: 'registry', as_of: '2024-05-03', url: null }, { type: 'licence', as_of: null, url: null }] }),
    party({ role: 'interest_holder', name: 'DOE, JANE', interest: 'interest holder', pids: ['007-273-924'] }),
    party({ role: 'interest_holder', name: 'ROE, RICHARD', interest: 'trustee', pids: ['007-273-924'] }),
    party({ role: 'manager', name: 'Cascadia Apartment Rentals',
      sources: [{ type: 'listing', as_of: '2026-09-30', url: 'https://cascadia.example/l/1' }] }),
    party({ role: 'licensee', name: 'Yorkshire Place Apt Ltd', same_as: 'owner',
      sources: [{ type: 'licence', as_of: null, url: null }] }),
  ],
});

export const MARBLE_ARCH = base({
  id: 2, address: '518 richards st', name: 'Marble Arch Hotel', also_known_as: ['Hotel Canada (Formerly Marble Arch)'],
  local_area: 'Downtown', units: 150, units_basis: 'inventory', year_built: 2007,
  listed_in: ['non_market_list', 'sro_inventory'],
  value: { land: 2393001, building: 313001, land_share: 0.884, land_share_pctl: 59 },
  issues: { count: 27, url: 'http://app.vancouver.ca/RPS_Net/y' }, network_id: 'bc-housing',
  sro: { rooms: 150, occupancy: 'open', owner_sector: 'government', operator_sector: 'non_profit' },
  parties: [
    party({ role: 'owner', name: 'BC Housing', sources: [{ type: 'sro_inventory', as_of: null, url: null }] }),
    party({ role: 'manager', name: 'Atira Property Management', sources: [{ type: 'sro_inventory', as_of: null, url: null }] }),
    party({ role: 'licensee', name: 'PHS Community Services Society', sources: [{ type: 'licence', as_of: null, url: null }] }),
  ],
});

export const E2ND = base({
  id: 3, address: '396 e 2nd ave', local_area: 'Mount Pleasant', units: 53, units_basis: 'inventory',
  year_built: 1978, listed_in: ['rental_inventory', 'rezoning'], network_id: 'net:lotus',
  registry_search: { status: 'filed', date: null },
  value: { land: 18949000, building: 534000, land_share: 0.973, land_share_pctl: 89 },
  rezoning: { status: 'approved', category: 'approved_market', detail: 'Approved March 13, 2025',
    url: 'https://www.shapeyourcity.ca/396-e-2-ave' },
  parties: [party({ role: 'owner', name: '396 EAST 2ND AVENUE HOLDINGS LTD.', pids: ['011-111-111'],
    sources: [{ type: 'registry', as_of: '2026-03-26', url: null }] })],
});

export const BIDWELL = base({
  id: 4, address: '1255 bidwell st', local_area: 'West End', units: 265, units_basis: 'inventory', year_built: 1963,
  network_id: 'feliz-enterprises-ltd',
  parties: [
    party({ role: 'owner', name: 'Feliz Enterprises Ltd', sources: [{ type: 'licence', as_of: null, url: null }] }),
    party({ role: 'licensee', name: 'Feliz Enterprises Ltd', same_as: 'owner', sources: [{ type: 'licence', as_of: null, url: null }] }),
  ],
});

export const OVERLAY = base({ id: 5, address: '9 nowhere st', origin: 'overlay_sro', name: 'Example Rooms',
  sro: { rooms: null, occupancy: 'open', owner_sector: null, operator_sector: null }, listed_in: ['sro_inventory'] });

export const CTX: PopupContext = { networks: NETWORKS, licenceYear: 2026, landShareMedian: 0.79 };
