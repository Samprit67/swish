// Hand-rolled SVG charts. No charting library.
// Each builder returns a <svg> node sized by a viewBox; CSS scales it to fit.
// Animation is done with CSS classes (.draw / .grow / .fade) set on insert.

const NS = "http://www.w3.org/2000/svg";
export const COL = {
  accent: "var(--accent)",
  accent2: "var(--accent-2)",
  cool: "var(--cool)",
  pos: "var(--pos)",
  neg: "var(--neg)",
  dim: "var(--text-3)",
  text: "var(--text)",
  grid: "var(--grid-line)",
};

function el(name, attrs = {}, kids = []) {
  const n = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) n.setAttribute(k, v);
  for (const kid of [].concat(kids)) if (kid) n.append(kid);
  return n;
}
function svg(w, h, cls) {
  return el("svg", { viewBox: `0 0 ${w} ${h}`, preserveAspectRatio: "xMidYMid meet", class: cls || "" });
}
function label(x, y, s, attrs = {}) {
  // fill via inline style so it beats the `.chart text` stylesheet default
  const { fill, ...rest } = attrs;
  const t = el("text", { x, y, "font-size": 10.5, ...rest });
  t.style.fill = fill || "var(--text-3)";
  t.textContent = s;
  return t;
}
function fmtM(d, digits = 1) {
  const sign = d < 0 ? "−" : "";
  return `${sign}$${(Math.abs(d) / 1e6).toFixed(digits)}M`;
}
function drawn(path) {
  // let the browser measure, then animate the stroke in
  requestAnimationFrame(() => {
    try {
      const len = path.getTotalLength();
      path.style.setProperty("--len", len);
      path.classList.add("draw");
    } catch {
      path.classList.add("fade");
    }
  });
  return path;
}
function niceTicks(lo, hi, n = 4) {
  const span = hi - lo || 1;
  const step = Math.pow(10, Math.floor(Math.log10(span / n)));
  const err = (span / n) / step;
  const mult = err >= 7.5 ? 10 : err >= 3 ? 5 : err >= 1.5 ? 2 : 1;
  const s = mult * step;
  const start = Math.ceil(lo / s) * s;
  const out = [];
  for (let v = start; v <= hi + 1e-9; v += s) out.push(+v.toFixed(10));
  return out;
}

// ---------------------------------------------------------------- line chart
export function lineChart(points, { w = 620, h = 232, caption } = {}) {
  // points: [{label, y}]
  const pad = { l: 34, r: 12, t: 14, b: 24 };
  const iw = w - pad.l - pad.r;
  const ih = h - pad.t - pad.b;
  const s = svg(w, h, "chart-line");
  const ys = points.map((p) => p.y);
  let lo = Math.min(0, ...ys);
  let hi = Math.max(...ys, 1);
  const pad_v = (hi - lo) * 0.12 || 1;
  hi += pad_v; lo -= pad_v * 0.4;
  const X = (i) => pad.l + (points.length === 1 ? iw / 2 : (i / (points.length - 1)) * iw);
  const Y = (v) => pad.t + ih - ((v - lo) / (hi - lo)) * ih;

  for (const t of niceTicks(lo, hi, 4)) {
    s.append(el("line", { x1: pad.l, y1: Y(t), x2: w - pad.r, y2: Y(t), stroke: COL.grid }));
    s.append(label(pad.l - 6, Y(t) + 3, t.toFixed(t % 1 ? 1 : 0), { "text-anchor": "end" }));
  }
  if (lo < 0) s.append(el("line", { x1: pad.l, y1: Y(0), x2: w - pad.r, y2: Y(0), stroke: COL.dim, "stroke-dasharray": "2 3" }));

  const every = points.length > 9 ? 2 : 1;
  points.forEach((p, i) => {
    if (i % every === 0 || i === points.length - 1)
      s.append(label(X(i), h - 7, p.label, { "text-anchor": "middle" }));
  });

  const d = points.map((p, i) => `${i ? "L" : "M"} ${X(i)} ${Y(p.y)}`).join(" ");
  const area = `${d} L ${X(points.length - 1)} ${Y(lo)} L ${X(0)} ${Y(lo)} Z`;
  s.append(el("path", { d: area, fill: COL.accent, "fill-opacity": 0.08, class: "fade" }));
  s.append(drawn(el("path", { d, fill: "none", stroke: COL.accent, "stroke-width": 2.5, "stroke-linejoin": "round", "stroke-linecap": "round" })));
  points.forEach((p, i) => s.append(el("circle", { cx: X(i), cy: Y(p.y), r: 3, fill: COL.accent, class: "fade" })));

  attachHover(s, w, h, pad, points.map((p, i) => X(i)), (i) => {
    const p = points[i];
    return { x: X(i), y: Y(p.y), text: `${p.label}  ·  ${p.y.toFixed(1)}`, cap: caption };
  });
  return s;
}

