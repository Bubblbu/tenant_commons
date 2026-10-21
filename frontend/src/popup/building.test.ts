// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { CTX, E2ND, MARBLE_ARCH, OVERLAY, YORK } from './fixtures';
import { renderBuilding } from './building';

const dom = (html: string) => { const d = document.createElement('div'); d.innerHTML = html; return d; };
const text = (html: string) => dom(html).textContent!.replace(/\s+/g, ' ');

describe('renderBuilding', () => {
  it('fills the value bar with the land share and marks the city median', () => {
    const d = dom(renderBuilding(E2ND, CTX));
    expect((d.querySelector('.value-bar .fill') as HTMLElement).style.width).toBe('97.3%');
    expect((d.querySelector('.value-bar .median') as HTMLElement).style.left).toBe('79%');
    expect(d.querySelector('.median-label')!.textContent).toBe('city median');
    const t = text(d.innerHTML);
    expect(t).toContain('Land $18.9M (97%) · Building $534K');
    expect(t).toContain('Land share higher than 89% of rental buildings on the map');
  });

  it('has no bar without assessed values or a median', () => {
    expect(dom(renderBuilding(OVERLAY, CTX)).querySelector('.value-bar')).toBeNull();
    expect(dom(renderBuilding(E2ND, { ...CTX, landShareMedian: null })).querySelector('.value-bar .median')).toBeNull();
  });

  it('shows rezoning details', () => {
    const t = text(renderBuilding(E2ND, CTX));
    expect(t).toContain('Approved · Mar 13, 2025');
    expect(t).toContain('Market');
    expect(t).toContain('Shape Your City');
  });

  it('shows the SRO section with sectors, issues and aliases', () => {
    const t = text(renderBuilding(MARBLE_ARCH, CTX));
    expect(t).toContain('150 registered');
    expect(t).toContain('Government owner · non-profit operator');
    expect(t).toContain('27 outstanding');
    expect(t).toContain('Also known as Hotel Canada (Formerly Marble Arch)');
  });

  it('shows a co-op with readable labels', () => {
    const coop = { ...YORK, coop: { status: 'closed' as const, ownership_model: 'non_profit' as const, url: 'https://www.chf.bc.ca/x' } };
    const t = text(renderBuilding(coop, CTX));
    expect(t).toContain('Non-profit (non-equity)');
    expect(t).toContain('Waitlist closed');
  });

  it('lists the records the building appears in', () => {
    expect(text(renderBuilding(MARBLE_ARCH, CTX))).toContain(
      'Listed in City of Vancouver non-market housing list · City of Vancouver SRO inventory');
  });

  it('renders an overlay record', () => {
    const t = text(renderBuilding(OVERLAY, CTX));
    expect(t).toContain('City of Vancouver SRO inventory');
    expect(t).not.toContain('null');
  });
});

describe('renderBuilding, co-op without status', () => {
  it('omits rows the co-op list does not give', () => {
    const coop = { ...YORK, coop: { status: null, ownership_model: null, url: null } };
    const t = text(renderBuilding(coop, CTX));
    expect(t).toContain('Co-op');
    expect(t).not.toContain('Waitlist');
    expect(t).not.toContain('Model');
  });
});

describe('renderBuilding, housing facts', () => {
  const t = (html: string) => { const d = document.createElement('div'); d.innerHTML = html; return d.textContent!.replace(/\s+/g, ' '); };
  const nm = { family_units: 12, seniors_units: 40, other_units: 0, operators: ['New Chelsea Society'], seniors: true };

  it('lists the City facts without repeating the header\'s year and units', () => {
    const html = renderBuilding({ ...YORK, housing: { licence_types: ['Apartment house'], purpose_built: true, zoning: 'RM-4', non_market: null } }, CTX);
    expect(t(html)).toContain("Apartment house (2024 City licence) · on the City's purpose-built rental list · zoned RM-4");
    expect(t(html)).not.toContain('built 1979');
  });

  it('gives non-market operator and units, and only the unit mix for a co-op', () => {
    expect(t(renderBuilding({ ...YORK, housing: { licence_types: [], purpose_built: false, zoning: null, non_market: nm } }, CTX)))
      .toContain('Non-market housing operated by New Chelsea Society · 40 seniors units · 12 family-size units (2+ bedrooms)');
    const coop = t(renderBuilding({ ...YORK, coop: { status: null, ownership_model: 'non_profit', url: null },
      housing: { licence_types: [], purpose_built: false, zoning: null, non_market: nm } }, CTX));
    expect(coop).toContain('40 seniors units');
    expect(coop).not.toContain('operated by');
  });
});
