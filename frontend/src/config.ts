/** Presentation settings, formerly config.toml's [options] and build.py's tile presets. */

/** config.toml's former [options].sidebar_width. */
export const SIDEBAR_WIDTH = 540;
/** legends_html(): the block legend sits just right of the sidebar. */
export const LEGEND_LEFT_OFFSET = SIDEBAR_WIDTH + 20;

/** Must match index.html's `@media (max-width: ...)` breakpoint for the mobile drawer layout. */
export const MOBILE_BREAKPOINT_PX = 768;

/** The artifact contract version this frontend understands (spec §4). */
export const EXPECTED_SCHEMA_VERSION = 1;

/** Artifact files live at <base>/data/ (served or copied by artifacts-plugin.ts). */
export function artifactUrl(name: string): string {
  return `${import.meta.env.BASE_URL}data/${name}`;
}

export interface Basemap {
  tiles: string;
  attribution: string;
  /** Optional reference layer (street/place labels) drawn above the base tiles. */
  labels?: string;
  /** Deepest zoom the base tiles have real imagery for; Leaflet upscales them beyond it. */
  maxNativeZoom?: number;
}

/** Street-level zoom; without it Leaflet drops tile layers past their default maxZoom (18). */
export const MAX_ZOOM = 19;

// Keyless Esri Light Gray Canvas. CARTO retired unauthenticated access to its
// positron tiles; this is the closest drop-in that needs no key.
const ESRI_CANVAS = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas';
const ESRI_GRAY_ATTR = 'Tiles © Esri — Esri, HERE, Garmin, © OpenStreetMap contributors';

export const BASEMAPS: Record<string, Basemap> = {
  'esri-gray': {
    tiles: `${ESRI_CANVAS}/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}`,
    attribution: ESRI_GRAY_ATTR,
    labels: `${ESRI_CANVAS}/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}`,
    // Light Gray Base serves a "Map data not yet available" placeholder from z17.
    maxNativeZoom: 16,
  },
  'esri-gray-plain': {
    tiles: `${ESRI_CANVAS}/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}`,
    attribution: ESRI_GRAY_ATTR,
    maxNativeZoom: 16,
  },
};

/** config.toml's former [options].tiles. */
export const DEFAULT_BASEMAP = 'esri-gray';
/** Only used if filter_config.json has no bounds; build.py's fallback. */
export const DEFAULT_CENTER: [number, number] = [49.286, -123.135];
export const DEFAULT_ZOOM = 14;
