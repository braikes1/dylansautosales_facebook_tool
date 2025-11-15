// panel.js

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

let state = {
  results: [],
  detail: null, // { base, fields, images, url, html }
  activeView: "list",
};

init();

function init() {
  $("#scrapeBtn").addEventListener("click", scrapeCurrentPage);
  $("#backToList").addEventListener("click", () => switchView("list"));
  $("#btnSendFacebook").addEventListener("click", sendToFacebookFromDetail);

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
    img.src =
      v.image ||
      "data:image/svg+xml;charset=utf-8," +
        encodeURIComponent(
          `<svg xmlns="http://www.w3.org/2000/svg" width="320" height="200">
             <rect width="100%" height="100%" fill="#e9ecef"/>
             <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle"
                   font-family="Arial, sans-serif" font-size="14" fill="#7a7a7a">
               No image
             </text>
           </svg>`
        );

    const meta = document.createElement("div");
    meta.className = "card-meta";

    const title = document.createElement("div");
    title.className = "card-title";
    title.textContent = v.title || "Untitled vehicle";

    const price = document.createElement("div");
    price.className = "card-price";
    price.textContent = v.price || "";

    const line2 = document.createElement("div");
    line2.className = "card-line2";
    const bits = [];
    if (v.mileage) bits.push(v.mileage);
    if (v.vin) bits.push(`VIN: ${v.vin}`);
    if (v.stockNumber) bits.push(`Stock: ${v.stockNumber}`);
    line2.textContent = bits.join(" • ");

    meta.appendChild(title);
    meta.appendChild(price);
    if (bits.length) meta.appendChild(line2);

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
}

function renderDetail() {
  const loading = $("#detailLoading");
  const content = $("#detailContent");

  if (!state.detail) {
    loading.textContent = "Select a vehicle from the list.";
    loading.hidden = false;
    content.hidden = true;
    return;
  }

  if (state.detail.loading) {
    loading.textContent = "Loading vehicle details…";
    loading.hidden = false;
    content.hidden = true;
    return;
  }

  const { base, fields, images } = state.detail;

  loading.hidden = true;
  content.hidden = false;

  const titleInput = $("#field-title");
  const yearInput = $("#field-year");
  const makeInput = $("#field-make");
  const modelInput = $("#field-model");
  const priceInput = $("#field-price");
  const mileageInput = $("#field-mileage");
  const vinInput = $("#field-vin");
  const bodyInput = $("#field-bodyType");
  const extInput = $("#field-extColor");
  const intInput = $("#field-intColor");
  const descInput = $("#field-description");

  const fallbackTitle =
    base.title ||
    `${fields.Year || ""} ${fields.Make || ""} ${fields.Model || ""}`.trim();

  titleInput.value = fields.Title || fallbackTitle || "";
  yearInput.value = fields.Year || "";
  makeInput.value = fields.Make || "";
  modelInput.value = fields.Model || "";
  priceInput.value = fields.Price || base.price || "";
  mileageInput.value = fields.Mileage || base.mileage || "";
  vinInput.value = fields.VIN || base.vin || "";
  bodyInput.value = fields["Body Type"] || "";
  extInput.value = fields["Exterior Color"] || "";
  intInput.value = fields["Interior Color"] || "";
  descInput.value = fields.Description || "";

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

    const img = document.createElement("img");
    img.src = url;
    img.alt = "Vehicle photo";

    item.appendChild(img);

    // click-to-remove
    item.addEventListener("click", () => {
      item.remove();
      updatePhotosCount();
    });

    grid.appendChild(item);
  });

  function updatePhotosCount() {
    const n = grid.querySelectorAll("img").length;
    count.textContent = n ? `${n} selected` : "No photos selected";
  }

  updatePhotosCount();
}

/* ========== DETAIL FLOW ========== */

