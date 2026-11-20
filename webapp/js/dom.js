// Rendering helpers shared by the three screens.
export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const $ = (sel, root = document) => root.querySelector(sel);

// Re-render a container without losing what the user is typing: input values are kept in
// `drafts` (by data-k key) and focus/selection is restored after the HTML is replaced.
export function render(el, html, drafts) {
  if (el._html === html) return; // nothing changed: keep the DOM (buttons stay clickable)
  el._html = html;
  const active = document.activeElement;
  const key = active && el.contains(active) ? active.dataset.k : null;
  const sel = key && 'selectionStart' in active ? [active.selectionStart, active.selectionEnd] : null;
  el.innerHTML = html;
  for (const input of el.querySelectorAll('[data-k]')) {
    const property = input.type === 'checkbox' ? 'checked' : 'value';
    if (drafts[input.dataset.k] !== undefined) input[property] = drafts[input.dataset.k];
    const remember = () => { drafts[input.dataset.k] = input[property]; };
    input.addEventListener('input', remember);
    input.addEventListener('change', remember);
  }
  if (key) {
    const again = el.querySelector(`[data-k="${CSS.escape(key)}"]`);
    if (again) {
      again.focus({ preventScroll: true });
      if (sel && again.setSelectionRange) try { again.setSelectionRange(sel[0], sel[1]); } catch (e) { /* number inputs */ }
    }
  }
}

export const num = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? Math.trunc(n) : NaN;
};

export const fmt = (x, d = 1) => (x === null || x === undefined ? '-' : Number(x).toFixed(d));
