// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import type { LandlordFilter, PickOption } from '../landlord-picker';
import { findFilterControls, readFilterState, writeFilterState, type FilterState } from './filter-state';
import type { MetricControls } from './metric-controls';

function setup() {
  document.body.innerHTML = `
    <input type="checkbox" class="filter-neighbourhood-option" value="West End">
    <input type="checkbox" class="filter-neighbourhood-option" value="chinatown">
    <button class="housing-chip" data-housing="sro" aria-pressed="false"></button>
    <button class="housing-chip" data-housing="co-op" aria-pressed="false"></button>
    <input type="checkbox" id="filter-only-issues"><input type="checkbox" id="filter-only-owned">
    <input type="checkbox" id="filter-only-units">`;
  const units = { summary: { min: 0, max: 100, step: 1, attr: 'units' }, currentMin: 0, currentMax: 100 };
  const metrics = {
    keys: ['units'],
    controls: { units },
    setRange(_m: string, min: number | null, max: number | null) { units.currentMin = min ?? 0; units.currentMax = max ?? 100; },
  } as unknown as MetricControls;
  let picked: PickOption[] = [];
  const landlords = { picked: () => [...picked], set: (p: PickOption[]) => { picked = [...p]; } } as unknown as LandlordFilter;
  return findFilterControls(document, landlords, metrics);
}

describe('readFilterState / writeFilterState', () => {
  it('round-trips through the controls', () => {
    const c = setup();
    const state: FilterState = {
      hoods: ['chinatown'], housing: ['co-op'],
      landlords: [{ kind: 'owner', key: 'acme', label: 'Acme', buildings: 4, detail: '' }],
      onlyIssues: true, onlyOwned: false, onlyUnits: true,
      thresholds: { units: { min: 20, max: null } },
    };
    writeFilterState(c, state);
    expect(readFilterState(c)).toEqual(state);
  });

  it('lowercases area checkbox values', () => {
    const c = setup();
    writeFilterState(c, { ...readFilterState(c), hoods: ['west end'] });
    expect(c.hoodInputs[0].checked).toBe(true);
    expect(readFilterState(c).hoods).toEqual(['west end']);
  });
});
