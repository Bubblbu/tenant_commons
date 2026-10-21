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

describe('renderSummary, key badges only', () => {
  const nm = { family_units: 12, seniors_units: 40, other_units: 0, operators: ['New Chelsea Society'], seniors: true };
  const badges = (html: string) =>
    [...new DOMParser().parseFromString(html, 'text/html').querySelectorAll('.popup-badge')].map((b) => b.textContent);
  const owner = { value: 'non_profit' as const, legal_forms: [], parts: [], reason: null, basis: ['registry' as const], inferred: false };

  it('shows program and owner type badges, and no classification or facts lines', () => {
    const b = { ...YORK, sro: null, housing: { licence_types: ['Apartment house' as const], purpose_built: true, zoning: 'RM-4', non_market: nm },
      classification: { owner, market: { value: 'non_market' as const, basis: ['non_market_list' as const], inferred: false }, operator: null, scale: 'small_portfolio' as const } };
    const html = renderSummary(b, CTX);
    expect(badges(html)).toEqual(['Non-market', 'Seniors', 'Non-profit']);
    const t = text(html);
    for (const gone of ['small portfolio', 'zoned RM-4', 'City licence', 'operated by', 'seniors units']) expect(t).not.toContain(gone);
  });

  it('marks an inferred owner type badge', () => {
    const b = { ...YORK, sro: null, classification: { owner: { ...owner, value: 'private' as const, basis: ['licence' as const], inferred: true },
      market: null, operator: null, scale: null } };
    const el = new DOMParser().parseFromString(renderSummary(b, CTX), 'text/html').querySelector('.popup-badge.owner')!;
    expect(el.textContent).toBe('Private');
    expect(el.classList.contains('inferred')).toBe(true);
  });

  it('a co-op on the non-market list shows Co-op, not Non-market', () => {
    const b = { ...YORK, sro: null, coop: { status: null, ownership_model: 'non_profit' as const, url: null },
      housing: { licence_types: [], purpose_built: false, zoning: null, non_market: { ...nm, seniors: false } } };
    expect(badges(renderSummary(b, CTX))).toEqual(['Co-op']);
  });
});
