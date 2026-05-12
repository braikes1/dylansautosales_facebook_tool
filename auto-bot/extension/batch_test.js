// batch_test.js — AutoBot Batch Test Mode
// Opens each dealer URL in a background tab, scrapes inventory,
// scores field extraction, and displays a full report in the panel.

const BATCH_DEALER_URLS = [
  // Mercedes-Benz
  "https://www.mboftampa.com/new-inventory/index.htm",
  "https://www.mbofbeverlyhills.com/new-inventory/index.htm",
  // BMW
  "https://www.bmwofnaples.com/new-inventory/index.htm",
  "https://www.bmwofsouthmountain.com/new-inventory/index.htm",
  // Honda
  "https://www.keatinghonda.com/new-inventory/index.htm",
  "https://www.hendrickhonda.com/new-inventory/index.htm",
  // Toyota
  "https://www.toyotaoforlando.com/new-inventory/index.htm",
  "https://www.toyotaofcoolsprings.com/new-inventory/index.htm",
  // Ford
  "https://www.vatlandford.com/new-inventory/index.htm",
  "https://www.fordofkissimmee.com/new-inventory/index.htm",
  // Chevrolet
  "https://www.peacockchevrolet.com/new-inventory/index.htm",
  "https://www.classicchevrolet.com/new-inventory/index.htm",
  // Nissan
  "https://www.tavernanissan.com/new-inventory/index.htm",
  "https://www.nissanofchattanooga.com/new-inventory/index.htm",
  // Jeep / CDJR
  "https://www.tavernacdjrf.com/new-inventory/index.htm",
  "https://www.hendersondodge.com/new-inventory/index.htm",
  // Cadillac
  "https://www.sewellcadillac.com/new-inventory/index.htm",
  // Audi
  "https://www.audinaples.com/new-inventory/index.htm",
  "https://www.audibroward.com/new-inventory/index.htm",
  "https://www.audiatlanta.com/new-inventory/index.htm",
  // Lexus
  "https://www.lexusoforlando.com/new-inventory/index.htm",
  "https://www.lexusofnashville.com/new-inventory/index.htm",
  // Acura
  "https://www.acuraoforlando.com/new-inventory/index.htm",
  // Hyundai
  "https://www.hyundaioforlando.com/new-inventory/index.htm",
  // Kia
  "https://www.kiaoforlando.com/new-inventory/index.htm",
  // Subaru
  "https://www.subaruofwakefield.com/new-inventory/index.htm",
  "https://www.larrymillersubaru.com/new-inventory/index.htm",
  // Volkswagen
  "https://www.vwoforlando.com/new-inventory/index.htm",
  // Volvo
  "https://www.volvocarsnaples.com/new-inventory/index.htm",
  // Mazda
  "https://www.mazdaofnaples.com/new-inventory/index.htm",
  // Porsche
  "https://www.porscheofnaples.com/new-inventory/index.htm",
  // Land Rover
  "https://www.landroveratl.com/new-inventory/index.htm",
  // Infiniti
  "https://www.infinitiofnaples.com/new-inventory/index.htm",
  // Buick / GMC
  "https://www.classicbuickgmc.com/new-inventory/index.htm",
  // Genesis
  "https://www.genesisoforlando.com/new-inventory/index.htm",
  // Mitsubishi
  "https://www.mitsubishioforlando.com/new-inventory/index.htm",
  // AutoNation
  "https://www.autonation.com/new-cars",
  // Hendrick
  "https://www.hendrickcars.com/new-inventory/index.htm",
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
