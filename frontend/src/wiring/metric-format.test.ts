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
