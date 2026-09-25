/**
 * Gutters between the data table, the map and the filters. Each gutter sizes
 * the panel beside it; the map takes whatever is left, never less than
 * MIN_MAP_WIDTH. Widths are set inline on each panel (the mobile layout
 * overrides them) and are remembered per viewer. Not a CSS variable on
 * <html>: changing one restyles every element on the page, ~15k table rows. Dragging applies at most
 * one width per frame; the caller's onResizeEnd (e.g. the map's
 * invalidateSize) runs once, on release.
 */

export const MIN_MAP_WIDTH = 320;
/** Arrow-key step; Shift+arrow moves four steps. */
export const KEY_STEP = 16;

export interface PaneSpec {
  /** Gutter element; the panel it sizes is on its `side`. */
  gutter: HTMLElement;
  side: 'left' | 'right';
  panel: HTMLElement;
  storageKey: string;
  min: number;
  max: number;
  defaultWidth: number;
}

/**
 * The width a panel actually gets: the preferred width within [min, max],
 * and no wider than leaves the map MIN_MAP_WIDTH beside the other panel.
 * `min` wins over the map when the window is too narrow for both.
 */
export function clampWidth(preferred: number, spec: { min: number; max: number }, viewport: number, otherPanel: number): number {
  const room = viewport - otherPanel - MIN_MAP_WIDTH;
  return Math.round(Math.max(spec.min, Math.min(preferred, spec.max, room)));
}

/** Width after dragging a gutter by dx pixels (a left panel grows rightwards, a right panel leftwards). */
export function draggedWidth(side: 'left' | 'right', startWidth: number, dx: number): number {
  return side === 'left' ? startWidth + dx : startWidth - dx;
}

function readStored(key: string): number | null {
  try {
    const v = Number(localStorage.getItem(key));
    return Number.isFinite(v) && v > 0 ? v : null;
  } catch {
    return null;
  }
}

function writeStored(key: string, width: number | null): void {
  try {
    if (width === null) localStorage.removeItem(key);
    else localStorage.setItem(key, String(Math.round(width)));
  } catch {
    // Storage unavailable: resizing still works, it just isn't remembered.
  }
}

interface Callbacks {
  /** Every applied width change (at most once per frame while dragging). */
  onResize?: () => void;
  /** Once a drag, key press, reset or window resize settles. */
  onResizeEnd?: () => void;
}

export function initPaneResize(panes: PaneSpec[], callbacks: Callbacks = {}): void {
  // What the viewer asked for; the applied width may be narrower while the window is.
  const preferred = panes.map((p) => readStored(p.storageKey) ?? p.defaultWidth);
  const applied = panes.map(() => 0);

  function apply(): void {
    // The gutters' own width comes out of the map's share too.
    const viewport = window.innerWidth - panes.reduce((sum, p) => sum + p.gutter.offsetWidth, 0);
    panes.forEach((p, i) => {
      const other = applied.reduce((sum, w, j) => (j === i ? sum : sum + w), 0);
      applied[i] = clampWidth(preferred[i], p, viewport, other);
    });
    // A second pass so the first panel sees the second one's final width.
    panes.forEach((p, i) => {
      const other = applied.reduce((sum, w, j) => (j === i ? sum : sum + w), 0);
      applied[i] = clampWidth(preferred[i], p, viewport, other);
      p.panel.style.width = `${applied[i]}px`;
      p.gutter.setAttribute('aria-valuenow', String(applied[i]));
      p.gutter.setAttribute('aria-valuemin', String(p.min));
      p.gutter.setAttribute('aria-valuemax', String(p.max));
    });
    callbacks.onResize?.();
  }

  function settle(): void {
    callbacks.onResizeEnd?.();
  }

  panes.forEach((p, i) => {
    const g = p.gutter;
    let frame = 0;

    g.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      g.setPointerCapture(e.pointerId);
      const startX = e.clientX;
      const startWidth = applied[i];
      let lastX = startX;
      document.body.classList.add('pane-resizing');

      const onMove = (m: PointerEvent) => {
        lastX = m.clientX;
        if (frame) return;
        frame = requestAnimationFrame(() => {
          frame = 0;
          preferred[i] = clampWidth(draggedWidth(p.side, startWidth, lastX - startX), p, Infinity, 0);
          apply();
        });
      };
      const onEnd = () => {
        g.removeEventListener('pointermove', onMove);
        g.removeEventListener('pointerup', onEnd);
        g.removeEventListener('pointercancel', onEnd);
        if (frame) {
          cancelAnimationFrame(frame);
          frame = 0;
          preferred[i] = clampWidth(draggedWidth(p.side, startWidth, lastX - startX), p, Infinity, 0);
          apply();
        }
        document.body.classList.remove('pane-resizing');
        // Remember what is on screen, not a drag that overshot the map's minimum.
        preferred[i] = applied[i];
        writeStored(p.storageKey, preferred[i]);
        settle();
      };
      g.addEventListener('pointermove', onMove);
      g.addEventListener('pointerup', onEnd);
      g.addEventListener('pointercancel', onEnd);
    });

    g.addEventListener('dblclick', () => {
      preferred[i] = p.defaultWidth;
      writeStored(p.storageKey, null);
      apply();
      settle();
    });

    g.addEventListener('keydown', (e) => {
      const step = e.shiftKey ? KEY_STEP * 4 : KEY_STEP;
      // Arrows move the gutter; which way the panel grows depends on its side.
      const grow = p.side === 'left' ? 1 : -1;
      let next: number;
      if (e.key === 'ArrowRight') next = applied[i] + step * grow;
      else if (e.key === 'ArrowLeft') next = applied[i] - step * grow;
      else if (e.key === 'Home') next = p.min;
      else if (e.key === 'End') next = p.max;
      else return;
      e.preventDefault();
      preferred[i] = clampWidth(next, p, Infinity, 0);
      apply();
      preferred[i] = applied[i];
      writeStored(p.storageKey, preferred[i]);
      settle();
    });
  });

  let resizeTimer = 0;
  window.addEventListener('resize', () => {
    apply();
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(settle, 150);
  });

  apply();
}
