import { describe, expect, it } from 'vitest';
import { initClearButton } from './search-clear';

class FakeInput extends EventTarget {
  value = '';
  focused = false;
  focus() {
    this.focused = true;
  }
}

class FakeButton extends EventTarget {
  hidden = false;
}

function setup(initial = '') {
  const input = new FakeInput();
  input.value = initial;
  const button = new FakeButton();
  const inputEvents: string[] = [];
  input.addEventListener('input', () => inputEvents.push(input.value));
  initClearButton(input as unknown as HTMLInputElement, button as unknown as HTMLElement);
  return { input, button, inputEvents };
}

describe('initClearButton', () => {
  it('hides the button while the field is empty', () => {
    expect(setup('').button.hidden).toBe(true);
  });

  it('shows the button once text is entered', () => {
    const { input, button } = setup('');
    input.value = 'glr';
    input.dispatchEvent(new Event('input'));
    expect(button.hidden).toBe(false);
  });

  it('clears the field, re-runs the filter via an input event, refocuses, and hides itself', () => {
    const { input, button, inputEvents } = setup('glr');
    button.dispatchEvent(new Event('click'));
    expect(input.value).toBe('');
    expect(inputEvents).toEqual(['']);
    expect(input.focused).toBe(true);
    expect(button.hidden).toBe(true);
  });
});