// ---------------------------------------------------------------- fan chart
export function fanChart(anchor, years, { w = 620, h = 224 } = {}) {
  const pad = { l: 34, r: 12, t: 16, b: 24 };
  const iw = w - pad.l - pad.r;
  const ih = h - pad.t - pad.b;
  const s = svg(w, h, "chart-fan");
  const cols = [{ label: anchor.label, p10: anchor.y, p50: anchor.y, p90: anchor.y }, ...years];
  let lo = Math.min(0, ...cols.map((c) => c.p10));
  let hi = Math.max(...cols.map((c) => c.p90), 1);
  const pv = (hi - lo) * 0.14 || 1; hi += pv; lo -= pv * 0.4;
  const X = (i) => pad.l + (i / (cols.length - 1)) * iw;
  const Y = (v) => pad.t + ih - ((v - lo) / (hi - lo)) * ih;

  const grad = el("linearGradient", { id: "fan-g", x1: 0, y1: 0, x2: 0, y2: 1 }, [
    el("stop", { offset: 0, "stop-color": COL.accent, "stop-opacity": 0.26 }),
    el("stop", { offset: 1, "stop-color": COL.accent, "stop-opacity": 0.04 }),
  ]);
  s.append(el("defs", {}, grad));

  for (const t of niceTicks(lo, hi, 4)) {
    s.append(el("line", { x1: pad.l, y1: Y(t), x2: w - pad.r, y2: Y(t), stroke: COL.grid }));
    s.append(label(pad.l - 6, Y(t) + 3, t.toFixed(t % 1 ? 1 : 0), { "text-anchor": "end" }));
  }
  const top = cols.map((c, i) => `${X(i)} ${Y(c.p90)}`);
  const bot = cols.map((c, i) => `${X(i)} ${Y(c.p10)}`).reverse();
  s.append(el("path", { d: `M ${top.join(" L ")} L ${bot.join(" L ")} Z`, fill: "url(#fan-g)", class: "fade" }));
  s.append(drawn(el("path", { d: "M " + cols.map((c, i) => `${X(i)} ${Y(c.p50)}`).join(" L "), fill: "none", stroke: COL.accent, "stroke-width": 2.5 })));
  s.append(el("line", { x1: X(0), y1: pad.t, x2: X(0), y2: pad.t + ih, stroke: COL.dim, "stroke-dasharray": "2 3", class: "fade" }));
  cols.forEach((c, i) => {
    s.append(el("circle", { cx: X(i), cy: Y(c.p50), r: 3, fill: COL.accent, class: "fade" }));
    s.append(label(X(i), h - 7, c.label, { "text-anchor": "middle" }));
  });
  attachHover(s, w, h, pad, cols.map((c, i) => X(i)), (i) => {
    const c = cols[i];
    return { x: X(i), y: Y(c.p50), text: `${c.label}  ·  ${c.p50.toFixed(1)}  (${c.p10.toFixed(1)}–${c.p90.toFixed(1)})` };
  });
  return s;
}

