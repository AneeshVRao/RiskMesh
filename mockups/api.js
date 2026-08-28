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
  const [m, t, rings, ev] = await Promise.all([
    j("/metrics"), j("/threshold-analysis"), j("/rings"),
    j("/rings/c_a00533/evidence"),
  ]);
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
    tb.innerHTML = rings.rings.map((r, i) => `
      <tr${i === 0 ? ' aria-selected="true"' : ""}>
        <td class="id">${esc(r.component_id)}</td>
        <td>${tag(r.action)}</td>
        <td class="r sc">${F.f4(r.score)}</td>
        <td class="r">${r.size}</td>
        <td class="r">${r.n_txns}</td>
        <td class="r">${F.money(r.exposure)}</td>
        <td>${labelCell(r)}</td>
      </tr>`).join("");
  }

  renderLedger(ev, document.querySelector("table.ev"));
  CURRENT = ev.component_id;
  renderAudit(ev.audit);   // no trail on this page; this sets the button state
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
  const [rings, ev] = await Promise.all([j("/rings"), j("/rings/c_a00533/evidence")]);
  const flagged = rings.rings.filter((r) => r.action !== "allow");
  bind({ ev, rings, cmp: ev.comparison, flagged: flagged.length });

  // picker
  const pick = document.querySelector(".pick");
  if (pick) {
    const group = (action, title) => {
      const rows = flagged.filter((r) => r.action === action);
      return `<div class="hdg">${title} · ${rows.length}</div>` + rows.map((r) => `
        <a href="#"${r.component_id === ev.component_id ? ' aria-current="true"' : ""}>
          <span class="pid">${esc(r.component_id)}</span>
          <span class="psc">${F.f4(r.score)}</span>
          <span class="plb">${esc(r.label || "family")} · ${r.size} accounts</span>
          <span class="ptag">${tag(r.action)}</span>
        </a>`).join("");
    };
    pick.innerHTML = group("escalate", "Escalate") + group("review", "Review");
  }

  renderDecomposition(ev);
  renderLedgerFull(ev);
  renderComparison(ev.comparison);
  CURRENT = ev.component_id;
  renderAudit(ev.audit);
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
