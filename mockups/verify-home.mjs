import { chromium } from "playwright";
const API = "http://127.0.0.1:8000";
const UI = "http://127.0.0.1:8080/index.html";

let fail = 0;
const ok = (l, c, d = "") => {
  console.log(`   ${c ? "ok  " : "FAIL"} ${l}${d ? " — " + d : ""}`);
  if (!c) fail++;
};

const b = await chromium.launch();
const errs = [];

/* --- desktop -------------------------------------------------------------- */
const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
p.on("pageerror", (e) => errs.push(e.message));
p.on("console", (m) => { if (m.type() === "error") errs.push(m.text()); });
await p.goto(UI, { waitUntil: "networkidle" });
await p.waitForFunction(() => document.querySelector("#hero-graph svg"), { timeout: 8000 });

// 1. The hero graph must be the component the API actually ranks first,
//    fetched separately by node -- never taken from the page that drew it.
const rings = await (await fetch(API + "/rings")).json();
const topId = rings.rings[0].component_id;
const ev = await (await fetch(`${API}/rings/${topId}/evidence`)).json();

ok("hero names the API's top-ranked component",
   (await p.$eval("#hero-id", (e) => e.textContent.trim())) === topId, topId);
ok("hero score matches that component",
   (await p.$eval("#hero-score", (e) => e.textContent.trim())) === ev.decomposition.score.toFixed(4));
const rects = await p.$$eval("#hero-graph svg rect", (r) => r.length);
const paths = await p.$$eval("#hero-graph svg path", (r) => r.length);
const expectBoxes = ev.graph.accounts.length + ev.graph.nodes.length;
ok("every graph node is drawn", rects === expectBoxes, `${rects} vs ${expectBoxes}`);
ok("every graph edge is drawn", paths === ev.graph.edges.length,
   `${paths} vs ${ev.graph.edges.length}`);
ok("fallback text was replaced by the real drawing",
   !(await p.$eval("#hero-graph", (e) => e.textContent)).includes("Start the API"));

// 2. Live figures must equal /metrics, not the static skeleton.
const m = await (await fetch(API + "/metrics")).json();
const money = (v) => Number(v).toLocaleString("en-US",
  { minimumFractionDigits: 2, maximumFractionDigits: 2 });
ok("expected loss bound live",
   (await p.$eval('[data-b="cost.expected_loss"]', (e) => e.textContent.trim()))
   === money(m.cost.expected_loss));
ok("escalated false positives bound live",
   (await p.$eval('[data-b="quality.escalated_false_positives"]', (e) => e.textContent.trim()))
   === String(m.quality.escalated_false_positives));

// 3. Content cuts actually happened.
const body = await p.$eval("body", (e) => e.innerText);
// "Bench" as a whole word only: "Benchmark" is a real screen and must stay.
for (const gone of ["Direction B", "Mosaic", "Cyclorama", "Assay", "\\bBench\\b",
                    "Ground", "Density", "nothing is wired", "Not yet drawn"]) {
  ok(`removed: "${gone}"`, !new RegExp(gone).test(body));
}
const links = await p.$$eval("a[href]", (as) => as.map((a) => a.getAttribute("href")));
ok("no links to the old direction mockups",
   !links.some((h) => /a-assay|c-cyclorama|d-bench/.test(h)), links.join(" "));

// 4. Craft floor / taste checks that are mechanical.
ok("zero em-dashes and en-dashes in visible copy",
   !/[\u2014\u2013]/.test(body), (body.match(/[\u2014\u2013]/g) || []).join(""));
ok("no scroll cue", !/scroll/i.test(body));
const dotLines = body.split("\n").filter((l) => (l.match(/·/g) || []).length > 1);
ok("no line spams the middle dot", dotLines.length <= 1, dotLines.join(" | "));

// 5. Layout: no horizontal overflow, nav on one line, hero above the fold.
const over = await p.evaluate(() =>
  document.documentElement.scrollWidth - document.documentElement.clientWidth);
ok("no horizontal page scroll at 1440", over <= 0, `${over}px`);
const topH = await p.$eval(".top", (e) => e.getBoundingClientRect().height);
ok("masthead height <= 80px", topH <= 80, `${topH}px`);
const ctaBottom = await p.$eval(".cta", (e) => e.getBoundingClientRect().bottom);
ok("hero CTAs visible without scrolling", ctaBottom < 900, `${Math.round(ctaBottom)}px`);
const h1Lines = await p.$eval("h1", (e) =>
  Math.round(e.getBoundingClientRect().height /
    parseFloat(getComputedStyle(e).lineHeight)));
ok("headline is at most 3 lines", h1Lines <= 3, `${h1Lines} lines`);
// Count the text's own line boxes. Comparing element height to line-height
// counts the button's padding as a second line and fails a button that is fine.
const wrapped = await p.$$eval(".cta a", (as) => as.filter((a) => {
  const r = document.createRange();
  r.selectNodeContents(a);
  return r.getClientRects().length > 1;
}).length);
ok("no CTA label wraps", wrapped === 0, `${wrapped} wrapped`);

// 6. The row index is a real hit target and keyboard reachable.
const rowH = await p.$$eval(".row", (rs) => rs.map((r) =>
  Math.round(r.getBoundingClientRect().height)));
ok("every screen row is a comfortable target", rowH.every((h) => h >= 44), rowH.join(" "));

await p.screenshot({ path: "C:/Users/ankit/.claude/jobs/3423769f/tmp/home-desktop.png",
  fullPage: true });

/* --- mobile --------------------------------------------------------------- */
const mp = await b.newPage({ viewport: { width: 390, height: 844 } });
mp.on("pageerror", (e) => errs.push(e.message));
await mp.goto(UI, { waitUntil: "networkidle" });
await mp.waitForFunction(() => document.querySelector("#hero-graph svg"), { timeout: 8000 });
const mOver = await mp.evaluate(() =>
  document.documentElement.scrollWidth - document.documentElement.clientWidth);
ok("no horizontal page scroll at 390", mOver <= 0, `${mOver}px`);
const cols = await mp.$eval(".figs", (e) => getComputedStyle(e).gridTemplateColumns);
ok("figures collapse to one column on mobile", !cols.includes(" "), cols);
await mp.screenshot({ path: "C:/Users/ankit/.claude/jobs/3423769f/tmp/home-mobile.png",
  fullPage: true });

/* --- negative control: API down ------------------------------------------- */
const dp = await b.newPage({ viewport: { width: 1440, height: 900 } });
await dp.route("**/127.0.0.1:8000/**", (r) => r.abort());
await dp.goto(UI, { waitUntil: "networkidle" });
await dp.waitForTimeout(1200);
const dBody = await dp.$eval("body", (e) => e.innerText);
ok("control: says the API is offline rather than passing stale numbers off as live",
   /offline/i.test(dBody), dBody.split("\n").find((l) => /offline/i.test(l)) || "no notice");
ok("control: hero degrades to an honest line, not an empty box",
   dBody.includes("Start the API"));
ok("control: the page still renders its sections",
   (await dp.$$eval(".row", (r) => r.length)) === 4);

ok("no js errors", errs.length === 0, errs.join("; "));
fail += errs.length;

await b.close();
console.log(fail === 0 ? "\nLANDING PAGE VERIFIED" : `\n${fail} PROBLEM(S)`);
process.exit(fail === 0 ? 0 : 1);
