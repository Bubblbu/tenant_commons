import type { FilterConfig } from '../types';
import { formatTickValue, formatWithSummary, niceLogTicks, sliderScale, type MetricSummary } from './metric-format';

export type MetricSection = 'building' | 'value' | 'portfolio';

export interface MetricControl {
  summary: MetricSummary;
  section: MetricSection;
  minSlider: HTMLInputElement;
  maxSlider: HTMLInputElement;
  minLabel: HTMLElement;
  maxLabel: HTMLElement;
  bars: HTMLElement[];
  useLog: boolean;
  toSlider(v: number): number;
  fromSlider(p: number): number;
  currentMin: number;
  currentMax: number;
}

export interface MetricControls {
  /** Metric keys in display order. */
  keys: string[];
  controls: Record<string, MetricControl>;
  updateLabels(metric: string): void;
  updateAllLabels(): void;
  reset(metric: string): void;
  /** Moves both handles (null = that end of the range) and updates labels. reset(m) = setRange(m, null, null). */
  setRange(metric: string, min: number | null, max: number | null): void;
  /** Live histogram: bar heights rescaled to the tallest count, titles updated. */
  setBarCounts(metric: string, counts: number[]): void;
}

// Under the Assessed value heading, "Land"/"Building" say enough.
const VALUE_METRIC_LABELS: Record<string, string> = { value_land: 'Land', value_bldg: 'Building' };

