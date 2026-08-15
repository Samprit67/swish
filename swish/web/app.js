import { api, ApiError } from "./api.js";
import * as F from "./format.js";
import * as C from "./charts.js";

// -------------------------------------------------------------------------
// dom helpers
// -------------------------------------------------------------------------
function h(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "html") n.innerHTML = v;
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

let toastT;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastT);
  toastT = setTimeout(() => (t.hidden = true), 3000);
}
function loading(label = "Fetching from Basketball-Reference…") {
  clear(view());
  view().append(h("div", { class: "loading" }, h("span", { class: "spinner" }), label));
}

// -------------------------------------------------------------------------
// state (analytics controls, persisted)
// -------------------------------------------------------------------------
const DEFAULTS = { horizon: 3, discount: 0.08, dpw: 3.3, metric: "blend", use_contract: true };
const state = { ...DEFAULTS };
try { Object.assign(state, JSON.parse(localStorage.getItem("swish.params") || "{}")); } catch {}
const saveState = () => { try { localStorage.setItem("swish.params", JSON.stringify(state)); } catch {} };
const qparams = () => ({
  horizon: state.horizon,
  discount: state.discount,
  dollars_per_win: state.dpw,
  metric: state.metric,
  use_contract: state.use_contract,
});

// -------------------------------------------------------------------------
// theme
// -------------------------------------------------------------------------
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

// -------------------------------------------------------------------------
// search
// -------------------------------------------------------------------------
function initSearch() {
  const box = $("#search-input");
  const panel = $("#search-results");
  let timer, active = -1, rows = [];
  const close = () => { panel.hidden = true; active = -1; };

  box.addEventListener("input", () => {
    clearTimeout(timer);
    const q = box.value.trim();
    if (q.length < 2) return close();
    timer = setTimeout(async () => {
      try {
        const res = await api.get("/players/search", { q });
        rows = res.results;
        if (!rows.length) return close();
        clear(panel);
        rows.forEach((r, i) =>
          panel.append(h("button", { type: "button", onclick: () => pick(r) },
            h("span", {}, r.name),
            h("span", { class: "sr-meta" }, `${r.position || ""} · ${r.from_year}–${r.to_year}`))));
        panel.hidden = false;
        active = -1;
      } catch { close(); }
    }, 180);
  });
  box.addEventListener("keydown", (e) => {
    if (panel.hidden) return;
    const btns = [...panel.querySelectorAll("button")];
    if (e.key === "ArrowDown") { active = Math.min(active + 1, btns.length - 1); e.preventDefault(); }
    else if (e.key === "ArrowUp") { active = Math.max(active - 1, 0); e.preventDefault(); }
    else if (e.key === "Enter") { e.preventDefault(); return pick(rows[active] || rows[0]); }
    else if (e.key === "Escape") return close();
    btns.forEach((b, i) => b.classList.toggle("active", i === active));
  });
  $("#search").addEventListener("submit", (e) => { e.preventDefault(); if (rows[0]) pick(rows[active >= 0 ? active : 0]); });
  document.addEventListener("click", (e) => { if (!$("#search").contains(e.target)) close(); });

  function pick(r) {
    if (!r) return;
    box.value = "";
    close();
    location.hash = `#/player/${r.pid}`;
  }
}

