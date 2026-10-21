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

describe('renderSummary, housing facts', () => {
  const withHousing = (housing: typeof YORK.housing) => ({ ...YORK, sro: null, housing });

  it('lists the plain facts with their sources', () => {
    const t = text(renderSummary(withHousing({ licence_types: ['Apartment house'], purpose_built: true, zoning: 'RM-4', non_market: null }), CTX));
    expect(t).toContain('Apartment house (2024 City licence) · on the City\'s purpose-built rental list · zoned RM-4 · built 1979 · 43 units');
  });

  it('flags non-market and seniors housing, with operator and units by clientele', () => {
    const html = renderSummary(withHousing({ licence_types: [], purpose_built: false, zoning: null,
      non_market: { family_units: 12, seniors_units: 40, other_units: 0, operators: ['New Chelsea Society'], seniors: true } }), CTX);
    const badges = [...new DOMParser().parseFromString(html, 'text/html').querySelectorAll('.popup-badge')].map((b) => b.textContent);
    expect(badges).toEqual(['Non-market', 'Seniors']);
    expect(text(html)).toContain('Non-market housing operated by New Chelsea Society · 40 seniors units · 12 family-size units (2+ bedrooms)');
  });

  it('says nothing extra when no facts are known', () => {
    const t = text(renderSummary(withHousing({ licence_types: [], purpose_built: false, zoning: null, non_market: null }), CTX));
    expect(t).not.toContain('City licence');
    expect(t).not.toContain('Non-market');
  });
});

describe('renderSummary, co-ops on the non-market list', () => {
  const coop = { status: null, ownership_model: 'non_profit' as const, url: null };
  const nm = (seniors: boolean) => ({ family_units: 23, seniors_units: seniors ? 58 : 0, other_units: 0,
    operators: ['North Arm Housing Co-op'], seniors });
  const badges = (html: string) =>
    [...new DOMParser().parseFromString(html, 'text/html').querySelectorAll('.popup-badge')].map((b) => b.textContent);

  it('shows Co-op, not Non-market, and only the unit mix', () => {
    const html = renderSummary({ ...YORK, sro: null, coop, housing: { licence_types: [], purpose_built: false, zoning: null, non_market: nm(false) } }, CTX);
    expect(badges(html)).toEqual(['Co-op']);
    expect(text(html)).toContain('23 family-size units (2+ bedrooms)');
    expect(text(html)).not.toContain('operated by');
  });

  it('still flags a seniors co-op', () => {
    const html = renderSummary({ ...YORK, sro: null, coop, housing: { licence_types: [], purpose_built: false, zoning: null, non_market: nm(true) } }, CTX);
    expect(badges(html)).toEqual(['Co-op', 'Seniors']);
  });
});
