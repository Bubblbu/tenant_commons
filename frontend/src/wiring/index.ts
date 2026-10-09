/**
 * Map interactivity: filters, selection and hover, table recounts, legend,
 * status and export. Everything here runs once, after bootstrap.ts has built
 * the map layers and rendered the sidebar tables.
 */
import { filterFields } from '../tables';
import { createBlockStyler } from './block-style';
import { initDisplay } from './display';
import { initFilterPass, type FilterPass } from './filter-pass';
import { readFilterState, writeFilterState } from './filter-state';
import { buildMapIndex } from './indexes';
import { createMarkerStyler, createRestack } from './marker-style';
import { buildMetricControls } from './metric-controls';
import { initSelection } from './selection';
import { createStatus, initCsvExport, watchMap } from './status-export';
import { initLiveTables } from './tables-live';
import { initLocate } from './locate';
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
  const fields = Object.values(ctx.buildingData.records).map(filterFields);
  const pass = initFilterPass({ ctx, index, markers, blocks, selection, tables, metrics, status, fields }, doc);
  filterPass = pass;
  const display = initDisplay(ctx, markers, blocks, restack, pass.apply, doc);
  initCsvExport(index, ctx.map, ctx.buildingData, doc);
  initLocate(index, ctx.map, doc);

  doc.getElementById('filter-reset')?.addEventListener('click', () => {
    pass.resetFilters();
    display.reset();
    selection.clearAll();
    pass.apply();
    display.updateLegend();
  });

  metrics.updateAllLabels();
  display.updateLegend();
  if (ctx.initialFilter) writeFilterState(pass.controls, { ...readFilterState(pass.controls), ...ctx.initialFilter });
  pass.apply();
}
