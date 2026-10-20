import { describe, expect, it } from 'vitest';
import { overlayLabelHtml, overlayLegendRowsHtml, overlayLook, overlayPathOptions, overlayTogglesHtml } from './overlays';

const AREAS = [
  { key: 'chinatown', name: 'Chinatown', count: 3, units: 40 },
  { key: 'deod', name: 'DEOD', count: 2, units: 90 },
  { key: 'village-plan', name: 'Villages Plan', count: 1, units: 8 },
  { key: 'gastown', name: 'Gastown', count: 0, units: 0 },
];
const ALL = new Set(AREAS.map((a) => a.key));

describe('overlay looks', () => {
  it('keeps Chinatown red and solid, the Villages Plan purple, dashed and hidden', () => {
    expect(overlayLook('chinatown', 0)).toEqual({ color: '#c0392b', dashed: false, shown: true });
    expect(overlayLook('village-plan', 2)).toEqual({ color: '#7b3fa0', dashed: true, shown: false });
    expect(overlayPathOptions(overlayLook('village-plan', 2)).dashArray).toBe('6 4');
    expect(overlayPathOptions(overlayLook('deod', 1)).dashArray).toBeUndefined();
  });

  it('gives an area with no theme colour a fallback, shown', () => {
    const look = overlayLook('gastown', 3);
    expect(look.color).toMatch(/^#[0-9a-f]{6}$/);
    expect(look.shown).toBe(true);
  });
});

describe('overlay labels', () => {
  it('escapes the name inside the coloured label', () => {
    const html = overlayLabelHtml('Fraser St & <E 33rd> Ave', '#7b3fa0');
    expect(html).toContain('Fraser St &amp; &lt;E 33rd&gt; Ave');
    expect(html).toContain('color:#7b3fa0');
  });
});

describe('overlay toggles and legend rows', () => {
  it('renders one toggle per drawable area, ticked unless hidden by default', () => {
    const html = overlayTogglesHtml(AREAS, new Set(['chinatown', 'deod', 'village-plan']));
    expect(html).toContain('data-area="chinatown" checked> Chinatown');
    expect(html).toContain('data-area="deod" checked> DEOD');
    expect(html).toContain('data-area="village-plan"> Villages Plan');
    expect(html).not.toContain('gastown');
  });

  it('draws the legend swatch in the area\'s colour and dash', () => {
    const html = overlayLegendRowsHtml(AREAS, ALL);
    expect(html).toContain('border:2px solid #c0392b;"></span> Chinatown');
    expect(html).toContain('border:2px dashed #7b3fa0;"></span> Villages Plan');
  });

  it('renders nothing without areas', () => {
    expect(overlayTogglesHtml(undefined, ALL)).toBe('');
    expect(overlayLegendRowsHtml([], ALL)).toBe('');
  });
});
