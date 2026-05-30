// panel.js

import { runBatchTest, generateCSV } from "./batch_test.js";

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

const API_BASE = "https://dylansautosales-facebook-tool.onrender.com";

let state = {
  results: [],
  detail: null,
  activeView: "list",
  batchResults: [],
};

/* ========== TERMS OF USE (first-run) ========== */

function initTerms() {
  const overlay   = $("#terms-overlay");
  const checkbox  = $("#termsCheckbox");
  const acceptBtn = $("#termsAcceptBtn");

  // Show overlay only if user hasn't accepted yet
  chrome.storage.local.get("termsAccepted", (data) => {
    if (!data.termsAccepted) {
      overlay.hidden = false;
    }
  });

  checkbox.addEventListener("change", () => {
    acceptBtn.disabled = !checkbox.checked;
  });

  acceptBtn.addEventListener("click", () => {
    chrome.storage.local.set({ termsAccepted: true });
    overlay.hidden = true;
  });
}

init();

function init() {
  initTerms();
  $("#scrapeBtn").addEventListener("click", scrapeCurrentPage);
  $("#backToList").addEventListener("click", () => switchView("list"));
  $("#backFromBatch").addEventListener("click", () => switchView("list"));
  $("#btnSendFacebook").addEventListener("click", sendToFacebookFromDetail);
  $("#scrubToggle").addEventListener("change", onScrubToggle);
  $("#batchTestBtn").addEventListener("click", () => switchView("batch"));
  $("#startBatchBtn").addEventListener("click", startBatchTest);
  $("#downloadCsvBtn").addEventListener("click", downloadCSV);
  renderList();
  renderDetail();
}

/* ========== SCRAPING CURRENT PAGE ========== */

async function pickTargetTab() {
  const active = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  let t = active.find((tab) => /^https?:/i.test(tab.url || ""));
  if (t) return t;
  const httpTabs = await chrome.tabs.query({ lastFocusedWindow: true });
  t = httpTabs.find((tab) => /^https?:/i.test(tab.url || ""));
  if (t) return t;
  const all = await chrome.tabs.query({});
  return all.find((tab) => /^https?:/i.test(tab.url || "")) || null;
}

async function scrapeCurrentPage() {
  const tab = await pickTargetTab();
  if (!tab?.id) {
    alert("Open a dealership page (not a PDF or Chrome page) and try again.");
    return;
  }
  try {
    const [inj] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: scrapeVehiclesOnPage,
    });
    const result = inj?.result || [];
    state.results = Array.isArray(result) ? result : [];
    renderList();
    switchView("list");
  } catch (err) {
    console.error("Scrape failed:", err);
    alert("Could not scrape this page.");
  }
}

/* ========== RENDER: LIST VIEW ========== */

function renderList() {
  const grid = $("#listGrid");
  const empty = $("#listEmpty");
  grid.innerHTML = "";
  if (!state.results.length) {
    empty.hidden = false;
    return;
  }
  empty.hidden = true;
  state.results.forEach((v, idx) => {
    const card = document.createElement("div");
    card.className = "card";
    card.dataset.index = String(idx);
    card.addEventListener("click", () => {
      $$("div.card").forEach((c) => c.classList.remove("card-active"));
      card.classList.add("card-active");
      openDetailFor(v);
    });

    const img = document.createElement("img");
    img.className = "card-thumb";
    img.alt = v.title || "Vehicle";
    img.src = v.image ||
      "data:image/svg+xml;charset=utf-8," +
        encodeURIComponent(
          `<svg xmlns="http://www.w3.org/2000/svg" width="320" height="200">
             <rect width="100%" height="100%" fill="#f2f2f7"/>
             <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle"
                   font-family="sans-serif" font-size="13" fill="#aeaeb2">No image</text>
           </svg>`
        );

    const meta = document.createElement("div");
    meta.className = "card-meta";

    const title = document.createElement("div");
    title.className = "card-title";
    // Build a sensible fallback from year/make/model if title is missing
    const displayTitle = v.title ||
      [v.year, v.make, v.model].filter(Boolean).join(" ").trim() ||
      "Vehicle";
    title.textContent = displayTitle;

    meta.appendChild(title);
    card.appendChild(img);
    card.appendChild(meta);
    grid.appendChild(card);
  });
}

