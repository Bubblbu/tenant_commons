/**
 * Every colour (and highlight/stroke weight) Leaflet paints on the map. CSS
 * cannot reach these — Leaflet draws them onto a canvas — so they live here
 * as JS values. Page (sidebar/filters) colours are in index.html's CSS.
 */
export const MAP_THEME = {
  highlight: { color: '#ff1744', markerWeight: 2, blockWeight: 4 },
  marker: {
    stroke: '#ffffff',
    strokeWeight: 0.6,
    fill: '#9e9e9e',
    rings: { coop: '#d97706', sro: '#3182bd', issues: '#dc2626' },
  },
  block: {
    stroke: '#b8b8b8',
    /** Light to dark, by share of the visible blocks' unit range. */
    scale: ['#c7e9c0', '#a1d99b', '#74c476', '#41ab5d', '#238b45', '#005a32'],
    unscaledFill: '#f0f0f0',
    filteredFill: '#f5f5f5',
  },
  boundary: { neighbourhood: '#ff8c00', villages: '#7b3fa0', chinatown: '#c0392b', labelHalo: '#fff' },
} as const;
