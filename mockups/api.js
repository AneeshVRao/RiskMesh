/* RiskMesh console -> live API.
 *
 * The static HTML stays the skeleton and the fallback: if the API is not
 * running the pages still render the frozen figures they shipped with, and the
 * banner says so. When it is running, every bound element is overwritten from
 * the API, so a number on screen can only come from out/.
 *
 * Binding: data-b="dotted.path" reads from the page's payload, data-f names a
 * formatter. Repeating sections (queue, ledger, picker) are rendered in JS
 * because their length comes from the data.
 */
const API = "http://127.0.0.1:8000";

async function j(path) {
  const r = await fetch(API + path);
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}

const F = {
  raw: (v) => String(v),
  int: (v) => Number(v).toLocaleString("en-US"),
  money: (v) => Number(v).toLocaleString("en-US",
    { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
  f4: (v) => Number(v).toFixed(4),
  f3: (v) => Number(v).toFixed(3),
  pct2: (v) => (Number(v) * 100).toFixed(2) + "%",
  pct1: (v) => (Number(v) * 100).toFixed(1) + "%",
  pct0: (v) => Math.round(Number(v) * 100) + "%",
  days: (v) => `${v} d`,
};

/* Escape any value that reaches innerHTML. This data comes from our own
 * read-only local API over synthetic records -- there is no user-input path in
 * this UI at all -- but interpolating unescaped strings into markup is a habit
 * worth not having, and the fix is four lines. */
function esc(v) {
  return String(v).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function get(obj, path) {
  return path.split(".").reduce((o, k) => (o == null ? o : o[k]), obj);
}

function bind(data, root = document) {
  root.querySelectorAll("[data-b]").forEach((el) => {
    const v = get(data, el.dataset.b);
    if (v === undefined || v === null) return;
    el.textContent = (F[el.dataset.f] || F.raw)(v);
  });
}

/* --- status banner ----------------------------------------------------- */
function banner(state, detail) {
  let el = document.getElementById("api-status");
  if (!el) {
    el = document.createElement("div");
    el.id = "api-status";
    document.querySelector(".rail-1").appendChild(el);
  }
  el.className = "apist " + state;
  el.textContent = detail;
}

/* --- shared row builders ----------------------------------------------- */
const ICON = {
  escalate: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 2 20h20L12 3z"/><path d="M12 11v3"/></svg>',
  review: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 8v5"/></svg>',
  allow: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12.5l5.2 5L20 7"/></svg>',
};
const TAGCLS = { escalate: "t-e", review: "t-r", allow: "t-a" };
const ABBR = { escalate: "Esc", review: "Rev", allow: "Alw" };

function tag(action) {
  return `<span class="tag ${TAGCLS[action]}">${ICON[action]}${ABBR[action]}</span>`;
}

function labelCell(r) {
  if (r.label && r.label !== "family") return esc(r.label);
  if (r.has_family) return '<span class="fam">family</span>';
  return '<span class="fam">-</span>';
}

/* --- Control Center ----------------------------------------------------- */
async function initControlCenter() {
  const [m, t, rings] = await Promise.all([
    j("/metrics"), j("/threshold-analysis"), j("/rings"),
  ]);
  // Open on the top-ranked component rather than a hardcoded id: /rings is
  // ordered by score, so the queue and the detail panel agree by construction.
  const ev = await selectComponent(rings.rings[0].component_id);
  const ladder = Object.fromEntries(t.ladder.map((r) => [r.policy, r.expected_loss]));
  const view = {
    m, t,
    saved: Math.abs(m.cost.delta),
    savedPct: Math.abs(m.cost.delta) / m.cost.binary_baseline,
    total: rings.total_in_split,
    negatives: m.quality.rings_in_test !== undefined
      ? rings.total_in_split - m.quality.rings_in_test : null,
    ladder,
    cmp: ev.comparison,
    ratio: Math.round(t.costs.false_negative / t.costs.false_positive),
  };
  bind(view);

  // band bar flex weights follow the real counts
  const bar = document.querySelector(".bandbar");
  if (bar) {
    const seg = { allow: ".b-allow", review: ".b-rev", escalate: ".b-esc" };
    for (const [k, sel] of Object.entries(seg)) {
      const el = bar.querySelector(sel);
      if (el) {
        el.style.flex = String(m.triage[k]);
        el.querySelector("span").textContent =
          `${k.toUpperCase()} · ${m.triage[k]}`;
      }
    }
  }

  // queue
  const tb = document.getElementById("queue-body");
  if (tb) {
    tb.innerHTML = rings.rings.map((r) => `
      <tr data-cid="${esc(r.component_id)}" tabindex="0"${
        r.component_id === CURRENT ? ' aria-selected="true"' : ""}>
        <td class="id">${esc(r.component_id)}</td>
        <td>${tag(r.action)}</td>
        <td class="r sc">${F.f4(r.score)}</td>
        <td class="r">${r.size}</td>
        <td class="r">${r.n_txns}</td>
        <td class="r">${F.money(r.exposure)}</td>
        <td>${labelCell(r)}</td>
      </tr>`).join("");
  }

  wireSelection();
  wireActions();
  banner("live", `live · ${m.config_fingerprint} · ${rings.total_in_split} components`);
}

/* --- evidence ledger (shared by Control Center + Investigator) ---------- */
function renderLedger(ev, table) {
  if (!table) return;
  const rows = ev.decomposition.signals.map((s) => `
    <tr${s.weighted ? "" : ' class="off"'}>
      <td><div class="nm">${esc(s.name.replace(/_/g, " "))}</div>
          <div class="dt">${esc(s.detail)}${s.note ? " (" + esc(s.note) + ")" : ""}</div></td>
      <td class="v">${F.f4(s.contribution)}</td>
      <td class="wt">w ${F.f4(s.weight)}</td>
      <td class="cb"><div class="mini${s.weighted ? "" : " off"}">
        <i style="width:${Math.max(2, (s.contribution / ev.decomposition.signals[0].contribution) * 100).toFixed(0)}%"></i>
      </div></td>
    </tr>`).join("");
  table.innerHTML = rows;
}

/* --- ring graph --------------------------------------------------------- */
/* Drawn from the `graph` block in the evidence payload -- the same
 * out/graph_edges.json the pipeline froze -- so the picture belongs to whichever
 * component is selected instead of being one component someone drew by hand.
 *
 * Three columns, left to right: shared attributes -> accounts -> merchants.
 * That is the order the finding is actually argued in ("one device carries nine
 * accounts, and those accounts converge on one merchant"), and it keeps the
 * widest column to 11 rows on this data.
 *
 * The layout is arithmetic, not a force simulation. Identical input has to give
 * an identical picture or the drawing cannot be checked against the API the way
 * every other number on screen is.
 */
const KIND = {
  device: { color: "#d81f26", op: 0.9, w: 1.6 },
  instrument: { color: "#a8171d", op: 0.9, w: 1.6 },
  ip: { color: "#8f5400", op: 0.75, w: 1.2 },
  merchant: { color: "#5c6670", op: 0.22, w: 0.8 },
};
const COLUMN = { device: 0, instrument: 1, ip: 2 };
const G = { BW: 88, BH: 20, PITCH: 26, TOP: 28, PAD: 12, W: 470,
  X: { left: 4, mid: 191, right: 378 } };

const byId = (a, b) => (a.id < b.id ? -1 : 1);
const merchants = (g) => g.nodes.filter((n) => n.type === "merchant")
  .sort((a, b) => b.degree - a.degree || byId(a, b));
const shared = (g) => g.nodes.filter((n) => n.type !== "merchant")
  .sort((a, b) => COLUMN[a.type] - COLUMN[b.type] || b.degree - a.degree || byId(a, b));

function renderGraph(ev, host) {
  if (!host || !ev.graph) return;
  const g = ev.graph;
  const left = shared(g), right = merchants(g), accts = g.accounts;
  // Floor the row count so the panel does not resize under the cursor while an
  // analyst clicks down the queue. Columns are centred, so a small component
  // sits in the middle of a steady frame instead of snapping the page shorter.
  const rows = Math.max(left.length, accts.length, right.length, 9);
  const H = G.TOP + rows * G.PITCH + G.PAD;

  const P = new Map();
  const lay = (items, x) => {
    const top = G.TOP + ((rows - items.length) * G.PITCH) / 2;
    items.forEach((it, i) => {
      const y = top + i * G.PITCH;
      P.set(typeof it === "string" ? it : it.id, { x, y, cy: y + G.BH / 2 });
    });
  };
  lay(left, G.X.left);
  lay(accts, G.X.mid);
  lay(right, G.X.right);

  // Edge thickness follows transaction count; merchant edges are the numerous
  // low-weight ones and stay faint so the structural links stay readable.
  const maxTxn = g.edges.reduce((m, e) => Math.max(m, e.txns), 1);
  const wires = g.edges.map((e) => {
    const k = KIND[e.kind] || KIND.merchant;
    const a = P.get(e.account), n = P.get(e.node);
    if (!a || !n) return "";
    const [s, t] = e.kind === "merchant" ? [a, n] : [n, a];
    const x1 = s.x + G.BW, x2 = t.x, m = (x1 + x2) / 2;
    const w = (k.w * (0.5 + 0.5 * (e.txns / maxTxn))).toFixed(2);
    return `<path d="M${x1} ${s.cy}C${m} ${s.cy} ${m} ${t.cy} ${x2} ${t.cy}" `
      + `fill="none" stroke="${k.color}" stroke-width="${w}" opacity="${k.op}"/>`;
  }).join("");

  const box = (id, stroke, label, heavy) => {
    const p = P.get(id);
    return `<rect x="${p.x}" y="${p.y}" width="${G.BW}" height="${G.BH}" fill="#fff" `
      + `stroke="${stroke}" stroke-width="${heavy ? 1.8 : 1.2}"/>`
      + `<text x="${p.x + G.BW / 2}" y="${p.y + 14}" text-anchor="middle" `
      + `font-family="ui-monospace,monospace" font-size="11" fill="#111418">${esc(label)}</text>`;
  };
  const boxes =
    left.map((n) => box(n.id, KIND[n.type].color, `${n.id} ×${n.degree}`,
      n.degree === accts.length)).join("")
    + accts.map((a) => box(a, "#767d87", a)).join("")
    + right.map((n) => box(n.id, KIND.merchant.color, `${n.id} ×${n.degree}`)).join("");

  const head = (x, t, n) => (n ? `<text x="${x}" y="15" font-family="ui-monospace,monospace" `
    + `font-size="10" fill="#767d87">${t}</text>` : "");
  const heads = head(G.X.left, "SHARED ATTRIBUTES", left.length)
    + head(G.X.mid, "ACCOUNTS", accts.length)
    + head(G.X.right, "MERCHANTS", right.length);

  const top = left[0];
  const alt = `Component ${ev.component_id}: ${accts.length} accounts, ${left.length} shared `
    + `attribute nodes, ${right.length} merchants, ${g.edges.length} links. `
    + (top ? `Most shared: ${top.type} ${top.id}, on ${top.degree} of ${accts.length} accounts.`
      : "No shared attributes.");

  host.innerHTML = `<svg class="g" viewBox="0 0 ${G.W} ${H}" role="img" `
    + `aria-label="${esc(alt)}">${heads}${wires}${boxes}</svg>`;
}

function graphCaption(ev) {
  const g = ev.graph, n = g.accounts.length;
  const top = shared(g).slice().sort((a, b) => b.degree - a.degree)[0];
  const m = merchants(g)[0];
  const out = [`<b>${n}</b> accounts · <b>${g.nodes.length}</b> shared nodes · `
    + `<b>${g.edges.length}</b> links.`];
  if (top) {
    out.push(`Strongest link: ${esc(top.type)} <b>${esc(top.id)}</b> on `
      + `<b>${top.degree}</b> of ${n} accounts.`);
  }
  if (m) out.push(`Busiest merchant <b>${esc(m.id)}</b> takes <b>${m.degree}</b>.`);
  // Said plainly because the two panels genuinely count different things: a
  // household can show nine IP boxes here and still score 6 on ip_sharing.
  out.push("Only attributes shared by two or more accounts are drawn, capped "
    + "infrastructure (<b>ip_nat*</b>) included — the ip_sharing signal skips "
    + "capped IPs, so the node count here is not the signal.");
  return out.join(" ");
}

/* --- component selection ------------------------------------------------- */
/* One function knows how to draw a component, so the Control Center and the
 * Investigator cannot drift apart about what "selected" means. Everything it
 * renders comes from the single /rings/{id}/evidence response for that id --
 * no panel is left holding the previous component's numbers. */
function setText(id, v) {
  const el = document.getElementById(id);
  if (el) el.textContent = v;
}

function ringLabel(ev) {
  return ev.summary.ring_id || (ev.summary.has_family ? "family" : "unlabelled");
}

async function selectComponent(id) {
  const ev = await j(`/rings/${encodeURIComponent(id)}/evidence`);
  CURRENT = ev.component_id;
  bind({ ev, cmp: ev.comparison });

  renderGraph(ev, document.getElementById("graph-host"));
  const cap = document.getElementById("graph-cap");
  if (cap) cap.innerHTML = graphCaption(ev);
  renderLedger(ev, document.querySelector("table.ev"));
  renderLedgerFull(ev);
  renderDecomposition(ev);
  renderComparison(ev.comparison);
  renderAudit(ev.audit);

  setText("sel-id", ev.component_id);
  setText("sel-meta", `${ringLabel(ev)} · ${ev.summary.size} accounts · ${ev.action}`);
  setText("sel-ring", ringLabel(ev));
  setText("sel-disp", ev.action.toUpperCase());
  setText("sel-score", F.f4(ev.decomposition.score));

  // Queue rows style off [aria-selected=true] and picker links off
  // [aria-current]; toggleAttribute would set a valueless attribute and miss
  // the first selector, so set the value explicitly.
  const marker = (el) => (el.tagName === "A" ? "aria-current" : "aria-selected");
  document.querySelectorAll("[data-cid]").forEach((el) => {
    if (el.dataset.cid === ev.component_id) el.setAttribute(marker(el), "true");
    else el.removeAttribute(marker(el));
  });
  return ev;
}

async function pickTo(id) {
  try {
    const ev = await selectComponent(id);
    if (document.body.dataset.page === "investigator") {
      banner("live", `live · ${ev.config_fingerprint} · ${ev.component_id}`);
    }
  } catch (err) {
    banner("down", `could not load ${id} — ${err.message}`);
  }
}

/* Delegated, so a re-rendered queue or picker keeps working. */
function wireSelection() {
  const pick = document.querySelector(".pick");
  if (pick && !pick.dataset.wired) {
    pick.dataset.wired = "1";
    pick.addEventListener("click", (e) => {
      const a = e.target.closest("a[data-cid]");
      if (!a) return;
      e.preventDefault();
      pickTo(a.dataset.cid);
    });
  }
  const tb = document.getElementById("queue-body");
  if (tb && !tb.dataset.wired) {
    tb.dataset.wired = "1";
    tb.addEventListener("click", (e) => {
      const tr = e.target.closest("tr[data-cid]");
      if (tr) pickTo(tr.dataset.cid);
    });
    // Table rows are not focusable by default, and a queue you can only reach
    // with a mouse is not a queue an analyst can work.
    tb.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" && e.key !== " ") return;
      const tr = e.target.closest("tr[data-cid]");
      if (!tr) return;
      e.preventDefault();
      pickTo(tr.dataset.cid);
    });
  }
}

/* --- action bar --------------------------------------------------------- */
/* The one write path in the whole console. A click posts to
 * /rings/{id}/review, and then the trail is RE-READ from the server rather than
 * patched in place: what you see after a click is what actually persisted to
 * out/audit_log.jsonl, so a write that silently failed cannot look like one
 * that succeeded. Button state is derived from that same server copy, which is
 * why it survives a reload. */
let CURRENT = null;
let AUDIT = [];

function wireActions() {
  const bar = document.querySelector(".act");
  if (!bar || bar.dataset.wired) return;
  bar.dataset.wired = "1";
  bar.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("button[data-act]");
    if (!btn || btn.disabled || !CURRENT) return;
    const hint = bar.querySelector(".hint");
    const act = btn.dataset.act;
    bar.querySelectorAll("button[data-act]").forEach((b) => (b.disabled = true));
    hint.className = "hint";
    hint.textContent = "recording…";
    try {
      const path = `/rings/${encodeURIComponent(CURRENT)}/review`;
      const r = await fetch(API + path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: act, analyst: "demo" }),
      });
      if (!r.ok) throw new Error(`${path} -> ${r.status}`);
      const fresh = await j(`/rings/${encodeURIComponent(CURRENT)}/evidence`);
      renderAudit(fresh.audit);
      hint.className = "hint done";
      hint.textContent =
        `recorded ${act} · ${fresh.audit[0].ts} · out/audit_log.jsonl`;
    } catch (err) {
      renderAudit(AUDIT); // restore the state the server last confirmed
      hint.className = "hint bad";
      hint.textContent = `not recorded — ${err.message}`;
    }
  });
}

