import { api, ApiError } from "./api.js";
import * as F from "./format.js";
import * as C from "./charts.js";

// ------------------------------------------------------------------ dom
function h(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "html") n.innerHTML = v;
    else if (k === "style" && typeof v === "string") n.style.cssText = v;
    else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2), v);
    else if (v === true) n.setAttribute(k, "");
    else n.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    n.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return n;
}
const $ = (s, r = document) => r.querySelector(s);
const view = () => $("#view");
const clear = (n) => { while (n.firstChild) n.removeChild(n.firstChild); };
const chart = (node) => h("div", { class: "chart" }, node);

let toastT;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastT);
  toastT = setTimeout(() => (t.hidden = true), 3000);
}

// ------------------------------------------------------------------ state
const DEFAULTS = { horizon: 3, discount: 0.08, dpw: 3.3, metric: "blend", use_contract: true };
const state = { ...DEFAULTS };
try { Object.assign(state, JSON.parse(localStorage.getItem("swish.params") || "{}")); } catch {}
const saveState = () => { try { localStorage.setItem("swish.params", JSON.stringify(state)); } catch {} };
const qparams = () => ({
  horizon: state.horizon, discount: state.discount, dollars_per_win: state.dpw,
  metric: state.metric, use_contract: state.use_contract,
});

// ------------------------------------------------------------------ theme
function initTheme() {
  const saved = localStorage.getItem("swish.theme");
  if (saved) document.documentElement.setAttribute("data-theme", saved);
  $("#theme-toggle").addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme");
    const next = cur === "dark" ? "light" : cur === "light" ? "auto" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    if (next === "auto") localStorage.removeItem("swish.theme");
    else localStorage.setItem("swish.theme", next);
  });
}

// ------------------------------------------------------------------ headshot
function headshot(pid, name) {
  const initials = (name || "").split(/\s+/).map((s) => s[0]).slice(0, 2).join("").toUpperCase();
  const box = h("div", { class: "shot" }, initials || "··");
  if (pid && !/\s/.test(pid)) {
    const img = new Image();
    img.onload = () => { box.textContent = ""; box.style.border = "0"; box.append(img); };
    img.className = "shot";
    img.style.cssText = "width:100%;height:100%;border:0";
    img.src = `/api/players/${encodeURIComponent(pid)}/headshot`;
  }
  return box;
}

// ------------------------------------------------------------------ typeahead
// Attaches a player-search dropdown to any <input> whose parent form/box is
// position:relative. onPick(ref) fires when the user chooses a player.
function typeahead(input, onPick, { min = 2, clearOnPick = true } = {}) {
  const host = input.closest("form") || input.parentElement;
  host.classList.add("ta-host");
  const menu = h("div", { class: "ta-menu" });
  menu.hidden = true;
  host.append(menu);
  let timer, rows = [], active = -1, seq = 0;
  input.setAttribute("autocomplete", "off");
  const close = () => { menu.hidden = true; active = -1; };
  const paint = () => {
    clear(menu);
    rows.forEach((r, i) => menu.append(h("button", {
      type: "button", class: i === active ? "active" : "",
      onmousedown: (e) => { e.preventDefault(); choose(r); },
    }, h("span", { class: "sr-name" }, r.name),
       h("span", { class: "sr-meta" }, `${r.position || "—"} · ${r.from_year}–${r.to_year}`))));
    menu.hidden = rows.length === 0;
    const cur = menu.querySelector(".active");
    if (cur) cur.scrollIntoView({ block: "nearest" });
  };
  const choose = (r) => { if (!r) return; if (clearOnPick) input.value = ""; close(); onPick(r); };
  input.addEventListener("input", () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < min) return close();
    const my = ++seq;
    timer = setTimeout(async () => {
      try {
        const res = (await api.get("/players/search", { q })).results;
        if (my !== seq) return;
        rows = res; active = -1; paint();
      } catch { close(); }
    }, 150);
  });
  input.addEventListener("keydown", (e) => {
    if (menu.hidden) return;
    if (e.key === "ArrowDown") { active = Math.min(active + 1, rows.length - 1); e.preventDefault(); paint(); }
    else if (e.key === "ArrowUp") { active = Math.max(active - 1, 0); e.preventDefault(); paint(); }
    else if (e.key === "Enter") { e.preventDefault(); choose(rows[active] || rows[0]); }
    else if (e.key === "Escape") { e.preventDefault(); close(); }
  });
  input.addEventListener("blur", () => setTimeout(close, 150));
}

