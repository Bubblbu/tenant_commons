import { describe, expect, it } from 'vitest';
import { CHINATOWN_LABEL, chinatownLabelHtml } from './chinatown';

describe('chinatown boundary label', () => {
  it('renders the fixed label in the red style', () => {
    const html = chinatownLabelHtml(CHINATOWN_LABEL);
    expect(html).toContain('Chinatown');
    expect(html).toContain('color:#c0392b');
  });
});
