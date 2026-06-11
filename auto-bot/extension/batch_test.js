// batch_test.js — AutoBot Batch Test Mode
// Calls the backend /fb/scrape_url endpoint for each dealer and scores results.
// SINGLE SOURCE OF TRUTH for the dealer list — both panel.js and test_harness.py
// must stay in sync with this list.

// Export the URL list so panel.js can read the count for the button label.
// Domain corrections applied June 2026 — see test_urls_verified.txt for details.
export const BATCH_DEALER_URLS = [
  // ── CORAL SPRINGS AREA ──────────────────────────────────────────────────
  "https://www.coralspringsautomall.com/new-inventory/index.htm",

  // ── RICK CASE AUTOMOTIVE GROUP ───────────────────────────────────────────
  "https://www.rickcasehonda.com/new-inventory/index.htm",
  "https://www.rickcaseacura.com/new-inventory/index.htm",
  "https://www.rickcasemazda.com/new-inventory/index.htm",
  // CORRECTED: rickcasehyundai.com (404) -> rickcase.com/hyundai
  "https://www.rickcase.com/hyundai/new-inventory/index.htm",
  // CORRECTED: rickcasevw.com (404) -> rickcasevolkswagen.com
  "https://www.rickcasevolkswagen.com/new-inventory/index.htm",
  // CORRECTED: rickcasealfaromeo.com (404) -> alfaromeousaofdavie.com
  "https://www.alfaromeousaofdavie.com/new-inventory/index.htm",
  "https://www.rickcasemitsubishi.com/new-inventory/index.htm",

  // ── BROWARD / PALM BEACH ─────────────────────────────────────────────────
  "https://www.toyotaofcoconutcreek.com/new-inventory/index.htm",
  // CORRECTED: bramanbmw.com (wrong) -> split into two real stores
  "https://www.bramanbmwwpb.com/new-inventory/index.htm",
  "https://www.bramanbmwjupiter.com/new-inventory/index.htm",
  "https://www.bramanmiamibmw.com/new-inventory/index.htm",
  // NOTE: bramanmercedes.com REMOVED (DNS dead, no live domain found)
  "https://www.bramanporsche.com/new-inventory/index.htm",
  // CORRECTED: bramanbentley.com -> bentleynaples.com (VDP URL confirmed)
  "https://www.bentleynaples.com/used-Naples-2022-Bentley-Continental+GTC-Speed+Naples+Dragonfly+Collection-SCBDT4ZG6NC093132",
  "https://www.bramanhondapalmbeach.com/new-inventory/index.htm",

  // ── PHIL SMITH AUTOMOTIVE GROUP ──────────────────────────────────────────
  "https://www.philsmithkia.com/new-inventory/index.htm",
  "https://www.philsmithford.com/new-inventory/index.htm",
  "https://www.philsmithtoyota.com/new-inventory/index.htm",
  "https://www.philsmithnissan.com/new-inventory/index.htm",

  // ── OTHER SOUTH FLORIDA ──────────────────────────────────────────────────
  "https://www.holmanhonda.com/new-inventory/index.htm",
  "https://www.keatinghonda.com/new-inventory/index.htm",

  // ── TAMPA / CENTRAL FLORIDA ──────────────────────────────────────────────
  "https://www.mboftampa.com/new-inventory/index.htm",

  // ── NAPLES / SOUTHWEST FLORIDA ───────────────────────────────────────────
  "https://www.audinaples.com/new-inventory/index.htm",
  "https://www.mazdaofnaples.com/new-inventory/index.htm",
  // CORRECTED: porscheofnaples.com (404) -> porschenaples.com
  "https://www.porschenaples.com/new-inventory/index.htm",
  // CORRECTED: infinitiofnaples.com -> naplesinfiniti.com (VDP confirmed)
  "https://www.naplesinfiniti.com/used-Naples-2023-Jeep-Grand+Cherokee-Altitude-1C4RJGAG6PC551745",

  // ── BROWARD ──────────────────────────────────────────────────────────────
  "https://www.audibroward.com/new-inventory/index.htm",

  // ── ORLANDO AREA ─────────────────────────────────────────────────────────
  // VDP confirmed: 2019 Porsche Cayenne WP1AA2AY1KDA08006
  "https://lexusoforlando.com/inventory/Used-2019-Porsche-Cayenne-Base-WP1AA2AY1KDA08006",
  // VDP confirmed: 2026 Toyota Tacoma 3TYLC5LN9TT073236
  "https://www.toyotaoforlando.com/new-Orlando-2026-Toyota-Tacoma+i+FORCE+MAX-TRD+Pro-3TYLC5LN9TT073236",
  "https://www.kiaoforlando.com/new-inventory/index.htm",
  "https://www.hyundaioforlando.com/new-inventory/index.htm",
  "https://www.vwoforlando.com/new-inventory/index.htm",
  "https://www.genesisoforlando.com/new-inventory/index.htm",

  // ── CHRYSLER / DODGE / JEEP / RAM ────────────────────────────────────────
  // CANARY — must always pass
  "https://www.tavernachryslerdodgejeepramfiat.com/new-inventory/index.htm",

  // ── HENDRICK ─────────────────────────────────────────────────────────────
  "https://www.hendrickhonda.com/new-inventory/index.htm",
];

const SCORED_FIELDS = [
  "Year", "Make", "Model", "Price",
  "VIN", "Body Type", "Exterior Color",
  "Interior Color", "Mileage", "Description",
];

const API_BASE    = "https://dylansautosales-facebook-tool.onrender.com";
const API_EXTRACT = `${API_BASE}/fb/extract_html`;
const DELAY_MS    = 3000; // 3s between tabs to avoid hammering

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

function scoreResult(fields) {
  let total = 0;
  const scores = {};
  for (const f of SCORED_FIELDS) {
    const val = fields[f] || "";
    const ok = typeof val === "string" ? val.trim().length > 0 : !!val;
    scores[f] = ok ? "✓" : "✗";
    if (ok) total++;
  }
  return { scores, pct: Math.round((total / SCORED_FIELDS.length) * 100) };
}

async function scrapeTabForBatch(url) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(
      { type: "BATCH_SCRAPE_URL", url },
      (resp) => {
        if (chrome.runtime.lastError || !resp) {
          resolve({ url, status: "FAILED", error: chrome.runtime.lastError?.message || "No response", fields: {}, pct: 0 });
          return;
        }
        if (!resp.ok) {
          resolve({ url, status: "FAILED", error: resp.error || "Unknown error", fields: {}, pct: 0 });
          return;
        }
        const { scores, pct } = scoreResult(resp.fields || {});
        resolve({ url, status: "OK", fields: resp.fields || {}, scores, pct });
      }
    );
  });
}

export async function runBatchTest(onProgress, onComplete) {
  const results = [];
  const total = BATCH_DEALER_URLS.length;

  for (let i = 0; i < total; i++) {
    const url = BATCH_DEALER_URLS[i];
    onProgress({ current: i + 1, total, url, status: "running" });

    const result = await scrapeTabForBatch(url);
    results.push(result);

    onProgress({ current: i + 1, total, url, status: result.status, pct: result.pct });
    await sleep(DELAY_MS);
  }

  onComplete(results);
  return results;
}

export function generateCSV(results) {
  const headers = ["url", "status", "score_pct", ...SCORED_FIELDS, "error"];
  const rows = results.map(r => [
    r.url,
    r.status,
    r.pct,
    ...SCORED_FIELDS.map(f => r.scores?.[f] || "✗"),
    r.error || "",
  ]);
  return [headers, ...rows].map(r => r.join(",")).join("\n");
}