function initSearch() {
  const box = $("#search-input");
  typeahead(box, (r) => (location.hash = `#/player/${r.pid}`));
  $("#search").addEventListener("submit", (e) => {
    e.preventDefault();
    const q = box.value.trim();
    if (q) { box.value = ""; location.hash = `#/player/${encodeURIComponent(q)}`; }
  });
}

// ------------------------------------------------------------------ controls
function controls(onChange) {
  const wrap = h("div", { class: "card" }, h("h3", {}, "Analytics"));
  const row = h("div", { class: "controls", style: "margin-top:14px" });
  const slider = (key, lbl, min, max, step, fmt) => {
    const out = h("span", { class: "v" }, fmt(state[key]));
    const input = h("input", {
      type: "range", min, max, step, value: state[key],
      oninput: () => { out.textContent = fmt(+input.value); },
      onchange: () => { state[key] = +input.value; saveState(); onChange(); },
    });
    return h("div", { class: "control" }, h("label", {}, lbl, " ", out), input);
  };
  row.append(slider("horizon", "Horizon", 1, 5, 1, (v) => `${v} yr`));
  row.append(slider("discount", "Discount", 0, 0.2, 0.01, (v) => F.pct(v)));
  row.append(slider("dpw", "$ / win", 2, 6, 0.1, (v) => `$${(+v).toFixed(1)}M`));
  const seg = h("div", { class: "seg" });
  [["vorp", "VORP"], ["blend", "Blend"], ["ws", "Win Shares"]].forEach(([m, txt]) =>
    seg.append(h("button", {
      type: "button", class: state.metric === m ? "on" : "",
      onclick: () => { state.metric = m; saveState(); [...seg.children].forEach((b, j) => b.classList.toggle("on", ["vorp", "blend", "ws"][j] === m)); onChange(); },
    }, txt)));
  row.append(h("div", { class: "control" }, h("label", {}, "Metric"), seg));
  const cb = h("input", { type: "checkbox", ...(state.use_contract ? { checked: true } : {}),
    onchange: () => { state.use_contract = cb.checked; saveState(); onChange(); } });
  row.append(h("div", { class: "control" }, h("label", {}, "Contract"), h("label", { class: "toggle" }, cb, "subtract salary")));
  wrap.append(row);
  return wrap;
}

// ------------------------------------------------------------------ player view
let token = 0;
async function renderPlayer(ident, hint) {
  const mine = ++token;
  playerSkeleton(hint);
  let d;
  try { d = await api.get(`/players/${encodeURIComponent(ident)}/value`, qparams()); }
  catch (e) { if (mine === token) renderError(e); return; }
  if (mine !== token) return;
  paintPlayer(d);
}

function playerSkeleton(hint) {
  const v = view();
  clear(v);
  if (hint) {
    v.append(h("div", { class: "hero" },
      headshot(hint.pid, hint.name),
      h("div", { class: "who" }, h("div", { class: "name" }, hint.name),
        h("div", { class: "meta muted" }, hint.position || "loading…")),
      h("div", { class: "headline" }, h("div", { class: "sk sk-wide", style: "width:180px;height:52px;margin-left:auto" }))));
  } else {
    v.append(h("div", { class: "sk sk-hero" }));
  }
  v.append(h("div", { class: "loading" },
    h("div", { class: "sk sk-wide" }),
    h("div", { class: "sk-row" }, h("div", { class: "sk sk-tall" }), h("div", { class: "sk sk-tall" }))));
}

