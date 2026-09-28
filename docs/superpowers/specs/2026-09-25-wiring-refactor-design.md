# Wiring refactor: modules, typed state, pure filter logic

Date: 2026-09-25
Status: design approved, plan not yet written

## Problem

`frontend/src/wiring.js` is ~2,200 lines of untyped JavaScript inside one
`startWiring()` closure. It holds all of the map's interactive behaviour:
filtering, selection and hover, marker/block styling, canvas restacking,
sidebar table sorting and live recounts, metric sliders and histograms, layer
toggles, the legend, status counts and CSV export.

Its state has no single home:

- Filter state is read back out of the DOM on every pass (`checkbox.checked`,
  chip `aria-pressed`, row `.hidden`).
- `applyFilters()` (~430 lines) reads building values from table rows'
  `data-*` attributes, not from the records they were rendered from.
- Selection and highlight state lives in ad-hoc fields on Leaflet objects
  (`marker._isFiltered`, `_selectionRefs`, `_highlighted`, `_baseColor`, …).
- Six lookup indexes plus the block colour scale are published as `window.*`
  globals (76 references).
- Declaration order matters: one temporal-dead-zone bug and one `var`
  hoisting workaround are documented in comments.

Every other module in `frontend/src/` is small, typed and tested; wiring has
no behavioural tests. For people and for coding agents alike, a change to
wiring means reading most of the file and verifying by clicking through the
map.

## Goals

1. Split wiring into focused TypeScript modules (target ≤ ~300 lines each),
   with explicit dependencies and no `window.*` globals.
2. Make the filter pass pure and unit-testable in Node: a typed
   `FilterState` in, visible buildings and histogram counts out.
3. Put behavioural tests around wiring before changing it, and keep them
   passing throughout.
4. Collect every map-drawing colour and stroke weight into one theme module.
5. Move the existing `?hood=` URL sync onto `FilterState`, as the pattern
   future linkable filters will follow.

## Non-goals

- React or any other framework.
- Behaviour changes, beyond the two listed under Decisions.
- New URL parameters (landlords, sliders, layer toggles) — a follow-up
  feature once this lands.
- CSS custom properties / theming of `index.html`'s inline styles.
- A central store for selection, hover, layer toggles or UI state; the
  Leaflet-facing code stays imperative.
- Changes to the popup, table rendering (beyond `filterFields`), or the
  Python pipeline.

## Decisions (from the design conversation)

| Decision | Answer |
|---|---|
| Depth | Modules + typed `FilterState` + pure filter logic ("option 2"), not a split alone and not a full store |
| Staging | Two stages: Stage 1 split with logic unchanged; Stage 2 pure filter. Each ends at a checkpoint and is useful alone |
| Test DOM | Add `jsdom` as a dev dependency for Stage 1 characterization tests |
| Theming | `map-theme.ts` holds map-drawing colours from wiring and the five layer files; page CSS is out of scope |
| URL | Stage 2 moves `?hood=` onto `FilterState`; same URL format and behaviour |
| Behaviour change 1 | Remove the `wireUp()` retry loop (Folium-era); a startup failure throws once into `bootstrap.ts`'s existing `showLoadError` banner |
| Behaviour change 2 | None other. Performance guards and known data-quirk handling are preserved exactly |
| Execution | Designed so each plan task fits one short session on a smaller model |

## Precondition

The working tree must be clean before Stage 1 starts. At the time of writing
there are uncommitted changes to `wiring.js`, `index.html`, `bootstrap.ts`,
`landlord-picker.ts`, `display-options.ts` and others; they land first, and
the refactor starts from that commit. The plan's first step checks
`git status` and stops if anything under `frontend/` is modified.

## Design

### Module layout

Everything moves into `frontend/src/wiring/`. `wiring.js` and `wiring.d.ts`
are deleted at the end of Stage 1. `bootstrap.ts` keeps calling
`startWiring(ctx)` with the same `WiringContext`; its import path changes to
`./wiring`.

