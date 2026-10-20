/**
 * Runs the real wiring against the real page (index.html), tables rendered by
 * tables.ts from the fixture, the real landlord picker, and fake Leaflet
 * objects that record what wiring does to them. For jsdom test files only.
 */
import { readFileSync } from 'node:fs';
import { dirname, resolve as resolvePath } from 'node:path';
import { fileURLToPath } from 'node:url';
import { vi } from 'vitest';
import { buildOptions, initLandlordPicker, type LandlordFilter } from '../landlord-picker';
import { renderLegend } from '../legend';
import { renderTables } from '../tables';
import type { FilterState } from './filter-state';
import { FIXTURE_BLOCKS, FIXTURE_BUILDING_DATA, FIXTURE_FILTER_CONFIG, FIXTURE_MARKERS } from './fixture';
import { startWiring } from './index';

export const HIGHLIGHT = '#ff1744';
// `new URL(rel, import.meta.url)` resolves against jsdom's window.location
// (http://localhost:3000/) instead of this file's `file:` base under
// `@vitest-environment jsdom`, even with Node's URL imported explicitly.
// fileURLToPath + path.resolve sidestep that relative-URL resolution.
const HERE = dirname(fileURLToPath(import.meta.url));
const INDEX_HTML = readFileSync(resolvePath(HERE, '../../index.html'), 'utf8');

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
  popupOpen = false;
  openPopup(): this { this.popupOpen = true; return this; }
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
  zoom = 14;
  view: { lat: number; lng: number; zoom: number } | null = null;
  getZoom(): number { return this.zoom; }
  setView(at: { lat: number; lng: number }, zoom: number): this {
    this.view = { lat: at.lat, lng: at.lng, zoom };
    this.zoom = zoom;
    return this;
  }
  getBounds(): { contains: () => boolean } { return { contains: () => true }; }
  invalidateSize(): this { return this; }
  private fire(event: string, payload?: unknown): void {
    (this.handlers.get(event) ?? []).forEach((fn) => (fn as (e?: unknown) => void)(payload));
  }
  /** Like Leaflet's popupopen: the event carries the popup, whose getElement() is its container. */
  firePopupOpen(el: HTMLElement): void { this.fire('popupopen', { popup: { getElement: () => el } }); }
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
  /** The blocks GeoJSON layer itself (on the map only while Show on map > Blocks is ticked). */
  blocksLayer: FakeLayer;
  paint: FakeLayer[];
  landlords: LandlordFilter;
  /** Overlay area layers by key, as bootstrap.ts hands them to wiring. */
  overlays: Record<string, FakeLayer>;
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
  /** FilterState from the most recent filter pass, or null before the first pass. */
  lastState(): FilterState | null;
}

function $<T extends Element = HTMLElement>(selector: string): T {
  const el = document.querySelector<T>(selector);
  if (!el) throw new Error(`no element matches ${selector}`);
  return el;
}

export function startHarness(opts: { initialFilter?: Partial<FilterState> } = {}): Harness {
  frames = [];
  const raf = (cb: FrameRequestCallback): number => { frames.push(cb); return frames.length; };
  vi.stubGlobal('requestAnimationFrame', raf);
  window.requestAnimationFrame = raf;

  document.body.innerHTML = new DOMParser().parseFromString(INDEX_HTML, 'text/html').body.innerHTML;
  renderLegend(FIXTURE_FILTER_CONFIG);
  renderTables(FIXTURE_BUILDING_DATA, document, null);
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
  const overlays = { chinatown: new FakeLayer(paint), deod: new FakeLayer(paint), 'village-plan': new FakeLayer(paint) };
  [blocksLayer, buildingsLayer, neighbourhoods, overlays.chinatown, overlays.deod].forEach((l) => map.addLayer(l));

  const seen: { visible: Set<string> | null; state: FilterState | null } = { visible: null, state: null };
  startWiring({
    map,
    layers: { blocks: blocksLayer, buildings: buildingsLayer, neighbourhoods, overlays },
    markersById: markers,
    ringsById: rings,
    filterConfig: FIXTURE_FILTER_CONFIG,
    markers: FIXTURE_MARKERS,
    buildingData: FIXTURE_BUILDING_DATA,
    landlordFilter: landlords,
    onFilter: (visible: Set<string>) => { seen.visible = new Set(visible); },
    initialFilter: opts.initialFilter,
    onStateChange: (s: FilterState) => { seen.state = s; },
  } as unknown as Parameters<typeof startWiring>[0]);
  flushFrames();
  if (!seen.visible || document.getElementById('summary-buildings-label')?.textContent !== 'Totals (visible)') {
    throw new Error('wiring did not finish starting up');
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
    map, markers, blocks, blocksLayer, paint, landlords, overlays,
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
    lastState: () => seen.state,
  };
}
