import { describe, expect, it } from 'vitest';
import { EXPLAINERS, initTipDismiss, ownerRowProvenance, provenanceIcon, tipPlacement } from './provenance';

describe('ownerRowProvenance', () => {
  it('names a single source plainly', () => {
    expect(ownerRowProvenance(['registry', 'registry'], 2026)).toBe('BC Land Owner Transparency Registry');
    expect(ownerRowProvenance(['licence'], 2026)).toBe('City of Vancouver business licence, 2026');
  });

  it('lists both sources with building counts when an owner mixes them', () => {
    expect(ownerRowProvenance(['registry', 'licence', 'registry'], 2026)).toBe(
      'BC Land Owner Transparency Registry (2 buildings); City of Vancouver business licence, 2026 (1 building)',
    );
  });

  it('has nothing to say for owners with no known source', () => {
    expect(ownerRowProvenance([null, null], 2026)).toBe('');
  });
});

describe('EXPLAINERS', () => {
  it('explains both ownership layers', () => {
    expect(EXPLAINERS.network).toMatch(/real owner/);
    expect(EXPLAINERS.network).toMatch(/business-licence name/);
    expect(EXPLAINERS.owner).toMatch(/Land Owner Transparency Registry/);
  });
});

describe('tipPlacement', () => {
  it('starts the tooltip at the icon when there is room', () => {
    expect(tipPlacement(100, 80, 0, 446)).toEqual({ left: 20, width: 240 });
  });

  it('pulls the tooltip back inside the right edge', () => {
    expect(tipPlacement(300, 250, 0, 400)).toEqual({ left: 148 - 250, width: 240 });
  });

  it('keeps the tooltip off the left edge', () => {
    expect(tipPlacement(-30, -40, 0, 400)).toEqual({ left: 12 + 40, width: 240 });
  });

  it('narrows the tooltip to fit a small area', () => {
    expect(tipPlacement(50, 40, 0, 200)).toEqual({ left: 12 - 40, width: 176 });
  });
});

describe('initTipDismiss', () => {
  const setup = () => {
    const doc = new EventTarget();
    const icon = Object.assign(new EventTarget(), {
      blurred: false,
      classList: { contains: (c: string) => c === 'prov' },
      blur() { this.blurred = true; },
    });
    initTipDismiss(doc as unknown as Document);
    const leave = (pointerType: string) => {
      const e = Object.assign(new Event('pointerout', { bubbles: true }), { pointerType });
      Object.defineProperty(e, 'target', { value: icon });
      doc.dispatchEvent(e);
    };
    return { icon, leave };
  };

  it('closes a clicked tooltip once the mouse leaves its icon', () => {
    const { icon, leave } = setup();
    leave('mouse');
    expect(icon.blurred).toBe(true);
  });

  it('leaves a tapped tooltip open on touch screens', () => {
    const { icon, leave } = setup();
    leave('touch');
    expect(icon.blurred).toBe(false);
  });
});

describe('provenanceIcon', () => {
  it('escapes its text into the tooltip and label', () => {
    const html = provenanceIcon('A "quoted" <b>');
    expect(html).toContain('data-tip="A &quot;quoted&quot; &lt;b&gt;"');
    expect(html).toContain('aria-label="Source: A &quot;quoted&quot; &lt;b&gt;"');
    expect(html).not.toContain('<b>');
  });
});
