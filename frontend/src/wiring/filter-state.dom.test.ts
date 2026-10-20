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
    <input type="checkbox" id="filter-only-units">
    <button class="owner-type-chip" data-owner-type="private" aria-pressed="false"></button>
    <button class="owner-type-chip" data-owner-type="non_profit" aria-pressed="false"></button>
    <button class="legal-form-chip" data-legal-form="numbered_company" aria-pressed="false"></button>
    <button class="legal-form-chip" data-legal-form="company" aria-pressed="false"></button>
    <button class="market-chip" data-market="market" aria-pressed="false"></button>
    <input type="checkbox" id="filter-include-inferred" checked>`;
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
      ownerTypes: [], legalForms: [], market: [], includeInferred: true,
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

describe('classification controls', () => {
  it('round-trips the classification filters', () => {
    const c = setup();
    const state: FilterState = {
      hoods: [], housing: [], landlords: [], onlyIssues: false, onlyOwned: false, onlyUnits: false,
      ownerTypes: ['private'], legalForms: ['numbered_company'], market: ['market'], includeInferred: false,
      thresholds: { units: { min: null, max: null } },
    };
    writeFilterState(c, state);
    expect(readFilterState(c)).toEqual(state);
  });

  it('legal form chips are disabled, and dropped, until Private is chosen', () => {
    const c = setup();
    const base: FilterState = {
      hoods: [], housing: [], landlords: [], onlyIssues: false, onlyOwned: false, onlyUnits: false,
      ownerTypes: [], legalForms: ['company'], market: [], includeInferred: true, thresholds: {},
    };
    writeFilterState(c, base);
    expect(c.legalFormChips.every((chip) => chip.hasAttribute('disabled'))).toBe(true);
    expect(readFilterState(c).legalForms).toEqual([]);
    writeFilterState(c, { ...base, ownerTypes: ['private'] });
    expect(c.legalFormChips.some((chip) => chip.hasAttribute('disabled'))).toBe(false);
  });
});
