// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { startHarness } from './test-harness';

afterEach(() => vi.unstubAllGlobals());

const popupButton = (network: string) => {
  const popup = document.createElement('div');
  popup.className = 'tc-popup';
  popup.innerHTML = `<button type="button" class="network-table" data-network="${network}">View in table</button>`;
  document.body.appendChild(popup);
};

describe('view a network in the table from the popup', () => {
  it('filters to the network as a Group tile and shows the Buildings table', () => {
    const h = startHarness();
    document.getElementById('tab-landlords')!.click();
    popupButton('nw1');
    h.click('.network-table');
    expect(h.landlords.picked().map((p) => [p.kind, p.key])).toEqual([['network', 'nw1']]);
    expect(h.visible()).toEqual(['1', '2', '3', '4', '7', '9', '10']);
    expect(document.getElementById('pane-buildings')!.classList.contains('active')).toBe(true);
    expect(document.getElementById('sidebar-container')!.classList.contains('open')).toBe(true);
  });

  it('replaces other landlord tiles rather than adding to them', () => {
    const h = startHarness();
    h.pickLandlord('Birch');
    expect(h.landlords.picked().map((p) => p.kind)).not.toEqual(['network']);
    popupButton('nw1');
    h.click('.network-table');
    expect(h.landlords.picked().map((p) => p.key)).toEqual(['nw1']);
  });

  it('does nothing for a network with no buildings in the table', () => {
    const h = startHarness();
    popupButton('nope');
    h.click('.network-table');
    expect(h.landlords.picked()).toEqual([]);
  });
});
