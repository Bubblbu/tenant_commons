import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

// The fragments lay the page out as a flex row on <body> and target the map as
// `body>.folium-map` (sidebar order 0, map order 1, filters order 2). Folium's
// map div carried that class and was position:relative; an absolutely
// positioned full-page map would cover both sidebars.
const page = readFileSync(new URL('../index.html', import.meta.url), 'utf8');

describe('index.html page layout', () => {
  it('makes the map a flex item the fragments can place between the sidebars', () => {
    expect(page).toMatch(/<div id="map" class="folium-map"><\/div>/);
  });

  it('does not absolutely position the map over the sidebars', () => {
    const mapRule = page.match(/#map\s*\{[^}]*\}/)?.[0] ?? '';
    expect(mapRule).not.toMatch(/position:\s*absolute/);
  });
});
