import { chromium } from "playwright";
const API = "http://127.0.0.1:8000";
const UI = "http://127.0.0.1:8080/investigator.html";

let fail = 0;
const ok = (l, c, d = "") => {
  console.log(`   ${c ? "ok  " : "FAIL"} ${l}${d ? " — " + d : ""}`);
  if (!c) fail++;
};

const b = await chromium.launch();

/* --- A: the narration matches what /explain itself returns ---------------- */
{
  const p = await b.newPage({ viewport: { width: 1500, height: 1200 } });
  const errs = [];
  p.on("pageerror", (e) => errs.push(e.message));
  p.on("console", (m) => { if (m.type() === "error") errs.push(m.text()); });
  await p.goto(UI, { waitUntil: "networkidle" });
  await p.waitForFunction(() => {
    const x = document.getElementById("api-status");
    return x && !x.classList.contains("wait");
  }, { timeout: 8000 });

  // Three different components, each checked against a SEPARATE call to the
  // API made by node -- never against the response the page itself received.
  const ids = await p.$$eval(".pick a[data-cid]", (as) =>
    as.slice(0, 4).map((a) => a.dataset.cid));
  ok("picker exposes at least 3 components", ids.length >= 3, ids.join(" "));

  for (const id of ids.slice(0, 3)) {
    await p.click(`.pick a[data-cid="${id}"]`);
    await p.waitForFunction(
      (cid) => document.querySelector("#sel-id")?.textContent.trim() === cid,
      id, { timeout: 5000 });
    await p.waitForFunction(
      () => {
        const t = document.querySelector("#explain .ntext");
        return t && t.textContent.trim() && t.textContent.trim() !== "…";
      }, { timeout: 5000 });

    const truth = await (await fetch(API + "/explain", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ component_id: id }),
    })).json();

    const shown = await p.$eval("#explain .ntext", (e) => e.textContent.trim());
    const src = await p.$eval("#explain .nsrc", (e) => e.textContent.trim());
    ok(`${id}: sentence == API text`, shown === truth.text,
       shown === truth.text ? "" : `page "${shown}" vs api "${truth.text}"`);
    ok(`${id}: every grounded signal named in the source line`,
       truth.grounded_in.every((s) => src.includes(s)), src);
    ok(`${id}: fallback state disclosed`,
       truth.fallback_used ? src.includes("no model called") : src.includes("model narration"), src);
    // Grounding contract: the sentence may only assert what the scorer said.
    const ev = await (await fetch(`${API}/rings/${id}/evidence`)).json();
    const details = ev.decomposition.signals.map((s) => s.detail);
    const parts = shown.replace(/\.$/, "").split(". ").map((s) => s.trim());
    ok(`${id}: every clause is a frozen detail string (no invention)`,
       parts.every((c) => details.some((d) => d.replace(/\.$/, "").trim() === c)),
       parts.filter((c) => !details.some((d) => d.replace(/\.$/, "").trim() === c)).join(" | "));
  }

  // Two different components must not share a sentence.
  const seen = [];
  for (const id of ids.slice(0, 3)) {
    await p.click(`.pick a[data-cid="${id}"]`);
    await p.waitForFunction(
      (cid) => document.querySelector("#sel-id")?.textContent.trim() === cid,
      id, { timeout: 5000 });
    await p.waitForFunction(() => {
      const t = document.querySelector("#explain .ntext");
      return t && t.textContent.trim() && t.textContent.trim() !== "…";
    }, { timeout: 5000 });
    seen.push(await p.$eval("#explain .ntext", (e) => e.textContent.trim()));
  }
  ok("three components produce three distinct narrations",
     new Set(seen).size === 3, seen.join(" || "));

  ok("no js errors", errs.length === 0, errs.join("; "));
  fail += errs.length;
  await p.close();
}

/* --- B: negative control. Kill /explain; evidence must survive intact ------ */
{
  const p = await b.newPage({ viewport: { width: 1500, height: 1200 } });
  await p.route("**/explain", (route) => route.abort());
  await p.goto(UI, { waitUntil: "networkidle" });
  await p.waitForFunction(() => {
    const x = document.getElementById("api-status");
    return x && !x.classList.contains("wait");
  }, { timeout: 8000 });

  const id = await p.$eval(".pick a[data-cid]", (a) => a.dataset.cid);
  await p.click(`.pick a[data-cid="${id}"]`);
  await p.waitForFunction(
    (cid) => document.querySelector("#sel-id")?.textContent.trim() === cid,
    id, { timeout: 5000 });

  // The detector's own evidence must be fully rendered even though the
  // narration is dead -- this is the "non-blocking" claim, tested.
  const rows = await p.$$eval("#ledger-body tr", (rs) => rs.length);
  const total = await p.$eval("#ledger-total", (e) => e.textContent.trim());
  const bars = await p.$$eval(".dbar i", (is) => is.length);
  const nodes = await p.$$eval("#graph-host svg *", (n) => n.length);
  ok("control: ledger still rendered with /explain dead", rows === 7, `${rows} rows`);
  ok("control: score total still rendered", /^0\.\d{4}$/.test(total), total);
  ok("control: decomposition bar still rendered", bars > 0, `${bars} segments`);
  ok("control: graph still drawn", nodes > 10, `${nodes} svg nodes`);

  await p.waitForFunction(
    () => document.getElementById("explain")?.classList.contains("bad"),
    { timeout: 5000 }).catch(() => {});
  const bad = await p.$eval("#explain", (e) => e.classList.contains("bad"));
  const shown = await p.$eval("#explain .ntext", (e) => e.textContent.trim());
  const src = await p.$eval("#explain .nsrc", (e) => e.textContent.trim());
  ok("control: narration reports itself unavailable", bad && src.includes("unavailable"), src);
  ok("control: no stale sentence left behind", shown === "", `"${shown}"`);
  await p.close();
}

await b.close();
console.log(fail === 0 ? "\nEXPLAIN WIRED AND GROUNDED" : `\n${fail} PROBLEM(S)`);
process.exit(fail === 0 ? 0 : 1);