/* --- Investigator ------------------------------------------------------- */
async function initInvestigator() {
  const rings = await j("/rings");
  const flagged = rings.rings.filter((r) => r.action !== "allow");
  bind({ rings, flagged: flagged.length });
  const ev = await selectComponent(flagged[0].component_id);

  // picker
  const pick = document.querySelector(".pick");
  if (pick) {
    const group = (action, title) => {
      const rows = flagged.filter((r) => r.action === action);
      return `<div class="hdg">${title} · ${rows.length}</div>` + rows.map((r) => `
        <a href="#" data-cid="${esc(r.component_id)}"${
          r.component_id === CURRENT ? ' aria-current="true"' : ""}>
          <span class="pid">${esc(r.component_id)}</span>
          <span class="psc">${F.f4(r.score)}</span>
          <span class="plb">${esc(r.label || "family")} · ${r.size} accounts</span>
          <span class="ptag">${tag(r.action)}</span>
        </a>`).join("");
    };
    pick.innerHTML = group("escalate", "Escalate") + group("review", "Review");
  }

  wireSelection();
  wireActions();
  banner("live", `live · ${ev.config_fingerprint} · ${ev.component_id}`);
}

function renderDecomposition(ev) {
  const bar = document.querySelector(".dbar");
  const leg = document.querySelector(".dleg");
  if (!bar || !leg) return;
  const shades = ["#d81f26", "#a8171d", "#8f5400", "#b07a2e", "#5c6670", "#8a939c"];
  const weighted = ev.decomposition.signals.filter((s) => s.weighted);
  bar.innerHTML = weighted.map((s, i) => {
    const w = Math.round(s.contribution * 10000);
    return `<i style="flex:${w};background:${shades[i % shades.length]}">` +
      (w > 600 ? `<span>${s.contribution.toFixed(4).slice(1)}</span>` : "") + "</i>";
  }).join("") +
    `<i style="flex:${Math.round(ev.decomposition.headroom * 10000)};background:#eceef1"></i>`;
  leg.innerHTML = weighted.map((s, i) =>
    `<span><i style="background:${shades[i % shades.length]}"></i>${s.name} <b>${s.contribution.toFixed(4).slice(1)}</b></span>`
  ).join("") +
    `<span><i style="background:#eceef1"></i>headroom <b>${ev.decomposition.headroom.toFixed(4).slice(1)}</b></span>`;
}