/* ========== DETAIL VIEW ========== */

function switchView(name) {
  state.activeView = name;
  $("#view-list").classList.toggle("active", name === "list");
  $("#view-detail").classList.toggle("active", name === "detail");
  $("#view-batch").classList.toggle("active", name === "batch");
}

function renderDetail() {
  const loading = $("#detailLoading");
  const content = $("#detailContent");
  if (!state.detail) {
    loading.hidden = false;
    content.hidden = true;
    return;
  }
  if (state.detail.loading) {
    loading.hidden = false;
    content.hidden = true;
    return;
  }
  const { base, fields, images } = state.detail;
  loading.hidden = true;
  content.hidden = false;

  const fallbackTitle =
    base.title ||
    `${fields.Year || ""} ${fields.Make || ""} ${fields.Model || ""}`.trim();

  $("#field-title").value       = fields.Title || fallbackTitle || "";
  $("#field-year").value        = fields.Year || "";
  $("#field-make").value        = fields.Make || "";
  $("#field-model").value       = fields.Model || "";
  $("#field-price").value       = fields.Price || base.price || "";
  $("#field-mileage").value     = fields.Mileage || base.mileage || "";
  $("#field-vin").value         = fields.VIN || base.vin || "";
  $("#field-bodyType").value    = fields["Body Type"] || "";
  $("#field-extColor").value    = fields["Exterior Color"] || "";
  $("#field-intColor").value    = fields["Interior Color"] || "";
  $("#field-condition").value   = fields["Condition"] || "";
  $("#field-fuelType").value    = fields["Fuel Type"] || "";
  $("#field-transmission").value = fields["Transmission"] || "";
  $("#field-description").value = fields.Description || "";

  $("#scrubToggle").checked = false;
  $("#scrubStatus").hidden = true;

  renderPhotos(images || []);
}

function renderPhotos(urls) {
  const grid = $("#photosGrid");
  const count = $("#photosCount");
  grid.innerHTML = "";
  const clean = [...new Set(urls.filter((u) => typeof u === "string" && u))];
  clean.forEach((url) => {
    const item = document.createElement("div");
    item.className = "photo-item";
    item.dataset.originalUrl = url;
    item.dataset.currentUrl = url;
    const img = document.createElement("img");
    img.src = url;
    img.alt = "Vehicle photo";
    item.appendChild(img);
    item.addEventListener("click", () => {
      item.remove();
      updatePhotosCount();
    });
    grid.appendChild(item);
  });
  function updatePhotosCount() {
    const n = grid.querySelectorAll("img").length;
    count.textContent = n ? `${n} selected` : "No photos";
  }
  updatePhotosCount();
}

/* ========== SCRUB TOGGLE ========== */

async function onScrubToggle() {
  const enabled = $("#scrubToggle").checked;
  const status  = $("#scrubStatus");
  const items   = Array.from($("#photosGrid").querySelectorAll(".photo-item"));

  if (!enabled) {
    items.forEach((item) => {
      const orig = item.dataset.originalUrl;
      if (orig) {
        item.querySelector("img").src = orig;
        item.dataset.currentUrl = orig;
        item.classList.remove("scrubbed", "scrubbing");
      }
    });
    status.hidden = true;
    return;
  }

  if (!items.length) return;

  status.hidden = false;
  status.textContent = `Scrubbing ${items.length} photos…`;

  let done = 0;
  await Promise.all(items.map(async (item) => {
    const url = item.dataset.originalUrl;
    if (!url) return;
    item.classList.add("scrubbing");
    try {
      const resp = await fetch(`${API_BASE}/fb/scrub_image`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image_url: url }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      if (data.scrubbed_url) {
        item.querySelector("img").src = data.scrubbed_url;
        item.dataset.currentUrl = data.scrubbed_url;
        item.classList.add("scrubbed");
      }
    } catch (e) {
      console.warn("[scrub] failed for", url, e);
    } finally {
      item.classList.remove("scrubbing");
      done++;
      status.textContent = done < items.length
        ? `Scrubbing photos… ${done}/${items.length}`
        : `✓ ${done} photos scrubbed`;
    }
  }));
}