| Module | Responsibility | Stage |
|---|---|---|
| `index.ts` | `startWiring(ctx)`: build indexes, construct modules, attach listeners in a fixed order, run the first filter pass | 1 |
| `indexes.ts` | `MapIndex` — buildings, blocks, block→buildings, owners, networks, hoods — built from `ctx` (today's `applyMarkerMetadata()` and block scan). Replaces all `window.*` globals | 1 |
| `marker-style.ts` | Typed `BuildingMarker` fields; zoom scale; effective stroke; rings; highlight; visibility; selection ref-counts; restack scheduling | 1 |
| `block-style.ts` | Block colour scale (visible-blocks min/max); filtered and highlight styles; legend scale text | 1 |
| `selection.ts` | Row checkbox selection and row hover → marker/block highlight, for all five tables | 1 |
| `tables-live.ts` | Header sort (with `pinLast`); cached row cells; group-row live recounts with stale-tab deferral; footer totals; buildings summary bar | 1 |
| `metric-format.ts` | Pure: `niceLogTicks`, `formatWithSummary`, `formatTickValue`, and `sliderScale(summary)` returning `{ toSlider, fromSlider, useLog }` | 1 |
| `metric-controls.ts` | Histogram + dual-slider DOM; label updates; reset; bar heights/titles from counts | 1 |
| `display.ts` | Show-on-map toggles; boundary layers; legend visibility; housing-type/issue rings toggle; pane resize; mobile panels; Reset button's display part | 1 |
| `status-export.ts` | Dataset and in-view status cells; visible-buildings CSV export; pure `escapeCSV` | 1 |
| `map-theme.ts` | Named map-drawing tokens (see below) | 1 |
| `filter-pass.ts` | `applyFilters()` / `scheduleApplyFilters()`: in Stage 1 the current logic moved as-is; in Stage 2 read state → pure filter → apply results | 1 → 2 |
| `filter-state.ts` | `FilterState`, `readFilterState`, `writeFilterState`, `defaultFilterState`, URL codec | 2 |
| `filter.ts` | Pure `filterBuildings` and `blockVisibility` | 2 |

Modules receive what they need as arguments (the `MapIndex`, the map, DOM
roots, other modules' functions) rather than reaching into shared closure
variables. Where two modules need each other (e.g. marker visibility and
ring sync), the dependency goes one way and is passed in explicitly.

### Typed marker fields

Today's ad-hoc properties on Leaflet objects become typed interfaces in
`marker-style.ts` and `block-style.ts`:

```ts
interface BuildingMarker extends L.CircleMarker {
  _baseColor: string; _baseOpacity: number; _baseRadius: number;
  _strokeColor: string; _strokeWeight: number;
  _primaryHousingType: string; _housingType: string;
  _extraRings: { housingType: string; marker: L.CircleMarker }[] | null;
  _units: number; _yearBuilt: number | null;
  _isFiltered: boolean; _selectionRefs: number; _highlighted: boolean;
}
```

Moving these into a side `WeakMap` or plain objects is out of scope; typing
them is enough to make misuse a compile error.

### `map-theme.ts`

One exported object of named tokens, replacing hex literals in wiring,
`blocks.ts`, `markers.ts`, `neighbourhoods.ts`, `villages.ts` and
`chinatown.ts`:

```ts
export const MAP_THEME = {
  highlight: { color: '#ff1744', markerWeight: 2, blockWeight: 4 },
  marker: { stroke: '#ffffff', strokeWeight: 0.6, fallbackFill: '#9e9e9e' },
  block: { stroke: '#b8b8b8', scale: [/* six greens */], unscaledFill: '#f0f0f0', … },
  boundary: { neighbourhood: {…}, villages: {…}, chinatown: {…} },
  …
} as const;
```

Values are copied exactly; tests referencing literal colours switch to the
tokens. A later move to CSS custom properties can populate this object from
`getComputedStyle` at startup without renaming anything.

### Stage 2 types

```ts
interface FilterState {
  hoods: string[];               // lowercased area keys incl. 'chinatown' / 'village-plan'; [] = all
  housing: string[];             // pressed housing chips
  landlords: PickOption[];       // picked landlord-picker tiles
  onlyIssues: boolean;
  onlyOwned: boolean;
  onlyUnits: boolean;
  thresholds: Record<string, { min: number | null; max: number | null }>;  // null = unbounded
}

interface FilterFields {         // one per building
  bid: string; area: string; chinatown: boolean; village: boolean;
  owner: string; network: string; manager: string;
  housingTypes: string[]; nIssues: number | null; hasOwner: boolean;
  metrics: Record<string, number | null>;   // keyed by the metric summary's attr
}
```

`tables.ts` gains `filterFields(record): FilterFields`. The building row's
`data-*` attributes are rendered from it, and `filter.ts` consumes it, so the
two cannot drift. `FilterFields` for all buildings are computed once at
startup.

`LandlordFilter` gains `picked(): PickOption[]` and
`set(picked: PickOption[]): void`; matching uses the existing pure
`selectionMatches(picked, row)`.

Threshold normalisation (a handle within half a step of the range end means
"no bound") happens in `readFilterState`, matching today's tolerance logic.

### Stage 2 filter pass

```
control event ─► readFilterState(controls) ─► filterBuildings(fields, state, metricSummaries)
                                                  │  → { visible: Set<bid>, binCounts }
                                                  ▼
                               filter-pass.ts applies results:
                                 markers (visibility; drop selections on hidden)
                                 building rows (.hidden; uncheck)
                                 blockVisibility(blocks, visible, state, showEmpty) → block rows + layers
                                 owner/network/hood rows hidden; stale-tab recount
                                 histogram bars; section counts; status; footers
                                 ctx.onFilter(visible)
                                 onStateChange(state) → URL
```

Pure-function rules carried over exactly from today:

- No area selected means every area. A row matches a selected area if its
  own area is selected, or it is flagged Chinatown / Villages Plan and that
  special area is selected.
- A building with no value for a metric passes that metric's threshold.
- Histogram counts per metric include buildings passing every *other* active
  filter, but not that metric's own threshold. The last bin is inclusive of
  its end.
- A block's area match uses the block's own `local_area`, never its member
  buildings' (the known spatial-join bug). A non-empty block shows only if
  one of its buildings is visible; an empty block shows only if "show empty
  blocks" is on.

Performance guards carried over exactly: once-per-frame coalescing of
filter passes, restacks and map-status updates; skip-if-unchanged on marker,
block and group-row writes; group rows recounted only for the visible tab,
others marked stale and recounted on activation.

### URL sync on `FilterState`

- `encodeFilterState(state, params)` / `decodeFilterState(params, allHoods)`:
  pure. In this refactor they cover `hood` only, with today's exact rules
  (one param per ticked area; none or all ticked → no param; unknown values
  dropped; legacy empty `hood=` reads as default).
- `writeFilterState(controls, state)` sets controls from a state. Used for
  URL restore at startup, section Clear, and Reset (`defaultFilterState`).
- `filter-pass.ts` calls `onStateChange(state)` after every pass;
  `index.ts` wires it to `history.replaceState`. This removes
  `hood-url.ts`'s `setTimeout` ordering workaround for Clear/Reset.
- The initial map framing on a `?hood=` link (`bootstrap.ts` +
  `initial-view.ts`) keeps working; it reads the decoded state instead of
  checkbox values.

### Error handling

The retry loop and `window.load` wait are removed. `bootstrap.ts` already
builds every layer and renders every table before calling `startWiring`, so
missing layers are a real bug. Missing optional DOM elements keep today's
null-tolerant behaviour (a missing toggle means its feature is skipped).

## Testing

### Stage 1 — characterization (jsdom)

`frontend/src/wiring/wiring.characterization.test.ts`, written against the
current `wiring.js` *before* any move, then kept passing unchanged through
the split (only its import path changes).

Fixture: ~12 buildings across 3 areas (one flagged Chinatown), 2 owners in
1 network, one building with a manager, 4 blocks (one empty), a mix of
housing types and issue counts, some buildings missing units or year built.
Tables are rendered with the real `tables.ts`; the map and markers are fakes
that record `setStyle`/`setRadius`/`bringToFront` calls and answer
`getBounds`/`hasLayer`/`getLatLng`.

Scenarios:

1. Area filter hides non-matching building rows and markers.
2. Chinatown selection matches a building in another area flagged Chinatown.
3. Landlord tile filter (owner, network, manager keys).
4. Issues-only, owned-only and units-only toggles.
5. Housing chip filter, including a building with two types.
6. Slider threshold hides out-of-range buildings; a building with no value passes.
7. Histogram counts exclude the metric's own threshold.
8. Group rows (owner/network/hood) hide when all buildings are filtered; stale tab recounts on activation.
9. Owner selection highlights its markers; filtering them away clears the selection.
10. Row hover highlights and unhighlights without clobbering selection.
11. Sort by header, with pinned rows staying last.
12. Section Clear and Reset restore defaults.
13. CSV export of visible buildings: columns and rows.
14. Block visibility: empty block, block own-area rule.

### Stage 2 — unit (Node)

- `filter.test.ts`: every rule listed under "Stage 2 filter pass", with
  direct inputs.
- `filter-state.test.ts`: `readFilterState`/`writeFilterState` round-trip;
  threshold tolerance; URL codec (existing `hood-url.test.ts` cases moved
  here).
- `tables.test.ts`: `filterFields` matches the rendered `data-*` values.
- The Stage 1 characterization suite passes unchanged.

### Always

`npm run typecheck` and `npm test` pass at the end of every task.

### Manual checkpoint (end of each stage)

Click through in `npm run dev`: marker restack order after toggling
blocks/buildings; housing-type rings on/off; slider drag smoothness at full
data; landlord hover and selection; mobile drawers; pane resize; a `?hood=`
link opens framed and filtered; CSV export opens in a spreadsheet.

## Touch points

- New: `frontend/src/wiring/*` (modules and tests above).
- Deleted: `frontend/src/wiring.js`, `frontend/src/wiring.d.ts`; most of
  `frontend/src/hood-url.ts` (Stage 2).
- Changed: `bootstrap.ts` (import path; Stage 2 URL restore via state),
  `tables.ts` (`filterFields`), `landlord-picker.ts` (`picked`/`set`),
  `blocks.ts`, `markers.ts`, `neighbourhoods.ts`, `villages.ts`,
  `chinatown.ts` (theme tokens), their tests where they assert literal
  colours, `package.json` (`jsdom` dev dependency, used per test file via `// @vitest-environment jsdom`; the global test environment stays `node`).

## Risks

- **Visual regressions tests can't see** (canvas stacking, ring visibility,
  slider feel) — covered by the manual checkpoint.
- **Records-vs-attributes divergence** in Stage 2 — prevented by the shared
  `filterFields` and the unchanged characterization suite.
- **Initialisation order** — `index.ts` constructs modules in dependency
  order explicitly; no function relies on hoisting.
- **Leaflet in jsdom** — tests use fake markers and map, not real Leaflet
  rendering; real rendering is only checked manually.
