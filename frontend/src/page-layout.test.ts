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

const wiring = readFileSync(new URL('./wiring.js', import.meta.url), 'utf8');

describe('Landlords tab', () => {
  it('has an Owners and a Networks table with the totals cells wiring.js fills', () => {
    const ids = [
      'owners-table', 'networks-table', 'owners-panel', 'networks-panel',
      'landlord-view-owners', 'landlord-view-networks',
      ...['owners', 'networks'].flatMap((t) => ['label', 'bldgs', 'units', 'avg'].map((c) => `summary-${t}-${c}`)),
    ];
    for (const id of ids) expect(page).toContain(`id="${id}"`);
    expect(page).not.toContain('id="landlords-table"');
  });

  it('is wired for both views', () => {
    expect(wiring).toContain("'#owners-table tbody tr'");
    expect(wiring).toContain("'#networks-table tbody tr'");
    expect(wiring).toContain("typ === 'network'");
    expect(wiring).not.toMatch(/landlords-table|summary-landlords/);
  });
});