function paintPlayer(d) {
  const v = view();
  clear(v);
  const pos = d.swish_value >= 0;

  v.append(h("div", { class: "hero" },
    headshot(d.player.pid, d.player.name),
    h("div", { class: "who" },
      h("div", { class: "name" }, d.player.name),
      h("div", { class: "meta" },
        [d.player.team || "free agent", d.player.positions, d.player.draft_pick ? `#${d.player.draft_pick} pick` : null].filter(Boolean).join("  ·  ")),
      h("div", { class: "chips" },
        h("span", { class: "chip accent" }, `${F.war(d.talent_war)} talent WAR`),
        h("span", { class: "chip" }, `proj ${F.seasonLabel(d.first_projected_season)}+`),
        h("span", { class: "chip cool" }, d.used_contract ? "surplus over contract" : "production value"))),
    h("div", { class: "headline" },
      h("div", { class: "big " + (pos ? "pos" : "neg") }, F.millions(d.swish_value, d.swish_value >= 1e8 || d.swish_value <= -1e8 ? 0 : 1)),
      h("div", { class: "label" }, d.used_contract ? "Swish value" : "on-court value"),
      h("div", { class: "range" }, `${F.millions(d.band.p10)} → ${F.millions(d.band.p90)}`),
      h("div", { class: "pick " + (d.pick.number > 60 ? "muted" : "") }, "≈ " + d.pick.text))));

  const hist = h("div", { class: "card" }, h("h3", {}, "Where the estimate could land"),
    chart(C.histogram(d.simulation.histogram,
      [{ v: d.band.p10, label: "10th" }, { v: d.band.p50, label: "median" }, { v: d.band.p90, label: "90th" }])));
  v.append(hist);

  v.append(controls(() => renderPlayer(d.player.pid)));

  const g = h("div", { class: "grid cols-2" });
  g.append(h("div", { class: "card" }, h("h3", {}, "Career trajectory"), h("div", { class: "sub" }, "wins above replacement, by season"),
    chart(C.lineChart(d.career.map((s) => ({ label: s.label, y: s.war })), { caption: "WAR" }))));
  g.append(h("div", { class: "card" }, h("h3", {}, "Projection"), h("div", { class: "sub" }, "median WAR with a 10th–90th band"),
    chart(C.fanChart(
      { label: d.career.at(-1).label, y: d.career.at(-1).war },
      d.simulation.years.map((y) => ({ label: F.seasonLabel(y.season_end), p10: y.p10, p50: y.p50, p90: y.p90 }))))));
  v.append(g);

  const steps = [];
  d.value_years.forEach((y, i) => {
    steps.push({ label: `${F.seasonLabel(y.season_end)}\nvalue`, delta: y.production_value });
    if (d.used_contract && y.salary > 0) steps.push({ label: `${F.seasonLabel(y.season_end)}\nsalary`, delta: -y.salary });
  });
  steps.push({ label: (d.used_contract ? "Swish\nvalue" : "Production\nvalue"), delta: d.swish_value, total: true });
  v.append(h("div", { class: "card span-2" },
    h("h3", {}, d.used_contract ? "How the value is built" : "Production value, year by year"),
    chart(C.waterfall(steps))));

  const g2 = h("div", { class: "grid cols-2" });
  if (d.percentiles.length) {
    const pc = h("div", { class: "card" }, h("h3", {}, `League rank · ${F.seasonLabel(d.as_of_season)}`));
    const bars = h("div", { class: "pbars", style: "margin-top:14px" });
    d.percentiles.forEach((p) => {
      const fill = h("span", { class: "fill" });
      bars.append(h("div", { class: "pbar" }, h("span", {}, p.label),
        h("span", { class: "track" }, fill), h("span", { class: "pv" }, Math.round(p.percentile))));
      requestAnimationFrame(() => (fill.style.width = `${p.percentile}%`));
    });
    pc.append(bars);
    g2.append(pc);
  }
  const pt = h("div", { class: "card" }, h("h3", {}, "Year by year"));
  const head = ["Season", "Age", "WAR", "Value", d.used_contract && "Salary", d.used_contract && "Surplus"].filter(Boolean);
  const tb = h("tbody", {});
  d.value_years.forEach((y, i) => {
    tb.append(h("tr", {},
      h("td", {}, F.seasonLabel(y.season_end)),
      h("td", {}, d.projection[i].age),
      h("td", {}, F.war(y.war)),
      h("td", {}, F.millions(y.production_value)),
      d.used_contract && h("td", {}, y.salary ? F.millions(y.salary) : "—"),
      d.used_contract && h("td", { class: y.surplus >= 0 ? "pos" : "neg" }, F.millions(y.surplus, 1))));
  });
  pt.append(h("div", { class: "table-wrap", style: "margin-top:14px" },
    h("table", {}, h("thead", {}, h("tr", {}, ...head.map((x) => h("th", {}, x)))), tb)));
  g2.append(pt);
  v.append(g2);

  if (d.notes.length) {
    v.append(h("div", { class: "card" }, h("h3", {}, "Caveats"),
      h("div", { class: "notes", style: "margin-top:12px" },
        ...d.notes.map((n, i) => h("div", { class: "note" + (i === 0 && n.length > 90 ? " big" : "") }, n)))));
  }
  v.append(h("div", { class: "foot", style: "border:0;padding:6px 0 0" },
    h("span", {}, `as of ${F.seasonLabel(d.as_of_season)} · $${(d.params.dollars_per_win / 1e6).toFixed(1)}M/win · ${F.pct(d.params.discount_rate)} discount`),
    h("a", { href: `#/compare?ids=${d.player.pid}`, style: "color:var(--accent-2);font-weight:700;text-decoration:none" }, "add to compare →")));
}