// -------------------------------------------------------------------------
// analytics controls
// -------------------------------------------------------------------------
function controls(onChange) {
  const wrap = h("div", { class: "card" }, h("h3", {}, "Analytics"));
  const row = h("div", { class: "controls" });

  const slider = (key, label, min, max, step, fmt) => {
    const out = h("span", { class: "val" }, fmt(state[key]));
    const input = h("input", {
      type: "range", min, max, step, value: state[key],
      oninput: () => { out.textContent = fmt(+input.value); },
      onchange: () => { state[key] = +input.value; saveState(); onChange(); },
    });
    return h("div", { class: "control" }, h("label", {}, label, " ", out), input);
  };

  row.append(slider("horizon", "Horizon", 1, 5, 1, (v) => `${v} yr`));
  row.append(slider("discount", "Discount", 0, 0.2, 0.01, (v) => F.pct(v)));
  row.append(slider("dpw", "$ / win", 2, 6, 0.1, (v) => `$${v.toFixed(1)}M`));

  const seg = h("div", { class: "seg" });
  ["vorp", "blend", "ws"].forEach((m) =>
    seg.append(h("button", {
      class: state.metric === m ? "on" : "", type: "button",
      onclick: () => { state.metric = m; saveState(); [...seg.children].forEach((b) => b.classList.toggle("on", b.textContent.toLowerCase() === m)); onChange(); },
    }, m === "vorp" ? "VORP" : m === "ws" ? "Win Shares" : "Blend")));
  row.append(h("div", { class: "control" }, h("label", {}, "Metric"), seg));

  const cb = h("input", { type: "checkbox", ...(state.use_contract ? { checked: true } : {}),
    onchange: () => { state.use_contract = cb.checked; saveState(); onChange(); } });
  row.append(h("div", { class: "control" }, h("label", {}, "Contract"),
    h("label", { class: "toggle" }, cb, "subtract salary")));

  wrap.append(row);
  return wrap;
}

// -------------------------------------------------------------------------
// player view
// -------------------------------------------------------------------------
let playerToken = 0;
async function renderPlayer(ident) {
  const token = ++playerToken;
  loading();
  let data;
  try {
    data = await api.get(`/players/${encodeURIComponent(ident)}/value`, qparams());
  } catch (e) {
    if (token === playerToken) renderError(e);
    return;
  }
  if (token !== playerToken) return;
  paintPlayer(data);
}

