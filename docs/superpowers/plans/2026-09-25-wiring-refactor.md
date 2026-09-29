# Wiring Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 2,200-line `frontend/src/wiring.js` closure with focused, typed modules under `frontend/src/wiring/`, then make the filter pass a pure, Node-testable function over typed state.

**Architecture:** Stage 1 pins today's behaviour with jsdom characterization tests, then moves code out of `wiring.js` one module at a time (each task leaves the suite green) until `wiring.js` is deleted. Stage 2 adds `FilterFields` (shared with table rendering), a pure `filterBuildings`/`blockVisibility`, and a typed `FilterState` with read/write/URL codec; `filter-pass.ts` becomes "read state → pure filter → apply results".

**Tech Stack:** TypeScript (strict), Vite, Vitest 4, jsdom (new dev dependency, per-file), Leaflet 1.9 (imperative, unchanged).

**Spec:** `docs/superpowers/specs/2026-09-25-wiring-refactor-design.md`

## Global Constraints

- All commands run from `frontend/`. Each task ends with `npm run typecheck` and `npm test` both passing.
- **No behaviour change** except removing the `wireUp()` retry loop and `window.load` wait (Task 8). Performance guards (per-frame coalescing, skip-if-unchanged writes, visible-tab-only recounts) and data-quirk handling (block own-area rule, missing metric values pass) stay exactly as they are.
- **Moving code:** function bodies are copied from `wiring.js`, not rewritten. Allowed edits while moving: `var` → `const`/`let`; add types; `window.xIndex` → `index.x`; closure variables → factory-local state or injected dependencies; drop `typeof x.method === 'function'` guards where the TS type guarantees the method. Keep every comment that explains *why* (performance, data quirks, ordering). Delete the moved code from `wiring.js` in the same task.
- `wiring.js` is plain JS and may import from `./wiring/*.ts` while it shrinks (Vite resolves it, as it already does for `./tables`).
- The characterization suite (`src/wiring/wiring.characterization.test.ts`) must not change after Task 2 except its import path (Task 8) and the scenarios Task 13 is told to extend. If it fails, the refactor is wrong, not the test.
- New test files that need a DOM start with `// @vitest-environment jsdom`. The global Vitest environment stays `node`.
- **Git:** never commit, branch or stash without asking the user first. Where a task says "Checkpoint", stop and ask whether to commit, with the suggested message. Never add Claude/AI attribution to commits.
- The precondition in Task 1 must hold before anything else.

## Review Focus