function renderLedgerFull(ev) {
  const tb = document.getElementById("ledger-body");
  const tf = document.getElementById("ledger-total");
  if (!tb) return;
  const shades = { device_sharing: "#d81f26", temporal_burst: "#a8171d",
    account_newness: "#8f5400", failure_refund_rate: "#b07a2e",
    instrument_sharing: "#5c6670", merchant_concentration: "#8a939c",
    ip_sharing: "#e3e6ea" };
  tb.innerHTML = ev.decomposition.signals.map((s) => `
    <tr${s.weighted ? "" : ' class="off"'}>
      <td><span class="sw" style="background:${shades[s.name] || "#8a939c"}"></span>
          <span class="nm">${esc(s.name)}</span>
          <div class="dt">${esc(s.detail)}${s.note ? " — " + esc(s.note) + "" : ""}</div></td>
      <td>${typeof s.raw === "number" && !Number.isInteger(s.raw) ? s.raw.toFixed(4) : s.raw}</td>
      <td>${F.f4(s.normalized)}</td>
      <td>${F.f4(s.weight)}</td>
      <td>${F.f4(s.contribution)}</td>
    </tr>`).join("");
  if (tf) tf.textContent = F.f4(ev.decomposition.score);
}

function renderComparison(cmp) {
  if (!cmp) return;
  const rows = [
    ["Accounts", "accounts", F.int],
    ["Median account age", "median_account_age_days", F.days],
    ["Burst convergence", "burst", F.raw],
    ["Max accounts per IP", "max_accounts_per_ip", F.int],
    ["Shared instruments", "shared_instruments", F.int],
    ["Refund rate", "refund_rate", F.pct1],
    ["Exposure", "exposure", F.money],
  ];
  for (const side of ["subject", "peer"]) {
    const host = document.querySelector(`[data-cmp="${side}"] .kv`);
    const head = document.querySelector(`[data-cmp="${side}"] .cmph`);
    const d = cmp[side];
    if (head) {
      head.textContent =
        `${esc(d.component_id)} · ${esc(d.label || "family")} · ${esc(d.action)} ${F.f4(d.score)}`;
    }
    if (!host) continue;
    host.innerHTML = rows.map(([lbl, key, fmt]) => {
      const hot = cmp.separating_fields.includes(key);
      const cls = hot ? (side === "subject" ? ' class="hi"' : ' class="lo"') : "";
      return `<dt>${lbl}</dt><dd${cls}>${fmt(d[key])}</dd>`;
    }).join("");
  }
}

