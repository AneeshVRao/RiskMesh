/* Verifies the ONE write path in the console: the Investigator action bar.
 *
 * The claim being tested is not "the button changes the screen" -- that is easy
 * and worthless. The claim is "the button changes the SERVER". So every
 * assertion about a recorded action is read back out-of-band, with Node's own
 * fetch against the API, never from the page that did the writing.
 *
 * Two halves, and the second is the point:
 *   A. Click Escalate -> the server's audit log gains exactly one matching
 *      record, and the timestamp and evidence hash rendered on screen are the
 *      ones the server stored.
 *   B. NEGATIVE CONTROL: abort the POST in the browser, click again, and the
 *      screen must refuse to show a record. If the UI were faking optimistic
 *      local state, A would pass and B would fail.
 *
 * Run with both servers up:  node mockups/verify-actions.mjs
 */
import { chromium } from "playwright";

const UI = "http://127.0.0.1:8080";
const API = "http://127.0.0.1:8000";
const CMP = "c_a00533";

let fail = 0;
const ok = (label, cond, detail = "") => {
  console.log(`   ${cond ? "ok  " : "FAIL"} ${label}${detail ? " — " + detail : ""}`);
  if (!cond) fail++;
};

/* Out-of-band read: the server's own copy, fetched by Node, not by the page. */
const serverAudit = async () =>
  (await (await fetch(`${API}/rings/${CMP}/evidence`)).json()).audit;

const before = await serverAudit();
console.log(`server audit for ${CMP} before any click: ${before.length} record(s)`);
if (before.length) {
  // The point of the run is watching an empty log gain exactly one record, so
  // it starts from the same clean state the pipeline leaves behind.
  console.log("start from a clean trail: delete out/audit_log.jsonl, then re-run");
  process.exit(1);
}

const browser = await chromium.launch();
const page = await browser.newPage();
const errors = [];
/* Part B aborts a request on purpose, and the browser logs that. Stop
 * collecting once we are the ones breaking things -- otherwise the negative
 * control reports its own success as a failure. */
let expectFailure = false;
page.on("pageerror", (e) => { if (!expectFailure) errors.push(`pageerror ${e.message}`); });
page.on("console", (m) => {
  if (!expectFailure && m.type() === "error") errors.push(m.text());
});

await page.goto(`${UI}/investigator.html`, { waitUntil: "networkidle" });
await page.waitForFunction(
  () => { const b = document.getElementById("api-status"); return b && !b.classList.contains("wait"); },
  { timeout: 8000 });

/* ---- A. the click must reach the server ------------------------------- */
console.log("\nA. click Escalate");
const esc = page.locator('.act button[data-act="escalate"]');
ok("Escalate enabled before any action", !(await esc.isDisabled()));

await esc.click();
await page.waitForFunction(
  () => document.querySelector(".act .hint").classList.contains("done"),
  { timeout: 8000 });

const after = await serverAudit();
ok("server gained exactly one record", after.length === before.length + 1,
   `${before.length} -> ${after.length}`);
const rec = after[0];
ok("record names the right component", rec.component_id === CMP, rec.component_id);
ok("record names the clicked action", rec.analyst_action === "escalate", rec.analyst_action);
ok("record carries an evidence snapshot",
   Array.isArray(rec.evidence_snapshot?.signals) && rec.evidence_snapshot.signals.length > 0,
   `${rec.evidence_snapshot?.signals?.length} signals`);
ok("record carries the band and fingerprint",
   rec.band?.t_lo !== undefined && !!rec.config_fingerprint,
   `band ${rec.band?.t_lo}/${rec.band?.t_hi} · cfg ${rec.config_fingerprint}`);

/* The screen must be showing THAT record -- same timestamp, same evidence
 * hash -- not a plausible-looking one it composed locally. */
const trail = await page.textContent(".trail");
ok("trail shows the server's timestamp", trail.includes(rec.ts), rec.ts);
ok("trail shows the server's evidence hash",
   trail.includes(rec.evidence_sha256.slice(0, 12)), rec.evidence_sha256.slice(0, 12));
ok("trail shows the recorded action", trail.includes("escalate"));
ok("confirmation names the log file",
   (await page.textContent(".act .hint")).includes("out/audit_log.jsonl"));
ok("Escalate is now disabled", await esc.isDisabled());
ok("Allow is still available (an analyst may change their mind)",
   !(await page.locator('.act button[data-act="allow"]').isDisabled()));

/* State came from the server, so it must survive a reload. */
await page.reload({ waitUntil: "networkidle" });
await page.waitForFunction(
  () => { const b = document.getElementById("api-status"); return b && !b.classList.contains("wait"); },
  { timeout: 8000 });
ok("Escalate still disabled after a full reload",
   await page.locator('.act button[data-act="escalate"]').isDisabled());
ok("trail survives a full reload", (await page.textContent(".trail")).includes(rec.ts));

/* ---- B. negative control: break the POST, the UI must go red ---------- */
expectFailure = true;
console.log("\nB. negative control — POST aborted in the browser");
await page.route("**/review", (route) =>
  route.request().method() === "POST" ? route.abort() : route.continue());

const mid = await serverAudit();
await page.locator('.act button[data-act="watch"]').click();
await page.waitForFunction(
  () => document.querySelector(".act .hint").classList.contains("bad"),
  { timeout: 8000 }).catch(() => {});

const post = await serverAudit();
const hint = await page.textContent(".act .hint");
const trail2 = await page.textContent(".trail");
ok("server wrote nothing", post.length === mid.length, `${mid.length} -> ${post.length}`);
ok("UI says it was not recorded", hint.includes("not recorded"), hint.trim());
ok("no fabricated 'watch' entry appeared in the trail", !trail2.includes("watch"));
ok("Watch is enabled again after the failure",
   !(await page.locator('.act button[data-act="watch"]').isDisabled()));
ok("the earlier real record is still shown", trail2.includes(rec.ts));

await browser.close();
console.log(`\njs errors: ${errors.length ? errors.join("; ") : "none"}`);
fail += errors.length;
console.log(fail === 0
  ? "\nWRITE PATH VERIFIED: clicks persist server-side, and a broken click cannot look like a good one"
  : `\n${fail} PROBLEM(S)`);
process.exit(fail === 0 ? 0 : 1);
