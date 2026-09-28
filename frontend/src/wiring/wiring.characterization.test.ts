// @vitest-environment jsdom
/**
 * Pins what wiring does, seen from the page: rows, markers, blocks, counts.
 * Written against wiring.js before the refactor; must keep passing unchanged
 * (only the harness's import changes, in Task 8).
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ALL_BIDS } from './fixture';
import { startHarness } from './test-harness';

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
