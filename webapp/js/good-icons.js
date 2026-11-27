// Original inline vector symbols, shared by the atlas and action panels.
const paths = {
  wheat: '<path d="M12 22V4m0 5C5 9 5 3 5 3s7 0 7 6Zm0 6c-7 0-7-6-7-6s7 0 7 6Zm0-3c7 0 7-6 7-6s-7 0-7 6Zm0 7c7 0 7-6 7-6s-7 0-7 6Z"/>',
  banana: '<path d="M4 4c2 10 8 14 16 8-1 8-13 12-17 2C1 10 2 7 4 4Zm0 0 2-2m12 10 3-2"/>',
  fuel: '<path d="M7 5h9v16H5V7a2 2 0 0 1 2-2Zm1 0V2h6v3M8 9h5m3 0 3 3v6c0 3 3 3 3 0v-7l-3-4"/>',
  ore: '<path d="m3 16 5-11 9-2 5 11-7 8-10-2Zm5-11 4 8 5-10M3 16l9-3 10 1m-10-1 3 9"/>',
  machine: '<path d="m9 3 6 0 1 4 4 1 2 5-3 3-1 5-6 1-3-4-4-1-3-5 3-4 4-1Z"/><circle cx="12" cy="12" r="4"/>',
  electronics: '<rect x="6" y="2" width="12" height="20" rx="2"/><path d="M9 6h6M9 9h6m-6 3h6m-6 3h6m-4 4h2"/>',
};
export function goodIcon(good, className = '') {
  return `<svg class="resource-icon ${className}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round" aria-hidden="true">${paths[good] || '<path d="m3 7 9-5 9 5v11l-9 4-9-4Zm0 0 9 5 9-5m-9 5v10"/>'}</svg>`;
}

// HUD icons (original line drawings in the same 24-unit style as the goods). uiIcon(name, className)
const ui = {
  coin: '<circle cx="12" cy="12" r="9" fill="#e9c46a" stroke="#8a6a1f"/><circle cx="12" cy="12" r="6" stroke="#8a6a1f"/><path d="M12 8v8M10 10h3.5a1.5 1.5 0 0 1 0 3H10" stroke="#8a6a1f"/>',
  market: '<path d="M3 9h18l-2-5H5Z"/><path d="M3 9c0 2 3 2 3 0 0 2 3 2 3 0 0 2 3 2 3 0 0 2 3 2 3 0 0 2 3 2 3 0"/><path d="M5 11v9h14v-9M10 20v-5h4v5"/>',
  trade: '<path d="M4 8h13l-3-3M20 16H7l3 3"/><circle cx="6" cy="16" r="1.4"/><circle cx="18" cy="8" r="1.4"/>',
  invest: '<path d="M3 20V10l5 3V10l5 3V6h4l1 14Z"/><path d="M3 20h18M17 6V3h2v3"/>',
  goals: '<path d="M5 21V3m0 1h12l-3 4 3 4H5"/>',
  log: '<path d="M7 3h10a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V3Zm0 0a2 2 0 0 0-2 2v2h2M10 8h6M10 12h6M10 16h4"/>',
  result: '<path d="M8 4h8v5a4 4 0 0 1-8 0Zm0 1H5v2a3 3 0 0 0 3 3m8-5h3v2a3 3 0 0 1-3 3m-4 3v4m-4 3h8l-1-3h-6Z"/>',
  nation: '<path d="M4 21V4m0 0h11l-2 3 2 3H4"/><path d="M14 21h6"/>',
  warn: '<path d="M12 3 2 20h20Z"/><path d="M12 10v4m0 3v.5"/>',
  mail: '<rect x="3" y="6" width="18" height="13" rx="1.5"/><path d="m3 7 9 6 9-6"/>',
  check: '<path d="m5 12 5 5 9-10"/>',
  cross: '<path d="M6 6l12 12M18 6 6 18"/>',
  pause: '<path d="M8 5v14M16 5v14"/>',
  ai: '<rect x="5" y="8" width="14" height="11" rx="2"/><path d="M12 8V4m-3 9h.01M15 13h.01M9 16h6"/>',
  listing: '<path d="M3 12 12 3h8v8l-9 9Z"/><circle cx="16" cy="8" r="1.5"/>',
  trading: '<path d="M12 4v16M5 20h14M4 8h16M7 8l-3 6a3 3 0 0 0 6 0Zm10 0-3 6a3 3 0 0 0 6 0Z"/>',
  finished: '<path d="M8 4h8v5a4 4 0 0 1-8 0Zm4 9v4m-4 3h8l-1-3h-6Z"/>',
  bell: '<path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4Zm4 3a2 2 0 0 0 4 0"/>',
  ship: '<path d="M3 15h18l-3 5H6Zm3 0V9h12v6M9 9V5h6v4"/>',
};
export function uiIcon(name, className = '') {
  return `<svg class="ui-icon ${className}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round" aria-hidden="true">${ui[name] || ui.bell}</svg>`;
}
