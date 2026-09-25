import { describe, expect, it } from 'vitest';
import { computeCoverage, coverageHtml } from './coverage';
import type { BuildingRecord } from './types';

const rec = (b_id: number, extra: Record<string, unknown>): BuildingRecord => ({ b_id, source: 'building', ...extra });

describe('computeCoverage', () => {
  const records = [
    rec(1, { units: 100, owner_key: 'a', owner_source: 'registry', network_source: 'claims' }),
    rec(2, { units: 50, owner_key: 'b', owner_source: 'licence', network_source: 'licence' }),
    rec(3, { units: 30, owner_key: 'unknown', owner_source: null }),
    rec(4, { units: null, owner_key: null }),
    rec(5, { units: 20, owner_key: 'c', owner_source: 'sro_list', source: 'overlay_sro' }),
  ];

  it('counts building rows only, treating "unknown" as no landlord', () => {
    expect(computeCoverage(records)).toEqual({
      buildings: 4,
      units: 180,
      withOwner: 2,
      withOwnerUnits: 150,
      bySource: { registry: 1, licence: 1 },
      grouped: 1,
    });
  });

  it('renders a collapsed card with per-source, missing and unit counts', () => {
    const html = coverageHtml(computeCoverage(records));
    expect(html).toMatch(/^<details class="coverage">/);
    expect(html).not.toContain('<details class="coverage" open');
    expect(html).toContain('<span class="coverage-headline">50% of 4 bldgs</span>');
    expect(html).toContain('class="coverage-seg seg-registry" style="width:25.00%"');
    expect(html).toContain('Land title registry</span><span class="coverage-n">1</span>');
    expect(html).not.toContain('SRO inventory');
    expect(html).toContain('Landlord missing</span><span class="coverage-n">2</span><span class="coverage-pct">50%</span>');
    expect(html).toContain('<dd>83% <span class="coverage-pct">· 30 missing</span></dd>');
  });

  it('says so when no buildings pass the filters', () => {
    expect(coverageHtml(computeCoverage([]))).toContain('no buildings match');
  });
});
