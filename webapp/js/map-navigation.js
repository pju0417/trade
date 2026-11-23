// Visual maritime routing only. No prices, transactions, timing or game rules live here.
const navigators = new WeakMap();
const cross = (a,b,c) => (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
function intersects(a,b,c,d) {
  if (Math.max(a[0],b[0]) < Math.min(c[0],d[0]) || Math.max(c[0],d[0]) < Math.min(a[0],b[0]) || Math.max(a[1],b[1]) < Math.min(c[1],d[1]) || Math.max(c[1],d[1]) < Math.min(a[1],b[1])) return false;
  return cross(a,b,c)*cross(a,b,d) <= 0 && cross(c,d,a)*cross(c,d,b) <= 0;
}
export function isLand(layout, [x, y]) {
  return (layout.landmasses || []).some(({ outline }) => {
    let inside = false;
    for (let i = 0, j = outline.length - 1; i < outline.length; j = i++) {
      const a = outline[i], b = outline[j];
      if ((a[1] > y) !== (b[1] > y) && x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
    }
    return inside;
  });
}
class SeaNavigator {
  constructor(layout) {
    this.layout = layout; this.cache = new Map(); this.visibility = new Map(); this.step = layout.terrainModel ? 12 : 24;
    const [x, y, width, height] = layout.viewBox;
    this.origin = [x, y]; this.cols = Math.floor(width / this.step) + 1; this.rows = Math.floor(height / this.step) + 1;
    this.water = Array.from({ length: this.cols * this.rows }, (_, i) => {
      const p = this.point(i);
      return [[0,0],[-5,0],[5,0],[0,-5],[0,5]].every(([dx,dy]) => !isLand(layout, [p[0] + dx, p[1] + dy]));
    });
  }
  point(i) { return [this.origin[0] + i % this.cols * this.step, this.origin[1] + Math.floor(i / this.cols) * this.step]; }
  nearest(point) {
    let best = -1, distance = Infinity;
    this.water.forEach((water, i) => { if (water) { const p = this.point(i), d = Math.hypot(p[0] - point[0], p[1] - point[1]); if (d < distance) { distance = d; best = i; } } });
    return best;
  }
  clear(a, b) {
    const key = [String(a),String(b)].sort().join(':');
    if (this.visibility.has(key)) return this.visibility.get(key);
    const clear = !isLand(this.layout,a) && !isLand(this.layout,b) && !this.layout.landmasses.some(({outline}) => outline.some((c,i) => intersects(a,b,c,outline[(i+1)%outline.length])));
    this.visibility.set(key, clear); return clear;
  }
  route(from, to) {
    const key = `${from}:${to}`, reverse = `${to}:${from}`;
    if (this.cache.has(key)) return this.cache.get(key);
    if (this.cache.has(reverse)) { const path = [...this.cache.get(reverse)].reverse(); this.cache.set(key, path); return path; }
    const start = this.nearest(from), end = this.nearest(to);
    if (start < 0 || end < 0) return [from, to];
    const open = new Set([start]), scores = new Map([[start, 0]]), previous = new Map(), closed = new Set();
    const destination = this.point(end);
    const heuristic = i => { const p = this.point(i); return Math.hypot(p[0] - destination[0], p[1] - destination[1]); };
    while (open.size) {
      let current = -1, best = Infinity;
      for (const i of open) { const estimate = scores.get(i) + heuristic(i); if (estimate < best) { current = i; best = estimate; } }
      if (current === end) break;
      open.delete(current); closed.add(current);
      const x = current % this.cols, y = Math.floor(current / this.cols);
      for (const dx of [-1,0,1]) for (const dy of [-1,0,1]) {
        if (!dx && !dy || x + dx < 0 || x + dx >= this.cols || y + dy < 0 || y + dy >= this.rows) continue;
        const next = current + dx + dy * this.cols;
        if (!this.water[next] || closed.has(next)) continue;
        if (dx && dy && (!this.water[current + dx] || !this.water[current + dy * this.cols])) continue;
        if (!this.clear(this.point(current), this.point(next))) continue;
        const score = scores.get(current) + this.step * Math.hypot(dx, dy);
        if (score >= (scores.get(next) ?? Infinity)) continue;
        scores.set(next, score); previous.set(next, current); open.add(next);
      }
    }
    if (start !== end && !previous.has(end)) return [from, to];
    const cells = [end]; let cursor = end;
    while (cursor !== start) { cursor = previous.get(cursor); cells.push(cursor); }
    const points = cells.reverse().map(i => this.point(i)), simplified = [points[0]];
    for (let i = 0; i < points.length - 1;) {
      let next = points.length - 1;
      while (next > i + 1 && !this.clear(points[i], points[next])) next--;
      simplified.push(points[next]); i = next;
    }
    const path = [from, ...simplified, to].filter((p, i, points) => !i || p[0] !== points[i-1][0] || p[1] !== points[i-1][1]); this.cache.set(key, path); return path;
  }
}
export function seaRoute(layout, from, to) {
  if (!layout.landmasses?.length) return [from, to];
  if (!navigators.has(layout)) navigators.set(layout, new SeaNavigator(layout));
  const countries = Object.values(layout.countries || {});
  const start = countries.find(c => c.port === from)?.approach || from;
  const end = countries.find(c => c.port === to)?.approach || to;
  const offshore = navigators.get(layout).route(start, end);
  return [from, ...offshore, to].filter((p, i, points) => !i || p[0] !== points[i-1][0] || p[1] !== points[i-1][1]);
}
