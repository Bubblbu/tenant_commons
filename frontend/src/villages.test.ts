import { describe, expect, it } from 'vitest';
import { villageLabelHtml } from './villages';

describe('village plan area labels', () => {
  it('escapes the name inside the purple label', () => {
    const html = villageLabelHtml('Fraser St & <E 33rd> Ave');
    expect(html).toContain('Fraser St &amp; &lt;E 33rd&gt; Ave');
    expect(html).toContain('color:#7b3fa0');
  });
});
