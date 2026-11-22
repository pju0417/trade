// Display-only projection of the existing student API. Never changes economy state.
export const COUNTRIES = Object.freeze({
  Tropia: { label: '트로피아', main: 'banana', color: '#e6b94d', landscape: 'tropical' },
  Grainia: { label: '그레니아', main: 'wheat', color: '#a4bb67', landscape: 'farmland' },
  Oilia: { label: '오일리아', main: 'fuel', color: '#d99158', landscape: 'desert' },
  Mechania: { label: '메카니아', main: 'machine', color: '#83abc1', landscape: 'industrial' },
  Mineria: { label: '미네리아', main: 'ore', color: '#c39c86', landscape: 'mountain' },
  Technia: { label: '테크니아', main: 'electronics', color: '#82bca8', landscape: 'city' },
});
export const STAGES = ['증기 시대', '산업 항구', '현대 무역항', '스마트 항구'];
export const SHIPS = ['증기 화물선', '디젤 화물선', '컨테이너선'];
export const VEHICLES = ['초기 화물차', '디젤 트럭', '전기 물류차'];
export const PLANES = ['복엽기', '쌍발 프로펠러기', '제트 화물기'];
const clamp = (v, max) => Math.min(max, Math.max(1, Math.floor(Number(v) || 1)));
const heldGeneration = (s, good) => Math.max(1, ...(s.stock || []).filter(r => r.good === good && Number(r.free) > 0).map(r => clamp(r.gen, 3)));
export function projectHarborState(s = {}) {
  const country = Object.hasOwn(COUNTRIES, s.country) ? s.country : 'Tropia';
  const main = s.main || COUNTRIES[country].main;
  const stage = clamp(s.levels?.[main], 4);
  const machine = Math.max(clamp(s.machine_gen ?? s.levels?.machine, 3), heldGeneration(s, 'machine'));
  const electronics = Math.max(clamp(s.electronics_gen ?? s.levels?.electronics, 3), heldGeneration(s, 'electronics'));
  return { country, label: s.label || COUNTRIES[country].label, main, stage, machine, electronics,
    round: clamp(s.round, 9), phase: s.phase || 'listing', paused: Boolean(s.room?.paused),
    cargo: Math.min(18, (s.stock || []).reduce((n, r) => n + Math.max(0, Number(r.free) || 0), 0)),
    tradeCount: (s.transactions_this_round || []).length,
    shortage: (s.settlement?.rows || []).some(r => r.short > 0),
    exportValue: Number(s.progress?.export_value) || 0, exportTarget: Number(s.progress?.export_target) || 0,
  };
}
export function demoState(country = 'Tropia', stage = 1, machine = 1, electronics = 1) {
  const c = COUNTRIES[country] || COUNTRIES.Tropia;
  return { country, label: c.label, main: c.main, levels: { [c.main]: clamp(stage, 4) },
    machine_gen: clamp(machine, 3), electronics_gen: clamp(electronics, 3), round: 1, phase: 'listing',
    stock: [{ good: c.main, gen: 1, free: 8 }], transactions_this_round: [],
    progress: { export_value: 0, export_target: 255 }, settlement: { rows: [] } };
}
