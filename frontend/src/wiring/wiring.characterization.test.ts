// @vitest-environment jsdom
/**
 * Pins what wiring does, seen from the page: rows, markers, blocks, counts.
 * Written against wiring.js before the refactor; must keep passing unchanged
 * (only the harness's import changes, in Task 8).
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ALL_BIDS } from './fixture';
import { flushFrames, startHarness } from './test-harness';

afterEach(() => vi.unstubAllGlobals());

const text = (id: string) => document.getElementById(id)?.textContent;

describe('starting up', () => {
  it('shows every building, hides only the empty block, and fills the status counts', () => {
    const h = startHarness();
    expect(h.visible()).toEqual(ALL_BIDS);
    expect(h.markerHidden(1)).toBe(false);
    expect(h.blockHidden(101)).toBe(false);
    expect(h.blockHidden(401)).toBe(true);
    expect(text('status-total-buildings')).toBe('10');
    expect(text('status-total-units')).toBe('296');
    expect(text('status-view-buildings')).toBe('10');
    expect(text('status-view-units')).toBe('296');
  });
});

const hood = (value: string) => `.filter-neighbourhood-option[value="${value}"]`;
const chip = (value: string) => `.housing-chip[data-housing="${value}"]`;
const bRow = (bid: number) => `#buildings-table tr[data-bid="${bid}"]`;
const ownerKeys = () => Array.from(document.querySelectorAll('#owners-table tbody tr')).map((r) => r.getAttribute('data-owner'));

describe('Filter by > Area', () => {
  it('hides rows and markers outside the ticked area', () => {
    const h = startHarness();
    h.setChecked(hood('west end'), true);
    expect(h.visible()).toEqual(['1', '2', '3']);
    expect(h.rowHidden(bRow(4))).toBe(true);
    expect(h.rowHidden(bRow(1))).toBe(false);
    expect(h.markerHidden(4)).toBe(true);
    expect(h.markerHidden(1)).toBe(false);
  });

  it('matches Chinatown by its flag, alongside ordinary areas', () => {
    const h = startHarness();
    h.setChecked(hood('chinatown'), true);
    expect(h.visible()).toEqual(['5']); // a Downtown building flagged in_chinatown
    h.setChecked(hood('strathcona'), true);
    expect(h.visible()).toEqual(['5', '7', '8', '9']);
  });
});

describe('Filter by > Ownership', () => {
  it('filters by an owner, a network, or a manager tile', () => {
    const h = startHarness();
    h.pickLandlord('acme');
    expect(h.visible()).toEqual(['1', '2', '7', '10']);
    h.landlords.clear();
    flushFrames();
    h.pickLandlord('cedar'); // network nw1 = acme + birch
    expect(h.visible()).toEqual(['1', '2', '3', '4', '7', '9', '10']);
    h.landlords.clear();
    flushFrames();
    h.pickLandlord('tribe'); // manager of building 5, which has no landlord on record
    expect(h.visible()).toEqual(['5']);
  });

  it('keeps only buildings with a landlord on record', () => {
    const h = startHarness();
    h.setChecked('#filter-only-owned', true);
    expect(h.visible()).toEqual(['1', '2', '3', '4', '7', '9', '10']);
  });
});

describe('Filter by > Building', () => {
  it('keeps buildings with open issues, or with a unit count', () => {
    const h = startHarness();
    h.setChecked('#filter-only-issues', true);
    expect(h.visible()).toEqual(['2', '5', '7']);
    h.setChecked('#filter-only-issues', false);
    h.setChecked('#filter-only-units', true);
    expect(h.visible()).toEqual(ALL_BIDS.filter((b) => b !== '6'));
  });

  it('filters by housing chips, matching either type of a two-type building', () => {
    const h = startHarness();
    h.click(chip('sro'));
    expect(h.visible()).toEqual(['2', '4']);
    h.click(chip('co-op'));
    expect(h.visible()).toEqual(['2', '4', '6']);
    h.click(chip('sro'));
    expect(h.visible()).toEqual(['4', '6']);
  });

  it('hides buildings below a slider minimum but keeps buildings with no value', () => {
    const h = startHarness();
    h.setSlider(0, 'min', 20);
    // units >= 20: 1 (40), 4 (120), 5 (30), 9 (60); 6 has no unit count and passes.
    expect(h.visible()).toEqual(['1', '4', '5', '6', '9']);
  });

  it('counts each histogram without its own slider', () => {
    const h = startHarness();
    h.setSlider(0, 'min', 20);
    // Units ignores its own slider: [4,40) 12,8,30,6,16,4 · [40,80) 40,60 · [80,120] 120
    expect(h.barCounts(0)).toEqual([6, 2, 1]);
    // Year counts only buildings passing the Units slider: 1930,1912 · 1965 · 2005,2015
    expect(h.barCounts(1)).toEqual([2, 1, 2]);
  });
});

describe('sidebar tables', () => {
  it('hides landlord and area rows with nothing visible, and recounts a tab when it opens', () => {
    const h = startHarness();
    h.setChecked(hood('west end'), true);
    const acmeBldgs = () => document.querySelector('#owners-table tr[data-owner="acme"]')?.children[2].textContent;
    expect(h.rowHidden('#owners-table tr[data-owner="acme"]')).toBe(false);
    expect(h.rowHidden('#owners-table tr[data-owner="unknown"]')).toBe(true);
    expect(h.rowHidden('#neighbourhoods-table tr[data-area="Downtown"]')).toBe(true);
    expect(acmeBldgs()).toBe('4'); // Landlords tab not open: still the build-time count
    h.click('#tab-landlords');
    expect(acmeBldgs()).toBe('2'); // buildings 1 and 2
  });

  it('sorts on a header click, keeping "Not on record" last both ways', () => {
    const h = startHarness();
    const bldgs = '#owners-table thead th:nth-child(3)';
    h.click(bldgs);
    expect(ownerKeys()).toEqual(['birch', 'acme', 'unknown']);
    h.click(bldgs);
    expect(ownerKeys()).toEqual(['acme', 'birch', 'unknown']);
  });

  it('does not sort when a header explainer icon is clicked', () => {
    const h = startHarness();
    const before = ownerKeys();
    h.click('#owners-table thead th:nth-child(2) .prov');
    expect(ownerKeys()).toEqual(before);
    expect(document.querySelector('#owners-table thead th:nth-child(2)')?.hasAttribute('data-sort-dir')).toBe(false);
  });

  it('totals only rows that are neither filtered nor hidden by table search', () => {
    const h = startHarness();
    h.setChecked(hood('west end'), true); // 1, 2, 3
    document.querySelector(bRow(1))?.classList.add('search-hidden');
    document.dispatchEvent(new Event('tablesearch'));
    expect(text('summary-buildings-units')).toBe('20'); // 12 + 8
    expect(text('summary-buildings-rows')).toBe('2 rows');
  });
});

describe('selection and hover', () => {
  it("highlights an owner's buildings and drops the selection when they are all filtered away", () => {
    const h = startHarness();
    const acme = '#owners-table input.row-select[data-target="acme"]';
    h.setChecked(acme, true);
    expect([1, 2, 7, 10].map((b) => h.markerHighlighted(b))).toEqual([true, true, true, true]);
    expect(h.markerHighlighted(3)).toBe(false);
    h.click(chip('co-op')); // leaves 4 and 6: no acme building
    expect(document.querySelector<HTMLInputElement>(acme)?.checked).toBe(false);
    h.click(chip('co-op'));
    expect(h.markerHighlighted(1)).toBe(false);
  });

  it("highlights a network's buildings", () => {
    const h = startHarness();
    h.setChecked('#networks-table input.row-select[data-target="nw1"]', true);
    expect([1, 2, 3, 4, 7, 9, 10].map((b) => h.markerHighlighted(b))).toEqual(Array(7).fill(true));
    expect(h.markerHighlighted(5)).toBe(false);
  });

  it('highlights on row hover, paints it on top, and leaves a selection alone', () => {
    const h = startHarness();
    h.hover(bRow(4), true);
    expect(h.markerHighlighted(4)).toBe(true);
    expect(h.paint.at(-1)).toBe(h.markers['4']);
    h.hover(bRow(4), false);
    expect(h.markerHighlighted(4)).toBe(false);
    h.setChecked(`${bRow(4)} input.row-select`, true);
    h.hover(bRow(4), true);
    h.hover(bRow(4), false);
    expect(h.markerHighlighted(4)).toBe(true);
  });
});

describe('Clear and Reset', () => {
  it('clears one section, and Reset clears everything', () => {
    const h = startHarness();
    h.setChecked(hood('downtown'), true);
    h.click(chip('sro'));
    expect(h.visible()).toEqual(['4']);
    expect(text('filter-count-area')).toBe('1');
    expect(text('filter-count-building')).toBe('1');
    h.click('#filter-clear-area');
    expect(h.visible()).toEqual(['2', '4']);
    expect(document.getElementById('filter-count-area')?.hidden).toBe(true);
    h.setSlider(0, 'min', 20);
    expect(h.visible()).toEqual(['4']);
    h.pickLandlord('acme');
    expect(h.visible()).toEqual([]);
    h.click('#filter-reset');
    expect(h.visible()).toEqual(ALL_BIDS);
    expect(document.querySelector(chip('sro'))?.getAttribute('aria-pressed')).toBe('false');
    expect(document.getElementById('filter-count-building')?.hidden).toBe(true);
    expect(document.getElementById('filter-count-ownership')?.hidden).toBe(true);
    expect(h.landlords.isActive()).toBe(false);
  });
});

describe('blocks', () => {
  it('shows empty blocks only on request, and matches a block by its own area', () => {
    const h = startHarness();
    h.setChecked('#viz-show-empty-blocks', true);
    expect(h.blockHidden(401)).toBe(false);
    h.setChecked('#viz-show-empty-blocks', false);
    expect(h.blockHidden(401)).toBe(true);
    h.setChecked(hood('downtown'), true);
    expect(h.visible()).toEqual(['4', '5', '6', '10']);
    expect(h.blockHidden(201)).toBe(false);
    expect(h.blockHidden(301)).toBe(true); // holds Downtown building 10, but is a Strathcona block
    expect(h.rowHidden('#blocks-table tr[data-block="301"]')).toBe(true);
  });
});

describe('CSV export', () => {
  it('exports the visible buildings with the dataset columns', () => {
    const h = startHarness();
    h.setChecked(hood('west end'), true);
    expect(h.exportCsv().split('\r\n')).toEqual([
      'b_id,address,local_area,units',
      '1,101 MAIN ST,West End,40',
      '2,102 MAIN ST,West End,12',
      '3,103 MAIN ST,West End,8',
    ]);
  });
});
