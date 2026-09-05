/* Click-through verification: every number the four tabs render must equal
 * what the API serves from the frozen record.
 *
 *   1. python -m uvicorn riskmesh.api.main:app --port 8000
 *   2. cd mockups && python -m http.server 8080
 *   3. npm i playwright && node verify-live.mjs
 *
 * Exits non-zero on any mismatch, any page that failed to reach the API, or
 * any JS console error.
 */
import { chromium } from "playwright";

const UI = "http://127.0.0.1:8080";
const API = "http://127.0.0.1:8000";

// Everything on screen must trace to the frozen record. Pull the API's own
// answers first, then assert the rendered DOM against them.
const api = Object.fromEntries(await Promise.all(
  ["/metrics", "/threshold-analysis", "/rings", "/benchmark"]
    .map(async (p) => [p, await (await fetch(API + p)).json()])
));

// Control Center opens on the top-ranked component (rings[0]) and
// Investigator opens on the top flagged one (flagged[0]) -- same rules
// api.js's initControlCenter/initInvestigator use. The frozen dataset's
// ranking changes on every re-freeze, so the id has to be discovered here
// too, never hardcoded (see tests/test_api.py's convention for the same).
const topId = api["/rings"].rings[0].component_id;
const flaggedId = api["/rings"].rings.filter((r) => r.action !== "allow")[0].component_id;
const [ccEvidence, invEvidence] = await Promise.all(
  [topId, flaggedId].map((id) =>
    fetch(`${API}/rings/${encodeURIComponent(id)}/evidence`).then((r) => r.json()))
);