export function buildMetricControls(filterConfig: FilterConfig, doc: Document, onChange: () => void): MetricControls {
  const controls: Record<string, MetricControl> = {};
  let keys: string[] = [];

  function updateLabels(metric: string): void {
    const ctrl = controls[metric];
    if (!ctrl) return;
    const summary = ctrl.summary;
    const parseSlider = (slider: HTMLInputElement): number | null => {
      const raw = parseFloat(slider.value);
      if (!Number.isFinite(raw)) return null;
      const value = ctrl.fromSlider(raw);
      return Number.isFinite(value) ? value : null;
    };
    let minVal = parseSlider(ctrl.minSlider);
    let maxVal = parseSlider(ctrl.maxSlider);
    if (minVal === null) minVal = summary.min;
    if (maxVal === null) maxVal = summary.max;
    minVal = Math.max(summary.min, Math.min(summary.max, minVal));
    maxVal = Math.max(summary.min, Math.min(summary.max, maxVal));
    if (minVal > maxVal) {
      if (ctrl.useLog) {
        maxVal = minVal;
      } else {
        minVal = maxVal;
      }
    }
    if (summary.type === 'int') {
      minVal = Math.round(minVal);
      maxVal = Math.round(maxVal);
    }
    ctrl.currentMin = minVal;
    ctrl.currentMax = maxVal;
    ctrl.minLabel.textContent = formatWithSummary(summary, minVal);
    ctrl.maxLabel.textContent = formatWithSummary(summary, maxVal);
    if (ctrl.bars && ctrl.bars.length) {
      const low = Math.min(minVal, maxVal);
      const high = Math.max(minVal, maxVal);
      ctrl.bars.forEach((bar) => {
        const start = parseFloat(bar.dataset.start || '');
        const end = parseFloat(bar.dataset.end || '');
        const active = !(end < low || start > high);
        bar.classList.toggle('active', active);
      });
    }
    ctrl.minSlider.value = String(ctrl.toSlider(minVal));
    ctrl.maxSlider.value = String(ctrl.toSlider(maxVal));
  }

  function updateAllLabels(): void {
    keys.forEach(updateLabels);
  }

  // Slider positions are in slider space (log for skewed metrics), not raw values.
  function setRange(metric: string, min: number | null, max: number | null): void {
    const ctrl = controls[metric];
    if (!ctrl) return;
    ctrl.minSlider.value = String(ctrl.toSlider(min ?? ctrl.summary.min));
    ctrl.maxSlider.value = String(ctrl.toSlider(max ?? ctrl.summary.max));
    updateLabels(metric);
  }

  function reset(metric: string): void {
    setRange(metric, null, null);
  }

  function setBarCounts(metric: string, counts: number[]): void {
    const ctrl = controls[metric];
    if (!ctrl) return;
    // Rescale to the current view's own tallest bar, not the original
    // full-dataset one — otherwise every bar reads near-flat once a filter
    // has narrowed the set well below the original max.
    const maxCount = Math.max(1, counts.reduce((m, c) => (c > m ? c : m), 0));
    ctrl.bars.forEach((bar, i) => {
      const count = counts[i] || 0;
      const height = maxCount ? Math.max(2, (count / maxCount) * 100) : 2;
      bar.style.height = `${height}%`;
      const start = parseFloat(bar.dataset.start || '');
      const end = parseFloat(bar.dataset.end || '');
      const rangeLabel = `${formatWithSummary(ctrl.summary, start)} – ${formatWithSummary(ctrl.summary, end)}`;
      const countLabel = ` (${count.toLocaleString()})`;
      bar.title = ctrl.useLog ? `${rangeLabel}${countLabel} [log bin]` : `${rangeLabel}${countLabel}`;
    });
  }

  // Sliders fire 'input' many times per second while dragging; onChange
  // (filter-pass.ts's schedule()) coalesces the expensive full-row-scan
  // pass to once per animation frame — only the label text below updates
  // synchronously.
  function makeSliderHandler(metric: string, role: 'min' | 'max'): () => void {
    return () => {
      const ctrl = controls[metric];
      if (!ctrl) return;
      const minVal = ctrl.fromSlider(parseFloat(ctrl.minSlider.value));
      const maxVal = ctrl.fromSlider(parseFloat(ctrl.maxSlider.value));
      if (role === 'min') {
        if (Number.isFinite(minVal) && Number.isFinite(maxVal) && minVal > maxVal) {
          ctrl.maxSlider.value = String(ctrl.toSlider(minVal));
        }
      } else if (role === 'max') {
        if (Number.isFinite(minVal) && Number.isFinite(maxVal) && maxVal < minVal) {
          ctrl.minSlider.value = String(ctrl.toSlider(maxVal));
        }
      }
      updateLabels(metric);
      onChange();
    };
  }

  // Renders one Craigslist-style histogram + dual-handle range slider control
  // into `container` and returns its bookkeeping object for controls[metric].
  function renderMetricControl(container: HTMLElement, metric: string, summary: MetricSummary, section: MetricSection): MetricControl {
    const control = doc.createElement('div');
    control.className = 'metric-control';

    const scale = sliderScale(summary);

    const header = doc.createElement('div');
    header.className = 'metric-header';
    header.textContent = summary.label || metric;
    control.appendChild(header);

    const hist = doc.createElement('div');
    hist.className = 'metric-histogram';
    const bars: HTMLElement[] = [];
    const maxCount = summary.max_count || 1;
    const bins = summary.bins || [];
    bins.forEach((bin) => {
      const bar = doc.createElement('div');
      bar.className = 'metric-hist-bar';
      const height = maxCount ? Math.max(2, (bin.count / maxCount) * 100) : 2;
      bar.style.height = `${height}%`;
      bar.dataset.start = String(bin.start);
      bar.dataset.end = String(bin.end);
      const rangeLabel = `${formatWithSummary(summary, bin.start)} – ${formatWithSummary(summary, bin.end)}`;
      const countLabel = ` (${bin.count.toLocaleString()})`;
      bar.title = scale.useLog ? `${rangeLabel}${countLabel} [log bin]` : `${rangeLabel}${countLabel}`;
      hist.appendChild(bar);
      bars.push(bar);
    });
    control.appendChild(hist);

    // Reference ticks under the histogram: the bars themselves are equal
    // SCREEN width per bin (the correct way to draw a log-scaled histogram —
    // equal ratio steps = equal distance), but with no visible value anywhere
    // except a per-bar hover tooltip, there's no way to tell what a bar's
    // position actually means. For a log axis the tick *values* are also
    // snapped to round numbers (niceLogTicks) — an evenly-spaced-fraction
    // tick would land on whatever raw value falls out of the interpolation
    // ($9,847, say), which reads as noise; decade boundaries ($10K, $100K,
    // $1M...) read as an axis.
    if (bins.length) {
      const axis = doc.createElement('div');
      axis.className = 'metric-axis';
      let tickValues: number[];
      if (scale.useLog) {
        tickValues = niceLogTicks(summary.min_positive as number, summary.max);
      } else {
        tickValues = [];
        const tickCount = 5;
        for (let t = 0; t < tickCount; t += 1) {
          const frac = t / (tickCount - 1);
          tickValues.push(summary.min + frac * (summary.max - summary.min));
        }
      }
      tickValues.forEach((value) => {
        const frac = scale.tickFraction(value);
        const tick = doc.createElement('span');
        tick.className = 'metric-axis-tick';
        tick.style.left = `calc(7px + (100% - 14px) * ${frac})`;
        tick.textContent = formatTickValue(summary, value);
        axis.appendChild(tick);
      });
      control.appendChild(axis);
    }

    const sliders = doc.createElement('div');
    sliders.className = 'metric-sliders';
    const minSlider = doc.createElement('input') as HTMLInputElement;
    minSlider.type = 'range';
    const maxSlider = doc.createElement('input') as HTMLInputElement;
    maxSlider.type = 'range';

    const sliderStep = scale.useLog ? 0.5 : (summary.step || ((summary.max - summary.min) / 200) || 1);

    if (scale.useLog) {
      minSlider.min = '0';
      minSlider.max = '100';
      maxSlider.min = '0';
      maxSlider.max = '100';
      minSlider.value = String(scale.toSlider(summary.min));
      maxSlider.value = String(scale.toSlider(summary.max));
    } else {
      minSlider.min = String(summary.min);
      minSlider.max = String(summary.max);
      maxSlider.min = String(summary.min);
      maxSlider.max = String(summary.max);
      minSlider.value = String(summary.min);
      maxSlider.value = String(summary.max);
    }
    minSlider.step = String(sliderStep);
    maxSlider.step = String(sliderStep);

    sliders.appendChild(minSlider);
    sliders.appendChild(maxSlider);
    control.appendChild(sliders);

    const values = doc.createElement('div');
    values.className = 'metric-values';
    const minLabel = doc.createElement('span');
    const maxLabel = doc.createElement('span');
    values.appendChild(minLabel);
    values.appendChild(maxLabel);
    control.appendChild(values);

    container.appendChild(control);

    const ctrl: MetricControl = {
      summary,
      section,
      minSlider,
      maxSlider,
      minLabel,
      maxLabel,
      bars,
      useLog: scale.useLog,
      toSlider: scale.toSlider,
      fromSlider: scale.fromSlider,
      currentMin: summary.min,
      currentMax: summary.max,
    };

    minSlider.addEventListener('input', makeSliderHandler(metric, 'min'));
    maxSlider.addEventListener('input', makeSliderHandler(metric, 'max'));
    return ctrl;
  }

  const buildingMetrics = filterConfig.building_metrics as Record<string, MetricSummary> | undefined;
  const buildingContainer = doc.getElementById('filter-building-section');
  const valueContainer = doc.getElementById('filter-value-section');
  if (buildingContainer && buildingMetrics) {
    buildingContainer.innerHTML = '';
    if (valueContainer) valueContainer.innerHTML = '';
    const order = (filterConfig.building_metric_order as string[] | undefined) || Object.keys(buildingMetrics);
    order.forEach((metric) => {
      const summary = buildingMetrics[metric];
      if (!summary) return;
      const section: MetricSection = VALUE_METRIC_LABELS[metric] && valueContainer ? 'value' : 'building';
      // Under the Assessed value heading, "Land"/"Building" say enough.
      const shown = section === 'value' ? { ...summary, label: VALUE_METRIC_LABELS[metric] } : summary;
      const container = section === 'value' ? valueContainer : buildingContainer;
      if (!container) return;
      controls[metric] = renderMetricControl(container, metric, shown, section);
    });
  }

  keys = Object.keys(controls);
  keys.forEach(updateLabels);

  return { keys, controls, updateLabels, updateAllLabels, reset, setRange, setBarCounts };
}
