// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest';
import { BIDWELL, CTX, OVERLAY, YORK } from './fixtures';
import { currentTab, initPopupTabs, renderPopup, resetTabMemory } from './index';

beforeEach(() => resetTabMemory());

const text = (html: string) => {
  const d = document.createElement('div');
  d.innerHTML = html;
  return d.textContent!.replace(/\s+/g, ' ');
};

function mount(html: string): HTMLElement {
  document.body.innerHTML = html;
  return document.body.firstElementChild as HTMLElement;
}

describe('renderPopup', () => {
  it('shares one header across tabs', () => {
    const html = renderPopup(YORK, CTX);
    expect(html).toContain('2145 York Ave');
    expect(html).toContain('Yorkshire Apartments · Kitsilano · 43 units · built 1979');
  });

  it('opens on Summary, with three tabs', () => {
    const el = mount(renderPopup(YORK, CTX));
    const tabs = [...el.querySelectorAll('[role="tab"]')].map((t) => t.textContent);
    expect(tabs).toEqual(['Summary', 'Ownership', 'Building']);
    expect(el.querySelector('[role="tab"][aria-selected="true"]')!.textContent).toBe('Summary');
    expect((el.querySelector('#tc-panel-ownership') as HTMLElement).hidden).toBe(true);
  });

  it('remembers the last tab across buildings, not across reloads', () => {
    initPopupTabs(document);
    let el = mount(renderPopup(YORK, CTX));
    (el.querySelector('[data-tab="ownership"]') as HTMLElement).click();
    expect(currentTab()).toBe('ownership');
    el = mount(renderPopup(BIDWELL, CTX));
    expect(el.querySelector('[aria-selected="true"]')!.getAttribute('data-tab')).toBe('ownership');
    resetTabMemory();
    el = mount(renderPopup(BIDWELL, CTX));
    expect(el.querySelector('[aria-selected="true"]')!.getAttribute('data-tab')).toBe('summary');
  });

  it('moves between tabs with the arrow keys', () => {
    initPopupTabs(document);
    const el = mount(renderPopup(YORK, CTX));
    const summary = el.querySelector('[data-tab="summary"]') as HTMLElement;
    summary.focus();
    summary.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    expect(currentTab()).toBe('ownership');
    expect(document.activeElement?.getAttribute('data-tab')).toBe('ownership');
  });

  it('renders an overlay record without owner data', () => {
    const html = renderPopup(OVERLAY, CTX);
    expect(html).toContain('Example Rooms');
    expect(html).toContain('Not on record');
    expect(html).not.toContain('(Unknown)');
    expect(html).not.toContain('undefined');
    expect(html).not.toContain('null');
  });

  it('escapes every name', () => {
    const evil = '<img src=x onerror=alert(1)>';
    const html = renderPopup({ ...YORK, name: evil, parties: YORK.parties.map((p) => ({ ...p, name: evil })) }, CTX);
    expect(html).not.toContain('<img');
  });
});

describe('renderPopup header, parcels', () => {
  it('shows the building\'s PID', () => {
    expect(text(renderPopup(YORK, CTX))).toContain('PID 007-273-924');
  });

  it('collapses a long PID list behind the first three', () => {
    const pids = ['001-000-001', '001-000-002', '001-000-003', '001-000-004', '001-000-005'];
    const html = renderPopup({ ...YORK, pids }, CTX);
    expect(text(html)).toContain('PIDs 001-000-001, 001-000-002, 001-000-003');
    const more = mount(html).querySelector<HTMLDetailsElement>('.popup-pids details')!;
    expect(more.querySelector('summary')!.textContent).toBe('+2 more');
    expect(more.open).toBe(false);
    expect(more.textContent).toContain('001-000-005');
  });

  it('sits in the header, under the building details and above the tabs', () => {
    const el = mount(renderPopup(YORK, CTX));
    const pids = el.querySelector('.popup-pids')!;
    expect(pids.previousElementSibling!.className).toBe('popup-sub');
    expect(pids.nextElementSibling!.className).toBe('tc-tabs');
  });

  it('says nothing about parcels when none is known', () => {
    expect(text(renderPopup(BIDWELL, CTX))).not.toContain('PID');
  });
});