// ---------------------------------------------------------------- waterfall
export function waterfall(steps, { w = 640, h = 250 } = {}) {
  // steps: [{label, delta, total?}]
  const pad = { l: 14, r: 14, t: 22, b: 42 };
  const iw = w - pad.l - pad.r;
  const ih = h - pad.t - pad.b;
  const s = svg(w, h, "chart-wf");
  let run = 0;
  const bars = steps.map((st) => {
    const from = st.total ? 0 : run;
    const to = st.total ? st.delta : run + st.delta;
    run = st.total ? st.delta : to;
    return { ...st, from, to };
  });
  const vals = bars.flatMap((b) => [b.from, b.to, 0]);
  let lo = Math.min(...vals), hi = Math.max(...vals);
  const pv = (hi - lo) * 0.1 || 1; hi += pv; lo -= pv;
  const Y = (v) => pad.t + ih - ((v - lo) / (hi - lo)) * ih;
  const slot = iw / bars.length;
  const bw = Math.min(58, slot * 0.62);

  s.append(el("line", { x1: pad.l, y1: Y(0), x2: w - pad.r, y2: Y(0), stroke: COL.grid }));
  bars.forEach((b, i) => {
    const cx = pad.l + slot * i + slot / 2;
    const y0 = Y(b.from), y1 = Y(b.to);
    const top = Math.min(y0, y1), bh = Math.max(2, Math.abs(y0 - y1));
    const color = b.total ? COL.cool : b.delta >= 0 ? COL.pos : COL.neg;
    const rect = el("rect", { x: cx - bw / 2, y: top, width: bw, height: bh, rx: 3, fill: color, class: "grow" });
    rect.style.setProperty("--baseline", `${b.delta >= 0 || b.total ? "bottom" : "top"}`);
    rect.style.animationDelay = `${i * 55}ms`;
    s.append(rect);
    if (i < bars.length - 1 && !bars[i + 1].total)
      s.append(el("line", { x1: cx + bw / 2, y1: y1, x2: cx + slot - bw / 2, y2: y1, stroke: COL.dim, "stroke-dasharray": "2 2", class: "fade" }));
    s.append(label(cx, top - 6, fmtM(b.total ? b.to : b.delta), { "text-anchor": "middle", "font-weight": 700, fill: COL.text, class: "fade" }));
    b.label.split("\n").forEach((part, li) =>
      s.append(label(cx, h - 26 + li * 12, part, { "text-anchor": "middle" })));
  });
  return s;
}

// ---------------------------------------------------------------- histogram
export function histogram(bins, marks = [], { w = 640, h = 92 } = {}) {
  const pad = { l: 4, r: 4, t: 8, b: 16 };
  const iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;
  const s = svg(w, h, "chart-hist");
  const xs = bins.map((b) => b.x);
  const lo = Math.min(...xs), hi = Math.max(...xs);
  const maxd = Math.max(...bins.map((b) => b.d), 1e-9);
  const X = (v) => pad.l + ((v - lo) / (hi - lo || 1)) * iw;
  const bw = (iw / bins.length) * 0.86;
  bins.forEach((b, i) => {
    const bh = Math.max(1, (b.d / maxd) * ih);
    const r = el("rect", { x: X(b.x) - bw / 2, y: pad.t + ih - bh, width: bw, height: bh, rx: 1.5, fill: b.x < 0 ? COL.neg : COL.accent, "fill-opacity": 0.5, class: "grow" });
    r.style.animationDelay = `${i * 12}ms`;
    s.append(r);
  });
  if (lo < 0 && hi > 0) s.append(el("line", { x1: X(0), y1: pad.t, x2: X(0), y2: pad.t + ih, stroke: COL.dim, "stroke-dasharray": "3 2" }));
  marks.forEach((m) => {
    s.append(el("line", { x1: X(m.v), y1: pad.t - 2, x2: X(m.v), y2: pad.t + ih, stroke: COL.text, "stroke-width": 1, "stroke-opacity": 0.55 }));
    s.append(label(X(m.v), h - 4, m.label, { "text-anchor": "middle", "font-weight": 600 }));
  });
  return s;
}

// ---------------------------------------------------------------- compare bars
export function compareBars(items, { w = 620, rowH = 40 } = {}) {
  const h = items.length * rowH + 16;
  const pad = { l: 124, r: 78, t: 8, b: 8 };
  const iw = w - pad.l - pad.r;
  const s = svg(w, h, "chart-bars");
  const lo = Math.min(0, ...items.map((d) => d.value));
  const hi = Math.max(0, ...items.map((d) => d.value)) || 1;
  const X = (v) => pad.l + ((v - lo) / (hi - lo || 1)) * iw;
  const x0 = X(0);
  s.append(el("line", { x1: x0, y1: pad.t, x2: x0, y2: h - pad.b, stroke: COL.grid }));
  items.forEach((d, i) => {
    const cy = pad.t + i * rowH + rowH / 2;
    s.append(label(pad.l - 10, cy + 4, d.label, { "text-anchor": "end", fill: COL.text, "font-weight": 650, "font-size": 12.5 }));
    const x1 = X(d.value);
    const bx = Math.min(x0, x1), bw = Math.max(2, Math.abs(x1 - x0));
    const g = el("g", { class: "grow" });
    g.style.setProperty("--baseline", "left");
    g.style.transformOrigin = `${x0}px ${cy}px`;
    g.style.animationDelay = `${i * 70}ms`;
    g.append(el("rect", { x: bx, y: cy - 10, width: bw, height: 20, rx: 4, fill: d.value >= 0 ? COL.accent : COL.neg }));
    s.append(g);
    const inside = bw > 54;
    s.append(label(inside ? (d.value >= 0 ? bx + bw - 7 : bx + 7) : (d.value >= 0 ? bx + bw + 6 : bx - 6), cy + 4,
      fmtM(d.value), { "text-anchor": d.value >= 0 ? (inside ? "end" : "start") : (inside ? "start" : "end"), fill: inside ? "#fff" : COL.text, "font-weight": 700, class: "fade" }));
  });
  return s;
}

