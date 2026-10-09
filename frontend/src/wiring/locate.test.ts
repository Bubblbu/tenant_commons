// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { startHarness } from './test-harness';

afterEach(() => vi.unstubAllGlobals());

describe('locate a building from the table', () => {
  it('puts a locate button in each building row\'s address cell', () => {
    startHarness();
    const btn = document.querySelector('#buildings-table tr[data-bid="1"] .locate-btn')!;
    expect(btn.tagName).toBe('BUTTON');
    expect(btn.getAttribute('aria-label')).toBe('Show 101 MAIN ST on the map');
  });

  it('centres the map on the building at street level and opens its popup', () => {
    const h = startHarness();
    h.click('#buildings-table tr[data-bid="1"] .locate-btn');
    const at = h.markers['1'].getLatLng()!;
    expect(h.map.view).toEqual({ lat: at.lat, lng: at.lng, zoom: 17 });
    expect(h.markers['1'].popupOpen).toBe(true);
    expect((document.querySelector('#buildings-table tr[data-bid="1"] .row-select') as HTMLInputElement).checked).toBe(false);
  });

  it('keeps a closer zoom', () => {
    const h = startHarness();
    h.map.zoom = 18;
    h.click('#buildings-table tr[data-bid="1"] .locate-btn');
    expect(h.map.view!.zoom).toBe(18);
  });

  it('closes the mobile drawer so the map shows', () => {
    const h = startHarness();
    document.getElementById('sidebar-container')!.classList.add('open');
    h.click('#buildings-table tr[data-bid="1"] .locate-btn');
    expect(document.getElementById('sidebar-container')!.classList.contains('open')).toBe(false);
  });

  it('turns the buildings layer back on first', () => {
    const h = startHarness();
    h.setChecked('#viz-show-buildings', false);
    h.click('#buildings-table tr[data-bid="1"] .locate-btn');
    expect((document.getElementById('viz-show-buildings') as HTMLInputElement).checked).toBe(true);
    expect(h.markers['1'].popupOpen).toBe(true);
  });
});
