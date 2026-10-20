/**
 * The filter pass: applies the current FilterState (wiring/filter-state.ts)
 * to markers, blocks and the sidebar tables via the pure
 * filterBuildings()/blockVisibility() (wiring/filter.ts), and drives the
 * live section counts and per-section Clear/Reset.
 */
import type { FilterFields } from '../tables';
import type { BlockStyler } from './block-style';
import { blockVisibility, filterBuildings, type BlockFields, type MetricSpec } from './filter';
import {
  clearSection as clearSectionState,
  defaultFilterState,
  findFilterControls,
  readFilterState,
  sectionCounts,
  writeFilterState,
  type FilterControls,
  type FilterSection,
} from './filter-state';
import type { MarkerStyler } from './marker-style';
import type { MetricControls } from './metric-controls';
import type { Selection } from './selection';
import type { Status } from './status-export';
import type { LiveTables } from './tables-live';
import type { CachedRow, MapIndex, WiringContext } from './types';

export interface FilterPass {
  apply(): void;
  /** Coalesced to one pass per animation frame. */
  schedule(): void;
  /** Clears one Filter by section's controls and re-applies. */
  clearSection(section: FilterSection): void;
  /** Reset's filter part: empty blocks off, areas, chips, landlords, only-* toggles, sliders. */
  resetFilters(): void;
  controls: FilterControls;
}

export interface FilterPassDeps {
  ctx: WiringContext;
  index: MapIndex;
  markers: MarkerStyler;
  blocks: BlockStyler;
  selection: Selection;
  tables: LiveTables;
  metrics: MetricControls;
  status: Status;
  fields: FilterFields[];
}

/**
 * The three owner/network/hood "hide the row if none of its markers are
 * visible" loops in apply() differ only in which index/rows/dispatch they
 * use — this is the shared body.
 */
function hideEmptyGroups(
  rows: CachedRow[],
  attr: string,
  groups: MapIndex['owners'] | MapIndex['networks'] | MapIndex['hoods'],
  deselect: (key: string, on: boolean) => void,
  lowercase: boolean,
): void {
  rows.forEach((row) => {
    const raw = row.getAttribute(attr) || '';
    const key = lowercase ? raw.toLowerCase().trim() : raw;
    const markers = groups[key] || [];
    const hasVisible = markers.some((m) => !m._isFiltered);
    row.classList.toggle('hidden', !hasVisible);
    const checkbox = row.__checkbox;
    if (!hasVisible && checkbox && checkbox.checked) {
      checkbox.checked = false;
      deselect(key, false);
    }
  });
}

export function initFilterPass(deps: FilterPassDeps, doc: Document): FilterPass {
  const { ctx, index, markers, blocks, selection, tables, metrics, status, fields } = deps;

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
      areas: row ? (row.getAttribute('data-areas') || '').split(' ').filter(Boolean) : [],
      buildingIds: index.blockBuildings[id] || [],
    };
  });

  const sectionEls = (['area', 'ownership', 'building', 'value'] as const).reduce(
    (acc, sec) => {
      acc[sec] = {
        count: doc.getElementById('filter-count-' + sec),
        clear: doc.getElementById('filter-clear-' + sec),
      };
      return acc;
    },
    {} as Record<FilterSection, { count: HTMLElement | null; clear: HTMLElement | null }>,
  );

  // How many filters each Filter by section has on, shown beside its heading.
  function renderSectionCounts(counts: Record<FilterSection, number>): void {
    (Object.keys(sectionEls) as FilterSection[]).forEach((sec) => {
      const els = sectionEls[sec];
      const n = counts[sec] || 0;
      if (els.count) {
        els.count.hidden = n === 0;
        els.count.textContent = String(n);
      }
      if (els.clear) els.clear.hidden = n === 0;
    });
  }

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
    selection.syncSelectAll();

    status.updateDataset();
    status.updateMapView();
    tables.updateSummaryBar();
    tables.updateGroupTableSummaries();
    renderSectionCounts(sectionCounts(state, metricSection));
    ctx.onFilter?.(visible);
    ctx.onStateChange?.(state);
  }

  // Sliders fire 'input' many times per second while dragging. apply() walks
  // every building/block/landlord row, so calling it synchronously per event
  // is what makes dragging a filter slider feel sluggish. Coalesce to at
  // most once per animation frame instead — the label text still updates
  // immediately, only the expensive full-row-scan pass gets throttled.
  let applyScheduled = false;
  function schedule(): void {
    if (applyScheduled) return;
    applyScheduled = true;
    window.requestAnimationFrame(() => {
      applyScheduled = false;
      apply();
    });
  }

  if (showEmptyChk) showEmptyChk.addEventListener('change', apply);
  if (controls.landlords) controls.landlords.onChange(schedule);
  if (controls.onlyIssues) controls.onlyIssues.addEventListener('change', apply);
  if (controls.onlyOwned) controls.onlyOwned.addEventListener('change', apply);
  if (controls.onlyUnits) controls.onlyUnits.addEventListener('change', apply);
  controls.hoodInputs.forEach((inp) => inp.addEventListener('change', apply));

  controls.housingChips.forEach((chip) => {
    chip.addEventListener('click', () => {
      chip.setAttribute('aria-pressed', chip.getAttribute('aria-pressed') === 'true' ? 'false' : 'true');
      apply();
    });
  });

  function clearSection(section: FilterSection): void {
    // writeFilterState(landlords.set([])) only replaces the tiles; clear()
    // also empties any typed-but-unpicked search text and closes the list.
    if (section === 'ownership') controls.landlords?.clear();
    writeFilterState(controls, clearSectionState(readFilterState(controls), section, metricSection));
    apply();
  }
  (Object.keys(sectionEls) as FilterSection[]).forEach((sec) => {
    const btn = sectionEls[sec].clear;
    if (!btn) return;
    btn.addEventListener('click', (e) => {
      // Inside <summary> (Assessed value), don't also toggle the section.
      e.preventDefault();
      clearSection(sec);
    });
  });

  function resetFilters(): void {
    if (showEmptyChk) showEmptyChk.checked = false;
    controls.landlords?.clear();
    writeFilterState(controls, defaultFilterState());
  }

  return { apply, schedule, clearSection, resetFilters, controls };
}
