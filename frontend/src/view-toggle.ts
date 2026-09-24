/** Segmented control: shows the panel of the pressed button and hides the others. */
export interface ToggleOption {
  button: HTMLElement;
  panel: HTMLElement;
}

export function initViewToggle(options: ToggleOption[]): void {
  const show = (active: ToggleOption) => {
    for (const o of options) {
      const on = o === active;
      o.panel.hidden = !on;
      o.button.classList.toggle('active', on);
      o.button.setAttribute('aria-pressed', String(on));
    }
  };
  for (const o of options) o.button.addEventListener('click', () => show(o));
  const initial = options.find((o) => o.button.classList.contains('active')) ?? options[0];
  if (initial) show(initial);
}
