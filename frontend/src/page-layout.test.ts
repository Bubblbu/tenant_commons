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

describe('sidebar', () => {
  it('orders the data tabs Buildings, Landlords, Neighbourhoods, opening on Buildings', () => {
    const tabs = [...page.matchAll(/<button id="tab-(\w+)"( class="active")?>/g)].map((m) => m[1] + (m[2] ? '*' : ''));
    expect(tabs).toEqual(['buildings*', 'landlords', 'neighbourhoods']);
    expect(page).toContain('<div id="pane-buildings" class="pane active">');
    expect(page).toContain('<div id="pane-neighbourhoods" class="pane">');
  });

  it('keeps the blocks table without a tab: the map block filter reads its rows', () => {
    expect(page).toContain('id="blocks-table"');
    expect(page).not.toContain('id="tab-blocks"');
  });

  it('shows the selection hint above the table search, as a note', () => {
    expect(page.indexOf('class="sidebar-hint"')).toBeLessThan(page.indexOf('id="table-search-bar"'));
  });

  it('has a Name column right after Address in the Buildings table', () => {
    const head = page.slice(page.indexOf('id="buildings-table"'), page.indexOf('</thead>', page.indexOf('id="buildings-table"')));
    expect(head).toMatch(/<th data-sort="text">Address<\/th>\s*<th data-sort="text">Name<\/th>/);
  });

  it('lists open issues instead of housing type in the Buildings table', () => {
    const head = page.slice(page.indexOf('id="buildings-table"'), page.indexOf('</thead>', page.indexOf('id="buildings-table"')));
    expect(head).toContain('<th data-sort="number">Open issues</th>');
    expect(head).not.toContain('Housing type');
  });
});

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

  it('marks the Landlord and Ownership group headers for explainer icons', () => {
    const head = (table: string) =>
      page.slice(page.indexOf(`id="${table}"`), page.indexOf('</thead>', page.indexOf(`id="${table}"`)));
    expect(head('owners-table')).toMatch(/data-explain="owner">Landlord</);
    expect(head('networks-table')).toMatch(/data-explain="network">Ownership group</);
    expect(head('buildings-table')).toMatch(/data-explain="owner">Landlord</);
    expect(head('buildings-table')).not.toContain('data-explain="network"');
  });

  it('opens on the by-landlord view, with ownership groups one click away', () => {
    expect(page).toMatch(/id="landlord-view-owners" class="active" aria-pressed="true">By landlord</);
    expect(page).toMatch(/id="landlord-view-networks" aria-pressed="false">By ownership group</);
    expect(page).toMatch(/id="networks-panel" hidden/);
    expect(page).not.toMatch(/id="owners-panel" hidden/);
  });

  it('keeps "Not on record" rows at the bottom when a column is sorted', () => {
    expect(wiring).toMatch(/pinLast\(/);
  });

  it('does not sort when an explainer icon in a header is clicked', () => {
    expect(wiring).toMatch(/closest\('\.prov'\)/);
  });

  it('is wired for both views', () => {
    expect(wiring).toContain("'#owners-table tbody tr'");
    expect(wiring).toContain("'#networks-table tbody tr'");
    expect(wiring).toContain("typ === 'network'");
    expect(wiring).not.toMatch(/landlords-table|summary-landlords/);
  });
});