/* ========== DETAIL FLOW ========== */

function openDetailFor(vehicle) {
  if (!vehicle.detailUrl) {
    alert("No detail link for this vehicle.");
    return;
  }
  state.detail = { base: vehicle, fields: {}, images: [], url: vehicle.detailUrl, html: "", loading: true };
  switchView("detail");
  renderDetail();
  let responded = false;
  const fallbackTimer = setTimeout(() => {
    if (responded) return;
    responded = true;
    state.detail.loading = false;
    state.detail.fields = { Description: "Request timed out. The server may be waking up — try again in 30 seconds." };
    state.detail.images = [];
    renderDetail();
  }, 50000);

  chrome.runtime.sendMessage(
    { type: "FETCH_DETAIL_VIA_API", detailUrl: vehicle.detailUrl },
    (resp) => {
      if (responded) return;
      responded = true;
      clearTimeout(fallbackTimer);
      if (!resp || !resp.ok) {
        state.detail.loading = false;
        state.detail.fields = { Description: resp?.error || "Could not reach server. Try again in 30 seconds." };
        state.detail.images = [];
        renderDetail();
        return;
      }
      state.detail.loading = false;
      state.detail.fields = resp.fields || {};
      state.detail.images = resp.images || [];
      state.detail.html = resp.html || "";
      renderDetail();
    }
  );
}

/* ========== SEND TO FACEBOOK ========== */

function sendToFacebookFromDetail() {
  if (!state.detail) return;
  const listing = {
    title:         $("#field-title").value.trim(),
    year:          $("#field-year").value.trim(),
    make:          $("#field-make").value.trim(),
    model:         $("#field-model").value.trim(),
    price:         $("#field-price").value.trim(),
    mileage:       $("#field-mileage").value.trim(),
    vin:           $("#field-vin").value.trim(),
    bodyType:      $("#field-bodyType").value.trim(),
    exteriorColor: $("#field-extColor").value.trim(),
    interiorColor: $("#field-intColor").value.trim(),
    condition:     $("#field-condition").value.trim(),
    fuelType:      $("#field-fuelType").value.trim(),
    transmission:  $("#field-transmission").value.trim(),
    description:   $("#field-description").value.trim(),
    images:        Array.from($("#photosGrid").querySelectorAll("img")).map((img) => img.src),
    sourceUrl:     state.detail.url || state.detail.base.detailUrl || "",
  };
  chrome.runtime.sendMessage({ type: "FB_OPEN_MARKETPLACE", payload: listing }, (resp) => {
    if (!resp || !resp.ok) console.error("FB_OPEN_MARKETPLACE failed:", resp);
  });
}

/* ========== BATCH TEST ========== */

const SCORED_FIELDS = [
  "Year", "Make", "Model", "Price",
  "VIN", "Body Type", "Exterior Color",
  "Interior Color", "Mileage", "Description",
];