// ------------------------------------------------------------------ compare
async function renderCompare(idsRaw) {
  const ids = (idsRaw || "").split(",").map((s) => s.trim()).filter(Boolean);
  const v = view();
  clear(v);
  v.append(h("h2", { class: "section-title" }, "Compare"));
  const addInput = h("input", { name: "q", type: "search", placeholder: "add a player…" });
  const add = (name) => (location.hash = `#/compare?ids=${[...ids, name].join(",")}`);
  const adder = h("form", { class: "search", style: "max-width:320px;margin:8px 0 20px",
    onsubmit: (e) => { e.preventDefault(); const q = addInput.value.trim(); if (q) add(q); } }, addInput);
  v.append(adder);
  typeahead(addInput, (r) => add(r.name));
  if (ids.length < 2) { v.append(h("p", { class: "muted" }, "Add at least two players.")); return; }

  v.append(h("div", { class: "sk sk-wide" }));
  let data;
  try { data = await api.get("/compare", { ids: ids.join(","), ...qparams() }); }
  catch (e) { return renderError(e); }
  v.lastChild.remove();

  const players = [...data.players].sort((a, b) => b.swish_value - a.swish_value);
  v.append(h("div", { class: "card" }, h("h3", {}, "Swish value"),
    chart(C.compareBars(players.map((p) => ({ label: p.player.name.split(" ").at(-1), value: p.swish_value }))))));

  const tb = h("tbody", {});
  players.forEach((p) => tb.append(h("tr", { class: "tap", onclick: () => (location.hash = `#/player/${p.player.pid}`) },
    h("td", {}, p.player.name),
    h("td", {}, p.projection[0].age - 1),
    h("td", {}, F.war(p.talent.war)),
    h("td", { class: p.swish_value >= 0 ? "pos" : "neg" }, F.millions(p.swish_value)),
    h("td", { class: "muted" }, `${F.millions(p.band.p10)} → ${F.millions(p.band.p90)}`),
    h("td", {}, p.pick.text))));
  v.append(h("div", { class: "card" }, h("h3", {}, "Detail"),
    h("div", { class: "table-wrap", style: "margin-top:14px" },
      h("table", {}, h("thead", {}, h("tr", {}, ...["Player", "Age", "Talent WAR", "Swish value", "10th–90th", "≈ pick"].map((x) => h("th", {}, x)))), tb))));

  if (players[0].percentiles.length) {
    const palette = [C.COL.accent, C.COL.cool, C.COL.pos, "#9d7bd8"];
    const axes = players[0].percentiles.map((p) => p.label.replace(/ \(.+\)/, ""));
    const card = h("div", { class: "card" }, h("h3", {}, "Skill percentiles"),
      h("div", { class: "chart", style: "max-width:420px;margin:10px auto 0" },
        C.radar(players.slice(0, 4).map((p, i) => ({
          name: p.player.name, color: palette[i], values: p.percentiles.map((x) => x.percentile),
        })), axes)));
    card.append(h("div", { class: "legend", style: "justify-content:center" }, ...players.slice(0, 4).map((p, i) =>
      h("span", {}, h("i", { style: `background:${palette[i]};height:10px;width:10px;border-radius:3px` }), p.player.name.split(" ").at(-1)))));
    v.append(card);
  }
}