function renderAudit(audit) {
  AUDIT = audit || [];
  // An action already on the server's record for this component cannot be
  // recorded twice; changing your mind to a different action still can be.
  const done = new Set(AUDIT.map((a) => a.analyst_action));
  document.querySelectorAll(".act button[data-act]").forEach((b) => {
    b.disabled = done.has(b.dataset.act);
    b.title = b.disabled ? "already recorded for this component" : "";
  });

  const host = document.querySelector(".trail");
  if (!host) return;
  if (!AUDIT.length) {
    host.innerHTML =
      '<div>No analyst actions recorded yet. Actions post to ' +
      '<b>/rings/{id}/review</b> and append to out/audit_log.jsonl.</div>';
    return;
  }
  host.innerHTML = AUDIT.map((a) => {
    const s = a.evidence_snapshot || {};
    const sum = s.summary || {};
    return `
    <div><b>${esc(a.ts)}</b> · ${esc(a.component_id)} · score <b>${F.f4(a.score)}</b>
      · band ${a.band.t_lo}/${a.band.t_hi} · analyst <b>${esc(a.analyst_action)}</b>
      ${a.agreed_with_system ? "" : "· <b>overrode</b> system " + esc(a.system_action)}
      · cfg ${esc(a.config_fingerprint)}</div>
    <div>evidence snapshot · ${(s.signals || []).length} signals ·
      ${esc(sum.size)} accounts · ${esc(sum.n_txns)} txns ·
      sha ${esc(String(a.evidence_sha256).slice(0, 12))}</div>`;
  }).join("");
}