function paintPlayer(d) {
  const v = view();
  clear(v);

  const pos = d.swish_value >= 0;
  const hero = h("div", { class: "card hero" },
    h("div", { class: "who" },
      h("div", { class: "name" }, d.player.name),
      h("div", { class: "meta" },
        [d.player.team || "free agent", d.player.positions, d.player.draft_pick ? `#${d.player.draft_pick} pick` : null]
          .filter(Boolean).join("  ·  ")),
      h("div", { class: "chips" },
        h("span", { class: "chip accent" }, `talent ${F.war(d.talent_war)} WAR`),
        h("span", { class: "chip" }, `proj from ${F.seasonLabel(d.first_projected_season)}`),
        h("span", { class: "chip cool" }, d.used_contract ? "surplus over contract" : "production value only"))),
    h("div", {},
      h("div", { class: "big " + (pos ? "pos" : "neg") }, F.millions(d.swish_value, 1)),
      h("div", { class: "range" }, `${F.millions(d.band.p10)}  to  ${F.millions(d.band.p90)}  (10th–90th)`),
      h("div", { class: "pick" }, "≈ " + d.pick.text)));
  v.append(hero);

  // histogram strip
  const hist = h("div", { class: "card" }, h("h3", {}, "Where the estimate could land"));
  hist.append(h("div", { class: "chart" },
    C.histogram(d.simulation.histogram, [
      { v: d.band.p10, label: "p10" }, { v: d.band.p50, label: "p50" }, { v: d.band.p90, label: "p90" },
    ], { w: 640, h: 96 })));
  v.append(hist);

  v.append(controls(() => renderPlayer(d.player.pid)));

  // charts row
  const grid = h("div", { class: "grid cols-2" });

  const traj = h("div", { class: "card" },
    h("h3", {}, "Career trajectory"),
    h("div", { class: "sub" }, "wins above replacement, by season"));
  const career = d.career && d.career.length ? d.career : d.talent.seasons.map((s) => ({ label: s.label, war: s.war_observed }));
  traj.append(h("div", { class: "chart" },
    C.lineChart(career.map((s) => s.label), [
      { points: career.map((s) => s.war), color: C.COL.accent, width: 2.5 },
    ], { zeroLine: true })));
  grid.append(traj);
  const seasons = d.talent.seasons;

  const fan = h("div", { class: "card" },
    h("h3", {}, "Projection"),
    h("div", { class: "sub" }, "median with a 10th–90th percentile band"));
  fan.append(h("div", { class: "chart" },
    C.fanChart(
      { label: seasons.at(-1).label, war: seasons.at(-1).war_observed },
      d.simulation.years.map((y, i) => ({
        label: F.seasonLabel(y.season_end), p10: y.p10, p50: y.p50, p90: y.p90,
      })),
    )));
  grid.append(fan);
  v.append(grid);

  // value waterfall
  const wf = h("div", { class: "card span-2" },
    h("h3", {}, d.used_contract ? "How the value is built" : "Production value by year"));
  const steps = [];
  d.value_years.forEach((y) => steps.push({ label: `${F.seasonLabel(y.season_end)}\nvalue`, delta: y.production_value }));
  if (d.used_contract) {
    d.value_years.forEach((y) => y.salary > 0 && steps.push({ label: `${F.seasonLabel(y.season_end)}\nsalary`, delta: -y.salary }));
    steps.push({ label: "Swish\nvalue", delta: d.swish_value, total: true });
  } else {
    steps.push({ label: "Production\nvalue", delta: d.swish_value, total: true });
  }
  wf.append(h("div", { class: "chart" }, C.waterfall(steps, { w: 660, h: 250 })));
  v.append(wf);

  // percentiles + projection table
  const grid2 = h("div", { class: "grid cols-2" });
  if (d.percentiles.length) {
    const pc = h("div", { class: "card" }, h("h3", {}, `League rank · ${F.seasonLabel(d.as_of_season)}`));
    const bars = h("div", { class: "pbars" });
    d.percentiles.forEach((p) => {
      bars.append(h("div", { class: "pbar" },
        h("span", {}, p.label),
        h("span", { class: "track" }, h("span", { class: "fill", style: `width:${p.percentile}%` })),
        h("span", { class: "pv" }, `${Math.round(p.percentile)}`)));
    });
    pc.append(bars);
    grid2.append(pc);
  }

  const pt = h("div", { class: "card" }, h("h3", {}, "Year by year"));
  const tbl = h("table", {},
    h("thead", {}, h("tr", {}, ...["Season", "Age", "WAR", "Value", d.used_contract ? "Salary" : "", d.used_contract ? "Surplus" : ""].filter(Boolean).map((x) => h("th", {}, x)))));
  const tb = h("tbody", {});
  d.value_years.forEach((y, i) => {
    const pj = d.projection[i];
    tb.append(h("tr", {},
      h("td", {}, F.seasonLabel(y.season_end)),
      h("td", {}, pj.age),
      h("td", {}, F.war(y.war)),
      h("td", {}, F.millions(y.production_value)),
      d.used_contract ? h("td", {}, y.salary ? F.millions(y.salary) : "—") : null,
      d.used_contract ? h("td", { class: y.surplus >= 0 ? "pos" : "neg" }, F.millions(y.surplus, 1)) : null));
  });
  tbl.append(tb);
  pt.append(h("div", { class: "table-wrap" }, tbl));
  grid2.append(pt);
  v.append(grid2);

  if (d.notes.length) {
    const nb = h("div", { class: "card" }, h("h3", {}, "Caveats"), h("div", { class: "notes" }, ...d.notes.map((n) => h("div", { class: "note" }, n))));
    v.append(nb);
  }

  const links = h("div", { class: "foot", style: "border:0;padding-top:6px" },
    h("span", {}, `as of ${F.seasonLabel(d.as_of_season)} · $${(d.params.dollars_per_win / 1e6).toFixed(1)}M per win · ${F.pct(d.params.discount_rate)} discount`),
    h("a", { href: `#/compare?ids=${d.player.pid}`, style: "color:var(--accent);font-weight:650;text-decoration:none" }, "add to compare →"));
  v.append(links);
}

