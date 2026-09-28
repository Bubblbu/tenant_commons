import type * as L from 'leaflet';
import type { LandlordFilter } from '../landlord-picker';
import type { StyledMarker } from '../markers';
import type { BuildingData, FilterConfig } from '../types';

/** A building's CircleMarker plus the state wiring keeps on it. */
export interface BuildingMarker extends L.CircleMarker {
  _baseColor: string;
  _baseOpacity: number;
  _baseRadius: number;
  _strokeColor: string;
  _strokeWeight: number;
  _primaryHousingType: string;
  _housingType: string;
  _extraRings: { housingType: string; marker: L.CircleMarker }[] | null;
  _units: number;
  _yearBuilt: number | null;
  _isFiltered: boolean;
  _selectionRefs: number;
  _highlighted: boolean;
}

/** One block polygon of the blocks GeoJSON layer. */
export interface BlockLayer extends L.Path {
  feature: { properties: Record<string, unknown> };
  _blockUnits: number;
  _blockBuildings: number;
  _baseStyle: L.PathOptions;
  _isFiltered: boolean;
  _selectionRefs: number;
  _highlighted: boolean;
}

/** Lookup tables built once at start-up (formerly window.* globals). */
export interface MapIndex {
  buildings: Record<string, BuildingMarker>;
  blocks: Record<string, BlockLayer>;
  /** Block layers in GeoJSON order. */
  blockLayers: BlockLayer[];
  blockBuildings: Record<string, string[]>;
  owners: Record<string, BuildingMarker[]>;
  networks: Record<string, BuildingMarker[]>;
  /** Keyed by lowercased, trimmed local_area. */
  hoods: Record<string, BuildingMarker[]>;
}

/** A sidebar table row with the lookups cached on it at start-up. */
export interface CachedRow extends HTMLTableRowElement {
  __checkbox: HTMLInputElement | null;
  __cells?: Record<string, Element | null>;
  __lastMetrics?: { bldgs: number; units: number; avg: number; medianYear: number | null };
}

export interface WiringContext {
  map: L.Map;
  layers: {
    blocks: L.GeoJSON;
    buildings: L.FeatureGroup;
    neighbourhoods: L.FeatureGroup;
    villages: L.FeatureGroup;
    chinatown: L.FeatureGroup;
  };
  markersById: Record<string, L.CircleMarker>;
  ringsById: Record<string, { housing_type: string; marker: L.CircleMarker }[]>;
  filterConfig: FilterConfig;
  markers: StyledMarker[];
  buildingData: BuildingData;
  landlordFilter?: LandlordFilter;
  /** Called after every filter pass with the b_ids of the buildings that pass. */
  onFilter?: (visibleBids: Set<string>) => void;
}
