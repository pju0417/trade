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
