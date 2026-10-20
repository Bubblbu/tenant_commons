/**
 * The flat view model the sidebar tables, landlord picker, map indexes,
 * coverage panel and CSV export read (spec 2026-10-08 §8). The popup reads
 * the nested Building instead. Missing values are null — never "unknown".
 */
import type { Building, Network, Party } from './contract.gen';
import type { BuildingRecord } from './types';

const OWNER_SOURCE: Record<string, string> = { registry: 'registry', licence: 'licence', sro_inventory: 'sro_list' };

export const FLAT_COLUMNS = [
  'b_id', 'source', 'address', 'building_name', 'local_area', 'units', 'year_built',
  'owner_name', 'owner_key', 'owner_source', 'licence_holder', 'managed_by',
  'network_key', 'network_name', 'network_source', 'network_buildings_on_map',
  'network_evidence_registry', 'network_evidence_city', 'network_evidence_research',
  'pids', 'registry_no_filing', 'value_land', 'value_bldg', 'bldg_land_ratio', 'land_share_pctl',
  'housing_type', 'rezoning_status', 'n_issues', 'issues_details',
  'areas', 'lat', 'lon',
];

const first = (b: Building, role: Party['role']): Party | null => b.parties.find((p) => p.role === role) ?? null;

export function flatten(b: Building, networks: Record<string, Network>): BuildingRecord {
  const owner = first(b, 'owner');
  const net = b.network_id ? networks[b.network_id] ?? null : null;
  const housing = [b.coop ? 'co-op' : '', b.sro ? 'sro' : ''].filter(Boolean).join(', ');
  return {
    b_id: b.id,
    source: b.origin,
    address: b.address,
    building_name: b.name,
    other_names: b.also_known_as,
    local_area: b.local_area,
    units: b.units,
    year_built: b.year_built,
    owner_name: owner?.name ?? null,
    owner_key: owner?.entity_key ?? null,
    owner_source: owner ? OWNER_SOURCE[owner.sources[0]?.type ?? ''] ?? null : null,
    licence_holder: first(b, 'licensee')?.name ?? null,
    managed_by: first(b, 'manager')?.name ?? null,
    network_key: net?.id ?? null,
    network_name: net?.name ?? null,
    network_source: net ? (net.tier === 'confirmed' ? 'claims' : 'name_match') : null,
    network_name_source: net?.name_source ?? null,
    network_entities: net ? net.entities.map((e) => e.name) : null,
    network_evidence: net ? net.evidence : null,
    network_evidence_registry: net ? net.evidence.registry : null,
    network_evidence_city: net ? net.evidence.city_records : null,
    network_evidence_research: net ? net.evidence.vtu_research : null,
    network_buildings_on_map: net?.totals.buildings ?? null,
    pids: b.pids.length ? b.pids.join('; ') : null,
    registry_no_filing: b.registry_search.status === 'no_filing' ? b.registry_search.date : null,
    value_land: b.value?.land ?? null,
    value_bldg: b.value?.building ?? null,
    bldg_land_ratio: b.value && b.value.land > 0 ? b.value.building / b.value.land : null,
    land_share_pctl: b.value?.land_share_pctl ?? null,
    housing_type: housing,
    rezoning_status: b.rezoning?.status ?? null,
    n_issues: b.issues?.count ?? null,
    issues_details: b.issues?.url ?? null,
    areas: b.areas.length ? b.areas.join('; ') : null,
    lat: b.lat,
    lon: b.lon,
  };
}