// -------------------------------------------------------------------------
// compare view
// -------------------------------------------------------------------------
async function renderCompare(idsRaw) {
  const ids = (idsRaw || "").split(",").map((s) => s.trim()).filter(Boolean);
  const v = view();
  clear(v);
  v.append(h("h2", { style: "margin:0 0 4px" }, "Compare"));
  const adder = h("form", { class: "search", style: "max-width:340px;margin:12px 0 20px",
    onsubmit: (e) => { e.preventDefault(); const q = $("#cmp-add").value.trim(); if (q) location.hash = `#/compare?ids=${[...ids, q].join(",")}`; } },
    h("input", { id: "cmp-add", type: "search", placeholder: "add a player…" }));
  v.append(adder);

  if (ids.length < 2) {
    v.append(h("p", { class: "muted" }, "Add at least two players to compare."));
    return;
  }
  v.append(h("div", { class: "loading" }, h("span", { class: "spinner" }), "Valuing players…"));
  let data;
  try { data = await api.get("/compare", { ids: ids.join(","), ...qparams() }); }
  catch (e) { return renderError(e); }

  clear(v);
  v.append(h("h2", { style: "margin:0 0 16px" }, "Compare"));
  const players = [...data.players].sort((a, b) => b.swish_value - a.swish_value);

  const bars = h("div", { class: "card" }, h("h3", {}, "Swish value"));
  bars.append(h("div", { class: "chart" }, C.compareBars(players.map((p) => ({ label: p.player.name, value: p.swish_value })))));
  v.append(bars);

  const tbl = h("table", {},
    h("thead", {}, h("tr", {}, ...["Player", "Age", "Talent WAR", "Swish value", "10th–90th", "≈ pick", ""].map((x) => h("th", {}, x)))));
  const tb = h("tbody", {});
  players.forEach((p) => {
    tb.append(h("tr", {},
      h("td", {}, p.player.name),
      h("td", {}, p.projection[0].age),
      h("td", {}, F.war(p.talent.war)),
      h("td", { class: p.swish_value >= 0 ? "pos" : "neg" }, F.millions(p.swish_value)),
      h("td", { class: "muted" }, `${F.millions(p.band.p10)} – ${F.millions(p.band.p90)}`),
      h("td", {}, p.pick.text),
      h("td", {}, h("a", { href: `#/player/${p.player.pid}`, style: "color:var(--accent);text-decoration:none" }, "open"))));
  });
  tbl.append(tb);
  v.append(h("div", { class: "card" }, h("h3", {}, "Details"), h("div", { class: "table-wrap" }, tbl)));

  // radar-ish: percentile bars overlay
  if (players[0].percentiles.length) {
    const skills = players[0].percentiles.map((p) => p.key);
    const rc = h("div", { class: "card" }, h("h3", {}, "Skill percentiles"));
    const tbl2 = h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Skill"), ...players.map((p) => h("th", {}, p.player.name.split(" ").at(-1))))));
    const tb2 = h("tbody", {});
    players[0].percentiles.forEach((_, i) => {
      tb2.append(h("tr", {}, h("td", {}, players[0].percentiles[i].label),
        ...players.map((p) => h("td", {}, Math.round(p.percentiles[i].percentile)))));
    });
    tbl2.append(tb2);
    rc.append(h("div", { class: "table-wrap" }, tbl2));
    v.append(rc);
  }
}