async function startBatchTest() {
  const startBtn      = $("#startBatchBtn");
  const downloadBtn   = $("#downloadCsvBtn");
  const statusEl      = $("#batchStatus");
  const resultsEl     = $("#batchResults");
  const progressBadge = $("#batchProgress");

  startBtn.disabled = true;
  startBtn.textContent = "Running…";
  downloadBtn.hidden = true;
  resultsEl.innerHTML = "";
  state.batchResults = [];

  await runBatchTest(
    // onProgress
    ({ current, total, url, status, pct }) => {
      progressBadge.textContent = `${current}/${total}`;
      statusEl.textContent = status === "running"
        ? `Testing: ${new URL(url).hostname}`
        : `${current}/${total} complete`;

      // Update or add row
      let row = resultsEl.querySelector(`[data-url="${CSS.escape(url)}"]`);
      if (!row) {
        row = document.createElement("div");
        row.className = "batch-row running";
        row.dataset.url = url;
        row.innerHTML = `
          <div class="batch-row-url">${new URL(url).hostname}</div>
          <div class="batch-row-fields"></div>
          <div class="batch-row-score">…</div>
        `;
        resultsEl.appendChild(row);
        resultsEl.scrollTop = resultsEl.scrollHeight;
      }
      if (status !== "running") {
        row.className = `batch-row ${status === "OK" ? "ok" : "fail"}`;
        row.querySelector(".batch-row-score").textContent = status === "OK" ? `${pct}%` : "FAIL";
      }
    },
    // onComplete
    (results) => {
      state.batchResults = results;
      const ok  = results.filter(r => r.status === "OK");
      const avg = ok.length ? Math.round(ok.reduce((s, r) => s + r.pct, 0) / ok.length) : 0;
      statusEl.textContent = `Done — ${ok.length}/${results.length} sites passed • avg score ${avg}%`;
      startBtn.disabled = false;
      startBtn.textContent = "▶ Run Again";
      downloadBtn.hidden = false;
      progressBadge.textContent = `${results.length}/${results.length}`;

      // Add field dots to each row
      results.forEach(r => {
        const row = resultsEl.querySelector(`[data-url="${CSS.escape(r.url)}"]`);
        if (!row) return;
        const dotsEl = row.querySelector(".batch-row-fields");
        dotsEl.innerHTML = SCORED_FIELDS.map(f => {
          const cls = r.scores?.[f] === "✓" ? "pass" : r.status !== "OK" ? "skip" : "fail";
          return `<div class="batch-field-dot ${cls}" title="${f}"></div>`;
        }).join("");
      });
    }
  );
}

