/**
 * Pure numeric helpers for the Filter by > Building/Assessed value sliders:
 * the log-scale slider<->value mapping (with a floor bin) and value/tick
 * formatting. No DOM — metric-controls.ts renders with these.
 */
export interface MetricBin {
  start: number;
  end: number;
  count: number;
}

export interface MetricSummary {
  label?: string;
  min: number;
  max: number;
  step?: number;
  bins?: MetricBin[];
  max_count?: number;
  format?: string;
  type?: string;
  decimals?: number;
  attr: string;
  min_positive?: number;
  use_log?: boolean;
}

export interface SliderScale {
  useLog: boolean;
  toSlider(value: number): number;
  fromSlider(position: number): number;
  /** Axis-tick fraction (0..1) for a value — the same transform the sliders use. */
  tickFraction(value: number): number;
}

/**
 * A log_floor (building_metrics.py) collapses everything at or below it into
 * the first bin, e.g. 0–2 units or $1–$10k. That bin is drawn as wide as any
 * other bar, so it gets the same share of the track, mapped linearly from the
 * true min to the floor; the log scale runs over the rest. Without it every
 * value under the floor shared track position 0, so a handle could never
 * select, say, 2 units or fewer.
 *
 * Returns identity transforms (and useLog: false) whenever the metric isn't
 * actually log-scaled, has no spread, or its log range collapses to a point.
 */
export function sliderScale(summary: MetricSummary): SliderScale {
  const hasSpread = summary.max > summary.min;
  const positiveMin = (typeof summary.min_positive === 'number' && summary.min_positive > 0) ? summary.min_positive : null;
  let useLog = false;
  if (summary.use_log !== undefined) {
    useLog = !!summary.use_log;
  } else {
    useLog = !!(summary.type !== 'int' && positiveMin !== null && hasSpread && (
      summary.format === 'currency' || (summary.max / positiveMin) >= 25
    ));
  }
  useLog = useLog && positiveMin !== null && hasSpread;

  const logMin = useLog ? Math.log(positiveMin as number) : 0;
  const logMax = useLog ? Math.log(Math.max(summary.max, positiveMin as number)) : 1;
  const bins = summary.bins || [];
  const hasFloorBin = useLog && bins.length > 1 && summary.min < (positiveMin as number) &&
    Math.abs(bins[0].end - (positiveMin as number)) <= (positiveMin as number) * 1e-9;
  const floorPos = hasFloorBin ? 100 / bins.length : 0;

  const active = useLog && logMax !== logMin;

  const toSlider = active
    ? (value: number): number => {
        if (!Number.isFinite(value)) return 0;
        const v = Math.max(summary.min, Math.min(Number(value), summary.max));
        if (hasFloorBin && v <= (positiveMin as number)) {
          return floorPos * (v - summary.min) / ((positiveMin as number) - summary.min);
        }
        if (v <= 0) return 0;
        const clamped = Math.max(positiveMin as number, v);
        return floorPos + ((Math.log(clamped) - logMin) / (logMax - logMin)) * (100 - floorPos);
      }
    : (value: number): number => Number(value);

  const fromSlider = active
    ? (pos: number): number => {
        const p = Math.min(100, Math.max(0, Number(pos)));
        // Position 0 always means "no lower bound": the true min, not the floor.
        if (p === 0) return summary.min;
        if (hasFloorBin && p <= floorPos) {
          return summary.min + (p / floorPos) * ((positiveMin as number) - summary.min);
        }
        const ratio = (p - floorPos) / (100 - floorPos);
        return Math.exp(logMin + ratio * (logMax - logMin));
      }
    : (pos: number): number => Number(pos);

  // Ticks are placed at their exact value's slider position (not evenly-spaced
  // fractions) so a tick and the slider always agree on what a given screen
  // position means. This intentionally does NOT reuse fromSlider(0)'s special
  // case (which reports the true min, i.e. "no lower bound") — the floor
  // bucket is drawn as one collapsed bar starting at positiveMin, so the
  // leftmost tick must label that same value, not the tail below it.
  const tickFraction = (value: number): number => (
    useLog
      ? (logMax !== logMin
          ? (Math.log(Math.max(positiveMin as number, Math.min(value, summary.max))) - logMin) / (logMax - logMin)
          : 0)
      : (value - summary.min) / ((summary.max - summary.min) || 1)
  );

  return { useLog: active, toSlider, fromSlider, tickFraction };
}

// Round tick values for a log-scaled axis: powers of ten spanning [minV,
// maxV], always anchored at minV itself (the slider/histogram floor) even
// when minV isn't an exact power of ten, so the leftmost tick always matches
// what the floor bucket actually starts at.
export function niceLogTicks(minV: number, maxV: number): number[] {
  if (!(minV > 0) || !(maxV > minV)) return [minV];
  const minExp = Math.ceil(Math.log10(minV) - 1e-9);
  const maxExp = Math.floor(Math.log10(maxV) + 1e-9);
  const ticks: number[] = [];
  for (let e = minExp; e <= maxExp; e += 1) {
    ticks.push(Math.pow(10, e));
  }
  if (!ticks.length || Math.abs(ticks[0] - minV) > minV * 1e-6) {
    ticks.unshift(minV);
  }
  const maxTicks = 6;
  if (ticks.length > maxTicks) {
    const stride = Math.ceil((ticks.length - 1) / (maxTicks - 1));
    const kept = [ticks[0]];
    for (let i = stride; i < ticks.length - 1; i += stride) {
      kept.push(ticks[i]);
    }
    kept.push(ticks[ticks.length - 1]);
    return kept;
  }
  return ticks;
}

export function formatWithSummary(summary: MetricSummary, value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '–';
  if (summary.format === 'currency') {
    return '$' + Math.round(value).toLocaleString();
  }
  if (summary.format === 'year') {
    return String(Math.round(value));
  }
  if (summary.format === 'ratio') {
    const decimals = summary.decimals ?? 2;
    return Number(value).toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  }
  if (summary.type === 'int') {
    return Math.round(value).toLocaleString();
  }
  const decimals = summary.decimals ?? 2;
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: decimals });
}

// Axis ticks specifically use compact currency notation ($10K, $1M) —
// formatWithSummary's full "$10,000,000" is right for the min/max readouts
// next to the sliders (only two numbers, plenty of room) but collides with
// its neighbours in a dense row of up to 5 axis ticks.
export function formatTickValue(summary: MetricSummary, value: number): string {
  if (summary.format === 'currency') {
    const v = Math.round(value);
    const abs = Math.abs(v);
    if (abs >= 1e6) return '$' + (v / 1e6).toFixed(v % 1e6 === 0 ? 0 : 1) + 'M';
    if (abs >= 1e3) return '$' + (v % 1e3 === 0 ? Math.round(v / 1e3) : (v / 1e3).toFixed(1)) + 'K';
    return '$' + v.toLocaleString();
  }
  return formatWithSummary(summary, value);
}
