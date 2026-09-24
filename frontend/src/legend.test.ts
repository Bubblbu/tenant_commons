import { describe, expect, it } from 'vitest';
import { blockLegendMax, blockTicks, hoodTagsHtml, specialAreaTagsHtml } from './legend';

describe('hoodTagsHtml', () => {
  it('renders one checked filter tag per neighbourhood, as legends_html did', () => {
    expect(hoodTagsHtml([{ name: 'West End', count: 1234, units: 56789 }])).toBe(
      '<label class="filter-tag"><input type="checkbox" class="filter-neighbourhood-option" ' +
        'value="west end" checked> West End ' +
        '<span class="filter-tag-count">(1,234 bldgs · 56,789 units)</span></label>',
    );
  });
  it('says so when there is no neighbourhood data', () => {
    expect(hoodTagsHtml([])).toBe('<em class="filter-none">No neighbourhood data</em>');
  });
  it('appends Chinatown/Villages Plan after a separator, same checkbox class', () => {
    const html = hoodTagsHtml(
      [{ name: 'West End', count: 1234, units: 56789 }],
      [{ key: 'chinatown', name: 'Chinatown', count: 12, units: 340 }],
    );
    expect(html).toContain('West End');
    expect(html.indexOf('<hr class="filter-tag-separator">')).toBeGreaterThan(html.indexOf('West End'));
    expect(html).toContain(
      '<label class="filter-tag"><input type="checkbox" class="filter-neighbourhood-option" ' +
        'value="chinatown" checked> Chinatown ' +
        '<span class="filter-tag-count">(12 bldgs · 340 units)</span></label>',
    );
  });
});

describe('specialAreaTagsHtml', () => {
  it('renders nothing when there are no special areas', () => {
    expect(specialAreaTagsHtml(undefined)).toBe('');
    expect(specialAreaTagsHtml([])).toBe('');
  });
});

describe('block legend', () => {
  it('draws six ticks from 0 to the maximum', () => {
    expect(blockTicks(1000)).toEqual(['0', '200', '400', '600', '800', '1,000']);
    expect(blockTicks(7)).toEqual(['0', '1', '3', '4', '6', '7']);
    expect(blockTicks(0)).toEqual(['0', '0', '0', '0', '0', '0']);
  });
  it('falls back to 0 when no max is set', () => {
    expect(blockLegendMax({ schema_version: 1, blocks_total_units_max: 480 })).toBe(480);
    expect(blockLegendMax({ schema_version: 1 })).toBe(0);
  });
});
