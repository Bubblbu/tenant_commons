import { describe, expect, it } from 'vitest';
import { initViewToggle } from './view-toggle';

class FakeClassList {
  private names = new Set<string>();
  add(name: string) { this.names.add(name); }
  contains(name: string) { return this.names.has(name); }
  toggle(name: string, on: boolean) {
    if (on) this.names.add(name);
    else this.names.delete(name);
    return on;
  }
}

class FakeButton extends EventTarget {
  classList = new FakeClassList();
  attrs: Record<string, string> = {};
  setAttribute(name: string, value: string) { this.attrs[name] = value; }
}

function setup() {
  const networks = { button: new FakeButton(), panel: { hidden: false } };
  const owners = { button: new FakeButton(), panel: { hidden: false } };
  networks.button.classList.add('active');
  initViewToggle([networks, owners] as unknown as Parameters<typeof initViewToggle>[0]);
  return { networks, owners };
}

describe('initViewToggle', () => {
  it('shows the initially active view and hides the others', () => {
    const { networks, owners } = setup();
    expect(networks.panel.hidden).toBe(false);
    expect(owners.panel.hidden).toBe(true);
    expect(networks.button.attrs['aria-pressed']).toBe('true');
    expect(owners.button.attrs['aria-pressed']).toBe('false');
  });

  it('switches views on click', () => {
    const { networks, owners } = setup();
    owners.button.dispatchEvent(new Event('click'));
    expect(owners.panel.hidden).toBe(false);
    expect(networks.panel.hidden).toBe(true);
    expect(owners.button.classList.contains('active')).toBe(true);
    expect(networks.button.classList.contains('active')).toBe(false);
  });
});
