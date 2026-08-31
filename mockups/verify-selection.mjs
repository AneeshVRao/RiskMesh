/* Verifies ring selection and the data-driven ring graph.
 *
 * The weak version of this check is "click a row, something changed". That
 * passes even if the panel renders a fixed drawing. So for every component the
 * script reads the SVG back out of the DOM, reconstructs the node ids, their
 * degrees and the edge count from what is actually painted, and compares that
 * against the graph block the API returned FOR THAT ID -- fetched separately by
 * Node, never taken from the page.
 *
 * The last section is the control that gives the rest its teeth: it asserts the
 * drawings for two different components are not the same drawing. Without it,
 * a renderer that ignored its input entirely would pass every equality above,
 * because it would be compared against whatever it happened to draw.
 *
 * Run with both servers up:  node mockups/verify-selection.mjs
 */
import { chromium } from "playwright";

const UI = "http://127.0.0.1:8080";
const API = "http://127.0.0.1:8000";

let fail = 0;
const ok = (label, cond, detail = "") => {
  console.log(`   ${cond ? "ok  " : "FAIL"} ${label}${detail ? " — " + detail : ""}`);
  if (!cond) fail++;
};
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);


const get = async (p) => (await fetch(API + p)).json();

/* What the page actually painted, read back out of the DOM. */
const painted = (page) => page.evaluate(() => {
  const svg = document.querySelector("#graph-host svg");
  if (!svg) return null;
  const HEADS = ["SHARED ATTRIBUTES", "ACCOUNTS", "MERCHANTS"];
  const labels = [...svg.querySelectorAll("text")]
    .map((t) => t.textContent.trim()).filter((t) => !HEADS.includes(t));
  return {
    accounts: labels.filter((t) => !t.includes("×")).sort(),
    nodes: labels.filter((t) => t.includes("×")).sort(),
    paths: svg.querySelectorAll("path").length,
    rects: svg.querySelectorAll("rect").length,
    alt: svg.getAttribute("aria-label"),
  };
});

const waitLive = (page) => page.waitForFunction(
  () => { const b = document.getElementById("api-status"); return b && !b.classList.contains("wait"); },
  { timeout: 8000 });