// ------------------------------------------------------------------ trade
const tradeState = { a: [], b: [] };
function renderTrade() {
  const v = view();
  clear(v);
  v.append(h("h2", { class: "section-title" }, "Trade calculator"));
  v.append(h("p", { class: "section-sub" }, "Put players on each side. Swish weighs what each team gives up against what it gets back."));
  const A = sideBox("a", "Side A sends"), B = sideBox("b", "Side B sends");
  v.append(h("div", { class: "trade" }, A, h("div", { class: "mid" }, "⇄"), B));
  v.append(h("div", { id: "trade-out" }));
  paintBaskets();
  recomputeTrade();

  function sideBox(key, lbl) {
    const input = h("input", { name: "q", type: "search", placeholder: "add player…" });
    const addOne = (name) => { tradeState[key].push(name); paintBaskets(); recomputeTrade(); };
    const form = h("form", {
      onsubmit: (e) => { e.preventDefault(); const q = input.value.trim(); if (q) { input.value = ""; addOne(q); } },
    }, input);
    typeahead(input, (r) => addOne(r.name));
    return h("div", { class: "side", "data-side": key }, h("h4", {}, lbl), h("div", { class: "basket" }), form);
  }
}
function paintBaskets() {
  document.querySelectorAll(".side").forEach((box) => {
    const key = box.dataset.side;
    const basket = $(".basket", box);
    clear(basket);
    tradeState[key].forEach((name, idx) =>
      basket.append(h("div", { class: "p" }, h("span", {}, name),
        h("button", { type: "button", title: "remove", onclick: () => { tradeState[key].splice(idx, 1); paintBaskets(); recomputeTrade(); } }, "×"))));
  });
}
async function recomputeTrade() {
  const out = $("#trade-out");
  if (!out) return;
  clear(out);
  if (!tradeState.a.length || !tradeState.b.length) {
    out.append(h("p", { class: "muted", style: "margin-top:16px" }, "Add at least one player to each side.")); return;
  }
  out.append(h("div", { class: "sk sk-wide", style: "margin-top:16px" }));
  const mine = ++token;
  let r;
  try { r = await api.post("/trade", { side_a: tradeState.a, side_b: tradeState.b, params: qparams() }); }
  catch (e) { if (mine === token) { clear(out); out.append(errBox(e)); } return; }
  if (mine !== token) return;
  tradeState.a = r.side_a.players.map((p) => p.player.name);
  tradeState.b = r.side_b.players.map((p) => p.player.name);
  paintBaskets();
  clear(out);
  out.append(h("div", { class: "card", style: "margin-top:16px" }, h("h3", {}, "Value each side receives"),
    chart(C.compareBars([
      { label: "Side A gets", value: r.side_a.receives },
      { label: "Side B gets", value: r.side_b.receives },
    ], { rowH: 46 }))));
  const fair = r.verdict === "roughly fair";
  out.append(h("div", { class: "verdict " + (fair ? "fair" : "") },
    fair ? "Roughly fair" : `${r.verdict} — by ${F.millions(r.margin)}`));
}

// ------------------------------------------------------------------ leaderboard
async function renderLeaderboard() {
  const v = view();
  clear(v);
  v.append(h("h2", { class: "section-title" }, "Trade-value leaders"));
  v.append(h("div", { class: "sk sk-tall" }));
  let d;
  try { d = await api.get("/leaderboard", { limit: 50, min_minutes: 1000, ...qparams() }); }
  catch (e) { return renderError(e); }
  clear(v);
  v.append(h("h2", { class: "section-title" }, `Trade-value leaders · ${F.seasonLabel(d.season)}`));
  v.append(h("p", { class: "section-sub" }, d.note + " — click a player for the full, contract-adjusted number."));
  const tb = h("tbody", {});
  d.rows.forEach((r) => tb.append(h("tr", { class: "tap", onclick: () => (location.hash = `#/player/${r.pid}`) },
    h("td", { class: "rank" }, r.rank),
    h("td", {}, r.name),
    h("td", {}, r.age),
    h("td", {}, r.minutes.toLocaleString()),
    h("td", {}, F.war(r.war)),
    h("td", {}, F.millions(r.production_value)))));
  v.append(h("div", { class: "card" }, h("div", { class: "table-wrap" },
    h("table", {}, h("thead", {}, h("tr", {}, ...["#", "Player", "Age", "MP", "WAR", "Production value"].map((x) => h("th", {}, x)))), tb))));
}

