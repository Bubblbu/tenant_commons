// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { startWiring, type WiringContext } from './index';

describe('startWiring', () => {
  it('throws once, instead of retrying, when the blocks layer is missing', () => {
    const ctx = { layers: { blocks: {} } } as unknown as WiringContext;
    expect(() => startWiring(ctx)).toThrow('Blocks layer not ready');
  });
});