const browser = await chromium.launch();
const errors = [];
const watch = (page, tag) => {
  page.on("pageerror", (e) => errors.push(`${tag}: pageerror ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") errors.push(`${tag}: ${m.text()}`); });
};

/* Compare the painted graph against the API's answer for this exact id. */
async function checkComponent(page, id, where) {
  const ev = await get(`/rings/${id}/evidence`);
  const g = ev.graph;
  const p = await painted(page);
  console.log(`\n${where} -> ${id}  (${ev.action}, ${g.accounts.length} accounts, `
    + `${g.nodes.length} nodes, ${g.edges.length} edges)`);

  ok("panel header names the selected component",
     (await page.textContent("#sel-id")).trim() === id);
  ok("graph drew this component's accounts",
     same(p.accounts, [...g.accounts].sort()),
     `${p.accounts.length} drawn`);
  ok("graph drew this component's nodes with the API's degrees",
     same(p.nodes, g.nodes.map((n) => `${n.id} ×${n.degree}`).sort()),
     `${p.nodes.length} drawn`);
  ok("one path per edge in the API's graph", p.paths === g.edges.length,
     `${p.paths} vs ${g.edges.length}`);
  ok("one box per account plus one per node",
     p.rects === g.accounts.length + g.nodes.length,
     `${p.rects} vs ${g.accounts.length + g.nodes.length}`);
  ok("alt text names this component", p.alt.includes(id));

  // Signals must move with the graph, not lag a component behind.
  const rows = await page.locator("#ledger-body tr").count().catch(() => 0);
  if (rows) {
    ok("signal ledger row count matches", rows === ev.decomposition.signals.length);
    const first = await page.locator("#ledger-body tr").first().locator("td").allTextContents();
    ok("first signal is this component's",
       first[0].includes(ev.decomposition.signals[0].name),
       first[0].split("\n")[0].trim());
    ok("ledger total is this component's score",
       (await page.textContent("#ledger-total")).trim()
         === ev.decomposition.score.toFixed(4),
       ev.decomposition.score.toFixed(4));
  } else {
    const ledger = await page.locator("table.ev tr").count();
    ok("evidence table row count matches", ledger === ev.decomposition.signals.length);
  }

  // Action bar: with a clean audit log nothing is recorded, so all four are live.
  const dis = await page.locator(".act button[data-act]:disabled").count();
  ok("action bar reflects this component's audit trail",
     dis === new Set(ev.audit.map((a) => a.analyst_action)).size,
     `${dis} disabled, ${ev.audit.length} record(s)`);
  return p;
}

/* ---- Investigator: click three different components in the picker ------- */
const rings = (await get("/rings")).rings;
const flagged = rings.filter((r) => r.action !== "allow");
const allow = rings.find((r) => r.action === "allow");
// Two escalates of different shape and one review household -- the review is
// the household whose graph is IP-heavy where the rings are device-heavy.
const targets = [
  flagged[0].component_id,
  flagged.find((r) => r.action === "review").component_id,
  flagged.filter((r) => r.action === "escalate").slice(-1)[0].component_id,
];

const inv = await browser.newPage();
watch(inv, "investigator");
await inv.goto(`${UI}/investigator.html`, { waitUntil: "networkidle" });
await waitLive(inv);

console.log(`picker entries: ${await inv.locator(".pick a[data-cid]").count()}`);
const drawings = {};
for (const id of targets) {
  if (id !== targets[0]) {
    await inv.locator(`.pick a[data-cid="${id}"]`).click();
    await inv.waitForFunction(
      (want) => document.getElementById("sel-id").textContent.trim() === want,
      id, { timeout: 8000 });
  }
  drawings[id] = await checkComponent(inv, id, "picker click");
  ok("picker marks the selection",
     await inv.locator(`.pick a[data-cid="${id}"][aria-current="true"]`).count() === 1);
}

/* ---- Control Center: click an allow row in the queue -------------------- */
const cc = await browser.newPage();
watch(cc, "control-center");
await cc.goto(`${UI}/b-mosaic.html`, { waitUntil: "networkidle" });
await waitLive(cc);
await cc.locator(`#queue-body tr[data-cid="${allow.component_id}"]`).click();
await cc.waitForFunction(
  (want) => document.getElementById("sel-id").textContent.trim() === want,
  allow.component_id, { timeout: 8000 });
drawings[allow.component_id] = await checkComponent(cc, allow.component_id, "queue click");
ok("queue marks the selected row",
   await cc.locator(`#queue-body tr[data-cid="${allow.component_id}"][aria-selected="true"]`).count() === 1);
ok("only one row is marked",
   await cc.locator("#queue-body tr[aria-selected]").count() === 1);

/* ---- the control: different components must draw differently ----------- */
console.log("\ncontrol — four components, four distinct drawings");
const ids = Object.keys(drawings);
let distinct = 0;
for (let i = 0; i < ids.length; i++) {
  for (let k = i + 1; k < ids.length; k++) {
    const a = drawings[ids[i]], b = drawings[ids[k]];
    const differs = !same(a.accounts, b.accounts) || !same(a.nodes, b.nodes);
    if (differs) distinct++;
    else console.log(`   FAIL ${ids[i]} and ${ids[k]} painted the same graph`);
  }
}
ok("every pair of components painted a different graph",
   distinct === (ids.length * (ids.length - 1)) / 2,
   `${distinct} of ${(ids.length * (ids.length - 1)) / 2} pairs differ`);

/* ---- negative control: tamper the payload, the drawing must follow ----- */
/* Distinct drawings prove the renderer reacts to something. This proves what:
 * a node's degree is rewritten in flight and the box on screen has to show the
 * rewritten number. A renderer reading anything but the payload fails here. */
console.log("\nnegative control — a node's degree rewritten in flight");
const victim = targets[0];
const real = await get(`/rings/${victim}/evidence`);
const target = real.graph.nodes[0];

const tam = await browser.newPage();
watch(tam, "tampered");
await tam.route(`**/rings/${victim}/evidence`, async (route) => {
  const body = JSON.parse(JSON.stringify(real));
  body.graph.nodes[0].degree = 99;
  await route.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify(body) });
});
await tam.goto(`${UI}/investigator.html`, { waitUntil: "networkidle" });
await waitLive(tam);
const bad = await painted(tam);
ok("the drawing shows the tampered degree",
   bad.nodes.includes(`${target.id} ×99`), `${target.id} ×99`);
ok("the drawing no longer matches the real API response",
   !same(bad.nodes, real.graph.nodes.map((n) => `${n.id} ×${n.degree}`).sort()));
await tam.close();

await browser.close();
console.log(`\njs errors: ${errors.length ? errors.join("; ") : "none"}`);
fail += errors.length;
console.log(fail === 0
  ? "\nSELECTION VERIFIED: every panel follows the clicked component, and the graph "
    + "is the API's graph for that id"
  : `\n${fail} PROBLEM(S)`);
process.exit(fail === 0 ? 0 : 1);