// -------------------------------------------------------------------------
// trade view
// -------------------------------------------------------------------------
const tradeState = { a: [], b: [] };
async function renderTrade() {
  const v = view();
  clear(v);
  v.append(h("h2", { style: "margin:0 0 4px" }, "Trade calculator"));
  v.append(h("p", { class: "sub muted" }, "Put players on each side. Swish weighs what each team gives up against what it gets back."));

  const wrap = h("div", { class: "trade" });
  wrap.append(side("a", "Side A sends"));
  wrap.append(h("div", { class: "mid" }, "⇄"));
  wrap.append(side("b", "Side B sends"));
  v.append(wrap);
  const out = h("div", { id: "trade-out" });
  v.append(out);
  recompute();

  function side(key, label) {
    const box = h("div", { class: "side" }, h("h4", {}, label));
    const basket = h("div", { class: "basket" });
    tradeState[key].forEach((name) =>
      basket.append(h("div", { class: "p" }, h("span", {}, name),
        h("button", { type: "button", title: "remove", onclick: () => { tradeState[key] = tradeState[key].filter((x) => x !== name); renderTrade(); } }, "×"))));
    box.append(basket);
    box.append(h("form", { class: "add", onsubmit: (e) => { e.preventDefault(); const q = e.target.q.value.trim(); if (q) { tradeState[key].push(q); renderTrade(); } } },
      h("input", { name: "q", type: "search", placeholder: "add player…" })));
    return box;
  }

  async function recompute() {
    if (!tradeState.a.length || !tradeState.b.length) {
      clear(out);
      out.append(h("p", { class: "muted", style: "margin-top:16px" }, "Add at least one player to each side."));
      return;
    }
    clear(out);
    out.append(h("div", { class: "loading" }, h("span", { class: "spinner" }), "Valuing…"));
    let r;
    try { r = await api.post("/trade", { side_a: tradeState.a, side_b: tradeState.b, params: qparams() }); }
    catch (e) { clear(out); out.append(errBox(e)); return; }
    clear(out);
    const bars = C.compareBars([
      { label: "Side A gets", value: r.side_a.receives },
      { label: "Side B gets", value: r.side_b.receives },
    ], { rowH: 44 });
    out.append(h("div", { class: "card", style: "margin-top:16px" }, h("h3", {}, "Value each side receives"), h("div", { class: "chart" }, bars)));
    const fair = r.verdict === "roughly fair";
    out.append(h("div", { class: "verdict " + (fair ? "fair" : "") },
      fair ? "Roughly fair" : `${r.verdict} — by ${F.millions(r.margin)}`));
  }
}

// -------------------------------------------------------------------------
// leaderboard
// -------------------------------------------------------------------------
async function renderLeaderboard() {
  loading("Loading the league…");
  let d;
  try { d = await api.get("/leaderboard", { limit: 50, min_minutes: 1000, ...qparams() }); }
  catch (e) { return renderError(e); }
  const v = view();
  clear(v);
  v.append(h("h2", { style: "margin:0 0 4px" }, `Trade-value leaders · ${F.seasonLabel(d.season)}`));
  v.append(h("p", { class: "sub muted" }, d.note + " — click a player for the full, contract-adjusted number."));
  const tbl = h("table", {}, h("thead", {}, h("tr", {}, ...["#", "Player", "Age", "MP", "WAR", "Production value"].map((x) => h("th", {}, x)))));
  const tb = h("tbody", {});
  d.rows.forEach((r) => {
    tb.append(h("tr", { style: "cursor:pointer", onclick: () => (location.hash = `#/player/${r.pid}`) },
      h("td", {}, r.rank),
      h("td", {}, r.name),
      h("td", {}, r.age),
      h("td", {}, r.minutes.toLocaleString()),
      h("td", {}, F.war(r.war)),
      h("td", {}, F.millions(r.production_value))));
  });
  tbl.append(tb);
  v.append(h("div", { class: "card" }, h("div", { class: "table-wrap" }, tbl)));
}

