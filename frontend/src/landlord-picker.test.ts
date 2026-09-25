import { describe, expect, it } from 'vitest';
import { buildOptions, selectionMatches, suggest, type PickOption } from './landlord-picker';
import type { BuildingRecord } from './types';

let nextId = 1;
const rec = (fields: Record<string, unknown>): BuildingRecord => ({ b_id: nextId++, ...fields });

const records = [
  rec({ owner_key: 'acme', owner_name: 'Acme Holdings', network_key: 'kim', network_name: 'Kim network', managed_by: 'Tribe' }),
  rec({ owner_key: 'acme', owner_name: 'ACME HOLDINGS', network_key: 'kim', network_name: 'Kim network' }),
  rec({ owner_key: 'acme', owner_name: 'Acme Holdings', network_key: 'kim', network_name: 'Kim network' }),
  rec({ owner_key: '0733603', owner_name: '0733603 BC Ltd', network_key: 'kim', network_name: 'Kim network', managed_by: 'tribe ' }),
  rec({ owner_key: 'solo', owner_name: 'Solo Rentals', network_key: 'solo', network_name: 'Solo Rentals' }),
  rec({ owner_key: 'unknown', owner_name: '(Unknown)', network_key: 'unknown', managed_by: 'Tribe' }),
];

const find = (opts: PickOption[], kind: string, key: string) => opts.find((o) => o.kind === kind && o.key === key);

describe('buildOptions', () => {
  const opts = buildOptions(records);

  it('lists each landlord once, under its commonest spelling, with its building count', () => {
    expect(find(opts, 'owner', 'acme')).toMatchObject({ label: 'Acme Holdings', buildings: 3 });
  });

  it('never offers "not on record" as a landlord or group', () => {
    expect(opts.some((o) => o.key === 'unknown')).toBe(false);
  });

  it('offers a group that joins several landlords, counting them', () => {
    expect(find(opts, 'network', 'kim')).toMatchObject({ label: 'Kim network', buildings: 4, detail: '2 landlords' });
  });

  it('leaves out a group that is just its one landlord under the same name', () => {
    expect(find(opts, 'network', 'solo')).toBeUndefined();
  });

  it('merges manager spellings by lowercased name, including buildings with no landlord on record', () => {
    expect(find(opts, 'manager', 'tribe')).toMatchObject({ label: 'Tribe', buildings: 3 });
  });
});

describe('suggest', () => {
  const opts = buildOptions(records);

  it('matches every typed term, case-insensitively', () => {
    expect(suggest(opts, 'acme HOLD', []).map((o) => o.key)).toEqual(['acme']);
    expect(suggest(opts, 'acme rentals', [])).toEqual([]);
  });

  it('ranks names that start with the query first', () => {
    const extra = [...opts, { kind: 'owner' as const, key: 'big', label: 'Big Kim Co', buildings: 99, detail: '' }];
    expect(suggest(extra, 'kim', []).map((o) => o.key)).toEqual(['kim', 'big']);
  });

  it('drops what is already picked', () => {
    const picked = [find(opts, 'owner', 'acme')!];
    expect(suggest(opts, 'acme', picked)).toEqual([]);
  });

  it('suggests the largest first when nothing is typed', () => {
    expect(suggest(opts, '', [], 2).map((o) => o.key)).toEqual(['kim', 'acme']);
  });
});

describe('selectionMatches', () => {
  const row = { owner: 'acme', network: 'kim', manager: '' };
  const opt = (kind: PickOption['kind'], key: string): PickOption => ({ kind, key, label: key, buildings: 1, detail: '' });

  it('passes everything when nothing is picked', () => {
    expect(selectionMatches([], row)).toBe(true);
  });

  it('matches a building by any picked tile, each tile checking its own kind', () => {
    expect(selectionMatches([opt('owner', 'solo'), opt('network', 'kim')], row)).toBe(true);
    expect(selectionMatches([opt('manager', 'acme')], row)).toBe(false);
  });

  it('does not match a building with no manager against an empty key', () => {
    expect(selectionMatches([opt('manager', '')], row)).toBe(false);
  });
});