1. **Log-scale sliders with a floor bin** (real Units and assessed-value metrics use `use_log: true`; the fixture's are linear): position 0 must mean the true minimum and the floor bin must map linearly. Pinned by `metric-format.test.ts` in Task 6.
2. **A block with no table row or no area while an area filter is on** must stay hidden. Pinned in `filter.test.ts` (Task 11).
3. **Landlord keys containing HTML-special characters** (`smith & sons`) must filter identically via `FilterFields` and via the escaped `data-*` attributes. Pinned in `tables.filter-fields.test.ts` (Task 10).
4. **A startup failure** must surface once as a thrown error (shown by `bootstrap.ts`'s `showLoadError`) instead of silently retrying. Pinned in Task 8.
5. **Table search and filters interact** — footers count rows that are neither `.hidden` nor `.search-hidden`. Pinned by characterization scenario 15 (Task 2).

---

## Stage 1 — characterization tests, then the split (logic unchanged)

### Task 1: Precondition, jsdom, fixture and test harness

**Files:**
- Modify: `frontend/package.json` (dev dependency)
- Create: `frontend/src/wiring/fixture.ts`
- Create: `frontend/src/wiring/test-harness.ts`
- Test: `frontend/src/wiring/wiring.characterization.test.ts` (smoke test only in this task)

**Interfaces:**
- Produces: `startHarness(): Harness`, `flushFrames(): void`, `HIGHLIGHT`, `FakeLayer`, `FakeMap`, and the `FIXTURE_*` constants, used by every later characterization test.

- [ ] **Step 1: Check the precondition**

Run: `git status --porcelain -- .` (from `frontend/`)
Expected: no output. If anything is listed, STOP and tell the user: the refactor must start from a commit that includes their in-progress frontend work.

- [ ] **Step 2: Add jsdom**

Run: `npm install --save-dev jsdom`
Expected: `jsdom` appears under `devDependencies`.

- [ ] **Step 3: Write the fixture**

Create `frontend/src/wiring/fixture.ts`:

```ts
/**
 * A tiny city for wiring tests: 10 buildings in 3 areas, two landlords in one
 * network, three buildings with no landlord on record (one with a manager),
 * and four blocks — one empty, and one (301, Strathcona) that also holds a
 * Downtown building, like the real block/building spatial-join quirk.
 */
import { markerStyle } from '../markers';
import type { BlocksCollection, BuildingData, BuildingRecord, FilterConfig, MarkerRecord } from '../types';

interface B {
  id: number; area: string; owner: string; units: number | null; year: number | null;
  housing: string; issues: number; block: number | null;
  chinatown?: boolean; village?: boolean; manager?: string;
}

const OWNERS: Record<string, { name: string; network: string; networkName: string }> = {
  acme: { name: 'Acme Holdings', network: 'nw1', networkName: 'Cedar Group' },
  birch: { name: 'Birch Properties Ltd', network: 'nw1', networkName: 'Cedar Group' },
};

const BUILDINGS: B[] = [
  { id: 1, area: 'West End', owner: 'acme', units: 40, year: 1965, housing: '', issues: 0, block: 101 },
  { id: 2, area: 'West End', owner: 'acme', units: 12, year: 1990, housing: 'sro', issues: 2, block: 101 },
  { id: 3, area: 'West End', owner: 'birch', units: 8, year: null, housing: '', issues: 0, block: 101, village: true },
  { id: 4, area: 'Downtown', owner: 'birch', units: 120, year: 2005, housing: 'co-op, sro', issues: 0, block: 201 },
  { id: 5, area: 'Downtown', owner: 'unknown', units: 30, year: 1930, housing: '', issues: 1, block: 201, chinatown: true, manager: 'Tribe Management' },
  { id: 6, area: 'Downtown', owner: 'unknown', units: null, year: 1912, housing: 'co-op', issues: 0, block: 201 },
  { id: 7, area: 'Strathcona', owner: 'acme', units: 6, year: 1908, housing: '', issues: 3, block: 301 },
  { id: 8, area: 'Strathcona', owner: 'unknown', units: 16, year: 1975, housing: '', issues: 0, block: 301 },
  { id: 9, area: 'Strathcona', owner: 'birch', units: 60, year: 2015, housing: '', issues: 0, block: 301 },
  { id: 10, area: 'Downtown', owner: 'acme', units: 4, year: 1999, housing: '', issues: 0, block: 301 },
];

export const ALL_BIDS = BUILDINGS.map((b) => String(b.id));

function record(b: B): BuildingRecord {
  const o = OWNERS[b.owner];
  return {
    b_id: b.id,
    address: `${100 + b.id} MAIN ST`,
    building_name: '',
    local_area: b.area,
    units: b.units,
    year_built: b.year,
    owner_key: b.owner,
    owner_name: o ? o.name : '',
    network_key: o ? o.network : 'unknown',
    network_name: o ? o.networkName : '',
    managed_by: b.manager ?? '',
    housing_type: b.housing,
    n_issues: b.issues,
    block_id: b.block,
    in_chinatown: b.chinatown === true,
    in_village_plan: b.village === true,
    value_land: null,
    value_bldg: null,
    bldg_land_ratio: null,
  };
}

export const FIXTURE_BUILDING_DATA: BuildingData = {
  schema_version: 1,
  columns: ['b_id', 'address', 'local_area', 'units'],
  records: Object.fromEntries(BUILDINGS.map((b) => [String(b.id), record(b)])),
};

const FIXTURE_MARKER_RECORDS: MarkerRecord[] = BUILDINGS.map((b) => ({
  b_id: b.id,
  lat: 49.28 + b.id * 0.001,
  lon: -123.12,
  owner_key: b.owner,
  network_key: OWNERS[b.owner] ? OWNERS[b.owner].network : 'unknown',
  block_id: b.block,
  units: b.units,
  year_built: b.year,
  local_area: b.area,
  housing_type: b.housing,
  n_issues: b.issues,
  source: 'building',
}));

export const FIXTURE_MARKERS = FIXTURE_MARKER_RECORDS.map((m) => ({ ...m, ...markerStyle(m) }));

function block(id: number, area: string, buildings: number, units: number) {
  const x = -123.12 + id * 0.0001;
  return {
    type: 'Feature' as const,
    geometry: { type: 'Polygon' as const, coordinates: [[[x, 49.28], [x + 0.001, 49.28], [x + 0.001, 49.281], [x, 49.28]]] },
    properties: {
      block_id: id, block_label: `Block ${id}`, local_area: area, buildings, total_units: units,
      median_year_built: null, in_chinatown: false, in_village_plan: false,
    },
  };
}

export const FIXTURE_BLOCKS: BlocksCollection = {
  type: 'FeatureCollection',
  schema_version: 1,
  features: [block(101, 'West End', 3, 60), block(201, 'Downtown', 3, 150), block(301, 'Strathcona', 4, 86), block(401, 'Strathcona', 0, 0)],
};

export const FIXTURE_FILTER_CONFIG: FilterConfig = {
  schema_version: 1,
  neighbourhoods: [
    { name: 'Downtown', count: 4, units: 154 },
    { name: 'Strathcona', count: 3, units: 82 },
    { name: 'West End', count: 3, units: 60 },
  ],
  special_areas: [
    { key: 'chinatown', name: 'Chinatown', count: 1, units: 30 },
    { key: 'village-plan', name: 'Villages Plan', count: 1, units: 8 },
  ],
  dataset_totals: { buildings: 10, units: 296 },
  blocks_total_units_max: 150,
  building_metric_order: ['units', 'year_built'],
  building_metrics: {
    units: {
      label: 'Units', min: 4, max: 120, step: 1, max_count: 6, format: 'number', type: 'int', decimals: 0,
      attr: 'units', use_log: false,
      bins: [{ start: 4, end: 40, count: 6 }, { start: 40, end: 80, count: 2 }, { start: 80, end: 120, count: 1 }],
    },
    year_built: {
      label: 'Year built', min: 1900, max: 2020, step: 1, max_count: 3, format: 'year', type: 'int', decimals: 0,
      attr: 'year-built', use_log: false,
      bins: [{ start: 1900, end: 1940, count: 3 }, { start: 1940, end: 1980, count: 3 }, { start: 1980, end: 2020, count: 3 }],
    },
  },
};
```

- [ ] **Step 4: Write the harness**

Create `frontend/src/wiring/test-harness.ts`:

```ts
/**
 * Runs the real wiring against the real page (index.html), tables rendered by
 * tables.ts from the fixture, the real landlord picker, and fake Leaflet
 * objects that record what wiring does to them. For jsdom test files only.
 */
import { readFileSync } from 'node:fs';
import { vi } from 'vitest';
import { buildOptions, initLandlordPicker, type LandlordFilter } from '../landlord-picker';
import { renderLegend } from '../legend';
import { renderTables } from '../tables';
import { startWiring } from '../wiring.js';
import { FIXTURE_BLOCKS, FIXTURE_BUILDING_DATA, FIXTURE_FILTER_CONFIG, FIXTURE_MARKERS } from './fixture';

export const HIGHLIGHT = '#ff1744';
const INDEX_HTML = readFileSync(new URL('../../index.html', import.meta.url), 'utf8');

type Style = Record<string, unknown>;

/** Stands in for a CircleMarker, a block polygon, or a layer group. */
export class FakeLayer {
  options: Style;
  children: FakeLayer[] = [];
  feature?: { properties: Record<string, unknown> };
  private paint: FakeLayer[];
  private latlng: { lat: number; lng: number } | null;

  constructor(paint: FakeLayer[], latlng: { lat: number; lng: number } | null = null, options: Style = {}) {
    this.paint = paint;
    this.latlng = latlng;
    this.options = { ...options };
  }
  setStyle(s: Style): this { Object.assign(this.options, s); return this; }
  setRadius(r: number): this { this.options.radius = r; return this; }
  bringToFront(): this { this.unpaint(); this.paint.push(this); return this; }
  bringToBack(): this { this.unpaint(); this.paint.unshift(this); return this; }
  getLatLng(): { lat: number; lng: number } | null { return this.latlng; }
  addTo(map: FakeMap): this { map.addLayer(this); return this; }
  eachLayer(fn: (l: FakeLayer) => void): void { this.children.forEach(fn); }
  addLayer(l: FakeLayer): this { this.children.push(l); this.paint.push(l); return this; }
  private unpaint(): void {
    const i = this.paint.indexOf(this);
    if (i !== -1) this.paint.splice(i, 1);
  }
}

export class FakeMap {
  layers = new Set<FakeLayer>();
  private handlers = new Map<string, (() => void)[]>();
  addLayer(l: FakeLayer): this { this.layers.add(l); this.fire('layeradd'); return this; }
  removeLayer(l: FakeLayer): this { this.layers.delete(l); this.fire('layerremove'); return this; }
  /** Like Leaflet: a marker inside a group on the map counts as on the map. */
  hasLayer(l: FakeLayer): boolean { return this.layers.has(l) || [...this.layers].some((g) => g.children.includes(l)); }
  on(event: string, fn: () => void): this { this.handlers.set(event, [...(this.handlers.get(event) ?? []), fn]); return this; }
  getZoom(): number { return 14; }
  getBounds(): { contains: () => boolean } { return { contains: () => true }; }
  invalidateSize(): this { return this; }
  private fire(event: string): void { (this.handlers.get(event) ?? []).forEach((fn) => fn()); }
}

let frames: FrameRequestCallback[] = [];

/** Runs queued requestAnimationFrame callbacks (and any they queue). */
export function flushFrames(): void {
  for (let i = 0; i < 10 && frames.length; i += 1) {
    const run = frames;
    frames = [];
    run.forEach((cb) => cb(0));
  }
}

export interface Harness {
  map: FakeMap;
  markers: Record<string, FakeLayer>;
  blocks: Record<string, FakeLayer>;
  paint: FakeLayer[];
  landlords: LandlordFilter;
  /** b_ids passed to ctx.onFilter by the latest filter pass, numerically sorted. */
  visible(): string[];
  markerHidden(bid: number): boolean;
  markerHighlighted(bid: number): boolean;
  blockHidden(id: number): boolean;
  rowHidden(selector: string): boolean;
  setChecked(selector: string, on: boolean): void;
  click(selector: string): void;
  hover(selector: string, on: boolean): void;
  /** index into Filter by > Building's sliders (0 = Units, 1 = Year built); value in slider space. */
  setSlider(index: number, role: 'min' | 'max', value: number): void;
  barCounts(index: number): number[];
  pickLandlord(query: string): void;
  exportCsv(): string;
}

function $<T extends Element = HTMLElement>(selector: string): T {
  const el = document.querySelector<T>(selector);
  if (!el) throw new Error(`no element matches ${selector}`);
  return el;
}

export function startHarness(): Harness {
  frames = [];
  const raf = (cb: FrameRequestCallback): number => { frames.push(cb); return frames.length; };
  vi.stubGlobal('requestAnimationFrame', raf);
  window.requestAnimationFrame = raf;

  document.body.innerHTML = new DOMParser().parseFromString(INDEX_HTML, 'text/html').body.innerHTML;
  renderLegend(FIXTURE_FILTER_CONFIG);
  renderTables(FIXTURE_BUILDING_DATA, FIXTURE_BLOCKS, document, null);
  const landlords = initLandlordPicker(buildOptions(Object.values(FIXTURE_BUILDING_DATA.records)), {
    input: $<HTMLInputElement>('#owner-search'),
    tiles: $('#owner-tiles'),
    list: $('#owner-suggestions'),
  });

  const paint: FakeLayer[] = [];
  const map = new FakeMap();
  const blocksLayer = new FakeLayer(paint);
  const blocks: Record<string, FakeLayer> = {};
  for (const f of FIXTURE_BLOCKS.features) {
    const layer = new FakeLayer(paint);
    layer.feature = { properties: { ...f.properties } };
    blocksLayer.addLayer(layer);
    blocks[String(f.properties.block_id)] = layer;
  }
  const buildingsLayer = new FakeLayer(paint);
  const markers: Record<string, FakeLayer> = {};
  for (const m of FIXTURE_MARKERS) {
    const marker = new FakeLayer(paint, { lat: m.lat as number, lng: m.lon as number }, {
      radius: m.base_radius, fill: true, fillOpacity: m.base_opacity,
      color: m.stroke_color, weight: m.stroke_weight, fillColor: m.base_color,
    });
    buildingsLayer.addLayer(marker);
    markers[String(m.b_id)] = marker;
  }
  const rings: Record<string, { housing_type: string; marker: FakeLayer }[]> = {};
  for (const m of FIXTURE_MARKERS) {
    if (!m.extra_rings.length) continue;
    rings[String(m.b_id)] = m.extra_rings.map((r, i) => {
      const ring = new FakeLayer(paint, { lat: m.lat as number, lng: m.lon as number }, { radius: m.base_radius + 3 * (i + 1), fill: false });
      buildingsLayer.addLayer(ring);
      return { housing_type: r.housing_type, marker: ring };
    });
  }
  const neighbourhoods = new FakeLayer(paint);
  const villages = new FakeLayer(paint);
  const chinatown = new FakeLayer(paint);
  [blocksLayer, buildingsLayer, neighbourhoods, chinatown].forEach((l) => map.addLayer(l));

  const seen: { visible: Set<string> | null } = { visible: null };
  startWiring({
    map,
    layers: { blocks: blocksLayer, buildings: buildingsLayer, neighbourhoods, villages, chinatown },
    markersById: markers,
    ringsById: rings,
    filterConfig: FIXTURE_FILTER_CONFIG,
    markers: FIXTURE_MARKERS,
    buildingData: FIXTURE_BUILDING_DATA,
    landlordFilter: landlords,
    onFilter: (visible: Set<string>) => { seen.visible = new Set(visible); },
  } as unknown as Parameters<typeof startWiring>[0]);
  // The old wiring.js waits for 'load' unless the document is already complete; harmless afterwards.
  window.dispatchEvent(new Event('load'));
  flushFrames();
  if (!seen.visible || document.getElementById('summary-buildings-label')?.textContent !== 'Totals (visible)') {
    throw new Error(
      'wiring did not finish starting up. The old wireUp() swallows its own errors and retries: ' +
      'temporarily log `e` in its catch block to see why (usually a fake here is missing a method).',
    );
  }

  const metricControl = (i: number): Element => {
    const el = document.querySelectorAll('#filter-building-section .metric-control')[i];
    if (!el) throw new Error(`no metric control ${i}`);
    return el;
  };
  const click = (selector: string): void => {
    $(selector).dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    flushFrames();
  };

  return {
    map, markers, blocks, paint, landlords,
    visible: () => [...(seen.visible ?? [])].sort((a, b) => Number(a) - Number(b)),
    markerHidden: (bid) => markers[String(bid)].options.radius === 0,
    markerHighlighted: (bid) => markers[String(bid)].options.color === HIGHLIGHT,
    blockHidden: (id) => blocks[String(id)].options.weight === 0,
    rowHidden: (selector) => $(selector).classList.contains('hidden'),
    setChecked(selector, on) {
      const input = $<HTMLInputElement>(selector);
      input.checked = on;
      input.dispatchEvent(new Event('change', { bubbles: true }));
      flushFrames();
    },
    click,
    hover(selector, on) {
      $(selector).dispatchEvent(new MouseEvent(on ? 'mouseenter' : 'mouseleave'));
      flushFrames();
    },
    setSlider(i, role, value) {
      const [min, max] = Array.from(metricControl(i).querySelectorAll<HTMLInputElement>('.metric-sliders input'));
      const input = role === 'min' ? min : max;
      input.value = String(value);
      input.dispatchEvent(new Event('input'));
      flushFrames();
    },
    barCounts: (i) => Array.from(metricControl(i).querySelectorAll<HTMLElement>('.metric-hist-bar')).map((bar) => {
      const m = /\(([\d,]+)\)(?: \[log bin\])?$/.exec(bar.title);
      if (!m) throw new Error(`unexpected bar title: ${bar.title}`);
      return Number(m[1].replace(/,/g, ''));
    }),
    pickLandlord(query) {
      const input = $<HTMLInputElement>('#owner-search');
      input.focus();
      input.value = query;
      input.dispatchEvent(new Event('input'));
      input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
      flushFrames();
    },
    exportCsv() {
      let parts: unknown[] = [];
      const RealBlob = globalThis.Blob;
      globalThis.Blob = class { constructor(p: unknown[]) { parts = p; } } as unknown as typeof Blob;
      URL.createObjectURL = () => 'blob:fixture';
      URL.revokeObjectURL = () => {};
      const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
      try {
        click('#export-visible-csv');
      } finally {
        globalThis.Blob = RealBlob;
        anchorClick.mockRestore();
      }
      return parts.join('');
    },
  };
}
```

- [ ] **Step 5: Write the smoke test**

Create `frontend/src/wiring/wiring.characterization.test.ts`:

```ts
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
```

- [ ] **Step 6: Run it**

Run: `npx vitest run src/wiring`
Expected: 1 test PASS. This is a characterization test, so it passes against the existing code; if the harness throws "wiring did not finish starting up", add `console.error(e)` in `wiring.js`'s outer `catch` temporarily, fix the fake, then remove the log.

- [ ] **Step 7: Full suite and types**

Run: `npm run typecheck && npm test`
Expected: both pass.

- [ ] **Step 8: Checkpoint** — ask the user whether to commit. Suggested message: `Add jsdom and a wiring test harness with a fixture city`

---

### Task 2: Characterization scenarios

**Files:**
- Test: `frontend/src/wiring/wiring.characterization.test.ts` (append)

**Interfaces:**
- Consumes: `startHarness`, `flushFrames`, `ALL_BIDS` from Task 1.

These tests describe today's behaviour and should pass immediately. A failing one means the expectation or the harness is wrong — re-check the fixture arithmetic in the comment next to it before touching anything else. Do not change `wiring.js` in this task.

- [ ] **Step 1: Append the scenarios**

Add to the imports: `import { flushFrames } from './test-harness';` (merge with the existing import). Then append:

```ts
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
```

- [ ] **Step 2: Run them**

Run: `npx vitest run src/wiring`
Expected: 19 tests PASS.

- [ ] **Step 3: Prove the suite can fail**

Temporarily change `wiring.js`'s `areaSelectionMatches` to `return true;` as its first line. Run `npx vitest run src/wiring`; expected: the area, Chinatown, blocks and Clear/Reset tests FAIL. Revert the change and re-run: all PASS.

- [ ] **Step 4:** `npm run typecheck && npm test` — both pass.

- [ ] **Step 5: Checkpoint** — ask to commit. Suggested message: `Pin wiring behaviour with characterization tests`

---

### Task 3: `map-theme.ts`

**Files:**
- Create: `frontend/src/wiring/map-theme.ts`
- Modify: `frontend/src/wiring.js`, `frontend/src/blocks.ts`, `frontend/src/markers.ts`, `frontend/src/neighbourhoods.ts`, `frontend/src/villages.ts`, `frontend/src/chinatown.ts`

**Interfaces:**
- Produces: `MAP_THEME` (below). Later tasks use `MAP_THEME.highlight`, `MAP_THEME.marker`, `MAP_THEME.block`.

Existing tests in `blocks.test.ts`, `markers.test.ts`, `neighbourhoods.test.ts`, `villages.test.ts`, `chinatown.test.ts` assert literal colours. **Leave them unchanged** — they prove the values were copied exactly.

- [ ] **Step 1: Create the theme**

```ts
/**
 * Every colour (and highlight/stroke weight) Leaflet paints on the map. CSS
 * cannot reach these — Leaflet draws them onto a canvas — so they live here
 * as JS values. Page (sidebar/filters) colours are in index.html's CSS.
 */
export const MAP_THEME = {
  highlight: { color: '#ff1744', markerWeight: 2, blockWeight: 4 },
  marker: {
    stroke: '#ffffff',
    strokeWeight: 0.6,
    fill: '#9e9e9e',
    rings: { coop: '#d97706', sro: '#3182bd', issues: '#dc2626' },
  },
  block: {
    stroke: '#b8b8b8',
    /** Light to dark, by share of the visible blocks' unit range. */
    scale: ['#c7e9c0', '#a1d99b', '#74c476', '#41ab5d', '#238b45', '#005a32'],
    unscaledFill: '#f0f0f0',
    filteredFill: '#f5f5f5',
  },
  boundary: { neighbourhood: '#ff8c00', villages: '#7b3fa0', chinatown: '#c0392b', labelHalo: '#fff' },
} as const;
```

- [ ] **Step 2: Replace literals**

Replace each literal with its token, keeping everything else identical:
- `markers.ts`: `NEUTRAL_COLOR` → `MAP_THEME.marker.fill`; `COOP_RING_COLOR`/`SRO_RING_COLOR`/`ISSUES_RING_COLOR` → `MAP_THEME.marker.rings.*`; `DEFAULT_STROKE_COLOR` → `MAP_THEME.marker.stroke` (keep the local const names if other code uses them, assigning from the theme).
- `blocks.ts`: `greensColor` returns `MAP_THEME.block.scale[0..5]` in the same threshold order; `'#b8b8b8'` → `MAP_THEME.block.stroke`.
- `neighbourhoods.ts`, `villages.ts`, `chinatown.ts`: the `*_STYLE.color` and the label `color:`/text-shadow `#fff` → `MAP_THEME.boundary.*` via template strings.
- `wiring.js`: add `import { MAP_THEME } from './wiring/map-theme';` and replace `'#ff1744'`, `'#ffffff'`/`MARKER_STROKE_COLOR`, `0.6`/`MARKER_STROKE_WEIGHT` (define the two consts from the theme), `'#9e9e9e'`, `'#b8b8b8'`, `'#f0f0f0'`, `'#f5f5f5'`, the six greens in `resetBlockStyle`, `weight:2`/`weight:4` in `highlightMarker`/`highlightBlock`.

- [ ] **Step 3: Check nothing was missed**

Run: `grep -nE "#[0-9a-fA-F]{3,6}\b" src/wiring.js src/blocks.ts src/markers.ts src/neighbourhoods.ts src/villages.ts src/chinatown.ts`
Expected: no output.

- [ ] **Step 4:** `npm run typecheck && npm test` — all pass (characterization + the five layer-file test files unchanged).

- [ ] **Step 5: Checkpoint** — suggested message: `Collect map-drawing colours into one theme`

---

### Task 4: `wiring/types.ts` and `indexes.ts` (no more `window.*`)

**Files:**
- Create: `frontend/src/wiring/types.ts`, `frontend/src/wiring/indexes.ts`
- Modify: `frontend/src/wiring.js`

**Interfaces:**
- Produces (`types.ts`, full code below): `BuildingMarker`, `BlockLayer`, `MapIndex`, `CachedRow`, `WiringContext`.
- Produces (`indexes.ts`): `buildMapIndex(ctx: WiringContext): MapIndex` — throws `Error('Blocks layer not ready')` if `ctx.layers.blocks.eachLayer` is missing and `Error('Building markers not ready')` if no marker was indexed.

`types.ts` is a small refinement of the spec's layout: the shared shapes get one home so modules don't import each other just for types.

- [ ] **Step 1: Create `types.ts`**

```ts
import type * as L from 'leaflet';
import type { LandlordFilter } from '../landlord-picker';
import type { StyledMarker } from '../markers';
import type { BuildingData, FilterConfig } from '../types';

/** A building's CircleMarker plus the state wiring keeps on it. */
export interface BuildingMarker extends L.CircleMarker {
  _baseColor: string;
  _baseOpacity: number;
  _baseRadius: number;
  _strokeColor: string;
  _strokeWeight: number;
  _primaryHousingType: string;
  _housingType: string;
  _extraRings: { housingType: string; marker: L.CircleMarker }[] | null;
  _units: number;
  _yearBuilt: number | null;
  _isFiltered: boolean;
  _selectionRefs: number;
  _highlighted: boolean;
}

/** One block polygon of the blocks GeoJSON layer. */
export interface BlockLayer extends L.Path {
  feature: { properties: Record<string, unknown> };
  _blockUnits: number;
  _blockBuildings: number;
  _baseStyle: L.PathOptions;
  _isFiltered: boolean;
  _selectionRefs: number;
  _highlighted: boolean;
}

/** Lookup tables built once at start-up (formerly window.* globals). */
export interface MapIndex {
  buildings: Record<string, BuildingMarker>;
  blocks: Record<string, BlockLayer>;
  /** Block layers in GeoJSON order. */
  blockLayers: BlockLayer[];
  blockBuildings: Record<string, string[]>;
  owners: Record<string, BuildingMarker[]>;
  networks: Record<string, BuildingMarker[]>;
  /** Keyed by lowercased, trimmed local_area. */
  hoods: Record<string, BuildingMarker[]>;
}

/** A sidebar table row with the lookups cached on it at start-up. */
export interface CachedRow extends HTMLTableRowElement {
  __checkbox: HTMLInputElement | null;
  __cells?: Record<string, Element | null>;
  __lastMetrics?: { bldgs: number; units: number; avg: number; medianYear: number | null };
}

export interface WiringContext {
  map: L.Map;
  layers: {
    blocks: L.GeoJSON;
    buildings: L.FeatureGroup;
    neighbourhoods: L.FeatureGroup;
    villages: L.FeatureGroup;
    chinatown: L.FeatureGroup;
  };
  markersById: Record<string, L.CircleMarker>;
  ringsById: Record<string, { housing_type: string; marker: L.CircleMarker }[]>;
  filterConfig: FilterConfig;
  markers: StyledMarker[];
  buildingData: BuildingData;
  landlordFilter?: LandlordFilter;
  /** Called after every filter pass with the b_ids of the buildings that pass. */
  onFilter?: (visibleBids: Set<string>) => void;
}
```

- [ ] **Step 2: Create `indexes.ts`**

`buildMapIndex(ctx)` contains, in this order: the block scan (`geo.eachLayer(...)` building `blocksIndex` and `blockLayers`, with its `_selectionRefs`/`_isFiltered`/`_blockUnits`/`_blockBuildings` initialisation) and the body of `applyMarkerMetadata()` **except** the two appearance calls at its end (`ensureMarkerBase(marker); updateMarkerColorAppearance(marker);`), which stay in `wiring.js`. Stroke defaults come from `MAP_THEME.marker`. The `layerBlocks.eachLayer` check and the "no markers" check throw the two errors named above. Return the `MapIndex`.

- [ ] **Step 3: Use it from `wiring.js`**

At the top of `wireUp()`: `const index = buildMapIndex(ctx);`. Delete the six `window.* = {}` lines, the block scan, and the moved part of `applyMarkerMetadata()`; where `applyMarkerMetadata()` was called, loop `Object.values(index.buildings)` calling `ensureMarkerBase(m); updateMarkerColorAppearance(m);`. Replace every `window.buildingIndex`/`blocksIndex`/`blockBuildingIndex`/`ownerIndex`/`networkIndex`/`hoodIndex` with `index.buildings`/`blocks`/`blockBuildings`/`owners`/`networks`/`hoods`, and `blockLayers` with `index.blockLayers`. Delete `window.blockColorMin`/`window.blockColorMax` (nothing reads them).

- [ ] **Step 4: Verify no globals remain**

Run: `grep -n "window\.\(blocksIndex\|blockBuildingIndex\|buildingIndex\|ownerIndex\|networkIndex\|hoodIndex\|blockColor\)" src/wiring.js`
Expected: no output.

- [ ] **Step 5:** `npm run typecheck && npm test` — all pass.

- [ ] **Step 6: Checkpoint** — suggested message: `Replace wiring's window globals with a typed MapIndex`

---

### Task 5: `marker-style.ts` and `block-style.ts`

**Files:**
- Create: `frontend/src/wiring/marker-style.ts`, `frontend/src/wiring/block-style.ts`
- Modify: `frontend/src/wiring.js`

**Interfaces:**
- Consumes: `MapIndex`, `BuildingMarker`, `BlockLayer` (Task 4), `MAP_THEME` (Task 3).
- Produces:

```ts
// marker-style.ts
export interface Restack {
  /** Coalesced to one restack per animation frame. */
  schedule(): void;
  now(): void;
  sendBlocksToBack(): void;
}
export function createRestack(index: MapIndex): Restack;

export interface MarkerStyler {
  ensureBase(marker: BuildingMarker): void;
  highlight(marker: BuildingMarker | undefined, on: boolean): void;
  adjustSelection(marker: BuildingMarker | undefined, delta: number): void;
  setVisible(marker: BuildingMarker | undefined, visible: boolean): void;
  /** updateMarkerColorAppearance: re-applies highlight state after a visibility flip. */
  refreshAppearance(marker: BuildingMarker): void;
  /** Hover on/off for a set of markers; leaves selected ones highlighted. */
  hover(markers: (BuildingMarker | undefined)[], on: boolean): void;
  applyZoom(zoom: number): void;
  /** Sets the Housing type / Rental issues display flags (read by stroke and ring logic). */
  setHousingFlags(showHousing: boolean, showIssues: boolean): void;
  /** The restyle loop at the end of applyHousingTypeFilter(). */
  restyleHousing(): void;
}
export function createMarkerStyler(index: MapIndex, scheduleRestack: () => void): MarkerStyler;

// block-style.ts
export interface BlockStyler {
  /** recomputeBlockColorScale(), including the legend scale text. */
  recomputeScale(): void;
  setColorScaling(enabled: boolean): void;
  colorScalingEnabled(): boolean;
  setFiltered(blockId: string, filtered: boolean): void;
  adjustSelection(layer: BlockLayer | undefined, delta: number): void;
  hover(blockId: string, on: boolean): void;
}
export function createBlockStyler(index: MapIndex, doc: Document, scheduleRestack: () => void): BlockStyler;
```

**Move map** (function in `wiring.js` → destination):
- `marker-style.ts`: `computeZoomScale`, `getScaledRadius`, `ensureMarkerBase`, `effectiveStrokeColor`, `effectiveStrokeWeight`, `syncMarkerAnnotations`, `restyleMarkerStroke`, `highlightMarker`, `adjustMarkerSelection`, `setMarkerVisibility`, `updateMarkerColorAppearance`, the zoom loop of `applyZoomScaling` (as `applyZoom(zoom)`; the caller passes `map.getZoom()`), the restyle loop of `applyHousingTypeFilter` (as `restyleHousing`), `buildingHover`/`ownerHover`/`networkHover`/`neighbourhoodHover` (collapsed into `hover(markers, on)` — they are the same loop), and the state `currentZoomScale`, `showHousingTypeChecked`, `showIssuesChecked`, `BASE_ZOOM`.
- Restack (`createRestack`, in `marker-style.ts`): `sendBlocksToBack`, `bringLayerToFront`, `restackCanvas`, `restackScheduled`/`scheduleRestack` (use `window.requestAnimationFrame`).
- `block-style.ts`: `resetBlockStyle`, `recomputeBlockColorScale`, `updateBlockLegendScale`, `setBlockFiltered`, `highlightBlock`, `adjustBlockSelection`, `blockHover` (as `hover(blockId, on)`), the colour-scaling part of `applyBlockColorScaling` (as `setColorScaling`; its trailing `updateLegendVisibility()` stays with the caller), and the state `blockColorScalingEnabled`, `blockColorMin`, `blockColorMax`.

- [ ] **Step 1:** Create both modules by moving the functions above, following the Global Constraints' move rules. The ordering hack comments ("Declared here … temporal dead zone", "`var`, not `let`") become unnecessary — delete those two comments only, since factories make the order explicit.

- [ ] **Step 2:** In `wiring.js`, create them near the top of `wireUp()` (after `buildMapIndex`): `const restack = createRestack(index); const blocks = createBlockStyler(index, document, restack.schedule); const markers = createMarkerStyler(index, restack.schedule);` and replace every call to a moved function with the matching method. `wiring.js`'s `applyHousingTypeFilter` becomes: read the two checkboxes into local variables, `markers.setHousingFlags(showHousing, showIssues); applyFilters(); updateLegendVisibility(); markers.restyleHousing();` — `updateLegendVisibility` keeps reading its own local copies of the two flags until Task 8 moves it.

- [ ] **Step 3:** `npm run typecheck && npm test` — all pass.

- [ ] **Step 4: Checkpoint** — suggested message: `Move marker and block styling out of wiring.js`

---

### Task 6: `metric-format.ts` and `metric-controls.ts`

**Files:**
- Create: `frontend/src/wiring/metric-format.ts`, `frontend/src/wiring/metric-controls.ts`
- Test: `frontend/src/wiring/metric-format.test.ts`
- Modify: `frontend/src/wiring.js`

**Interfaces:**
- Produces:

```ts
// metric-format.ts (pure)
export interface MetricBin { start: number; end: number; count: number }
export interface MetricSummary {
  label?: string; min: number; max: number; step?: number; bins?: MetricBin[]; max_count?: number;
  format?: string; type?: string; decimals?: number; attr: string; min_positive?: number; use_log?: boolean;
}
export interface SliderScale {
  useLog: boolean;
  toSlider(value: number): number;
  fromSlider(position: number): number;
  /** Axis-tick fraction (0..1) for a value — the same transform the sliders use. */
  tickFraction(value: number): number;
}
export function sliderScale(summary: MetricSummary): SliderScale;
export function niceLogTicks(minV: number, maxV: number): number[];
export function formatWithSummary(summary: MetricSummary, value: number | null | undefined): string;
export function formatTickValue(summary: MetricSummary, value: number): string;

// metric-controls.ts
export type MetricSection = 'building' | 'value';
export interface MetricControl {
  summary: MetricSummary; section: MetricSection;
  minSlider: HTMLInputElement; maxSlider: HTMLInputElement;
  minLabel: HTMLElement; maxLabel: HTMLElement; bars: HTMLElement[];
  useLog: boolean; toSlider(v: number): number; fromSlider(p: number): number;
  currentMin: number; currentMax: number;
}
export interface MetricControls {
  /** Metric keys in display order. */
  keys: string[];
  controls: Record<string, MetricControl>;
  updateLabels(metric: string): void;
  updateAllLabels(): void;
  reset(metric: string): void;
  /** Live histogram: bar heights rescaled to the tallest count, titles updated. */
  setBarCounts(metric: string, counts: number[]): void;
}
export function buildMetricControls(filterConfig: FilterConfig, doc: Document, onChange: () => void): MetricControls;
```

`sliderScale` holds the `useLog` decision and the `logMin`/`logMax`/`hasFloorBin`/`floorPos`/`toSlider`/`fromSlider` code from the top of `renderMetricControl`, plus the per-tick `frac` expression from its axis loop (as `tickFraction`). It returns identity transforms whenever the final `useLog` (`useLog && logMax !== logMin`) is false — exactly what `renderMetricControl` stores on `ctrl`.

**Move map:** `niceLogTicks`, `formatWithSummary`, `formatTickValue` → `metric-format.ts`. `formatMetricValue` has no callers — delete it (check with `grep -n formatMetricValue src/wiring.js`). `renderMetricControl` (now calling `sliderScale`), `updateMetricLabels`, `makeSliderHandler` (calling `onChange` instead of `scheduleApplyFilters`), `resetMetric`, `buildMetricControls`, `VALUE_METRIC_LABELS`, `metricSection` (now `control.section`), and the bar-height/title loop from the end of `applyFilters` (as `setBarCounts`) → `metric-controls.ts`.

- [ ] **Step 1: Write the failing tests**

```ts
import { describe, expect, it } from 'vitest';
import { formatTickValue, formatWithSummary, niceLogTicks, sliderScale, type MetricSummary } from './metric-format';

// The real Units metric: log scale with a floor bin (0–2.5) as wide as any other bar.
const units: MetricSummary = {
  min: 0, max: 449, min_positive: 2.5, use_log: true, type: 'int', attr: 'units',
  bins: [{ start: 0, end: 2.5, count: 1 }, { start: 2.5, end: 10, count: 1 }, { start: 10, end: 100, count: 1 }, { start: 100, end: 449, count: 1 }],
};

describe('sliderScale', () => {
  it('reads position 0 as the true minimum, not the floor', () => {
    expect(sliderScale(units).fromSlider(0)).toBe(0);
  });

  it('gives the floor bin its share of the track, linearly', () => {
    const s = sliderScale(units);
    expect(s.toSlider(2.5)).toBeCloseTo(25);
    expect(s.toSlider(1.25)).toBeCloseTo(12.5);
    expect(s.fromSlider(12.5)).toBeCloseTo(1.25);
    expect(s.toSlider(449)).toBeCloseTo(100);
  });

  it('round-trips positions on the log part of the track', () => {
    const s = sliderScale(units);
    for (const p of [30, 60, 90]) expect(s.toSlider(s.fromSlider(p))).toBeCloseTo(p);
  });

  it('is the identity for a linear metric, or one with no spread', () => {
    const year: MetricSummary = { min: 1900, max: 2025, use_log: false, attr: 'year-built' };
    expect(sliderScale(year).useLog).toBe(false);
    expect(sliderScale(year).toSlider(1950)).toBe(1950);
    expect(sliderScale({ ...units, max: 0 }).useLog).toBe(false);
  });
});

describe('niceLogTicks', () => {
  it('uses powers of ten, anchored at the minimum', () => {
    expect(niceLogTicks(10000, 92737000)).toEqual([1e4, 1e5, 1e6, 1e7]);
    expect(niceLogTicks(2.5, 449)).toEqual([2.5, 10, 100]);
  });

  it('thins to six ticks, keeping both ends', () => {
    expect(niceLogTicks(1, 1e9)).toEqual([1, 1e2, 1e4, 1e6, 1e8, 1e9]);
  });
});

describe('formatting', () => {
  it('formats years plainly and missing values as a dash', () => {
    expect(formatWithSummary({ min: 0, max: 1, attr: 'y', format: 'year' }, 1965.4)).toBe('1965');
    expect(formatWithSummary({ min: 0, max: 1, attr: 'y' }, null)).toBe('–');
  });

  it('abbreviates currency ticks', () => {
    const money: MetricSummary = { min: 0, max: 1, attr: 'v', format: 'currency' };
    expect(formatTickValue(money, 10000)).toBe('$10K');
    expect(formatTickValue(money, 1500)).toBe('$1.5K');
    expect(formatTickValue(money, 1e6)).toBe('$1M');
    expect(formatTickValue(money, 2.5e6)).toBe('$2.5M');
    expect(formatTickValue(money, 950)).toBe('$950');
  });
});
```

- [ ] **Step 2:** Run `npx vitest run src/wiring/metric-format.test.ts` — FAIL (module not found).

- [ ] **Step 3:** Create `metric-format.ts` by moving the functions listed above; run the test again — PASS.

- [ ] **Step 4:** Create `metric-controls.ts` by moving the functions listed above. In `wiring.js`: `const metrics = buildMetricControls(filterConfig, document, scheduleApplyFilters);` and replace `metricControls`/`metricKeys`/`metricSection`/`updateMetricLabels`/`resetMetric` uses with `metrics.controls`/`metrics.keys`/`metrics.controls[k].section`/`metrics.updateLabels`/`metrics.reset`; replace the bar loop in `applyFilters` with `metrics.keys.forEach((k) => metrics.setBarCounts(k, binCounts[k]));`.

- [ ] **Step 5:** `npm run typecheck && npm test` — all pass.

- [ ] **Step 6: Checkpoint** — suggested message: `Move metric sliders out of wiring.js, with pure scale and format helpers`

---

### Task 7: `tables-live.ts`, `selection.ts`, `status-export.ts`

**Files:**
- Create: `frontend/src/wiring/tables-live.ts`, `frontend/src/wiring/selection.ts`, `frontend/src/wiring/status-export.ts`
- Test: `frontend/src/wiring/status-export.test.ts`
- Modify: `frontend/src/wiring.js`

**Interfaces:**
- Consumes: `MapIndex`, `CachedRow` (Task 4); `MarkerStyler`, `BlockStyler` (Task 5).
- Produces:

```ts
// tables-live.ts
export interface LiveTables {
  buildingRows: CachedRow[];
  ownerRows: CachedRow[];
  networkRows: CachedRow[];
  neighbourhoodRows: CachedRow[];
  blockRows: CachedRow[];
  blockRowById: Record<string, CachedRow>;
  updateSummaryBar(): void;
  updateGroupTableSummaries(): void;
  /** refreshGroupRowsAfterFilter: recount the visible tab, mark the rest stale. */
  refreshAfterFilter(): void;
}
/** Caches rows, wires tabs, header sorting, and the 'tablesearch' footer refresh. */
export function initLiveTables(index: MapIndex, doc: Document): LiveTables;

// selection.ts
export interface Selection {
  owner(key: string, on: boolean): void;
  network(key: string, on: boolean): void;
  hood(key: string, on: boolean): void;
  blockMarkers(blockId: string, on: boolean): void;
  /** Reset's "untick every row" loop (dispatches change so counts follow). */
  clearAll(): void;
}
/** Wires row checkboxes and row hover for all five tables. */
export function initSelection(index: MapIndex, markers: MarkerStyler, blocks: BlockStyler, tables: LiveTables, doc: Document): Selection;

// status-export.ts
export function escapeCSV(value: unknown): string;
export interface Status { updateDataset(): void; updateMapView(): void }
export function createStatus(index: MapIndex, map: L.Map, filterConfig: FilterConfig, doc: Document): Status;
/** Coalesced map moveend/zoomend/layeradd/layerremove handling, plus the start-up invalidateSize. */
export function watchMap(map: L.Map, status: Status, onZoom: () => void): void;
export function initCsvExport(index: MapIndex, map: L.Map, buildingData: BuildingData, doc: Document): void;
```

**Move map:**
- `tables-live.ts`: tab refs + `activate` + tab listeners, `getSortValue`, `sortByHeader` + header listeners, the row caches (`buildingRows`, `ownerRows`, `networkRows`, `neighbourhoodRows`, `blockRows`, `blockRowById`, `cacheRowCells`), `computeLiveGroupMetrics`, `setCellValue`, `updateGroupRowValues`, `staleGroupRows`, `groupPanes`, `blockBuilding`, `refreshGroupRows`, `refreshGroupRowsAfterFilter`, `refreshStaleGroupRows`, `updateGroupTableSummary(ies)`, `updateSummaryBar`, the `tablesearch` listener.
- `selection.ts`: `setOwnerSelection`, `setNetworkSelection`, `setHoodSelection`, `setBlockSelectionMarkers`, `handleSelectionChange` + `.row-select` listeners, the five row-hover listener blocks (building/owner/network/hood rows call `markers.hover([...], on)`; block rows call `blocks.hover(id, on)`), and Reset's `.row-select` untick loop (as `clearAll`). `collectSelectedBuildingIds` has no callers — delete it (check with grep first).
- `status-export.ts`: `setStatusCell`, `updateDatasetStatus`, `computeMapSummary`, `updateMapStatus`, `mapStatusScheduled`/`scheduleMapStatusUpdate` + `map.on(...)` + the `setTimeout(invalidateSize…, 50)` block (as `watchMap`), `escapeCSV`, `collectVisibleBuildingIds`, `exportVisibleBuildingsCsv` + button listener. `computeMapSummary` and `collectVisibleBuildingIds` share one private `markersInView(index, map): [string, BuildingMarker][]` (same filter: not filtered, on the map, inside the bounds; `Object.keys` order).

- [ ] **Step 1: Write the failing test**

```ts
import { describe, expect, it } from 'vitest';
import { escapeCSV } from './status-export';

describe('escapeCSV', () => {
  it('leaves plain values alone and blanks missing ones', () => {
    expect(escapeCSV('West End')).toBe('West End');
    expect(escapeCSV(40)).toBe('40');
    expect(escapeCSV(null)).toBe('');
    expect(escapeCSV(undefined)).toBe('');
  });

  it('quotes commas, quotes and newlines', () => {
    expect(escapeCSV('101 Main St, Vancouver')).toBe('"101 Main St, Vancouver"');
    expect(escapeCSV('the "Tower"')).toBe('"the ""Tower"""');
    expect(escapeCSV('a\nb')).toBe('"a\nb"');
  });

  it('writes objects as JSON', () => {
    expect(escapeCSV(['a', 'b'])).toBe('"[""a"",""b""]"');
  });
});
```

- [ ] **Step 2:** Run `npx vitest run src/wiring/status-export.test.ts` — FAIL (module not found).

- [ ] **Step 3:** Create the three modules by moving the functions above. In `wiring.js`, create them after the stylers: `const status = createStatus(index, mapInstance, filterConfig, document); watchMap(mapInstance, status, () => markers.applyZoom(mapInstance.getZoom())); const tables = initLiveTables(index, document); const selection = initSelection(index, markers, blocks, tables, document); initCsvExport(index, mapInstance, buildingData, document);` and replace the moved calls with the methods.

- [ ] **Step 4:** `npm run typecheck && npm test` — all pass.

- [ ] **Step 5: Checkpoint** — suggested message: `Move tables, selection, status and CSV export out of wiring.js`

---

### Task 8: `display.ts`, `filter-pass.ts`, `index.ts`; delete `wiring.js`

**Files:**
- Create: `frontend/src/wiring/display.ts`, `frontend/src/wiring/filter-pass.ts`, `frontend/src/wiring/index.ts`
- Test: `frontend/src/wiring/index.test.ts`
- Delete: `frontend/src/wiring.js`, `frontend/src/wiring.d.ts`
- Modify: `frontend/src/bootstrap.ts` (import), `frontend/src/wiring/test-harness.ts` (import), `frontend/src/page-layout.test.ts`, `frontend/src/tables.ts` (doc comment)

**Interfaces:**
- Consumes: everything from Tasks 4–7.
- Produces:

```ts
// display.ts
export interface Display {
  updateLegend(): void;
  /** Reset's display part: layer toggles, block shading, boundaries, housing rings. */
  reset(): void;
}
/** Wires Show-on-map toggles, legend, pane gutters and mobile drawers; applies initial toggle state. */
export function initDisplay(
  ctx: WiringContext, markers: MarkerStyler, blocks: BlockStyler, restack: Restack,
  applyFilters: () => void, doc: Document,
): Display;

// filter-pass.ts (Stage 1 shape)
export interface FilterPass {
  apply(): void;
  /** Coalesced to one pass per animation frame. */
  schedule(): void;
  /** Reset's filter part: empty blocks off, areas, chips, landlords, only-* toggles, sliders. */
  resetFilters(): void;
}
export interface FilterPassDeps {
  ctx: WiringContext; index: MapIndex; markers: MarkerStyler; blocks: BlockStyler;
  selection: Selection; tables: LiveTables; metrics: MetricControls; status: Status;
}
export function initFilterPass(deps: FilterPassDeps, doc: Document): FilterPass;

// index.ts
export type { WiringContext } from './types';
export function startWiring(ctx: WiringContext, doc?: Document): void;
```

**Move map:**
- `display.ts`: `toggleLayerVisibility`, `boundaryVisibility`, `syncBoundaryLayers`, `setLegendDisplay`, `updateLegendVisibility`, `applyHousingTypeFilter` (as in Task 5), `initMobilePanels`, `initPaneResize`, the Show-on-map listener/initial-state blocks (`showBuildingsChk`, `colorBlocksChk` → `blocks.setColorScaling(x); updateLegend()`, `vizBlocksChk`, boundary checkboxes, housing/issues checkboxes), and the display half of the Reset handler.
- `filter-pass.ts`: `applyFiltersScheduled`/`scheduleApplyFilters`, `updateSectionCounts`, `applyFilters`, the filter-control listeners (`showEmptyBlocksChk`, `landlordFilter.onChange`, `onlyIssuesChk`, `onlyOwnedChk`, `onlyUnitsChk`, `hoodInputs`, `housingChips`), `clearSection` + section Clear listeners, and the filter half of the Reset handler (as `resetFilters`). The three owner/network/hood "hide empty group row" loops in `applyFilters` become one private helper `hideEmptyGroups(rows, attr, groups, deselect, lowercase)`.
- `index.ts`: `startWiring` — composition only, no logic of its own. **No retry loop, no `window.load` wait**: bootstrap calls it after everything is built, so any throw is a real bug and propagates to `main().catch(showLoadError)`.

`index.ts` in full:

```ts
/**
 * Map interactivity: filters, selection and hover, table recounts, legend,
 * status and export. Everything here runs once, after bootstrap.ts has built
 * the map layers and rendered the sidebar tables.
 */
import { createBlockStyler } from './block-style';
import { initDisplay } from './display';
import { initFilterPass, type FilterPass } from './filter-pass';
import { buildMapIndex } from './indexes';
import { createMarkerStyler, createRestack } from './marker-style';
import { buildMetricControls } from './metric-controls';
import { initSelection } from './selection';
import { createStatus, initCsvExport, watchMap } from './status-export';
import { initLiveTables } from './tables-live';
import type { WiringContext } from './types';

export type { WiringContext } from './types';

export function startWiring(ctx: WiringContext, doc: Document = document): void {
  const index = buildMapIndex(ctx);
  const restack = createRestack(index);
  const blocks = createBlockStyler(index, doc, restack.schedule);
  blocks.recomputeScale();
  restack.sendBlocksToBack();
  const markers = createMarkerStyler(index, restack.schedule);
  Object.values(index.buildings).forEach((m) => markers.refreshAppearance(m));
  restack.now();
  markers.applyZoom(ctx.map.getZoom());

  const status = createStatus(index, ctx.map, ctx.filterConfig, doc);
  watchMap(ctx.map, status, () => markers.applyZoom(ctx.map.getZoom()));
  const tables = initLiveTables(index, doc);
  const selection = initSelection(index, markers, blocks, tables, doc);
  // Sliders are built before the filter pass they trigger exists.
  let filterPass: FilterPass | undefined;
  const metrics = buildMetricControls(ctx.filterConfig, doc, () => filterPass?.schedule());
  status.updateDataset();
  const pass = initFilterPass({ ctx, index, markers, blocks, selection, tables, metrics, status }, doc);
  filterPass = pass;
  const display = initDisplay(ctx, markers, blocks, restack, pass.apply, doc);
  initCsvExport(index, ctx.map, ctx.buildingData, doc);

  doc.getElementById('filter-reset')?.addEventListener('click', () => {
    pass.resetFilters();
    display.reset();
    selection.clearAll();
    pass.apply();
    display.updateLegend();
  });

  metrics.updateAllLabels();
  display.updateLegend();
  pass.apply();
}
```

- [ ] **Step 1: Write the failing test** (Review Focus 4)

```ts
// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { startWiring, type WiringContext } from './index';

describe('startWiring', () => {
  it('throws once, instead of retrying, when the blocks layer is missing', () => {
    const ctx = { layers: { blocks: {} } } as unknown as WiringContext;
    expect(() => startWiring(ctx)).toThrow('Blocks layer not ready');
  });
});
```

Run: `npx vitest run src/wiring/index.test.ts` — FAIL (module not found).

- [ ] **Step 2:** Create `display.ts` and `filter-pass.ts` by moving the functions above, and `index.ts` as shown. Delete `wiring.js` and `wiring.d.ts`.

- [ ] **Step 3: Repoint imports**

- `bootstrap.ts`: `import { startWiring } from './wiring.js';` → `import { startWiring } from './wiring';`
- `test-harness.ts`: `import { startWiring } from '../wiring.js';` → `import { startWiring } from './index';` and delete the `window.dispatchEvent(new Event('load'));` line and its comment. Update the thrown message to drop the retry advice: `'wiring did not finish starting up'`.
- `tables.ts` doc comment: "wiring.js reads these rows" → "wiring/ reads these rows"; "(wiring.js cacheRowCells)" → "(wiring/tables-live.ts cacheRowCells)"; "before wiring.js starts" → "before startWiring()".

- [ ] **Step 4: Retire the source-grep tests**

In `page-layout.test.ts`, delete `const wiring = readFileSync(new URL('./wiring.js', …))` and the three tests that read it (`keeps "Not on record" rows at the bottom…`, `does not sort when an explainer icon…`, `is wired for both views`). The characterization suite now checks the same behaviour by running it (sort with pinned rows, explainer click, owner and network selection). Update the remaining test name "…with the totals cells wiring.js fills" → "…with the totals cells wiring fills".

- [ ] **Step 5: Verify**

Run: `npm run typecheck && npm test`
Expected: all pass, including `index.test.ts` and the unchanged characterization suite.

Run: `wc -l src/wiring/*.ts | sort -n | tail -5`
Expected: no module over ~350 lines (`filter-pass.ts` is the largest until Stage 2).

Run: `grep -rn "wiring\.js" src` — expected: no output.

- [ ] **Step 6: Checkpoint** — suggested message: `Finish splitting wiring into typed modules and drop the start-up retry loop`

---

### Task 9: Stage 1 manual checkpoint

- [ ] **Step 1:** `npm run dev`, open the printed URL with the full data, and click through:
  1. Toggle Blocks off and on, Buildings off and on: markers stay above blocks; highlighted markers above others.
  2. Housing type and Rental issues toggles: rings appear/disappear; single-type buildings' stroke colour follows the toggle.
  3. Drag the Units and Land value sliders: smooth, labels update live, histograms reshape.
  4. Hover and select a landlord in the Landlords tab (both views): its markers highlight; deselecting clears.
  5. Narrow the window below the mobile breakpoint: both drawers open/close; resize the side panes by their gutters.
  6. Open a `?hood=west+end` link: map frames West End and filters to it.
  7. Export CSV: opens in a spreadsheet with the expected rows.
- [ ] **Step 2:** Report results to the user. Stage 1 is complete only when they confirm.

---

## Stage 2 — typed state and pure filter logic

### Task 10: `filterFields` in `tables.ts`

**Files:**
- Modify: `frontend/src/tables.ts`
- Test: `frontend/src/tables.filter-fields.test.ts`

**Interfaces:**
- Produces:

```ts
export interface FilterFields {
  bid: string;
  /** lowercased, trimmed local_area */
  area: string;
  chinatown: boolean;
  village: boolean;
  owner: string;
  network: string;
  manager: string;
  housingTypes: string[];
  nIssues: number | null;
  hasOwner: boolean;
  /** Keyed by a metric summary's attr: 'units', 'year-built', 'value-land', 'value-bldg', 'value-ratio'. */
  metrics: Record<string, number | null>;
}
export function filterFields(r: BuildingRecord): FilterFields;
```

- [ ] **Step 1: Write the failing test** (Review Focus 3)

```ts
// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { buildingRow, filterFields } from './tables';
import type { BuildingRecord } from './types';

function renderedRow(r: BuildingRecord): HTMLTableRowElement {
  const t = document.createElement('template');
  t.innerHTML = `<table><tbody>${buildingRow(r)}</tbody></table>`;
  const row = t.content.querySelector('tr');
  if (!row) throw new Error('no row');
  return row;
}

const attrOf = (v: number | null) => (v === null ? '' : String(v));

describe('filterFields', () => {
  it('agrees with every data-* attribute the building row renders', () => {
    const r: BuildingRecord = {
      b_id: 7, local_area: ' West End ', owner_key: 'smith & sons', owner_name: 'Smith & Sons',
      network_key: 'nw<1>', network_name: 'N', managed_by: 'Tribe Management',
      housing_type: 'co-op, sro', n_issues: 2.7, units: 12.9, year_built: 1965,
      value_land: 1234567.5, value_bldg: null, bldg_land_ratio: 0.12345,
      in_chinatown: true, in_village_plan: false,
    };
    const f = filterFields(r);
    const row = renderedRow(r);
    const a = (name: string) => row.getAttribute(`data-${name}`);
    expect(a('bid')).toBe(f.bid);
    expect(a('area')?.toLowerCase().trim()).toBe(f.area);
    expect(a('owner')).toBe(f.owner);
    expect(a('network')).toBe(f.network);
    expect(a('manager')).toBe(f.manager);
    expect(a('chinatown')).toBe(f.chinatown ? '1' : '');
    expect(a('village')).toBe(f.village ? '1' : '');
    expect(a('has-owner')).toBe(f.hasOwner ? '1' : '');
    expect(a('n-issues')).toBe(attrOf(f.nIssues));
    expect((a('housing-type') ?? '').split(',').map((t) => t.trim()).filter(Boolean)).toEqual(f.housingTypes);
    for (const attr of ['units', 'year-built', 'value-land', 'value-bldg', 'value-ratio']) {
      expect(a(attr)).toBe(attrOf(f.metrics[attr]));
    }
    expect(f).toMatchObject({ owner: 'smith & sons', nIssues: 2, housingTypes: ['co-op', 'sro'] });
    expect(f.metrics).toMatchObject({ units: 12, 'year-built': 1965, 'value-bldg': null });
  });

  it('treats a bare record as missing everything', () => {
    const f = filterFields({ b_id: 3 });
    expect(f).toMatchObject({ area: '', owner: '', hasOwner: false, nIssues: null, housingTypes: [] });
    expect(renderedRow({ b_id: 3 }).getAttribute('data-units')).toBe('');
  });
});
```

- [ ] **Step 2:** Run `npx vitest run src/tables.filter-fields.test.ts` — FAIL (`filterFields` not exported).

- [ ] **Step 3: Implement**, and render the row's filter attributes from it so the two cannot drift:

```ts
const truncOrNull = (v: unknown): number | null => {
  const n = num(v);
  return n === null ? null : Math.trunc(n);
};
const roundOrNull = (v: unknown, digits = 0): number | null => {
  const n = num(v);
  return n === null ? null : roundHalfEven(n, digits);
};
const attr = (v: number | null): string => (v === null ? '' : String(v));

/** What the filters read about a building. The row's data-* attributes are rendered from this. */
export function filterFields(r: BuildingRecord): FilterFields {
  return {
    bid: String(Math.trunc(Number(r.b_id))),
    area: text(r.local_area).toLowerCase().trim(),
    chinatown: r.in_chinatown === true,
    village: r.in_village_plan === true,
    owner: text(r.owner_key),
    network: text(r.network_key),
    manager: managerKey(r.managed_by),
    housingTypes: text(r.housing_type).split(',').map((t) => t.trim()).filter((t) => t !== ''),
    nIssues: truncOrNull(r.n_issues),
    hasOwner: !notOnRecord(r.owner_key),
    metrics: {
      units: truncOrNull(r.units),
      'year-built': truncOrNull(r.year_built),
      'value-land': roundOrNull(r.value_land),
      'value-bldg': roundOrNull(r.value_bldg),
      'value-ratio': roundOrNull(r.bldg_land_ratio, 3),
    },
  };
}
```

In `buildingRow`, start with `const f = filterFields(r);` and derive `bid`, `units` (`attr(f.metrics.units)`), `year` (`attr(f.metrics['year-built'])`), `nIssues` (`attr(f.nIssues)`), `valLand`, `valBldg`, `ratioVal`, `onRecord` (`f.hasOwner`), `chinatown`, `village`, and the `data-owner`/`data-network`/`data-manager` values from `f`. Remove the locals they replace. `data-area`, `data-housing-type` and the visible cells keep their display text.

- [ ] **Step 4:** `npx vitest run src/tables.filter-fields.test.ts` — PASS; `npm run typecheck && npm test` — all pass (the existing `tables.test.ts` proves the HTML is unchanged).

- [ ] **Step 5: Checkpoint** — suggested message: `Derive building rows' filter attributes from one filterFields()`

---

### Task 11: Pure `filter.ts`

**Files:**
- Create: `frontend/src/wiring/filter.ts`, and the `FilterState` type in `frontend/src/wiring/filter-state.ts` (type only in this task; functions arrive in Task 12)
- Test: `frontend/src/wiring/filter.test.ts`

**Interfaces:**
- Consumes: `FilterFields` (Task 10), `selectionMatches`/`PickOption` (`landlord-picker.ts`).
- Produces:

```ts
// filter-state.ts (this task: types only)
export interface Threshold { min: number | null; max: number | null }
export interface FilterState {
  /** lowercased area keys, incl. 'chinatown' / 'village-plan'; [] = every area */
  hoods: string[];
  housing: string[];
  landlords: PickOption[];
  onlyIssues: boolean;
  onlyOwned: boolean;
  onlyUnits: boolean;
  /** Missing key or null bound = unbounded. */
  thresholds: Record<string, Threshold>;
}

// filter.ts
export interface MetricSpec { key: string; attr: string; bins: { start: number; end: number }[] }
export interface FilterResult { visible: Set<string>; binCounts: Record<string, number[]> }
export interface BlockFields { id: string; area: string; chinatown: boolean; village: boolean; buildingIds: string[] }
export function areaMatches(hoods: string[], area: string, chinatown: boolean, village: boolean): boolean;
export function filterBuildings(fields: FilterFields[], state: FilterState, metrics: MetricSpec[]): FilterResult;
/** Ids of blocks to hide. */
export function blockVisibility(blocks: BlockFields[], visible: Set<string>, hoods: string[], showEmpty: boolean): Set<string>;
```

- [ ] **Step 1: Write the failing tests** (includes Review Focus 2)

```ts
import { describe, expect, it } from 'vitest';
import type { PickOption } from '../landlord-picker';
import type { FilterFields } from '../tables';
import { blockVisibility, filterBuildings, type MetricSpec } from './filter';
import type { FilterState } from './filter-state';

const none: FilterState = { hoods: [], housing: [], landlords: [], onlyIssues: false, onlyOwned: false, onlyUnits: false, thresholds: {} };
const f = (bid: string, o: Partial<FilterFields> = {}): FilterFields => ({
  bid, area: 'west end', chinatown: false, village: false, owner: '', network: '', manager: '',
  housingTypes: [], nIssues: null, hasOwner: false, metrics: { units: 10 }, ...o,
});
const unitsSpec: MetricSpec = { key: 'units', attr: 'units', bins: [{ start: 0, end: 10 }, { start: 10, end: 20 }] };
const ids = (s: Set<string>) => [...s].sort();

describe('filterBuildings', () => {
  it('shows everything when nothing is set', () => {
    expect(ids(filterBuildings([f('1'), f('2')], none, []).visible)).toEqual(['1', '2']);
  });

  it('matches an area, or a special-area flag, when areas are ticked', () => {
    const fields = [f('1'), f('2', { area: 'downtown', chinatown: true }), f('3', { area: 'downtown' })];
    expect(ids(filterBuildings(fields, { ...none, hoods: ['west end'] }, []).visible)).toEqual(['1']);
    expect(ids(filterBuildings(fields, { ...none, hoods: ['chinatown'] }, []).visible)).toEqual(['2']);
    const village = [f('4', { area: 'kits', village: true })];
    expect(ids(filterBuildings(village, { ...none, hoods: ['village-plan'] }, []).visible)).toEqual(['4']);
  });

  it('matches landlord tiles by owner, network or manager key', () => {
    const tile = (kind: PickOption['kind'], key: string): PickOption => ({ kind, key, label: key, buildings: 1, detail: '' });
    const fields = [f('1', { owner: 'a' }), f('2', { network: 'n' }), f('3', { manager: 'm' }), f('4')];
    const state = { ...none, landlords: [tile('owner', 'a'), tile('network', 'n'), tile('manager', 'm')] };
    expect(ids(filterBuildings(fields, state, []).visible)).toEqual(['1', '2', '3']);
  });

  it('applies the only-* toggles and housing types', () => {
    const fields = [
      f('1', { nIssues: 2, hasOwner: true, housingTypes: ['co-op', 'sro'] }),
      f('2', { nIssues: 0, metrics: { units: null } }),
    ];
    expect(ids(filterBuildings(fields, { ...none, onlyIssues: true }, []).visible)).toEqual(['1']);
    expect(ids(filterBuildings(fields, { ...none, onlyOwned: true }, []).visible)).toEqual(['1']);
    expect(ids(filterBuildings(fields, { ...none, onlyUnits: true }, []).visible)).toEqual(['1']);
    expect(ids(filterBuildings(fields, { ...none, housing: ['sro'] }, []).visible)).toEqual(['1']);
  });

  it('lets a building with no value pass a threshold', () => {
    const fields = [f('1', { metrics: { units: 5 } }), f('2', { metrics: { units: 15 } }), f('3', { metrics: { units: null } })];
    const state = { ...none, thresholds: { units: { min: 10, max: null } } };
    expect(ids(filterBuildings(fields, state, [unitsSpec]).visible)).toEqual(['2', '3']);
  });

  it("counts each metric's bins without its own threshold, with the last bin inclusive", () => {
    const year: MetricSpec = { key: 'year', attr: 'year-built', bins: [{ start: 1900, end: 1950 }, { start: 1950, end: 2000 }] };
    const fields = [
      f('1', { metrics: { units: 5, 'year-built': 1920 } }),
      f('2', { metrics: { units: 15, 'year-built': 2000 } }), // 2000 is the last bin's end: counted
      f('3', { metrics: { units: 20, 'year-built': 1960 } }), // 20 is the last units bin's end: counted
    ];
    const state = { ...none, thresholds: { units: { min: 10, max: null } } };
    const r = filterBuildings(fields, state, [unitsSpec, year]);
    expect(r.binCounts.units).toEqual([1, 2]); // own threshold ignored: 5 | 15, 20
    expect(r.binCounts.year).toEqual([0, 2]); // only 2 and 3 pass the units threshold
  });
});

describe('blockVisibility', () => {
  const b = (id: string, o: Partial<{ area: string; chinatown: boolean; village: boolean; buildingIds: string[] }> = {}) =>
    ({ id, area: 'west end', chinatown: false, village: false, buildingIds: ['1'], ...o });

  it('hides a block whose buildings are all filtered out', () => {
    expect(ids(blockVisibility([b('A'), b('B', { buildingIds: ['2'] })], new Set(['1']), [], false))).toEqual(['B']);
  });

  it('shows an empty block only when asked, and only in a ticked area', () => {
    const empty = b('E', { buildingIds: [] });
    expect(ids(blockVisibility([empty], new Set(), [], false))).toEqual(['E']);
    expect(ids(blockVisibility([empty], new Set(), [], true))).toEqual([]);
    expect(ids(blockVisibility([empty], new Set(), ['downtown'], true))).toEqual(['E']);
  });

  it("matches the block's own area, not its buildings'", () => {
    const strathcona = b('S', { area: 'strathcona', buildingIds: ['10'] }); // building 10 is Downtown
    expect(ids(blockVisibility([strathcona], new Set(['10']), ['downtown'], false))).toEqual(['S']);
  });

  it('hides a block with no area while an area filter is on', () => {
    expect(ids(blockVisibility([b('X', { area: '' })], new Set(['1']), ['west end'], false))).toEqual(['X']);
  });
});
```

- [ ] **Step 2:** Run `npx vitest run src/wiring/filter.test.ts` — FAIL (module not found).

- [ ] **Step 3: Implement.** Create `filter-state.ts` with only the two interfaces above (plus `import type { PickOption } from '../landlord-picker';`). Create `filter.ts`:

```ts
/**
 * The filter pass as pure functions: which buildings and blocks pass the
 * current FilterState, and the live histogram counts. filter-pass.ts applies
 * the result to the map and tables.
 */
import { selectionMatches } from '../landlord-picker';
import type { FilterFields } from '../tables';
import type { FilterState } from './filter-state';

export interface MetricSpec { key: string; attr: string; bins: { start: number; end: number }[] }
export interface FilterResult { visible: Set<string>; binCounts: Record<string, number[]> }
export interface BlockFields { id: string; area: string; chinatown: boolean; village: boolean; buildingIds: string[] }

/**
 * No area ticked means every area. Chinatown and the Villages Plan areas are
 * flags a building carries alongside its own local_area, so a row matches if
 * its area is ticked OR it is flagged for a ticked special area.
 */
export function areaMatches(hoods: string[], area: string, chinatown: boolean, village: boolean): boolean {
  if (hoods.length === 0) return true;
  if (hoods.includes(area)) return true;
  if (chinatown && hoods.includes('chinatown')) return true;
  if (village && hoods.includes('village-plan')) return true;
  return false;
}

/** Every filter except the per-metric thresholds. */
function baseMatches(f: FilterFields, s: FilterState): boolean {
  if (!areaMatches(s.hoods, f.area, f.chinatown, f.village)) return false;
  if (s.landlords.length > 0 && !selectionMatches(s.landlords, f)) return false;
  if (s.onlyIssues && !(f.nIssues !== null && f.nIssues > 0)) return false;
  if (s.housing.length > 0 && !s.housing.some((t) => f.housingTypes.includes(t))) return false;
  // Otherwise the Units slider lets buildings with no count through (see below).
  if (s.onlyUnits && f.metrics.units == null) return false;
  if (s.onlyOwned && !f.hasOwner) return false;
  return true;
}

export function filterBuildings(fields: FilterFields[], state: FilterState, metrics: MetricSpec[]): FilterResult {
  const visible = new Set<string>();
  const binCounts: Record<string, number[]> = {};
  for (const m of metrics) binCounts[m.key] = m.bins.map(() => 0);

  for (const f of fields) {
    if (!baseMatches(f, state)) continue;
    // A building with no value for a metric (e.g. an SRO record with no unit
    // count) passes that metric's threshold rather than failing a NaN test.
    const values = metrics.map((m) => f.metrics[m.attr] ?? null);
    const pass = metrics.map((m, i) => {
      const v = values[i];
      const t = state.thresholds[m.key];
      if (v === null || !t) return true;
      return !((t.min !== null && v < t.min) || (t.max !== null && v > t.max));
    });
    if (pass.every(Boolean)) visible.add(f.bid);

    // Live histograms: each metric's bars count buildings passing every OTHER
    // filter but not its own threshold — "how many more if I loosen just this
    // slider". Bin edges stay fixed; the last bin includes its end.
    metrics.forEach((m, i) => {
      const v = values[i];
      if (v === null) return;
      if (!pass.every((p, j) => j === i || p)) return;
      const bins = m.bins;
      for (let b = 0; b < bins.length; b += 1) {
        const isLast = b === bins.length - 1;
        if (v >= bins[b].start && (isLast ? v <= bins[b].end : v < bins[b].end)) {
          binCounts[m.key][b] += 1;
          break;
        }
      }
    });
  }
  return { visible, binCounts };
}

/**
 * A block's area match always uses the block's own local_area, never its
 * member buildings': the block/building spatial join has a known bug where a
 * few blocks claim buildings from other, sometimes distant, neighbourhoods.
 * A non-empty block shows if any of its buildings is visible; an empty block
 * only when "Include empty blocks" is on.
 */
export function blockVisibility(blocks: BlockFields[], visible: Set<string>, hoods: string[], showEmpty: boolean): Set<string> {
  const hidden = new Set<string>();
  for (const b of blocks) {
    const hoodMatch = areaMatches(hoods, b.area, b.chinatown, b.village);
    const hide = b.buildingIds.length === 0
      ? !showEmpty || !hoodMatch
      : !b.buildingIds.some((id) => visible.has(id)) || !hoodMatch;
    if (hide) hidden.add(b.id);
  }
  return hidden;
}
```

- [ ] **Step 4:** `npx vitest run src/wiring/filter.test.ts` — PASS; `npm run typecheck && npm test` — all pass.

- [ ] **Step 5: Checkpoint** — suggested message: `Add a pure filterBuildings/blockVisibility over typed filter state`

---

### Task 12: `filter-state.ts` functions, landlord `picked`/`set`, URL codec

**Files:**
- Modify: `frontend/src/wiring/filter-state.ts`, `frontend/src/landlord-picker.ts`, `frontend/src/wiring/metric-controls.ts`
- Test: `frontend/src/wiring/filter-state.test.ts` (Node), `frontend/src/wiring/filter-state.dom.test.ts` (jsdom)

**Interfaces:**
- Consumes: `FilterState`, `Threshold` (Task 11); `MetricControls`, `MetricSection` (Task 6); `MetricSummary` (Task 6).
- Produces:

```ts
// landlord-picker.ts — LandlordFilter gains:
picked(): PickOption[];
/** Replaces the tiles; notifies listeners only if the selection changed. */
set(picked: PickOption[]): void;

// metric-controls.ts — MetricControls gains:
/** Moves both handles (null = that end of the range) and updates labels. reset(m) = setRange(m, null, null). */
setRange(metric: string, min: number | null, max: number | null): void;

// filter-state.ts
export type FilterSection = 'area' | 'ownership' | 'building' | 'value';
export interface FilterControls {
  hoodInputs: HTMLInputElement[];
  housingChips: HTMLElement[];
  onlyIssues: HTMLInputElement | null;
  onlyOwned: HTMLInputElement | null;
  onlyUnits: HTMLInputElement | null;
  landlords?: LandlordFilter;
  metrics: MetricControls;
}
export function defaultFilterState(): FilterState;
export function normalizeThreshold(summary: MetricSummary, currentMin: number, currentMax: number): Threshold;
export function clearSection(state: FilterState, section: FilterSection, metricSection: Record<string, MetricSection>): FilterState;
export function sectionCounts(state: FilterState, metricSection: Record<string, MetricSection>): Record<FilterSection, number>;
export function findFilterControls(doc: Document, landlords: LandlordFilter | undefined, metrics: MetricControls): FilterControls;
/** Reads the controls. Call metrics.updateAllLabels() first so currentMin/currentMax are fresh. */
export function readFilterState(c: FilterControls): FilterState;
export function writeFilterState(c: FilterControls, state: FilterState): void;
export function decodeFilterState(params: URLSearchParams, allHoods: string[]): Partial<FilterState>;
export function encodeFilterState(state: FilterState, params: URLSearchParams, allHoods: string[]): void;
```

- [ ] **Step 1: Write the failing Node tests**

Create `filter-state.test.ts`. Port every case from `src/hood-url.test.ts` into it, mapping `readHoodParam(p, ALL)` → `decodeFilterState(p, ALL)` (a `null` result becomes `{}`, a list `L` becomes `{ hoods: L }`) and `writeHoodParam(params, checked, ALL)` → `encodeFilterState({ ...defaultFilterState(), hoods: checked }, params, ALL)`. Then add:

```ts
import { describe, expect, it } from 'vitest';
import type { MetricSection } from './metric-controls';
import { clearSection, decodeFilterState, defaultFilterState, encodeFilterState, normalizeThreshold, sectionCounts } from './filter-state';

const sections: Record<string, MetricSection> = { units: 'building', value_land: 'value' };

describe('normalizeThreshold', () => {
  it('reads a handle within half a step of its end as no bound', () => {
    const s = { min: 0, max: 100, step: 1, attr: 'units' };
    expect(normalizeThreshold(s, 0.4, 99.6)).toEqual({ min: null, max: null });
    expect(normalizeThreshold(s, 20, 80)).toEqual({ min: 20, max: 80 });
  });
});

describe('clearSection', () => {
  const busy = {
    ...defaultFilterState(),
    hoods: ['west end'], housing: ['sro'], onlyIssues: true, onlyOwned: true, onlyUnits: true,
    landlords: [{ kind: 'owner' as const, key: 'a', label: 'A', buildings: 1, detail: '' }],
    thresholds: { units: { min: 5, max: null }, value_land: { min: null, max: 9 } },
  };

  it('clears only the named section', () => {
    expect(clearSection(busy, 'area', sections)).toEqual({ ...busy, hoods: [] });
    expect(clearSection(busy, 'ownership', sections)).toEqual({ ...busy, landlords: [], onlyOwned: false });
    expect(clearSection(busy, 'building', sections)).toEqual({
      ...busy, housing: [], onlyIssues: false, onlyUnits: false, thresholds: { value_land: { min: null, max: 9 } },
    });
    expect(clearSection(busy, 'value', sections)).toEqual({ ...busy, thresholds: { units: { min: 5, max: null } } });
  });

  it('counts active filters per section', () => {
    expect(sectionCounts(busy, sections)).toEqual({ area: 1, ownership: 2, building: 4, value: 1 });
    expect(sectionCounts(defaultFilterState(), sections)).toEqual({ area: 0, ownership: 0, building: 0, value: 0 });
  });
});

describe('URL codec', () => {
  it('round-trips the ticked areas', () => {
    const all = ['west end', 'downtown', 'chinatown'];
    const params = new URLSearchParams();
    encodeFilterState({ ...defaultFilterState(), hoods: ['downtown', 'chinatown'] }, params, all);
    expect(decodeFilterState(params, all)).toEqual({ hoods: ['downtown', 'chinatown'] });
  });
});
```

- [ ] **Step 2: Write the failing jsdom round-trip test**

Create `filter-state.dom.test.ts`:

```ts
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
```

- [ ] **Step 3:** Run `npx vitest run src/wiring/filter-state` — FAIL (functions not exported).

- [ ] **Step 4: Implement**

`landlord-picker.ts`, in the returned object next to `clear()`:

```ts
    picked: () => [...picked],
    set(next) {
      const same = next.length === picked.length && next.every((o, i) => sameOption(o, picked[i]));
      picked.splice(0, picked.length, ...next);
      renderTiles();
      if (!same) changed();
    },
```
and add both members to the `LandlordFilter` interface with the doc comments above.

`metric-controls.ts`: add `setRange` (sets both sliders via `toSlider(min ?? summary.min)` / `toSlider(max ?? summary.max)`, then `updateLabels`) and make `reset(m)` call `setRange(m, null, null)`.

`filter-state.ts` (append to the Task 11 types):

```ts
import type { LandlordFilter, PickOption } from '../landlord-picker';
import type { MetricControls, MetricSection } from './metric-controls';
import type { MetricSummary } from './metric-format';

export type FilterSection = 'area' | 'ownership' | 'building' | 'value';

export interface FilterControls {
  hoodInputs: HTMLInputElement[];
  housingChips: HTMLElement[];
  onlyIssues: HTMLInputElement | null;
  onlyOwned: HTMLInputElement | null;
  onlyUnits: HTMLInputElement | null;
  landlords?: LandlordFilter;
  metrics: MetricControls;
}

export function defaultFilterState(): FilterState {
  return { hoods: [], housing: [], landlords: [], onlyIssues: false, onlyOwned: false, onlyUnits: false, thresholds: {} };
}

/** A handle within half a step of its end of the range means "no bound". */
export function normalizeThreshold(summary: MetricSummary, currentMin: number, currentMax: number): Threshold {
  const tolerance = summary.step ? summary.step * 0.5 : 0;
  return {
    min: currentMin <= summary.min + tolerance ? null : currentMin,
    max: currentMax >= summary.max - tolerance ? null : currentMax,
  };
}

function withoutSection(thresholds: Record<string, Threshold>, section: MetricSection, metricSection: Record<string, MetricSection>) {
  return Object.fromEntries(Object.entries(thresholds).filter(([k]) => metricSection[k] !== section));
}

export function clearSection(state: FilterState, section: FilterSection, metricSection: Record<string, MetricSection>): FilterState {
  switch (section) {
    case 'area': return { ...state, hoods: [] };
    case 'ownership': return { ...state, landlords: [], onlyOwned: false };
    case 'building':
      return { ...state, housing: [], onlyIssues: false, onlyUnits: false, thresholds: withoutSection(state.thresholds, 'building', metricSection) };
    case 'value': return { ...state, thresholds: withoutSection(state.thresholds, 'value', metricSection) };
  }
}

/** How many filters each Filter by section has on, shown beside its heading. */
export function sectionCounts(state: FilterState, metricSection: Record<string, MetricSection>): Record<FilterSection, number> {
  const active: Record<MetricSection, number> = { building: 0, value: 0 };
  for (const [k, t] of Object.entries(state.thresholds)) {
    const section = metricSection[k];
    if (section && (t.min !== null || t.max !== null)) active[section] += 1;
  }
  return {
    area: state.hoods.length,
    ownership: state.landlords.length + (state.onlyOwned ? 1 : 0),
    building: state.housing.length + (state.onlyIssues ? 1 : 0) + (state.onlyUnits ? 1 : 0) + active.building,
    value: active.value,
  };
}

const areaKey = (v: string): string => (v || '').toLowerCase().trim();

export function findFilterControls(doc: Document, landlords: LandlordFilter | undefined, metrics: MetricControls): FilterControls {
  const checkbox = (id: string) => doc.getElementById(id) as HTMLInputElement | null;
  return {
    hoodInputs: Array.from(doc.querySelectorAll<HTMLInputElement>('.filter-neighbourhood-option')),
    housingChips: Array.from(doc.querySelectorAll<HTMLElement>('.housing-chip')),
    onlyIssues: checkbox('filter-only-issues'),
    onlyOwned: checkbox('filter-only-owned'),
    onlyUnits: checkbox('filter-only-units'),
    landlords,
    metrics,
  };
}

export function readFilterState(c: FilterControls): FilterState {
  const thresholds: Record<string, Threshold> = {};
  for (const key of c.metrics.keys) {
    const ctrl = c.metrics.controls[key];
    thresholds[key] = normalizeThreshold(ctrl.summary, ctrl.currentMin, ctrl.currentMax);
  }
  return {
    hoods: c.hoodInputs.filter((i) => i.checked).map((i) => areaKey(i.value)),
    housing: c.housingChips
      .filter((chip) => chip.getAttribute('aria-pressed') === 'true')
      .map((chip) => chip.getAttribute('data-housing') ?? ''),
    landlords: c.landlords ? c.landlords.picked() : [],
    onlyIssues: !!c.onlyIssues?.checked,
    onlyOwned: !!c.onlyOwned?.checked,
    onlyUnits: !!c.onlyUnits?.checked,
    thresholds,
  };
}

export function writeFilterState(c: FilterControls, state: FilterState): void {
  const hoods = new Set(state.hoods);
  c.hoodInputs.forEach((i) => { i.checked = hoods.has(areaKey(i.value)); });
  c.housingChips.forEach((chip) => {
    chip.setAttribute('aria-pressed', state.housing.includes(chip.getAttribute('data-housing') ?? '') ? 'true' : 'false');
  });
  if (c.onlyIssues) c.onlyIssues.checked = state.onlyIssues;
  if (c.onlyOwned) c.onlyOwned.checked = state.onlyOwned;
  if (c.onlyUnits) c.onlyUnits.checked = state.onlyUnits;
  c.landlords?.set(state.landlords);
  for (const key of c.metrics.keys) {
    const t = state.thresholds[key];
    c.metrics.setRange(key, t ? t.min : null, t ? t.max : null);
  }
}

const HOOD_PARAM = 'hood';

/**
 * Ticked areas from a shared link: one `hood` param per area. No param — or
 * every area, or only areas that no longer exist — means the default (none
 * ticked, every area shown). Older links' lone empty `hood=` reads as default.
 */
export function decodeFilterState(params: URLSearchParams, allHoods: string[]): Partial<FilterState> {
  const raw = params.getAll(HOOD_PARAM);
  if (raw.length === 0) return {};
  const wanted = new Set(raw.map(areaKey));
  const hoods = allHoods.filter((v) => wanted.has(v));
  if (hoods.length === 0) return {};
  if (hoods.length === allHoods.length) return { hoods: [] };
  return { hoods };
}

export function encodeFilterState(state: FilterState, params: URLSearchParams, allHoods: string[]): void {
  params.delete(HOOD_PARAM);
  if (state.hoods.length === allHoods.length) return;
  for (const v of state.hoods) params.append(HOOD_PARAM, v);
}
```

Check each ported `hood-url.test.ts` expectation against `decodeFilterState`'s mapping; in particular the old "every area ticked → `[]`" case becomes `{ hoods: [] }`.

- [ ] **Step 5:** `npx vitest run src/wiring/filter-state` — PASS; `npm run typecheck && npm test` — all pass.

- [ ] **Step 6: Checkpoint** — suggested message: `Add typed filter state with read/write, section helpers and URL codec`

---

### Task 13: Rewire `filter-pass.ts` onto the pure filter; move `?hood=` onto `FilterState`

**Files:**
- Modify: `frontend/src/wiring/filter-pass.ts`, `frontend/src/wiring/index.ts`, `frontend/src/wiring/types.ts`, `frontend/src/bootstrap.ts`, `frontend/src/wiring/test-harness.ts`, `frontend/src/wiring/wiring.characterization.test.ts` (append only)
- Delete: `frontend/src/hood-url.ts`, `frontend/src/hood-url.test.ts`

**Interfaces:**
- Consumes: Tasks 10–12.
- Produces: `WiringContext` gains
  ```ts
  /** Filter state restored from the URL, applied before the first pass. */
  initialFilter?: Partial<FilterState>;
  /** Called after every filter pass (bootstrap mirrors it into the URL). */
  onStateChange?: (state: FilterState) => void;
  ```
  and `FilterPass` becomes `{ apply(): void; schedule(): void; clearSection(section: FilterSection): void; resetFilters(): void; controls: FilterControls }`; `FilterPassDeps` gains `fields: FilterFields[]`.

Spec refinement: `onStateChange` is wired to `history.replaceState` in `bootstrap.ts`, not `index.ts`, so wiring never touches `window.location` and stays testable.

- [ ] **Step 1: Write the failing characterization tests**

Append to `wiring.characterization.test.ts` (and add `restoreHoods?: string[]` support to the harness as described in Step 3):

```ts
describe('filter state', () => {
  it('reports the state after every pass', () => {
    const h = startHarness();
    h.setChecked(hood('downtown'), true);
    expect(h.lastState()?.hoods).toEqual(['downtown']);
    h.click('#filter-clear-area');
    expect(h.lastState()?.hoods).toEqual([]); // no setTimeout ordering needed any more
  });

  it('applies a restored state before the first pass', () => {
    const h = startHarness({ initialFilter: { hoods: ['west end'] } });
    expect(h.visible()).toEqual(['1', '2', '3']);
    expect(document.querySelector<HTMLInputElement>(hood('west end'))?.checked).toBe(true);
  });
});
```

Run: `npx vitest run src/wiring` — the two new tests FAIL; every earlier test still PASSES.

- [ ] **Step 2: Rewrite `apply()` in `filter-pass.ts`**

```ts
  const controls = findFilterControls(doc, ctx.landlordFilter, metrics);
  const showEmptyChk = doc.getElementById('viz-show-empty-blocks') as HTMLInputElement | null;
  const metricSpecs: MetricSpec[] = metrics.keys.map((key) => ({
    key, attr: metrics.controls[key].summary.attr, bins: metrics.controls[key].summary.bins ?? [],
  }));
  const metricSection = Object.fromEntries(metrics.keys.map((k) => [k, metrics.controls[k].section]));
  // Block areas come from the block's own row (never its buildings): see blockVisibility().
  const blockFields: BlockFields[] = Object.keys(index.blocks).map((id) => {
    const row = tables.blockRowById[id];
    return {
      id,
      area: row ? (row.getAttribute('data-area') || '').toLowerCase().trim() : '',
      chinatown: row ? row.getAttribute('data-chinatown') === '1' : false,
      village: row ? row.getAttribute('data-village') === '1' : false,
      buildingIds: index.blockBuildings[id] || [],
    };
  });

  function apply(): void {
    metrics.updateAllLabels();
    const state = readFilterState(controls);
    const { visible, binCounts } = filterBuildings(fields, state, metricSpecs);

    tables.buildingRows.forEach((row) => {
      const bid = row.getAttribute('data-bid') ?? '';
      const marker = index.buildings[bid];
      const matches = visible.has(bid);
      row.classList.toggle('hidden', !matches);
      const checkbox = row.__checkbox;
      if (!matches && checkbox && checkbox.checked) {
        const current = marker ? marker._selectionRefs || 0 : 0;
        checkbox.checked = false;
        if (marker && current > 0) markers.adjustSelection(marker, -current);
      }
      const wasFiltered = marker ? marker._isFiltered : null;
      markers.setVisible(marker, matches);
      // refreshAppearance() re-applies the highlight via another setStyle —
      // only worth it when this pass actually flipped the marker.
      if (marker && wasFiltered !== marker._isFiltered) markers.refreshAppearance(marker);
    });

    metrics.keys.forEach((k) => metrics.setBarCounts(k, binCounts[k]));

    const hiddenBlocks = blockVisibility(blockFields, visible, state.hoods, showEmptyChk ? showEmptyChk.checked : false);
    blockFields.forEach(({ id }) => {
      const hide = hiddenBlocks.has(id);
      const row = tables.blockRowById[id];
      if (row) {
        row.classList.toggle('hidden', hide);
        const checkbox = row.__checkbox;
        if (hide && checkbox && checkbox.checked) {
          checkbox.checked = false;
          const layer = index.blocks[id];
          if (layer) layer._selectionRefs = 0;
          selection.blockMarkers(id, false);
        }
      }
      blocks.setFiltered(id, hide);
    });
    // Re-stretch the block colour scale to the blocks visible now.
    blocks.recomputeScale();

    hideEmptyGroups(tables.ownerRows, 'data-owner', index.owners, selection.owner, false);
    hideEmptyGroups(tables.networkRows, 'data-network', index.networks, selection.network, false);
    hideEmptyGroups(tables.neighbourhoodRows, 'data-area', index.hoods, selection.hood, true);
    tables.refreshAfterFilter();

    status.updateDataset();
    status.updateMapView();
    tables.updateSummaryBar();
    tables.updateGroupTableSummaries();
    renderSectionCounts(sectionCounts(state, metricSection));
    ctx.onFilter?.(visible);
    ctx.onStateChange?.(state);
  }
```

`renderSectionCounts(counts)` is the DOM half of the old `updateSectionCounts` (count badge text/hidden, clear button hidden). Section Clear becomes `clearSection(sec) { writeFilterState(controls, clearSectionState(readFilterState(controls), sec, metricSection)); apply(); }` (import `clearSection as clearSectionState`), and its click listeners call it. `resetFilters()` becomes `if (showEmptyChk) showEmptyChk.checked = false; writeFilterState(controls, defaultFilterState());`. Delete the old inline predicate, threshold, histogram and `areaSelectionMatches` code and the old `updateSectionCounts`.

- [ ] **Step 3: Wire state in and out**

- `types.ts`: add `initialFilter` and `onStateChange` to `WiringContext` (import `FilterState` as a type).
- `index.ts`: `const fields = Object.values(ctx.buildingData.records).map(filterFields);` passed in `FilterPassDeps`; just before the final `pass.apply()`: `if (ctx.initialFilter) writeFilterState(pass.controls, { ...readFilterState(pass.controls), ...ctx.initialFilter });`
- `test-harness.ts`: `startHarness(opts: { initialFilter?: Partial<FilterState> } = {})` passes `initialFilter: opts.initialFilter` and `onStateChange: (s) => { seen.state = s; }` (add `state: FilterState | null` to `seen`), and `Harness` gains `lastState(): FilterState | null`.
- `bootstrap.ts`: remove `initHoodUrlSync` and its import. After `renderLegend(...)`:

  ```ts
  const hoodValues = Array.from(document.querySelectorAll<HTMLInputElement>('.filter-neighbourhood-option')).map((i) => i.value);
  const restored = decodeFilterState(new URLSearchParams(window.location.search), hoodValues);
  // A ?hood= link that narrows the neighbourhoods opens framed on them.
  const selected = selectionBounds(restored.hoods ?? [], hoodValues, areaBounds(artifacts.boundaries, artifacts.chinatown, artifacts.villages));
  ```
  replacing the old `hoodInputs`-based `selectionBounds` call, and pass to `startWiring`:

  ```ts
    initialFilter: restored,
    onStateChange: (state) => {
      const url = new URL(window.location.href);
      encodeFilterState(state, url.searchParams, hoodValues);
      // Only when it changed: this runs on every slider frame, and Safari
      // throws after 100 replaceState calls in 30 seconds.
      if (url.href !== window.location.href) window.history.replaceState(window.history.state, '', url);
    },
  ```
- Delete `hood-url.ts` and `hood-url.test.ts` (their cases now live in `filter-state.test.ts`). `display-options.ts`'s deferred Reset resync is unrelated — leave it.

- [ ] **Step 4: Verify**

Run: `npx vitest run src/wiring` — all PASS, including every Stage 1 scenario unchanged.
Run: `npm run typecheck && npm test` — all pass.
Run: `grep -rn "hood-url\|getAttribute('data-n-issues')\|areaSelectionMatches" src` — expected: no output.
Run: `wc -l src/wiring/filter-pass.ts` — expected: roughly 150–200 lines.

- [ ] **Step 5: Checkpoint** — suggested message: `Run the filter pass through typed state and move ?hood= onto it`

---

### Task 14: Stage 2 manual checkpoint

- [ ] **Step 1:** `npm run dev` and repeat Task 9's click-through, plus:
  1. Tick two neighbourhoods: the URL gains two `hood=` params; untick both: they disappear. Use Clear (Area) and Reset: the URL follows immediately.
  2. Drag a slider for a few seconds: the URL does not change and nothing is logged (no replaceState spam).
  3. Open `?hood=downtown&hood=chinatown`: map frames both, both boxes ticked, rows filtered.
  4. Pick a landlord tile, then Clear (Ownership): tile gone, filter lifted, count badge hidden.
- [ ] **Step 2:** Report results to the user. The refactor is complete when they confirm.
