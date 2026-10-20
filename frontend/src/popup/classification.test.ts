// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import type { Building, Classification } from '../contract.gen';
import { classificationHeadline, kindChip } from './classification';
import { YORK } from './fixtures';

const withClass = (classification: Classification): Building => ({ ...YORK, classification });
// Without the provenance icons' "i".
const text = (html: string) => {
  const d = document.createElement('div');
  d.innerHTML = html;
  d.querySelectorAll('.prov').forEach((n) => n.remove());
  return d.textContent!;
};
const nothing: Classification = { owner: null, market: null, operator: null, scale: null };

describe('classificationHeadline', () => {
  it('headline is empty when nothing is known', () => {
    expect(classificationHeadline(withClass(nothing))).toBe('');
  });

  it('names type, legal form, scale and market, marking inferred parts', () => {
    const html = classificationHeadline(withClass({
      owner: { value: 'private', legal_forms: ['numbered_company'], parts: [], reason: null, basis: ['registry', 'name_rule'], inferred: false },
      market: { value: 'market', basis: ['registry'], inferred: true }, operator: null, scale: 'large_portfolio' }));
    expect(text(html)).toContain('Private · numbered company · large portfolio · market (inferred)');
    expect(html).toMatch(/class="popup-class inferred"[^>]*>market \(inferred\)/);
    expect(html).not.toMatch(/class="popup-class inferred"[^>]*>Private/);
  });

  it('says an owner from the licence holder is not confirmed on title', () => {
    const html = classificationHeadline(withClass({ ...nothing,
      owner: { value: 'private', legal_forms: ['company'], parts: [], reason: null, basis: ['licence', 'name_rule'], inferred: true } }));
    expect(html).toContain('not confirmed on title');
  });

  it('spells out a leasehold on City land, naming the leaseholder type', () => {
    const owner = (parts: ('government' | 'non_profit' | 'private')[]) => classificationHeadline(withClass({ ...nothing,
      owner: { value: 'mixed', legal_forms: [], parts, reason: 'public_land_leasehold', basis: ['registry', 'city_owned'], inferred: false } }));
    expect(text(owner(['government', 'non_profit']))).toContain('City land, non-profit leasehold');
    expect(text(owner(['government', 'private']))).toContain('City land, private leasehold');
  });

  it('names the parts of mixed ownership', () => {
    const html = classificationHeadline(withClass({ ...nothing,
      owner: { value: 'mixed', legal_forms: ['numbered_company'], parts: ['non_profit', 'private'], reason: 'owners_differ', basis: ['registry'], inferred: false } }));
    expect(text(html)).toContain('Mixed: Non-profit and Private');
  });
});

describe('kindChip', () => {
  it('shows kind and institutional flag, nothing when unknown', () => {
    const p = YORK.parties[0];
    expect(text(kindChip({ ...p, kind: 'numbered_company', institutional: 'reit' }))).toContain('numbered company · REIT');
    expect(kindChip({ ...p, kind: null, institutional: null })).toBe('');
  });
});
