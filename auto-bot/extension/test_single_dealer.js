// test_single_dealer.js
// Single-dealer test harness for AutoBot.
// Load this script in Chrome DevTools → Console on any page with the AutoBot extension loaded.
//
// Usage:
//   await testDealer("https://www.rickcaseacura.com/new-inventory/index.htm")
//
// Returns:
//   { url, status, score, filled, missing, fields }

(function() {

const SCORED_FIELDS = [
  "Year", "Make", "Model", "Price", "VIN",
  "Body Type", "Exterior Color", "Interior Color",
  "Mileage", "Description",
];

async function testDealer(url) {
  console.log("\n========================================");
  console.log("[test] Testing:", url);
  console.log("========================================");

  const result = await new Promise((resolve) => {
    chrome.runtime.sendMessage(
      { type: "BATCH_SCRAPE_URL", url },
      (resp) => {
        if (chrome.runtime.lastError) {
          resolve({ ok: false, error: chrome.runtime.lastError.message });
        } else {
          resolve(resp || { ok: false, error: "No response" });
        }
      }
    );
  });

  if (!result.ok) {
    console.log("❌ FAILED:", result.error);
    return { url, status: "FAILED", score: 0, filled: 0, missing: SCORED_FIELDS, fields: {} };
  }

  const fields = result.fields || {};

  let filled = 0;
  const missing = [];
  const present = [];

  for (const f of SCORED_FIELDS) {
    const val = fields[f];
    if (val && String(val).trim().length > 0) {
      filled++;
      present.push(f);
    } else {
      missing.push(f);
    }
  }

  const score = Math.round((filled / SCORED_FIELDS.length) * 100);

  console.log(`\n✓ Score: ${score}% (${filled}/${SCORED_FIELDS.length})`);
  console.log("✅ Present:", present.join(", ") || "(none)");
  console.log("❌ Missing:", missing.join(", ") || "(none)");
  console.log("\nAll extracted fields:");
  for (const [k, v] of Object.entries(fields)) {
    if (k !== "images") {
      const display = String(v || "").substring(0, 80);
      console.log(`  ${k.padEnd(20)}: ${display || "(empty)"}`);
    }
  }
  console.log("Images:", (result.images || []).length);

  return { url, status: "OK", score, filled, missing, fields, images: result.images || [] };
}

async function testMultipleDealers(urls) {
  const results = [];
  for (const url of urls) {
    const r = await testDealer(url);
    results.push(r);
    // Brief pause between tests
    await new Promise(r => setTimeout(r, 2000));
  }

  console.log("\n========================================");
  console.log("SUMMARY");
  console.log("========================================");
  for (const r of results) {
    const hostname = (() => { try { return new URL(r.url).hostname; } catch { return r.url; } })();
    const status = r.status === "FAILED" ? "❌ FAIL" : `${r.score}%`;
    console.log(`${status.padStart(8)} | ${hostname}`);
    if (r.missing && r.missing.length) {
      console.log(`         Missing: ${r.missing.join(", ")}`);
    }
  }

  const ok = results.filter(r => r.score >= 97);
  console.log(`\nPassing (97%+): ${ok.length}/${results.length}`);
  return results;
}

// Tier 1 SFL dealers (Quick wins)
const SFL_TIER1 = [
  "https://www.rickcaseacura.com/new-inventory/index.htm",
  "https://www.philsmithkia.com/new-inventory/index.htm",
  "https://www.rickcasehonda.com/new-inventory/index.htm",
];

// Tier 2 SFL dealers (Bot-blocked)
const SFL_TIER2 = [
  "https://www.philsmithford.com/new-inventory/index.htm",
  "https://www.philsmithtoyota.com/new-inventory/index.htm",
  "https://www.philsmithnissan.com/new-inventory/index.htm",
  "https://www.bramanmercedes.com/new-inventory/index.htm",
  "https://www.bramanbentley.com/new-inventory/index.htm",
  "https://www.bramanmiamibmw.com/new-inventory/index.htm",
  "https://www.bramanhondapalmbeach.com/new-inventory/index.htm",
  "https://www.rickcasemitsubishi.com/new-inventory/index.htm",
];

// Tier 3 SFL dealers (0% extraction)
const SFL_TIER3 = [
  "https://www.rickcasehyundai.com/new-inventory/index.htm",
  "https://www.rickcasevw.com/new-inventory/index.htm",
  "https://www.rickcasealfaromeo.com/new-inventory/index.htm",
  "https://www.holmanhonda.com/new-inventory/index.htm",
];

// All SFL dealers
const SFL_ALL = [
  ...SFL_TIER1, ...SFL_TIER2, ...SFL_TIER3,
  "https://www.rickcasemazda.com/new-inventory/index.htm",
  "https://www.coralspringsautomall.com/new-inventory/index.htm",
  "https://www.bramanporsche.com/new-inventory/index.htm",
  "https://www.toyotaofcoconutcreek.com/new-inventory/index.htm",
  "https://www.bramanbmw.com/new-inventory/index.htm",
];

// Attach to window so available in DevTools
window.testDealer = testDealer;
window.testMultipleDealers = testMultipleDealers;
window.SFL_TIER1 = SFL_TIER1;
window.SFL_TIER2 = SFL_TIER2;
window.SFL_TIER3 = SFL_TIER3;
window.SFL_ALL = SFL_ALL;

console.log("✅ AutoBot test harness loaded.");
console.log("Commands:");
console.log("  await testDealer(url)           — test one dealer");
console.log("  await testMultipleDealers(urls) — test array of dealers");
console.log("  await testMultipleDealers(SFL_TIER1) — test Tier 1");
console.log("  await testMultipleDealers(SFL_ALL)   — test all SFL");

})();
