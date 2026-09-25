import { describe, expect, it } from 'vitest';
import { clampWidth, draggedWidth, MIN_MAP_WIDTH } from './pane-resize';

const spec = { min: 240, max: 520 };

describe('clampWidth', () => {
  it('keeps a preferred width that fits', () => {
    expect(clampWidth(300, spec, 1600, 480)).toBe(300);
  });

  it('holds the panel within its min and max', () => {
    expect(clampWidth(100, spec, 1600, 480)).toBe(240);
    expect(clampWidth(900, spec, 3000, 480)).toBe(520);
  });

  it('never squeezes the map below its minimum beside the other panel', () => {
    expect(clampWidth(500, spec, 1200, 480)).toBe(1200 - 480 - MIN_MAP_WIDTH);
  });

  it('lets the panel minimum win when the window is too narrow for both', () => {
    expect(clampWidth(500, spec, 900, 480)).toBe(240);
  });
});

describe('draggedWidth', () => {
  it('grows a left panel when the gutter moves right', () => {
    expect(draggedWidth('left', 480, 40)).toBe(520);
  });

  it('grows a right panel when the gutter moves left', () => {
    expect(draggedWidth('right', 300, -40)).toBe(340);
  });
});
