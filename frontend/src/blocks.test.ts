import { describe, expect, it } from 'vitest';
import { blockPopupHtml, blockStyle, greensColor, maxTotalUnits } from './blocks';
import type { BlocksCollection } from './types';

describe('greensColor', () => {
  it('matches colors.py greens_color at each threshold', () => {
    expect([0, 0.1, 0.2, 0.5, 0.75, 0.99, 1, 2, null].map(greensColor)).toEqual([
      '#c7e9c0', '#c7e9c0', '#a1d99b', '#74c476', '#41ab5d', '#238b45', '#005a32', '#005a32', '#c7e9c0',
    ]);
  });
});

describe('blockStyle', () => {
  it('leaves empty blocks transparent', () => {
    expect(blockStyle({ buildings: 0, total_units: 0 }, 100)).toEqual({
      fillColor: 'transparent', color: '#b8b8b8', weight: 1, fillOpacity: 0,
    });
  });
  it('scales units against the dataset maximum', () => {
    expect(blockStyle({ buildings: 3, total_units: 50 }, 100)).toEqual({
      fillColor: '#74c476', color: '#b8b8b8', weight: 1, fillOpacity: 0.7,
    });
  });
});

describe('maxTotalUnits', () => {
  it('takes the largest total_units, truncated like int()', () => {
    const fc = { type: 'FeatureCollection', schema_version: 1, features: [
      { type: 'Feature', geometry: null, properties: { total_units: 12.9 } },
      { type: 'Feature', geometry: null, properties: { total_units: null } },
    ] } as unknown as BlocksCollection;
    expect(maxTotalUnits(fc)).toBe(12);
  });
});

describe('blockPopupHtml', () => {
  it('lists the six Folium popup fields in order, escaping text and not grouping the year', () => {
    const html = blockPopupHtml({
      block_label: 'West <End>-03', buildings: 12, total_units: 1234, median_year_built: 1965.4,
      member_buildings: 2, total_members: 3,
    });
    const aliases = [...html.matchAll(/<th>([^<]*)<\/th>/g)].map((m) => m[1]);
    expect(aliases).toEqual(['Block', 'Buildings', '# Units', 'Median year', 'Buildings w/ VTU', 'Total VTU members']);
    expect(html).toContain('West &lt;End&gt;-03');
    expect(html).toContain('<td>1965</td>');
    expect(html).toContain('<td>1,234</td>'); // en-US grouping whatever the locale
  });
});
