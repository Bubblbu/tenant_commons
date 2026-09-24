/**
 * An "×" button inside a text filter that shows only while the field has text.
 * Clearing dispatches an input event so the existing filter listener re-runs.
 */
export function initClearButton(input: HTMLInputElement, button: HTMLElement): void {
  const sync = () => {
    button.hidden = input.value === '';
  };
  input.addEventListener('input', sync);
  button.addEventListener('click', () => {
    input.value = '';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.focus();
  });
  sync();
}
