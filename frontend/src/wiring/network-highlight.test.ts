// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { startHarness } from './test-harness';

afterEach(() => vi.unstubAllGlobals());

const popupButton = (network: string) => {
  const popup = document.createElement('div');
  popup.className = 'tc-popup';
  popup.innerHTML = `<button type="button" class="network-highlight" data-network="${network}" aria-pressed="false">Highlight on map</button>`;
  document.body.appendChild(popup);
  return popup.querySelector('button')!;
};
const rowBox = () => document.querySelector('#networks-table input.row-select[data-target="nw1"]') as HTMLInputElement;

describe('highlight a network from the popup', () => {
  it('selects the network, as its Networks-table checkbox does, and toggles back', () => {
    const h = startHarness();
    const btn = popupButton('nw1');
    h.click('.network-highlight');
    expect(rowBox().checked).toBe(true);
    expect([1, 2, 3, 4, 7, 9, 10].every((bid) => h.markerHighlighted(bid))).toBe(true);
    expect(h.markerHighlighted(5)).toBe(false);
    expect(btn.getAttribute('aria-pressed')).toBe('true');
    expect(btn.textContent).toBe('Stop highlighting');
    h.click('.network-highlight');
    expect(rowBox().checked).toBe(false);
    expect(h.markerHighlighted(1)).toBe(false);
    expect(btn.textContent).toBe('Highlight on map');
  });

  it('shows the current state when a popup opens', () => {
    const h = startHarness();
    h.setChecked('#networks-table input.row-select[data-target="nw1"]', true);
    const btn = popupButton('nw1');
    h.map.firePopupOpen(btn.closest('.tc-popup') as HTMLElement);
    expect(btn.getAttribute('aria-pressed')).toBe('true');
  });
});
