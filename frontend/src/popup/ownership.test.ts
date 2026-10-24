// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import type { Building } from '../contract.gen';
import { BIDWELL, CTX, MARBLE_ARCH, NETWORKS, OVERLAY, YORK } from './fixtures';
import { renderOwnership } from './ownership';

const dom = (html: string) => { const d = document.createElement('div'); d.innerHTML = html; return d; };
const text = (html: string) => dom(html).textContent!.replace(/\s+/g, ' ');

describe('renderOwnership', () => {
  it('draws network → this building, with who holds title and who manages it inside the building', () => {
    const d = dom(renderOwnership(YORK, CTX));
    const nodes = [...d.querySelectorAll('.chain > .node > .role')].map((n) => n.textContent);
    expect(nodes).toEqual(['Network', 'This building · 2145 York Ave']);
    const rows = [...d.querySelectorAll('.node.bldg .popup-k')].map((k) => k.textContent);
    expect(rows).toEqual(['On title', 'Managed by']);
    expect(d.querySelector('.node.net')!.textContent).not.toContain('Cascadia');
    expect(d.querySelector('.node.bldg')!.textContent).toContain('Cascadia Apartment Rentals');
    expect(d.querySelector('.popup-aside')).toBeNull();
  });

  it('shows the building alone, outside a chain, when there is no network', () => {
    const d = dom(renderOwnership(BIDWELL, CTX));
    expect(d.querySelector('.chain')).toBeNull();
    expect(d.querySelector('.node.bldg')).not.toBeNull();
    expect(text(d.innerHTML)).toContain('Managed by Not on record');
  });

  it('adds a Licensed to row only for a licensee that is neither owner nor manager', () => {
    const rows = (b: typeof YORK) => [...dom(renderOwnership(b, CTX)).querySelectorAll('.node.bldg .popup-k')].map((k) => k.textContent);
    expect(rows(MARBLE_ARCH)).toEqual(['On title', 'Managed by', 'Licensed to']);
    expect(rows(YORK)).not.toContain('Licensed to');
  });

  it('shows network evidence and the portfolio card', () => {
    const t = text(renderOwnership(YORK, CTX));
    expect(t).toContain('One landlord: its companies and people are linked by 7 registry filings and 9 VTU research claims.');
    expect(t).toMatch(/10\s*buildings/);
    expect(t).toMatch(/609\s*units/);
    expect(t).toMatch(/2\s*open issues/);
  });

  it('collapses the network people, its companies and the interest holders, with interest types', () => {
    const d = dom(renderOwnership(YORK, CTX));
    const details = [...d.querySelectorAll('details')];
    expect(details.map((x) => x.querySelector('summary')!.textContent)).toEqual(
      ['2 people', '16 companies', '2 interest holders']);
    expect(details.every((x) => !x.open)).toBe(true);
    expect(details[2].textContent).toContain('ROE, RICHARD (trustee)');
  });

  it('introduces the people and companies as the entities the network links', () => {
    const d = dom(renderOwnership(YORK, CTX));
    const intro = d.querySelector('.net-entities-intro')!;
    expect(intro.textContent).toMatch(/linked/i);
    expect(intro.nextElementSibling!.tagName).toBe('DETAILS');
  });

  it('lists companies by the buildings they own on the map, others last', () => {
    const items = [...dom(renderOwnership(YORK, CTX)).querySelectorAll('details')[1].querySelectorAll('li')]
      .map((li) => li.textContent!.replace(/\s+/g, ' ').replace(/i$/, '').trim());
    expect(items[0]).toBe('Victoria Place Apts. Ltd. 2 buildings');
    expect(items[1]).toBe('Yorkshire Place Apts. Ltd. 1 building');
    expect(items[2]).toBe('Cressey Holding 0 Ltd not on the map');
  });

  it('gives other spellings of an entity on hover', () => {
    const d = dom(renderOwnership(YORK, CTX));
    const people = d.querySelectorAll('details')[0];
    expect(people.textContent).toContain('Cressey, Norman Edward');
    expect(people.querySelector('.prov')!.getAttribute('data-tip')).toBe('Also named: Norman Cressey');
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
    const owner = (name: string, pids: string[]) => ({ role: 'owner' as const, name, entity_key: name, kind: null, institutional: null,
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

describe('renderOwnership, City records', () => {
  it('counts City records as their own evidence, leaving out empty kinds', () => {
    const net = { ...NETWORKS['net:cressey'], evidence: { registry: 0, city_records: 4, vtu_research: 1 } };
    const t = text(renderOwnership(YORK, { ...CTX, networks: { ...NETWORKS, 'net:cressey': net } }));
    expect(t).toContain('linked by 4 City records and 1 VTU research claim.');
    expect(t).not.toContain('0 registry');
  });

  it('explains only the sources it counts, on hover', () => {
    const net = { ...NETWORKS['net:cressey'], evidence: { registry: 0, city_records: 4, vtu_research: 1 } };
    const d = dom(renderOwnership(YORK, { ...CTX, networks: { ...NETWORKS, 'net:cressey': net } }));
    const tip = d.querySelector('.node.net > .popup-muted .prov')!.getAttribute('data-tip')!;
    expect(tip).toContain("City record: the City's SRO inventory");
    expect(tip).toContain('VTU research:');
    expect(tip).not.toContain('Registry filing');
  });

  it('says a name-matched network is not confirmed', () => {
    const net = { ...NETWORKS['net:cressey'], tier: 'name_match' as const };
    const t = text(renderOwnership(YORK, { ...CTX, networks: { ...NETWORKS, 'net:cressey': net } }));
    expect(t).toContain('Buildings owned under the same name. Nothing yet confirms they are one landlord.');
  });
});

describe('renderOwnership, highlight the network', () => {
  it('offers a toggle on the network node, keyed by the network', () => {
    const btn = dom(renderOwnership(YORK, CTX)).querySelector('.network-highlight')!;
    expect(btn.tagName).toBe('BUTTON');
    expect(btn.getAttribute('data-network')).toBe('net:cressey');
    expect(btn.getAttribute('aria-pressed')).toBe('false');
    expect(btn.textContent).toBe('Highlight on map');
  });

  it('sits in the network card, under its totals', () => {
    const card = dom(renderOwnership(YORK, CTX)).querySelector('.node.net .net-card')!;
    expect(card.querySelector('.popup-stats')!.nextElementSibling!.className).toBe('net-actions');
    expect(card.querySelectorAll('.net-actions button')).toHaveLength(2);
  });

  it('offers "View in table" beside it, keyed by the network', () => {
    const btn = dom(renderOwnership(YORK, CTX)).querySelector('.net-actions .network-table')!;
    expect(btn.getAttribute('data-network')).toBe('net:cressey');
    expect(btn.textContent).toBe('View in table');
  });

  it('has no toggle without a network node', () => {
    expect(dom(renderOwnership(BIDWELL, CTX)).querySelector('.network-highlight')).toBeNull();
  });
});

describe('network members by kind', () => {
  it('groups network members by kind', () => {
    const net = { ...NETWORKS['net:cressey'], entities: [
      { name: 'Kim, Phil', also_named: [], kind: 'individual' as const, buildings: 0 },
      { name: '0733603 BC Ltd', also_named: [], kind: 'numbered_company' as const, buildings: 3 },
      { name: '0733604 BC Ltd', also_named: [], kind: 'numbered_company' as const, buildings: 1 },
      { name: 'Kim Holdings Ltd', also_named: [], kind: 'company' as const, buildings: 2 },
      { name: 'Who Knows', also_named: [], kind: null, buildings: 1 },
    ] };
    const t = text(renderOwnership(YORK, { ...CTX, networks: { ...NETWORKS, 'net:cressey': net } }));
    expect(t).toContain('1 person');
    expect(t).toContain('2 numbered companies');
    expect(t).toContain('1 company');
    expect(t).toContain('1 other');
  });

  it('puts a kind chip after the owner on title', () => {
    const york = { ...YORK, parties: YORK.parties.map((p) => (p.role === 'owner' ? { ...p, kind: 'company' as const } : p)) };
    expect(dom(renderOwnership(york, CTX)).querySelector('.node.bldg .popup-kind')!.textContent).toBe('company');
  });
});

describe('renderOwnership, classification', () => {
  it('opens with the classification line', () => {
    const b = { ...YORK, classification: { owner: { value: 'private' as const, legal_forms: ['numbered_company' as const], parts: [], reason: null,
      basis: ['registry' as const], inferred: false }, market: null, operator: null, scale: 'large_portfolio' as const } };
    const d = dom(renderOwnership(b, CTX));
    d.querySelectorAll('.prov').forEach((n) => n.remove());  // provenance icons' "i"
    const t = d.textContent!.replace(/\s+/g, ' ');
    expect(t.indexOf('Private · numbered company · large portfolio')).toBeGreaterThanOrEqual(0);
    expect(t.indexOf('Private')).toBeLessThan(t.indexOf('Network'));
  });
});
