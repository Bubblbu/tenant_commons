import { describe, expect, it } from 'vitest';
import { labelPosition, neighbourhoodLabelHtml } from './neighbourhoods';

describe('neighbourhood labels', () => {
  it('escapes the name inside the orange label', () => {
    const html = neighbourhoodLabelHtml('Grandview & <Woodland>');
    expect(html).toContain('Grandview &amp; &lt;Woodland&gt;');
    expect(html).toContain('color:#ff8c00');
  });
  it("uses the City's geo_point_2d, falling back to the given point", () => {
    expect(labelPosition({ geo_point_2d: { lat: 49.2, lon: -123.1 } }, [0, 0])).toEqual([49.2, -123.1]);
    expect(labelPosition({ name: 'X' }, [49.3, -123.2])).toEqual([49.3, -123.2]);
  });
});