const money = (v) => Number(v).toLocaleString("en-US",
  { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const f4 = (v) => Number(v).toFixed(4);

let fail = 0;
const eq = (label, got, want) => {
  const ok = String(got).trim() === String(want).trim();
  if (!ok) { console.log(`   MISMATCH ${label}: rendered ${JSON.stringify(got)} != frozen ${JSON.stringify(want)}`); fail++; }
  return ok;
};

const browser = await chromium.launch();
const errors = [];

async function open(page_file) {
  const page = await browser.newPage();
  page.on("console", (m) => { if (m.type() === "error") errors.push(`${page_file}: ${m.text()}`); });
  page.on("pageerror", (e) => errors.push(`${page_file}: pageerror ${e.message}`));
  await page.goto(`${UI}/${page_file}`, { waitUntil: "networkidle" });
  await page.waitForFunction(
    () => { const b = document.getElementById("api-status"); return b && !b.classList.contains("wait"); },
    { timeout: 8000 });
  const banner = (await page.textContent("#api-status")).trim();
  if (!banner.startsWith("live")) { console.log(`   NOT LIVE ${page_file}: ${banner}`); fail++; }
  return page;
}

const txt = (p, sel) => p.textContent(sel).then((t) => (t || "").trim());

/* ---------------- Control Center ---------------- */
{
  console.log("\nControl Center (b-mosaic.html)");
  const p = await open("b-mosaic.html");
  const m = api["/metrics"], t = api["/threshold-analysis"], r = api["/rings"];
  const hero = await p.locator(".figs.hero dd").allTextContents();
  eq("escalate tile", hero[0], m.triage.escalate);
  eq("review tile", hero[1], m.triage.review);
  eq("allow tile", hero[2], m.triage.allow);
  const subs = await p.locator(".figs.hero .sub").allTextContents();
  eq("escalate caption", subs[0], m.narration.escalate);
  eq("review caption", subs[1], m.narration.review);
  eq("allow caption", subs[2], m.narration.allow);
  const meta = await p.locator(".figs.meta dd").allTextContents();
  eq("expected loss", meta[0], money(m.cost.expected_loss));
  eq("saved", meta[1], money(Math.abs(m.cost.delta)));
  eq("queue row count", await p.locator("#queue-body tr").count(), r.rings.length);
  const first = p.locator("#queue-body tr").first();
  eq("queue row 1 id", await first.locator("td.id").textContent(), r.rings[0].component_id);
  eq("queue row 1 score", await first.locator("td.sc").textContent(), f4(r.rings[0].score));
  const bandLbl = await p.locator(".bandbar span").allTextContents();
  eq("band bar allow", bandLbl[0], `ALLOW · ${m.triage.allow}`);
  eq("band bar escalate", bandLbl[2], `ESCALATE · ${m.triage.escalate}`);
  const cost = await p.locator(".mod.q.c12 .figs dd").allTextContents();
  eq("C_review", cost[0], money(t.costs.manual_review));
  eq("C_fn", cost[1], money(t.costs.false_negative));
  eq("C_fp", cost[2], money(t.costs.false_positive));
  const ledger = await p.locator("table.ev tr").count();
  eq("evidence rows", ledger, ccEvidence.decomposition.signals.length);
  console.log(`   banner: ${await txt(p, "#api-status")}`);
  await p.close();
}

/* ---------------- Investigator ---------------- */
{
  console.log("\nInvestigator (investigator.html)");
  const p = await open("investigator.html");
  const ev = invEvidence, r = api["/rings"];
  const flagged = r.rings.filter((x) => x.action !== "allow");
  eq("picker entries", await p.locator(".pick a").count(), flagged.length);
  const rows = await p.locator("#ledger-body tr").count();
  eq("ledger rows", rows, ev.decomposition.signals.length);
  for (let i = 0; i < ev.decomposition.signals.length; i++) {
    const s = ev.decomposition.signals[i];
    const tds = await p.locator("#ledger-body tr").nth(i).locator("td").allTextContents();
    eq(`ledger[${s.name}].norm`, tds[2], f4(s.normalized));
    eq(`ledger[${s.name}].weight`, tds[3], f4(s.weight));
    eq(`ledger[${s.name}].contrib`, tds[4], f4(s.contribution));
  }
  eq("ledger total", await txt(p, "#ledger-total"), f4(ev.decomposition.score));
  const legend = await p.locator(".dleg b").allTextContents();
  const weighted = ev.decomposition.signals.filter((s) => s.weighted);
  eq("legend entries", legend.length, weighted.length + 1);
  eq("legend[0]", legend[0], weighted[0].contribution.toFixed(4).slice(1));
  const subj = await p.locator('[data-cmp="subject"] .kv dd').allTextContents();
  const peer = await p.locator('[data-cmp="peer"] .kv dd').allTextContents();
  eq("subject max acc/ip", subj[3], String(ev.comparison.subject.max_accounts_per_ip));
  eq("peer max acc/ip", peer[3], String(ev.comparison.peer.max_accounts_per_ip));
  eq("subject burst", subj[2], ev.comparison.subject.burst);
  eq("peer burst", peer[2], ev.comparison.peer.burst);
  console.log(`   banner: ${await txt(p, "#api-status")}`);
  await p.close();
}

/* ---------------- Threshold & Cost ---------------- */
{
  console.log("\nThreshold & Cost (threshold-cost.html)");
  const p = await open("threshold-cost.html");
  const t = api["/threshold-analysis"];
  const ladder = Object.fromEntries(t.ladder.map((x) => [x.policy, x.expected_loss]));
  const vals = await p.locator(".lval").allTextContents();
  eq("flag_nothing", vals[0], money(ladder.flag_nothing));
  eq("flag_everything", vals[1], money(ladder.flag_everything));
  eq("binary", vals[2], money(ladder.binary));
  eq("three_way", vals[3], money(ladder.three_way));
  eq("bands considered", await txt(p, '[data-b="t.search.bands_considered"]'),
     t.search.bands_considered.toLocaleString("en-US"));
  eq("bands refused", await txt(p, '[data-b="t.search.bands_refused_by_coverage"]'),
     t.search.bands_refused_by_coverage.toLocaleString("en-US"));
  console.log(`   banner: ${await txt(p, "#api-status")}`);
  await p.close();
}

/* ---------------- Benchmark ---------------- */
{
  console.log("\nBenchmark (benchmark.html)");
  const p = await open("benchmark.html");
  const b = api["/benchmark"];
  const cm = await p.locator(".cm .v").allTextContents();
  eq("TP", cm[0], b.primary.tp);
  eq("FN", cm[1], b.primary.fn);
  eq("FP", cm[2], b.primary.fp);
  eq("TN", cm[3], b.primary.tn);
  eq("panel rows", await p.locator("#panel-body tr").count(),
     Object.keys(b.panel.checks).length);
  eq("weight candidates", await p.locator("#weights-body tr").count(),
     b.weight_search.candidates.length);
  // Task 7a: seven PRD baselines, including Tier 2 (xgboost_scorer) refused
  // with no held-out read and Tier 3 (gnn_scorer) with a real one. A null
  // held_out on the refused row previously crashed the renderer's sort
  // comparator, which the top-level .catch swallowed -- the page fell back
  // to "API offline" and the static 5-row placeholder with no visible sign
  // of a bug. This guards against that regressing silently.
  eq("baseline rows", await p.locator("#base-body tr").count(),
     b.baselines.baselines.length);
  const baseText = await p.locator("#base-body").innerText();
  const refused = b.baselines.baselines.find((r) => r.feasible === false);
  eq("refused baseline visible", refused && baseText.includes(refused.baseline), true);
  eq("refusal reason visible", refused && baseText.includes(refused.status), true);
  const gnn = b.baselines.baselines.find((r) => r.baseline === "gnn_scorer");
  eq("gnn_scorer row visible", gnn && baseText.includes("gnn_scorer"), true);
  eq("gnn_scorer F1 rendered", gnn && baseText.includes(f4(gnn.held_out.f1)), true);
  const ss = await p.locator(".ssv").allTextContents();
  const best = Math.max(...Object.values(b.single_signal_max_f1));
  eq("top single-signal F1", ss[0], best.toFixed(4).slice(1));
  eq("single-signal rows", ss.length, Object.keys(b.single_signal_max_f1).length);
  console.log(`   banner: ${await txt(p, "#api-status")}`);
  await p.close();
}

await browser.close();
console.log(`\njs errors: ${errors.length ? errors.join("; ") : "none"}`);
if (errors.length) fail += errors.length;
console.log(fail === 0
  ? "\nALL RENDERED VALUES MATCH THE FROZEN RECORD"
  : `\n${fail} PROBLEM(S)`);
process.exit(fail === 0 ? 0 : 1);
