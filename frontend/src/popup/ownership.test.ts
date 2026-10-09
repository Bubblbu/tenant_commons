// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import type { Building } from '../contract.gen';
import { BIDWELL, CTX, MARBLE_ARCH, NETWORKS, OVERLAY, YORK } from './fixtures';
import { renderOwnership } from './ownership';

const dom = (html: string) => { const d = document.createElement('div'); d.innerHTML = html; return d; };
const text = (html: string) => dom(html).textContent!.replace(/\s+/g, ' ');

describe('renderOwnership', () => {
  it('draws network → on title → this building, manager outside the chain', () => {
    const d = dom(renderOwnership(YORK, CTX));
    const roles = [...d.querySelectorAll('.chain .node .role')].map((n) => n.textContent);
    expect(roles).toEqual(['Network', 'On title', 'This building']);
    expect(d.querySelector('.chain')!.textContent).not.toContain('Cascadia');
    expect(d.querySelector('.popup-aside')!.textContent).toContain('Cascadia Apartment Rentals');
  });

  it('shows network evidence and the portfolio card', () => {
    const t = text(renderOwnership(YORK, CTX));
    expect(t).toContain('7 registry filings + 9 VTU research claims');
    expect(t).toMatch(/10\s*buildings/);
    expect(t).toMatch(/609\s*units/);
    expect(t).toMatch(/2\s*open issues/);
  });

  it('collapses linked entities and interest holders, with interest types', () => {
    const d = dom(renderOwnership(YORK, CTX));
    const details = [...d.querySelectorAll('details')];
    expect(details.map((x) => x.querySelector('summary')!.textContent)).toEqual(['18 linked entities', '2 interest holders']);
    expect(details.every((x) => !x.open)).toBe(true);
    expect(details[1].textContent).toContain('ROE, RICHARD (trustee)');
  });

  it('shows the owner with PID, registry date and "Licensed as" for a differently spelled licence', () => {
    const t = text(renderOwnership(YORK, CTX));
    expect(t).toContain('Yorkshire Place Apts. Ltd.');
    expect(t).toContain('PID 007-273-924 · registry, May 2024');
    expect(t).toContain('Licensed as Yorkshire Place Apt Ltd');
  });

  it('omits "Licensed as" when the licence is spelled the same', () => {
    expect(text(renderOwnership(BIDWELL, CTX))).not.toContain('Licensed as');
  });

  it('distinguishes joint owners of one parcel from owners of separate parcels', () => {
    const owner = (name: string, pids: string[]) => ({ role: 'owner' as const, name, entity_key: name, kind: null,
      interest: null, pids, same_as: null, sources: [{ type: 'registry' as const, as_of: '2026-01-01', url: null }] });
    const joint: Building = { ...BIDWELL, network_id: null, parties: [owner('RENER, ALENKA', ['1']), owner('RENER, GEORGE', ['1'])] };
    const split: Building = { ...BIDWELL, network_id: null, parties: [owner('A LTD.', ['1']), owner('B LTD.', ['2'])] };
    expect(text(renderOwnership(joint, CTX))).toContain('Jointly owned by RENER, ALENKA and RENER, GEORGE');
    expect(text(renderOwnership(split, CTX))).toContain('A LTD. (PID 1)');
    expect(text(renderOwnership(split, CTX))).toContain('B LTD. (PID 2)');
  });

  it('shows the unmatched licensee and SRO-sourced parties', () => {
    const t = text(renderOwnership(MARBLE_ARCH, CTX));
    expect(t).toContain('BC Housing');
    expect(t).toContain('Licensed to PHS Community Services Society');
  });

  it('says when the registry was searched without a filing, and handles no owner', () => {
    const t = text(renderOwnership({ ...OVERLAY, registry_search: { status: 'no_filing', date: '2026-10-06' } }, CTX));
    expect(t).toContain('Not on record');
    expect(t).toContain('No filing in the land title registry (searched 2026-10-06)');
  });
});

describe('renderOwnership, chain terminus', () => {
  it('formats the building address like the header', () => {
    const d = dom(renderOwnership(YORK, CTX));
    expect(d.querySelector('.node.bldg')!.textContent).toContain('2145 York Ave');
  });
});

describe('renderOwnership, City records', () => {
  it('counts City records as their own evidence, leaving out empty kinds', () => {
    const net = { ...NETWORKS['net:cressey'], evidence: { registry: 0, city_records: 4, vtu_research: 1 } };
    const t = text(renderOwnership(YORK, { ...CTX, networks: { ...NETWORKS, 'net:cressey': net } }));
    expect(t).toContain('4 City records + 1 VTU research claim');
    expect(t).not.toContain('0 registry');
  });
});
