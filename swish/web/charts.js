// Hand-rolled SVG charts. No charting library.
// Every chart returns a <svg> DOM node sized by a viewBox; CSS scales it to fit.

const NS = "http://www.w3.org/2000/svg";
export const COL = {
  accent: "var(--accent)",
  cool: "var(--cool)",
  pos: "var(--pos)",
  neg: "var(--neg)",
  dim: "var(--text-dim)",
  grid: "var(--grid)",
};

function el(name, attrs = {}, kids = []) {
  const n = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) n.setAttribute(k, v);
  for (const kid of [].concat(kids)) if (kid) n.append(kid);
  return n;
}
function svg(w, h) {
  return el("svg", { viewBox: `0 0 ${w} ${h}`, preserveAspectRatio: "xMidYMid meet", class: "chartsvg" });
}
function text(x, y, s, attrs = {}) {
  const t = el("text", { x, y, fill: COL.dim, "font-size": 11, "font-family": "inherit", ...attrs });
  t.textContent = s;
  return t;
}
const lerp = (a, b, t) => a + (b - a) * t;

// --------------------------------------------------------------------------
// line chart — one or more series over a shared x (season labels)
// --------------------------------------------------------------------------
export function lineChart(labels, series, { w = 620, h = 240, yLabel = "", zeroLine = false } = {}) {
  const pad = { l: 40, r: 14, t: 12, b: 26 };
  const iw = w - pad.l - pad.r;
  const ih = h - pad.t - pad.b;
  const s = svg(w, h);

  const all = series.flatMap((ser) => ser.points.filter((v) => v !== null));
  let lo = Math.min(0, ...all);
  let hi = Math.max(...all, 1);
  const span = hi - lo || 1;
  hi += span * 0.08;
  lo -= span * 0.04;

  const x = (i) => pad.l + (labels.length === 1 ? iw / 2 : (i / (labels.length - 1)) * iw);
  const y = (v) => pad.t + ih - ((v - lo) / (hi - lo)) * ih;

  for (let g = 0; g <= 4; g++) {
    const gy = pad.t + (g / 4) * ih;
    s.append(el("line", { x1: pad.l, y1: gy, x2: w - pad.r, y2: gy, stroke: COL.grid }));
    s.append(text(pad.l - 6, gy + 3, (hi - (g / 4) * (hi - lo)).toFixed(1), { "text-anchor": "end" }));
  }
  if (zeroLine && lo < 0) s.append(el("line", { x1: pad.l, y1: y(0), x2: w - pad.r, y2: y(0), stroke: COL.dim, "stroke-dasharray": "3 3" }));

  labels.forEach((lab, i) => s.append(text(x(i), h - 8, lab, { "text-anchor": "middle" })));

  series.forEach((ser) => {
    const pts = ser.points.map((v, i) => (v === null ? null : [x(i), y(v)]));
    let d = "";
    pts.forEach((p) => (d += p ? (d ? " L" : "M") + p[0] + " " + p[1] : ""));
    s.append(el("path", { d, fill: "none", stroke: ser.color || COL.accent, "stroke-width": ser.width || 2.5, "stroke-linejoin": "round", "stroke-linecap": "round" }));
    pts.forEach((p) => p && s.append(el("circle", { cx: p[0], cy: p[1], r: 3, fill: ser.color || COL.accent })));
  });
  if (yLabel) s.append(text(pad.l, pad.t - 2, yLabel, { "text-anchor": "start", "font-weight": 600 }));
  return s;
}

