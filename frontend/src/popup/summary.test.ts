// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { BIDWELL, CTX, E2ND, MARBLE_ARCH, YORK } from './fixtures';
import { renderSummary } from './summary';

const text = (html: string) => {
  const d = document.createElement('div');
  d.innerHTML = html;
  return d.textContent!.replace(/\s+/g, ' ');
};

describe('renderSummary', () => {
  it('names a confirmed network as the owner, then the manager and portfolio', () => {
    const t = text(renderSummary(YORK, CTX));
    expect(t).toContain('Owned by Cressey Development Group');
    expect(t).toContain('confirmed');
    expect(t).toContain('Managed by Cascadia Apartment Rentals');
    expect(t).toContain('Cressey Development Group holds 10 buildings · 609 units on the map');
    expect(t).toContain('1 outstanding City issue');
    expect(t).not.toContain('Licensed to');
  });

  it('shows an SRO: badges, owner, manager and the unmatched licensee', () => {
    const t = text(renderSummary(MARBLE_ARCH, CTX));
    expect(t).toContain('SRO');
    expect(t).toContain('Open');
    expect(t).toContain('Owned by BC Housing');
    expect(t).toContain('Managed by Atira Property Management');
    expect(t).toContain('Licensed to PHS Community Services Society');
    expect(t).toContain('27 outstanding City issues');
  });

  it('leads with an approved rezoning', () => {
    const html = renderSummary(E2ND, CTX);
    expect(text(html)).toContain('Rezoning approved');
    expect(html).toContain('href="https://www.shapeyourcity.ca/396-e-2-ave"');
    expect(text(html)).toContain('Managed by Not on record');
  });

  it('labels licence-only ownership and a single-building owner', () => {
    const t = text(renderSummary(BIDWELL, CTX));
    expect(t).toContain('Owned by Feliz Enterprises Ltd');
    expect(t).toContain('licence only');
    expect(t).toContain('Only building we know of for this owner');
  });
});
