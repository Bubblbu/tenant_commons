// frontend/src/wiring.d.ts — types for wiring.js, which stays JavaScript (spec §2).
import type { CircleMarker, FeatureGroup, GeoJSON, Map } from 'leaflet';
import type { StyledMarker } from './markers';
import type { BuildingData, FilterConfig } from './types';

export interface WiringContext {
  map: Map;
  layers: {
    blocks: GeoJSON;
    buildings: FeatureGroup;
    neighbourhoods: FeatureGroup;
    villages: FeatureGroup;
    chinatown: FeatureGroup;
  };
  markersById: Record<string, CircleMarker>;
  ringsById: Record<string, { housing_type: string; marker: CircleMarker }[]>;
  filterConfig: FilterConfig;
  markers: StyledMarker[];
  buildingData: BuildingData;
}

export function startWiring(ctx: WiringContext): void;