// --------------------------------------------------------------------------
// fan chart — projected WAR with a p10–p90 band
// --------------------------------------------------------------------------
export function fanChart(anchor, years, { w = 620, h = 230 } = {}) {
  // anchor: {label, war}  ·  years: [{label, p10, p50, p90}]
  const pad = { l: 40, r: 14, t: 14, b: 26 };
  const iw = w - pad.l - pad.r;
  const ih = h - pad.t - pad.b;
  const s = svg(w, h);
  const cols = [{ label: anchor.label, p10: anchor.war, p50: anchor.war, p90: anchor.war }, ...years];

  let lo = Math.min(0, ...cols.map((c) => c.p10));
  let hi = Math.max(...cols.map((c) => c.p90), 1);
  const span = hi - lo || 1; hi += span * 0.1; lo -= span * 0.05;
  const x = (i) => pad.l + (i / (cols.length - 1)) * iw;
  const y = (v) => pad.t + ih - ((v - lo) / (hi - lo)) * ih;

  for (let g = 0; g <= 4; g++) {
    const gy = pad.t + (g / 4) * ih;
    s.append(el("line", { x1: pad.l, y1: gy, x2: w - pad.r, y2: gy, stroke: COL.grid }));
    s.append(text(pad.l - 6, gy + 3, (hi - (g / 4) * (hi - lo)).toFixed(1), { "text-anchor": "end" }));
  }
  const top = cols.map((c, i) => `${x(i)} ${y(c.p90)}`);
  const bot = cols.map((c, i) => `${x(i)} ${y(c.p10)}`).reverse();
  s.append(el("path", { d: `M ${top.join(" L ")} L ${bot.join(" L ")} Z`, fill: COL.accent, "fill-opacity": 0.16 }));
  s.append(el("path", { d: "M " + cols.map((c, i) => `${x(i)} ${y(c.p50)}`).join(" L "), fill: "none", stroke: COL.accent, "stroke-width": 2.5 }));
  cols.forEach((c, i) => {
    s.append(el("circle", { cx: x(i), cy: y(c.p50), r: 3, fill: COL.accent }));
    s.append(text(x(i), h - 8, c.label, { "text-anchor": "middle" }));
  });
  s.append(el("line", { x1: x(0), y1: pad.t, x2: x(0), y2: pad.t + ih, stroke: COL.dim, "stroke-dasharray": "2 3" }));
  return s;
}

// --------------------------------------------------------------------------
// waterfall — production value, minus salary, to surplus
// --------------------------------------------------------------------------
export function waterfall(steps, { w = 620, h = 240 } = {}) {
  // steps: [{label, delta, total?}]  total step draws an absolute bar from 0
  const pad = { l: 46, r: 14, t: 14, b: 40 };
  const iw = w - pad.l - pad.r;
  const ih = h - pad.t - pad.b;
  const s = svg(w, h);

  let run = 0;
  const bars = steps.map((st) => {
    const from = st.total ? 0 : run;
    const to = st.total ? st.delta : run + st.delta;
    run = to;
    return { ...st, from, to };
  });
  const vals = bars.flatMap((b) => [b.from, b.to]);
  let lo = Math.min(0, ...vals);
  let hi = Math.max(0, ...vals);
  const spanv = hi - lo || 1; hi += spanv * 0.08; lo -= spanv * 0.08;
  const y = (v) => pad.t + ih - ((v - lo) / (hi - lo)) * ih;
  const bw = (iw / bars.length) * 0.6;
  const gap = iw / bars.length;

  s.append(el("line", { x1: pad.l, y1: y(0), x2: w - pad.r, y2: y(0), stroke: COL.dim }));
  bars.forEach((b, i) => {
    const cx = pad.l + gap * i + gap / 2;
    const top = Math.min(y(b.from), y(b.to));
    const barH = Math.max(2, Math.abs(y(b.from) - y(b.to)));
    const color = b.total ? COL.cool : b.delta >= 0 ? COL.pos : COL.neg;
    s.append(el("rect", { x: cx - bw / 2, y: top, width: bw, height: barH, rx: 2, fill: color, "fill-opacity": b.total ? 0.9 : 0.8 }));
    if (i < bars.length - 1 && !bars[i + 1].total)
      s.append(el("line", { x1: cx + bw / 2, y1: y(b.to), x2: cx + gap - bw / 2, y2: y(b.to), stroke: COL.dim, "stroke-dasharray": "2 2" }));
    s.append(text(cx, top - 5, fmtM(b.total ? b.to : b.delta), { "text-anchor": "middle", "font-weight": 600, fill: "var(--text)" }));
    for (const [li, part] of b.label.split("\n").entries())
      s.append(text(cx, h - 24 + li * 12, part, { "text-anchor": "middle" }));
  });
  return s;
}
function fmtM(d) {
  const sign = d < 0 ? "−" : "";
  return `${sign}$${(Math.abs(d) / 1e6).toFixed(1)}M`;
}