/* --- Threshold & Cost --------------------------------------------------- */
async function initThreshold() {
  const t = await j("/threshold-analysis");
  const ladder = Object.fromEntries(t.ladder.map((r) => [r.policy, r]));
  bind({ t, ladder,
    ratio: Math.round(t.costs.false_negative / t.costs.false_positive),
    eligible: t.search.bands_considered - t.search.bands_refused_by_coverage,
    refusedPct: t.search.bands_refused_by_coverage / t.search.bands_considered,
  });
  // ladder bars scale against the worst case
  const worst = ladder.flag_nothing.expected_loss;
  document.querySelectorAll("[data-ladder]").forEach((el) => {
    const row = ladder[el.dataset.ladder];
    if (row) el.style.width = ((row.expected_loss / worst) * 100).toFixed(2) + "%";
  });
  const gcut = document.querySelector(".g-cut");
  const gok = document.querySelector(".g-ok");
  if (gcut && gok) {
    gcut.style.flex = String(t.search.bands_refused_by_coverage);
    gok.style.flex = String(t.search.bands_considered - t.search.bands_refused_by_coverage);
  }
  banner("live", `live · ${t.config_fingerprint}`);
}

/* --- Benchmark ---------------------------------------------------------- */
async function initBenchmark() {
  const b = await j("/benchmark");
  bind({ b, ring_pct: b.primary.ring_recovery_rate });

  const ss = document.querySelector(".ss");
  if (ss) {
    const entries = Object.entries(b.single_signal_max_f1).sort((a, c) => c[1] - a[1]);
    const top = entries[0][1];
    ss.innerHTML = entries.map(([name, f1]) => `
      <div class="ssrow"><span class="ssn">${esc(name)}</span>
        <span class="sst"><i class="${f1 === top ? "hi" : ""}" style="width:${(f1 * 100).toFixed(2)}%"></i></span>
        <span class="ssv">${f1.toFixed(4).slice(1)}</span></div>`).join("") +
      `<div class="sslg"><span>0.0</span><span>best single signal ${top.toFixed(4)}</span><span>1.0</span></div>`;
  }

  const wt = document.getElementById("weights-body");
  if (wt) {
    const PILL = { PASS: "p-pass", FAIL: "p-ref" };
    wt.innerHTML = b.weight_search.candidates.map((c) => `
      <tr><td><span class="nm">${esc(c.policy)}</span>
        <div class="why">${esc(c.reason || (c.policy === "A_baseline"
          ? "Retained. Frozen as the shipped scorer."
          : "Feasible; not preferred over the incumbent."))}</div></td>
        <td class="r ${c.panel_verdict === "FAIL" ? "bad" : ""}">${esc(c.panel_verdict)}</td>
        <td class="r">${F.f4(c.positives_below_max_negative)}</td>
        <td class="r">${c.hard_negatives_inside_positive_range}</td>
        <td class="r">${c.expected_loss == null ? "—" : F.money(c.expected_loss)}</td>
        <td class="r"><span class="pill ${c.feasible ? "p-pass" : "p-ref"}">${
          c.feasible ? (c.policy === "A_baseline" ? "Kept" : "Tied") : "Refused"}</span></td>
      </tr>`).join("");
  }

  /* PRD row 63. Ordered by held-out F1, best first, so a baseline that beats
   * the shipped scorer sits above it rather than needing to be looked for. */
  const bb = document.getElementById("base-body");
  if (bb && b.baselines) {
    const rows = b.baselines.baselines;
    const ship = rows.find((r) => r.baseline === "ring_score").held_out.f1;
    bb.innerHTML = [...rows].sort((x, y) => y.held_out.f1 - x.held_out.f1).map((r) => {
      const h = r.held_out, hard = r.held_out_hard_negatives_only;
      // A challenger at or above the shipped scorer is marked, not buried.
      const beat = r.baseline !== "ring_score" && h.f1 >= ship ? " bad" : "";
      return `<tr><td><span class="nm">${esc(r.baseline)}</span>
        <div class="why">${esc(r.description)}</div></td>
        <td class="r">${esc(r.uses_graph)}</td>
        <td class="r">${r.direction === ">=" ? "≥" : "≤"} ${esc(r.cutoff)}</td>
        <td class="r${beat}">${F.f4(h.f1)}</td>
        <td class="r">${F.f4(h.false_positive_rate)}</td>
        <td class="r${hard.f1 >= 1 ? " bad" : ""}">${F.f4(hard.f1)}</td></tr>`;
    }).join("");
  }

  /* PRD row 70. Full model first, then the groups ordered by how much removing
   * them costs -- most damaging at the top. */
  const ab = document.getElementById("abl-body");
  if (ab && b.ablations) {
    const cfgs = b.ablations.configurations;
    const full = cfgs.find((c) => c.group === "full");
    const rest = cfgs.filter((c) => c.group !== "full")
      .sort((x, y) => x.delta_f1 - y.delta_f1);
    const row = (c, isFull) => {
      const h = c.held_out, d = c.delta_f1;
      const cls = isFull || d === 0 ? "" : d < 0 ? " bad" : " good";
      const why = isFull
        ? `All seven signals · threshold ${c.threshold} · rings ${h.rings_recovered}/${h.rings_in_test}`
        : c.identical_to_full
          ? `${esc(c.signals_removed.join(", "))} · weight already 0.0 (RISK-001) · identical to full by construction`
          : `${esc(c.signals_removed.join(", "))} · threshold ${c.threshold} · rings ${h.rings_recovered}/${h.rings_in_test}`;
      return `<tr><td><span class="nm">${isFull ? "— full model" : esc(c.group)}</span>
        <div class="why">${why}</div></td>
        <td class="r">${isFull ? "—" : F.f4(c.weight_removed)}</td>
        <td class="r">${F.f4(h.f1)}</td>
        <td class="r${cls}">${isFull ? "—" : (d > 0 ? "+" : "") + F.f4(d)}</td>
        <td class="r">${F.f4(c.held_out_hard_negatives_only.f1)}</td></tr>`;
    };
    ab.innerHTML = row(full, true) + rest.map((c) => row(c, false)).join("");
  }

  const pb = document.getElementById("panel-body");
  if (pb) {
    pb.innerHTML = Object.entries(b.panel.checks).map(([name, c]) => `
      <tr><td class="why">${esc(name.replace(/_/g, " "))}</td>
        <td class="r">${c.value === null ? "—" : esc(Array.isArray(c.value) ? c.value.join(", ") : c.value)}</td>
        <td class="r">${esc(c.bound)}</td>
        <td class="r"><span class="pill ${c.status === "PASS" ? "p-pass" : "p-flag"}">${esc(c.status)}</span></td>
      </tr>`).join("");
  }
  banner("live", `live · ${b.config_fingerprint} · read once`);
}

/* --- boot --------------------------------------------------------------- */
const PAGES = {
  "control-center": initControlCenter,
  investigator: initInvestigator,
  threshold: initThreshold,
  benchmark: initBenchmark,
};

document.addEventListener("DOMContentLoaded", () => {
  const page = document.body.dataset.page;
  const init = PAGES[page];
  if (!init) return;
  banner("wait", "connecting…");
  init().catch((err) => {
    // The static values stay on screen; say plainly that they are not live.
    banner("down", `API offline — showing the static frozen values (${err.message})`);
  });
});