// -------------------------------------------------------------------------
// method
// -------------------------------------------------------------------------
function renderMethod() {
  const v = view();
  clear(v);
  v.append(h("div", { class: "card", html: METHOD_HTML }));
}
const METHOD_HTML = `
<h3>How the number is built</h3>
<p style="color:var(--text-dim);max-width:60ch">Swish turns a player's Basketball-Reference stat line into an estimate of what he's worth as a trade asset. Every step is a plain function you can read in <code>swish/model/</code>.</p>
<ol style="line-height:1.9;max-width:65ch">
<li><b>Production → wins.</b> Blend VORP and Win Shares into wins above replacement, calibrated so the best players land near 15 (not the 25+ a raw VORP×2.7 implies).</li>
<li><b>True talent.</b> Regress the last three seasons toward the player's own recent form, weighting recent, higher-minute seasons more.</li>
<li><b>Age curve.</b> Project each future season with a population aging curve — improvement into the mid-twenties, decline accelerating through the thirties.</li>
<li><b>Dollars.</b> Price the wins (~$3.3M each), grown with the cap and discounted, with a premium for production concentrated in one roster spot.</li>
<li><b>Contract.</b> Subtract guaranteed salary to get <i>surplus</i> value — a great player on a bad deal can be worth little.</li>
<li><b>Draft picks.</b> Map the surplus onto a pick-value curve so the answer reads as "≈ the #7 pick".</li>
<li><b>Uncertainty.</b> Resample talent, aging, health and $/win a few thousand times for the 10th–90th percentile band.</li>
</ol>
<p style="color:var(--text-dim)"><b>Known limits:</b> box-score metrics underrate high-usage shot creators; the aging curve is a population average; options are treated as guaranteed; it needs recent NBA minutes to say anything.</p>
`;

// -------------------------------------------------------------------------
// errors, landing, router
// -------------------------------------------------------------------------
function errBox(e) {
  const box = h("div", { class: "err" }, e instanceof ApiError ? e.message : "Something went wrong.");
  if (e instanceof ApiError && e.payload.suggestions?.length) {
    const s = h("div", { class: "sugg" }, "Did you mean: ");
    e.payload.suggestions.forEach((name, i) => {
      s.append(h("button", { onclick: () => (location.hash = `#/player/${encodeURIComponent(name)}`) }, name));
      if (i < e.payload.suggestions.length - 1) s.append("· ");
    });
    box.append(s);
  }
  return box;
}
function renderError(e) {
  clear(view());
  view().append(errBox(e));
}
function renderLanding() {
  const v = view();
  clear(v);
  const ex = h("div", { class: "examples" });
  ["Nikola Jokic", "Luka Doncic", "Victor Wembanyama", "Shai Gilgeous-Alexander", "Chris Paul"].forEach((n) =>
    ex.append(h("button", { onclick: () => (location.hash = `#/player/${encodeURIComponent(n)}`) }, n)));
  v.append(h("div", { class: "landing" },
    h("div", { style: "font-size:44px" }, "🏀"),
    h("h2", {}, "What's he worth in a trade?"),
    h("p", {}, "Search any NBA player. Swish reads his career and contract and estimates his trade value — with the math shown."),
    ex));
}

function setTab(name) {
  document.querySelectorAll("#tabs a").forEach((a) => a.classList.toggle("active", a.dataset.tab === name));
}

function route() {
  const hash = location.hash || "#/";
  const [path, query] = hash.slice(2).split("?");
  const params = new URLSearchParams(query || "");
  const parts = path.split("/").filter(Boolean);
  window.scrollTo(0, 0);

  if (parts[0] === "player" && parts[1]) { setTab(""); return renderPlayer(decodeURIComponent(parts.slice(1).join("/"))); }
  if (parts[0] === "compare") { setTab("compare"); return renderCompare(params.get("ids")); }
  if (parts[0] === "trade") { setTab("trade"); return renderTrade(); }
  if (parts[0] === "leaderboard") { setTab("leaderboard"); return renderLeaderboard(); }
  if (parts[0] === "method") { setTab("method"); return renderMethod(); }
  setTab("");
  renderLanding();
}

async function boot() {
  initTheme();
  initSearch();
  $(".brand").addEventListener("click", () => (location.hash = "#/"));
  window.addEventListener("hashchange", route);
  try {
    const meta = await api.get("/meta");
    $("#version").textContent = `Swish v${meta.version}`;
  } catch {}
  route();
}
boot();