function downloadCSV() {
  if (!state.batchResults.length) return;
  const csv = generateCSV(state.batchResults);
  const blob = new Blob([csv], { type: "text/csv" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href = url;
  a.download = `autobot_batch_test_${Date.now()}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

/* ========== IN-PAGE SCRAPER ========== */

function scrapeVehiclesOnPage() {
  const PRICE_RE    = /\$\s*\d[\d,]*/;
  const VIN_RE      = /\b[A-HJ-NPR-Z0-9]{17}\b/;
  const MILES_RE    = /\b\d[\d,]*\s*(?:mi|miles)\b/i;
  const TITLE_RE    = /\b(19|20)\d{2}\s+[A-Z][a-zA-Z\-]+(?:\s+[A-Za-z0-9\-]+){1,4}/;

  const JUNK_TITLE  = /^(pricing|new inventory|specials|finance|service|parts|about|contact|search|filter|sort|view all|load more|show more|start here|lower price|calculate|payment|get a quote|check availability|get my quote|shop|offers|sell|trade|click|nationwide|want a|add photo|add video)\b/i;
  const VEHICLE_URL = /\/(vehicle|inventory|used|new|pre.?owned|detail|vdp|listing|cars)[\/?]/i;

  const abs = (u) => {
    try {
      if (!u || /^javascript:/i.test(u)) return null;
      return new URL(u, location.href).href;
    } catch { return null; }
  };

  const MONEY_RE  = /\$\s*-?\d[\d,]*(?:\.\d{2})?/g;
  const LABEL_WIN = 42;

  function classifyPriceContext(txt) {
    const t = txt.toLowerCase();
    if (/(savings?|you\s*save|discount|rebate)/i.test(t))          return "savings";
    if (/(best\s*price|internet\s*price|e-?price|sale\s*price|our\s*price|special\s*price|web\s*price|market\s*price)/i.test(t)) return "best";
    if (/\bprice\b/i.test(t))                                       return "price";
    if (/\b(msrp|retail|list)\b/i.test(t))                         return "msrp";
    return "unknown";
  }

  function findPricesInCard(card) {
    const results = [];
    const nodes = Array.from(card.querySelectorAll("*")).slice(0, 250);
    for (const n of nodes) {
      const txt = (n.textContent || "").trim();
      if (!txt) continue;
      let m;
      while ((m = MONEY_RE.exec(txt))) {
        const i = m.index, j = i + m[0].length;
        const around = txt.slice(Math.max(0, i - LABEL_WIN), Math.min(txt.length, j + LABEL_WIN));
        results.push({ label: classifyPriceContext(around), value: m[0] });
      }
    }
    const pick = (want) => results.find((r) => r.label === want)?.value;
    const best = pick("best") || pick("price") || null;
    const msrp = pick("msrp") || null;
    const fallback = results.find((r) => r.label !== "savings")?.value || null;
    return { bestPrice: best || fallback, msrp };
  }

  function extractTitle(card, text) {
    const sels = [
      "h1", "h2", "h3",
      ".vehicle-title", ".vehicleName", ".vehicle-name",
      "[data-vehicle-name]",
      "[class*='vehicleTitle']", "[class*='VehicleTitle']",
      "[class*='vehicle-title']", "[class*='vehicle_title']",
      "[class*='listing-title']", "[class*='listingTitle']",
      "[class*='inventory-title']",
    ];
    for (const s of sels) {
      const el = card.querySelector(s);
      if (!el) continue;
      const t = el.textContent.trim();
      if (t.length > 4 && !JUNK_TITLE.test(t)) return t;
    }
    const m = text.match(TITLE_RE);
    if (m) return m[0].trim();
    return null;
  }

  function findDetailLink(card) {
    const textMatch = Array.from(card.querySelectorAll("a[href]")).find((a) =>
      /view\s*details|details|more info|view vehicle|see details/i.test(a.textContent || "")
    );
    if (textMatch) return textMatch.getAttribute("href");
    const urlMatch = Array.from(card.querySelectorAll("a[href]")).find((a) =>
      VEHICLE_URL.test(a.getAttribute("href") || "")
    );
    if (urlMatch) return urlMatch.getAttribute("href");
    const dataHref = card.getAttribute("data-href");
    if (dataHref) return dataHref;
    return null;
  }

  const nodes = Array.from(document.querySelectorAll("article,li,div,section"));
  const candidates = [];
  for (const el of nodes) {
    const txt = el.innerText?.trim() ?? "";
    let score = 0;
    if (PRICE_RE.test(txt))                                   score += 2;
    if (VIN_RE.test(txt))                                     score += 3;
    if (MILES_RE.test(txt))                                   score += 1;
    if (/\b(VIN|Stock|Mileage|Certified|MSRP)\b/i.test(txt)) score += 1;
    if (score >= 3) candidates.push(el);
    if (candidates.length > 250) break;
  }

  const pickAttr = (el, sels, attr) => {
    for (const s of sels) {
      const n = el.querySelector(s);
      const v = n?.getAttribute(attr);
      if (v) return v;
    }
    return null;
  };

  const out = [];
  for (const card of candidates) {
    const text       = card.innerText || "";
    const title      = extractTitle(card, text);
    const detailHref = findDetailLink(card);
    const detailUrl  = abs(detailHref);
    const vin        = (text.match(VIN_RE) || [])[0] || null;

    const hasVin        = !!vin;
    const hasVehicleUrl = !!detailUrl && VEHICLE_URL.test(detailUrl);
    if (!hasVin && !hasVehicleUrl) continue;
    if (title && JUNK_TITLE.test(title)) continue;

    const { bestPrice, msrp } = findPricesInCard(card);
    const mileage     = (text.match(MILES_RE) || [])[0] || null;
    const stockMatch  = text.match(/Stock\s*#?:?\s*([A-Z0-9\-]+)/i);
    const stockNumber = stockMatch ? stockMatch[1] : null;

    const imgRaw =
      pickAttr(card, ["img[src]", "img[data-src]", "img[data-original]"], "src") ||
      pickAttr(card, ["img[data-src]", "img[data-original]"], "data-src") ||
      null;
    const image = abs(imgRaw);

    out.push({ title, price: bestPrice, mileage, vin, stockNumber, image, detailUrl, msrp });
  }

  const seen  = new Set();
  const dedup = [];
  for (const r of out) {
    const key = r.vin || r.detailUrl || r.title;
    if (key && !seen.has(key)) {
      seen.add(key);
      dedup.push(r);
    }
  }
  return dedup;
}