// ------------------------------------------------------------------ method
function renderMethod() {
  const v = view();
  clear(v);
  v.append(h("div", { class: "card prose", html: METHOD }));
}
const METHOD = `
<h3>How the number is built</h3>
<p>Swish turns a player's Basketball-Reference stat line into an estimate of what he's worth as a trade asset. Every step is a plain function in <code>swish/model/</code>.</p>
<ol>
<li><b>Production → wins.</b> Blend VORP and Win Shares into wins above replacement, calibrated so the best players land near 15, not the 25+ a raw VORP×2.7 implies.</li>
<li><b>True talent.</b> Regress the last three seasons toward the player's own recent form, weighting recent, higher-minute seasons more.</li>
<li><b>Age curve.</b> Project each future season with a population aging curve — improvement into the mid-twenties, decline accelerating through the thirties.</li>
<li><b>Dollars.</b> Price the wins (~$3.3M each), grown with the cap and discounted, with a premium for production concentrated on one roster spot.</li>
<li><b>Contract.</b> Subtract guaranteed salary to get <i>surplus</i> value — a great player on a bad deal can be worth little.</li>
<li><b>Draft picks.</b> Map the surplus onto a pick-value curve so the answer reads as "≈ the #7 pick".</li>
<li><b>Uncertainty.</b> Resample talent, aging, health and $/win a few thousand times for the 10th–90th percentile band.</li>
</ol>
<p><b>Known limits:</b> box-score metrics underrate high-usage shot creators; the aging curve is a population average; options are treated as guaranteed; it needs recent NBA minutes to say anything.</p>
`;

// ------------------------------------------------------------------ error / landing / router
function errBox(e) {
  const box = h("div", { class: "err" }, h("div", { class: "msg" }, e instanceof ApiError ? e.message : "Something went wrong."));
  if (e instanceof ApiError && e.payload.suggestions?.length) {
    const s = h("div", { class: "sugg" }, "Did you mean: ");
    e.payload.suggestions.forEach((name, i) => {
      s.append(h("button", { onclick: () => (location.hash = `#/player/${encodeURIComponent(name)}`) }, name));
      if (i < e.payload.suggestions.length - 1) s.append(" · ");
    });
    box.append(s);
  }
  return box;
}
function renderError(e) { clear(view()); view().append(errBox(e)); }
function renderLanding() {
  const v = view();
  clear(v);
  const ex = h("div", { class: "ex" });
  ["Nikola Jokic", "Luka Doncic", "Victor Wembanyama", "Shai Gilgeous-Alexander", "Anthony Edwards"].forEach((n) =>
    ex.append(h("button", { onclick: () => (location.hash = `#/player/${encodeURIComponent(n)}`) }, n)));
  v.append(h("div", { class: "landing" },
    h("div", { class: "mark" }, "🏀"),
    h("h2", {}, "What's he worth in a trade?"),
    h("p", {}, "Search any NBA player. Swish reads his career and contract and estimates his trade value — with the math shown."),
    ex));
}
function setTab(name) {
  document.querySelectorAll("#tabs a").forEach((a) => a.classList.toggle("active", a.dataset.tab === name));
}
function route() {
  const [path, query] = (location.hash || "#/").slice(2).split("?");
  const params = new URLSearchParams(query || "");
  const parts = path.split("/").filter(Boolean);
  window.scrollTo(0, 0);
  if (parts[0] === "player" && parts[1]) { setTab(""); return renderPlayer(decodeURIComponent(parts.slice(1).join("/"))); }
  if (parts[0] === "compare") { setTab("compare"); return renderCompare(params.get("ids")); }
  if (parts[0] === "trade") { setTab("trade"); return renderTrade(); }
  if (parts[0] === "leaderboard") { setTab("leaderboard"); return renderLeaderboard(); }
  if (parts[0] === "method") { setTab("method"); return renderMethod(); }
  setTab(""); renderLanding();
}
async function boot() {
  initTheme();
  initSearch();
  $(".brand").addEventListener("click", () => (location.hash = "#/"));
  window.addEventListener("hashchange", route);
  try { $("#version").textContent = `Swish v${(await api.get("/meta")).version}`; } catch {}
  route();
}
boot();
