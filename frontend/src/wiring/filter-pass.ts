/**
 * The filter pass: Filter by controls (area, landlords, housing type,
 * only-* toggles, metric sliders), the live section counts, and applying the
 * result to markers, blocks and the sidebar tables. Stage 1 shape — Stage 2
 * splits this into a pure filterBuildings()/blockVisibility() over typed
 * FilterState, applied here.
 */
import type { BlockStyler } from './block-style';
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
  /** Reset's filter part: empty blocks off, areas, chips, landlords, only-* toggles, sliders. */
  resetFilters(): void;
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
}

/**
 * The three owner/network/hood "hide the row if none of its markers are
 * visible" loops in applyFilters() differ only in which index/rows/dispatch
 * they use — this is the shared body.
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
  const { ctx, index, markers, blocks, selection, tables, metrics, status } = deps;
  const landlordFilter = ctx.landlordFilter;

  const hoodInputs = Array.from(doc.querySelectorAll<HTMLInputElement>('.filter-neighbourhood-option'));
  const housingChips = Array.from(doc.querySelectorAll<HTMLElement>('.housing-chip'));
  const sectionCounts = (['area', 'ownership', 'building', 'value'] as const).reduce(
    (acc, sec) => {
      acc[sec] = {
        count: doc.getElementById('filter-count-' + sec),
        clear: doc.getElementById('filter-clear-' + sec),
      };
      return acc;
    },
    {} as Record<string, { count: HTMLElement | null; clear: HTMLElement | null }>,
  );
  const showEmptyBlocksChk = doc.getElementById('viz-show-empty-blocks') as HTMLInputElement | null;
  const onlyIssuesChk = doc.getElementById('filter-only-issues') as HTMLInputElement | null;
  const onlyOwnedChk = doc.getElementById('filter-only-owned') as HTMLInputElement | null;
  const onlyUnitsChk = doc.getElementById('filter-only-units') as HTMLInputElement | null;

  // Sliders fire 'input' many times per second while dragging. applyFilters()
  // walks every building/block/landlord row, so calling it synchronously per
  // event is what makes dragging a filter slider feel sluggish. Coalesce to
  // at most once per animation frame instead — the label text still updates
  // immediately, only the expensive full-row-scan pass gets throttled.
  let applyFiltersScheduled = false;
  function scheduleApplyFilters(): void {
    if (applyFiltersScheduled) return;
    applyFiltersScheduled = true;
    window.requestAnimationFrame(() => {
      applyFiltersScheduled = false;
      applyFilters();
    });
  }

  // How many filters each Filter by section has on, shown beside its heading.
  function updateSectionCounts(hoods: number, housing: number, thresholds: Record<string, { min: number | null; max: number | null; summary: { attr: string } }>): void {
    const activeMetrics = { building: 0, value: 0 };
    Object.keys(thresholds).forEach((metric) => {
      const t = thresholds[metric];
      if (t.min !== null || t.max !== null) activeMetrics[metrics.controls[metric].section] += 1;
    });
    const counts: Record<string, number> = {
      area: hoods,
      ownership: (landlordFilter ? landlordFilter.count() : 0) + (onlyOwnedChk && onlyOwnedChk.checked ? 1 : 0),
      building: housing + (onlyIssuesChk && onlyIssuesChk.checked ? 1 : 0) +
        (onlyUnitsChk && onlyUnitsChk.checked ? 1 : 0) + activeMetrics.building,
      value: activeMetrics.value,
    };
    Object.keys(sectionCounts).forEach((sec) => {
      const els = sectionCounts[sec];
      const n = counts[sec] || 0;
      if (els.count) {
        els.count.hidden = n === 0;
        els.count.textContent = String(n);
      }
      if (els.clear) els.clear.hidden = n === 0;
    });
  }

  function applyFilters(): void {
    metrics.updateAllLabels();
    const selectedHoods = hoodInputs
      .filter((inp) => inp.checked)
      .map((inp) => (inp.value || '').toLowerCase().trim());
    // No area ticked means every area.
    const restrictHoods = selectedHoods.length > 0;
    const selectedHousing = housingChips
      .filter((chip) => chip.getAttribute('aria-pressed') === 'true')
      .map((chip) => chip.getAttribute('data-housing'));
    // Chinatown/Villages Plan are two more checkboxes in the same list (see
    // legend.ts's specialAreaTagsHtml) but aren't a row's own local_area — a
    // building/block can be in a real neighbourhood *and* one of these
    // overlays at once — so a row matches the selection if its area is
    // selected OR it's flagged for a selected special area.
    function areaSelectionMatches(area: string, inChinatown: boolean, inVillage: boolean): boolean {
      if (selectedHoods.includes(area)) return true;
      if (inChinatown && selectedHoods.includes('chinatown')) return true;
      if (inVillage && selectedHoods.includes('village-plan')) return true;
      return false;
    }
    const thresholds: Record<string, { min: number | null; max: number | null; summary: import('./metric-format').MetricSummary }> = {};
    metrics.keys.forEach((metric) => {
      const ctrl = metrics.controls[metric];
      const summary = ctrl.summary;
      const minVal = ctrl.currentMin;
      const maxVal = ctrl.currentMax;
      const tolerance = summary.step ? summary.step * 0.5 : 0;
      thresholds[metric] = {
        min: (minVal <= summary.min + tolerance) ? null : minVal,
        max: (maxVal >= summary.max - tolerance) ? null : maxVal,
        summary,
      };
    });
    // Live histograms (see metric-controls.ts's renderMetricControl): each
    // metric's bars are recomputed below from the rows that pass every OTHER
    // active filter — neighbourhood, search, issues-only, and every other
    // metric's own slider — but not this metric's own threshold. That
    // answers "how many more would I get if I loosened just this slider"
    // (the usual faceted-search convention) rather than a metric's own bars
    // shrinking toward whatever range it's already dragged to. Bin edges and
    // the slider's min/max range stay fixed; only bar heights (counts) are live.
    const binCounts: Record<string, number[]> = {};
    metrics.keys.forEach((metric) => {
      binCounts[metric] = metrics.controls[metric].bars.map(() => 0);
    });

    const visibleBids = new Set<string>();
    tables.buildingRows.forEach((row) => {
      const bid = row.getAttribute('data-bid');
      const marker = index.buildings[bid ?? ''];

      // Every filter except the per-metric thresholds — shared by the final
      // `matches` below and by each metric's "exclude own filter" histogram
      // recount.
      let baseMatches = true;
      const rowArea = (row.getAttribute('data-area') || '').toLowerCase().trim();
      if (restrictHoods) {
        baseMatches = areaSelectionMatches(
          rowArea,
          row.getAttribute('data-chinatown') === '1',
          row.getAttribute('data-village') === '1',
        );
      }
      if (baseMatches && landlordFilter && landlordFilter.isActive()) {
        baseMatches = landlordFilter.matches({
          owner: row.getAttribute('data-owner') || '',
          network: row.getAttribute('data-network') || '',
          manager: row.getAttribute('data-manager') || '',
        });
      }
      if (baseMatches && onlyIssuesChk && onlyIssuesChk.checked) {
        const rawIssues = row.getAttribute('data-n-issues');
        const nIssues = rawIssues === null || rawIssues === '' ? NaN : parseFloat(rawIssues);
        baseMatches = Number.isFinite(nIssues) && nIssues > 0;
      }
      if (baseMatches && selectedHousing.length) {
        // "co-op, sro" is both.
        const types = (row.getAttribute('data-housing-type') || '').split(',').map((t) => t.trim());
        baseMatches = selectedHousing.some((t) => types.indexOf(t as string) !== -1);
      }
      if (baseMatches && onlyUnitsChk && onlyUnitsChk.checked) {
        // Otherwise the Units slider lets buildings with no count through (see below).
        baseMatches = (row.getAttribute('data-units') || '') !== '';
      }
      if (baseMatches && onlyOwnedChk && onlyOwnedChk.checked) {
        baseMatches = row.getAttribute('data-has-owner') === '1';
      }

      // Rows with no value for a metric (e.g. SRO/co-op records with no
      // building match have no units/year built) are skipped per-metric —
      // treated as passing that one threshold — rather than hidden by a NaN
      // comparison.
      let matches = baseMatches;
      const metricPass: Record<string, boolean> = {};
      const metricValue: Record<string, number> = {};
      if (baseMatches && metrics.keys.length) {
        for (let i = 0; i < metrics.keys.length; i += 1) {
          const metric = metrics.keys[i];
          const threshold = thresholds[metric];
          const attrName = 'data-' + threshold.summary.attr;
          const rawValue = row.getAttribute(attrName);
          const value = rawValue === null || rawValue === '' ? NaN : parseFloat(rawValue);
          metricValue[metric] = value;
          if (Number.isNaN(value)) {
            metricPass[metric] = true;
            continue;
          }
          const pass = !((threshold.min !== null && value < threshold.min) ||
            (threshold.max !== null && value > threshold.max));
          metricPass[metric] = pass;
          if (!pass) matches = false;
        }
      }

      if (baseMatches) {
        for (let i = 0; i < metrics.keys.length; i += 1) {
          const metric = metrics.keys[i];
          const value = metricValue[metric];
          if (value === undefined || Number.isNaN(value)) continue;
          let othersPass = true;
          for (let j = 0; j < metrics.keys.length; j += 1) {
            if (j !== i && !metricPass[metrics.keys[j]]) { othersPass = false; break; }
          }
          if (!othersPass) continue;
          const bins = thresholds[metric].summary.bins || [];
          for (let b = 0; b < bins.length; b += 1) {
            const isLast = b === bins.length - 1;
            if (value >= bins[b].start && (isLast ? value <= bins[b].end : value < bins[b].end)) {
              binCounts[metric][b] += 1;
              break;
            }
          }
        }
      }

      row.classList.toggle('hidden', !matches);
      const checkbox = row.__checkbox;
      if (!matches) {
        if (checkbox && checkbox.checked) {
          const current = marker ? (marker._selectionRefs || 0) : 0;
          checkbox.checked = false;
          if (marker && current > 0) markers.adjustSelection(marker, -current);
        }
      }

      const wasFiltered = marker ? marker._isFiltered : null;
      markers.setVisible(marker, matches);
      // refreshAppearance() re-applies the highlight state via another
      // setStyle call — only worth doing when this tick actually flipped the
      // marker's filtered state.
      if (marker && wasFiltered !== marker._isFiltered) {
        markers.refreshAppearance(marker);
      }

      if (matches) {
        visibleBids.add(String(bid));
      }
    });

    metrics.keys.forEach((k) => metrics.setBarCounts(k, binCounts[k]));

    const hideEmptyBlocks = showEmptyBlocksChk ? !showEmptyBlocksChk.checked : true;
    Object.keys(index.blocks).forEach((blockId) => {
      const ids = index.blockBuildings[blockId] || [];
      const isEmpty = ids.length === 0;
      const row = tables.blockRowById[blockId];
      // The neighbourhood filter always has to be checked against the
      // block's own local_area (data-area), never inferred solely from which
      // of its member buildings are visible: the block<->building spatial
      // join has a known data bug where a handful of blocks pick up member
      // buildings from other, sometimes distant, neighbourhoods (e.g. a
      // "Fairview" block claiming a Marpole or Strathcona building) —
      // relying on hasVisible alone let a block from one neighbourhood stay
      // on-screen just because one of its mismatched buildings belonged to
      // whichever neighbourhood *was* selected, which is what made toggling
      // one neighbourhood appear to affect blocks "across the whole city".
      const blockArea = row ? (row.getAttribute('data-area') || '').toLowerCase().trim() : '';
      let hoodMatch = true;
      if (restrictHoods) {
        hoodMatch = areaSelectionMatches(
          blockArea,
          row ? row.getAttribute('data-chinatown') === '1' : false,
          row ? row.getAttribute('data-village') === '1' : false,
        );
      }
      let shouldHide: boolean;
      if (isEmpty) {
        // Empty blocks have no buildings to derive visibility from at all.
        shouldHide = hideEmptyBlocks || !hoodMatch;
      } else {
        const hasVisible = ids.some((id) => visibleBids.has(String(id)));
        shouldHide = !hasVisible || !hoodMatch;
      }
      const layer = index.blocks[blockId];
      if (row) {
        row.classList.toggle('hidden', shouldHide);
        const checkbox = row.__checkbox;
        if (shouldHide && checkbox && checkbox.checked) {
          checkbox.checked = false;
          if (layer) layer._selectionRefs = 0;
          selection.blockMarkers(blockId, false);
        }
      }
      blocks.setFiltered(blockId, shouldHide);
    });

    // Re-stretch the block color scale to whichever blocks are visible now
    // that this pass's filtering is settled (e.g. narrowing to a single
    // selected neighbourhood re-scales hue to that neighbourhood's own
    // min/max instead of the whole dataset's).
    blocks.recomputeScale();

    // Was a per-row `document.querySelector('...:not(.hidden)')` CSS scan
    // over all building rows for every one of ~1,500 landlords —
    // O(landlords x buildings) via the selector engine, on every slider
    // tick. index.owners (built once at load) plus the marker._isFiltered
    // flag set just above give the same answer as a plain array check with
    // no DOM/CSS involved.
    hideEmptyGroups(tables.ownerRows, 'data-owner', index.owners, selection.owner, false);
    hideEmptyGroups(tables.networkRows, 'data-network', index.networks, selection.network, false);
    hideEmptyGroups(tables.neighbourhoodRows, 'data-area', index.hoods, selection.hood, true);

    tables.refreshAfterFilter();

    status.updateDataset();
    status.updateMapView();
    tables.updateSummaryBar();
    tables.updateGroupTableSummaries();
    updateSectionCounts(selectedHoods.length, selectedHousing.length, thresholds);
    if (typeof ctx.onFilter === 'function') ctx.onFilter(visibleBids);
  }

  if (showEmptyBlocksChk) showEmptyBlocksChk.addEventListener('change', applyFilters);
  if (landlordFilter) landlordFilter.onChange(scheduleApplyFilters);
  if (onlyIssuesChk) onlyIssuesChk.addEventListener('change', applyFilters);
  if (onlyOwnedChk) onlyOwnedChk.addEventListener('change', applyFilters);
  if (onlyUnitsChk) onlyUnitsChk.addEventListener('change', applyFilters);
  hoodInputs.forEach((inp) => inp.addEventListener('change', applyFilters));

  housingChips.forEach((chip) => {
    chip.addEventListener('click', () => {
      chip.setAttribute('aria-pressed', chip.getAttribute('aria-pressed') === 'true' ? 'false' : 'true');
      applyFilters();
    });
  });

  // Per-section Clear: resets that section's controls only.
  const clearSection: Record<string, () => void> = {
    area: () => {
      hoodInputs.forEach((inp) => { inp.checked = false; });
    },
    ownership: () => {
      if (landlordFilter) landlordFilter.clear();
      if (onlyOwnedChk) onlyOwnedChk.checked = false;
    },
    building: () => {
      housingChips.forEach((chip) => chip.setAttribute('aria-pressed', 'false'));
      if (onlyIssuesChk) onlyIssuesChk.checked = false;
      if (onlyUnitsChk) onlyUnitsChk.checked = false;
      metrics.keys.forEach((metric) => {
        if (metrics.controls[metric].section === 'building') metrics.reset(metric);
      });
    },
    value: () => {
      metrics.keys.forEach((metric) => {
        if (metrics.controls[metric].section === 'value') metrics.reset(metric);
      });
    },
  };
  Object.keys(sectionCounts).forEach((sec) => {
    const btn = sectionCounts[sec].clear;
    if (!btn) return;
    btn.addEventListener('click', (e) => {
      // Inside <summary> (Assessed value), don't also toggle the section.
      e.preventDefault();
      clearSection[sec]();
      applyFilters();
    });
  });

  function resetFilters(): void {
    if (showEmptyBlocksChk) showEmptyBlocksChk.checked = false;
    hoodInputs.forEach((inp) => { inp.checked = false; });
    housingChips.forEach((chip) => chip.setAttribute('aria-pressed', 'false'));
    if (landlordFilter) landlordFilter.clear();
    if (onlyIssuesChk) onlyIssuesChk.checked = false;
    if (onlyOwnedChk) onlyOwnedChk.checked = false;
    if (onlyUnitsChk) onlyUnitsChk.checked = false;
    metrics.keys.forEach(metrics.reset);
  }

  return { apply: applyFilters, schedule: scheduleApplyFilters, resetFilters };
}