// --------------------------------------------------------------------------
// histogram — Monte Carlo distribution of the headline value
// --------------------------------------------------------------------------
export function histogram(bins, marks = [], { w = 620, h = 90 } = {}) {
  const s = svg(w, h);
  const pad = { l: 6, r: 6, t: 6, b: 16 };
  const iw = w - pad.l - pad.r;
  const ih = h - pad.t - pad.b;
  const xs = bins.map((b) => b.x);
  const lo = Math.min(...xs), hi = Math.max(...xs);
  const maxd = Math.max(...bins.map((b) => b.d), 1e-12);
  const x = (v) => pad.l + ((v - lo) / (hi - lo || 1)) * iw;
  const bw = (iw / bins.length) * 0.9;
  bins.forEach((b) => {
    const bh = (b.d / maxd) * ih;
    const col = b.x < 0 ? COL.neg : COL.accent;
    s.append(el("rect", { x: x(b.x) - bw / 2, y: pad.t + ih - bh, width: bw, height: bh, fill: col, "fill-opacity": 0.55, rx: 1 }));
  });
  s.append(el("line", { x1: x(0), y1: pad.t, x2: x(0), y2: pad.t + ih, stroke: COL.dim, "stroke-dasharray": "3 2" }));
  marks.forEach((m) => {
    s.append(el("line", { x1: x(m.v), y1: pad.t, x2: x(m.v), y2: pad.t + ih, stroke: "var(--text)", "stroke-width": 1 }));
    s.append(text(x(m.v), h - 4, m.label, { "text-anchor": "middle" }));
  });
  return s;
}

// --------------------------------------------------------------------------
// horizontal bars — compare view
// --------------------------------------------------------------------------
export function compareBars(items, { w = 620, rowH = 36 } = {}) {
  const h = items.length * rowH + 20;
  const pad = { l: 132, r: 74, t: 10, b: 10 };
  const iw = w - pad.l - pad.r;
  const s = svg(w, h);
  const lo = Math.min(0, ...items.map((d) => d.value));
  const hi = Math.max(0, ...items.map((d) => d.value)) || 1;
  const x = (v) => pad.l + ((v - lo) / (hi - lo || 1)) * iw;
  const x0 = x(0);
  s.append(el("line", { x1: x0, y1: pad.t, x2: x0, y2: h - pad.b, stroke: COL.dim }));
  items.forEach((d, i) => {
    const cy = pad.t + i * rowH + rowH / 2;
    s.append(text(pad.l - 10, cy + 4, d.label, { "text-anchor": "end", fill: "var(--text)", "font-weight": 600, "font-size": 12.5 }));
    const x1 = x(d.value);
    const bx = Math.min(x0, x1);
    const bw = Math.max(2, Math.abs(x1 - x0));
    s.append(el("rect", { x: bx, y: cy - 10, width: bw, height: 20, rx: 3, fill: d.value >= 0 ? COL.accent : COL.neg }));
    const label = fmtM(d.value);
    if (bw > 52) {
      // inside the bar, near its outboard end
      const inx = d.value >= 0 ? bx + bw - 6 : bx + 6;
      s.append(text(inx, cy + 4, label, { "text-anchor": d.value >= 0 ? "end" : "start", fill: "#fff", "font-weight": 700 }));
    } else {
      const outx = d.value >= 0 ? bx + bw + 6 : bx - 6;
      s.append(text(outx, cy + 4, label, { "text-anchor": d.value >= 0 ? "start" : "end", fill: "var(--text)", "font-weight": 700 }));
    }
  });
  return s;
}

export { lerp };