function openDetailFor(vehicle) {
  if (!vehicle.detailUrl) {
    alert("No detail link for this vehicle.");
    return;
  }

  state.detail = {
    base: vehicle,
    fields: {},
    images: [],
    url: vehicle.detailUrl,
    html: "",
    loading: true,
  };
  switchView("detail");
  renderDetail();

  chrome.runtime.sendMessage(
    { type: "FETCH_DETAIL_VIA_API", detailUrl: vehicle.detailUrl },
    (resp) => {
      if (!resp || !resp.ok) {
        console.error("AI detail fetch failed:", resp);
        state.detail.loading = false;
        state.detail.fields = {};
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
    title: $("#field-title").value.trim(),
    year: $("#field-year").value.trim(),
    make: $("#field-make").value.trim(),
    model: $("#field-model").value.trim(),
    price: $("#field-price").value.trim(),
    mileage: $("#field-mileage").value.trim(),
    vin: $("#field-vin").value.trim(),
    bodyType: $("#field-bodyType").value.trim(),
    exteriorColor: $("#field-extColor").value.trim(),
    interiorColor: $("#field-intColor").value.trim(),
    description: $("#field-description").value.trim(),
    images: Array.from($("#photosGrid").querySelectorAll("img")).map(
      (img) => img.src
    ),
    sourceUrl: state.detail.url || state.detail.base.detailUrl || "",
  };

  chrome.runtime.sendMessage(
    {
      type: "FB_OPEN_MARKETPLACE",
      payload: listing,
    },
    (resp) => {
      if (!resp || !resp.ok) {
        console.error("FB_OPEN_MARKETPLACE failed:", resp);
      }
    }
  );
}

/* ========== IN-PAGE SCRAPER (same logic as before) ========== */

function scrapeVehiclesOnPage() {
  const PRICE_RE = /\$\s*\d[\d,]*/;
  const VIN_RE = /\b[A-HJ-NPR-Z0-9]{17}\b/;
  const MILES_RE = /\b\d[\d,]*\s*(?:mi|miles)\b/i;

  const abs = (u) => {
    try {
      if (!u || /^javascript:/i.test(u)) return null;
      return new URL(u, location.href).href;
    } catch {
      return null;
    }
  };

  const MONEY_RE = /\$\s*-?\d[\d,]*(?:\.\d{2})?/g;
  const LABEL_WIN = 42;
  function classifyPriceContext(textAround) {
    const t = textAround.toLowerCase();
    if (/(savings?|you\s*save|discount|rebate|dealer\s*(?:discount|savings?))/i.test(t))
      return "savings";
    if (
      /(best\s*price|internet\s*price|e-?price|eprice|sale\s*price|our\s*price|special\s*price|web\s*price|market\s*price|buy\s*it\s*now)/i.test(
        t
      )
    )
      return "best";
    if (/\bprice\b/i.test(t)) return "price";
    if (/\b(msrp|retail|list)\b/i.test(t)) return "msrp";
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
        const i = m.index,
          j = i + m[0].length;
        const around = txt.slice(
          Math.max(0, i - LABEL_WIN),
          Math.min(txt.length, j + LABEL_WIN)
        );
        results.push({ label: classifyPriceContext(around), value: m[0] });
      }
    }
    const pick = (want) => results.find((r) => r.label === want)?.value;
    const bestPrice = pick("best") || pick("price") || null;
    const msrp = pick("msrp") || null;
    const savings = pick("savings") || null;
    const fallback = results.find((r) => r.label !== "savings")?.value || null;
    return { bestPrice: bestPrice || fallback, msrp, savings };
  }

  const nodes = Array.from(document.querySelectorAll("article,li,div,section"));
  const candidates = [];
  for (const el of nodes) {
    const txt = el.innerText?.trim() ?? "";
    let score = 0;
    if (PRICE_RE.test(txt)) score += 2;
    if (VIN_RE.test(txt)) score += 3;
    if (MILES_RE.test(txt)) score += 1;
    if (/\b(VIN|Stock|Mileage|Certified|MSRP|Sale)\b/i.test(txt)) score += 1;
    if (score >= 3) candidates.push(el);
    if (candidates.length > 250) break;
  }

  const pick = (el, sels) => {
    for (const s of sels) {
      const n = el.querySelector(s);
      if (n) return n.textContent.trim();
    }
    return null;
  };

  const pickAttr = (el, sels, attr) => {
    for (const s of sels) {
      const n = el.querySelector(s);
      const v = n?.getAttribute(attr);
      if (v) return v;
    }
    return null;
  };

  const findDetailLink = (card) => {
    const textMatches = Array.from(card.querySelectorAll("a[href]")).filter((a) =>
      /view\s*details|details|more info|view vehicle|see details/i.test(
        a.textContent || ""
      )
    );
    if (textMatches[0]) return textMatches[0].getAttribute("href");

    const pathMatches = Array.from(card.querySelectorAll("a[href]")).filter((a) =>
      /\/(used|pre[-\s]?owned|vehicle|inventory)\b/i.test(
        a.getAttribute("href") || ""
      )
    );
    if (pathMatches[0]) return pathMatches[0].getAttribute("href");

    const dataHref = card.getAttribute("data-href");
    if (dataHref) return dataHref;

    const any = card.querySelector("a[href]");
    return any ? any.getAttribute("href") : null;
  };

  const out = [];
  for (const card of candidates) {
    const text = card.innerText || "";
    const title =
      pick(card, [
        "h1",
        "h2",
        "h3",
        ".vehicle-title",
        ".title",
        ".vehicleName",
        ".heading",
      ]) || card.querySelector("a[href]")?.textContent?.trim() || null;

    const { bestPrice, msrp, savings } = findPricesInCard(card);
    const price = bestPrice;

    const mileage = (text.match(MILES_RE) || [])[0] || null;
    const vin = (text.match(VIN_RE) || [])[0] || null;

    const stockMatch = text.match(/Stock\s*#?:?\s*([A-Z0-9\-]+)/i);
    const stockNumber = stockMatch ? stockMatch[1] : null;

    const imgRaw =
      pickAttr(card, ["img", "img[data-src]", "img[data-original]"], "src") ||
      pickAttr(card, ["img[data-src]", "img[data-original]"], "data-src") ||
      null;
    const image = abs(imgRaw);

    const detailUrl = abs(findDetailLink(card));

    if (price || vin || title) {
      out.push({
        title,
        price,
        mileage,
        vin,
        stockNumber,
        image,
        detailUrl,
        msrp,
        savings,
      });
    }
  }

  const seen = new Set();
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