// ---------------------------------------------------------------- radar
export function radar(series, axes, { w = 400, h = 340 } = {}) {
  // series: [{name, color, values:[0..100]}]   axes: ["Scoring", ...]
  const cx = w / 2, cy = h / 2, R = Math.min(w, h) / 2 - 40;
  const s = svg(w, h, "chart-radar");
  const n = axes.length;
  const solo = series.length === 1;
  const pt = (ang, r) => [cx + r * Math.cos(ang - Math.PI / 2), cy + r * Math.sin(ang - Math.PI / 2)];

  for (let ring = 1; ring <= 4; ring++) {
    const poly = axes.map((_, i) => pt((i / n) * 2 * Math.PI, (ring / 4) * R).join(",")).join(" ");
    s.append(el("polygon", { points: poly, fill: "none", stroke: COL.grid }));
  }
  axes.forEach((ax, i) => {
    const ang = (i / n) * 2 * Math.PI;
    const [ex, ey] = pt(ang, R);
    s.append(el("line", { x1: cx, y1: cy, x2: ex, y2: ey, stroke: COL.grid }));
    const [lx, ly] = pt(ang, R + 14);
    s.append(label(lx, ly + 3, ax, {
      "text-anchor": Math.abs(lx - cx) < 10 ? "middle" : lx > cx ? "start" : "end",
      "font-size": 9.5,
    }));
  });
  series.forEach((ser, si) => {
    const poly = ser.values.map((v, i) => pt((i / n) * 2 * Math.PI, (Math.max(0, Math.min(100, v)) / 100) * R).join(",")).join(" ");
    const g = el("g", { class: "fade" });
    g.style.animationDelay = `${si * 90}ms`;
    g.append(el("polygon", {
      points: poly, fill: ser.color, "fill-opacity": solo ? 0.16 : 0.05,
      stroke: ser.color, "stroke-width": 2, "stroke-linejoin": "round",
    }));
    ser.values.forEach((v, i) => {
      const [px, py] = pt((i / n) * 2 * Math.PI, (Math.max(0, Math.min(100, v)) / 100) * R);
      g.append(el("circle", { cx: px, cy: py, r: 2.4, fill: ser.color }));
    });
    s.append(g);
  });
  return s;
}

// ---------------------------------------------------------------- hover
function attachHover(s, w, h, pad, xs, at) {
  const marker = el("g", { style: "opacity:0;transition:opacity .1s" });
  const vline = el("line", { y1: pad.t, y2: h - pad.b, stroke: COL.dim, "stroke-width": 1 });
  const dot = el("circle", { r: 4, fill: COL.accent, stroke: "var(--surface)", "stroke-width": 2 });
  const tagBg = el("rect", { rx: 4, height: 18, fill: COL.text });
  const tag = el("text", { "font-size": 10.5, fill: "var(--surface)", "font-weight": 600, "text-anchor": "middle", dy: 3 });
  marker.append(vline, tagBg, tag, dot);
  s.append(marker);
  const hit = el("rect", { x: 0, y: 0, width: w, height: h, fill: "transparent" });
  s.append(hit);
  hit.addEventListener("pointermove", (e) => {
    const r = s.getBoundingClientRect();
    const mx = ((e.clientX - r.left) / r.width) * w;
    let bi = 0, bd = Infinity;
    xs.forEach((x, i) => { const d = Math.abs(x - mx); if (d < bd) { bd = d; bi = i; } });
    const info = at(bi);
    vline.setAttribute("x1", info.x); vline.setAttribute("x2", info.x);
    dot.setAttribute("cx", info.x); dot.setAttribute("cy", info.y);
    tag.textContent = info.text;
    const tw = info.text.length * 5.6 + 12;
    const tx = Math.max(tw / 2 + 2, Math.min(w - tw / 2 - 2, info.x));
    tag.setAttribute("x", tx); tag.setAttribute("y", pad.t - 4);
    tagBg.setAttribute("x", tx - tw / 2); tagBg.setAttribute("y", pad.t - 17); tagBg.setAttribute("width", tw);
    marker.style.opacity = "1";
  });
  hit.addEventListener("pointerleave", () => (marker.style.opacity = "0"));
}
