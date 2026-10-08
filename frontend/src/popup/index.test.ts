// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest';
import { BIDWELL, CTX, OVERLAY, YORK } from './fixtures';
import { currentTab, initPopupTabs, renderPopup, resetTabMemory } from './index';

beforeEach(() => resetTabMemory());

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
