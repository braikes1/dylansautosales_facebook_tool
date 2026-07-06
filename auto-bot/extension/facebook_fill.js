// facebook_fill.js
// Fills Facebook Marketplace Vehicle composer using data from the extension.
//
// It expects the background script to respond to:
//   { type: "FB_GET_VEHICLE_DATA" } -> { listing: { title, year, make, model, price, description, ... } }
//
// This script:
//   - Uses the *real* listing data (no more Toyota/Camry defaults)
//   - Fills Price, Make, Model, Year (dropdown/combobox), and Description
//   - Handles React-style inputs + contenteditable fields

(() => {
  if (window.__fbFillInjected) return;
  window.__fbFillInjected = true;

  const LOG = (...a) => console.log("[fb-fill]", ...a);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  LOG("Injected facebook_fill.js");

  // ---------- Utilities ----------

  function setNativeValue(el, value) {
    if (!el) return;

    const tag = (el.tagName || "").toUpperCase();
    let desc = null;

    if (tag === "INPUT") {
      desc = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        "value"
      );
    } else if (tag === "TEXTAREA") {
      desc = Object.getOwnPropertyDescriptor(
        HTMLTextAreaElement.prototype,
        "value"
      );
    }

    const proto = Object.getPrototypeOf(el);
    const protoDesc = proto && Object.getOwnPropertyDescriptor(proto, "value");

    if (protoDesc && desc && protoDesc.set && protoDesc.set !== desc.set) {
      // React-style override
      protoDesc.set.call(el, value);
    } else if (desc && desc.set) {
      desc.set.call(el, value);
    } else if (el.isContentEditable) {
      el.textContent = value;
    } else {
      el.value = value;
    }
  }

  function fireInputEvents(el) {
    if (!el) return;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  async function typeIntoInput(el, value, commitEnter = false) {
    if (!el) return false;

    el.focus();
    el.click();
    await sleep(60);

    setNativeValue(el, "");
    fireInputEvents(el);

    setNativeValue(el, value);
    fireInputEvents(el);

    if (commitEnter) {
      el.dispatchEvent(
        new KeyboardEvent("keydown", { key: "Enter", bubbles: true })
      );
      await sleep(50);
      el.dispatchEvent(
        new KeyboardEvent("keyup", { key: "Enter", bubbles: true })
      );
    }
    return true;
  }

  async function typeContentEditable(el, value) {
    if (!el) return false;
    el.focus();
    await sleep(80);

    const sel = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(el);
    sel.removeAllRanges();
    sel.addRange(range);

    document.execCommand("delete", false, null);
    document.execCommand("insertText", false, value);

    fireInputEvents(el);
    return true;
  }

  // ---------- Generic finders ----------

  function findInputByLabels(labels, scope = document) {
    const lower = labels.map((l) => l.toLowerCase());

    // 1) Direct inputs / textareas via placeholder or aria-label
    const all = Array.from(scope.querySelectorAll("input,textarea"));

    for (const el of all) {
      const ph = (el.getAttribute("placeholder") || "").toLowerCase();
      const al = (el.getAttribute("aria-label") || "").toLowerCase();

      if (
        lower.some(
          (lbl) =>
            ph === lbl ||
            ph.includes(lbl) ||
            al === lbl ||
            al.includes(lbl)
        )
      ) {
        const r = el.getBoundingClientRect();
        if (r.width && r.height) return el;
      }
    }

    // 2) Visible label text near inputs
    const labelsNodes = Array.from(
      scope.querySelectorAll("label,div,span,strong")
    ).filter((n) => {
      const t = (n.textContent || "").trim().toLowerCase();
      return lower.some((lbl) => t === lbl || t.includes(lbl));
    });

    for (const lab of labelsNodes) {
      const container =
        lab.closest(
          'form,[role="group"],[data-visualcompletion],section,div,[aria-labelledby]'
        ) || lab.parentElement;
      if (!container) continue;
      const input = container.querySelector("input,textarea");
      if (input) {
        const r = input.getBoundingClientRect();
        if (r.width && r.height) return input;
      }
    }

    return null;
  }

  async function waitForComposer(scope = document, timeout = 20000) {
    const start = Date.now();
    const selectors = [
      '[data-pagelet="MarketplaceComposerPagelet"]',
      'form[action*="marketplace"]',
      '[role="main"]',
    ];
    while (Date.now() - start < timeout) {
      for (const s of selectors) {
        const el = scope.querySelector(s);
        if (el) {
          LOG("Composer found with selector:", s);
          return el;
        }
      }
      await sleep(150);
    }
    LOG("Composer not found within timeout");
    return null;
  }

  // ---------- Special: Year finder (dropdown / combobox) ----------

  function findYearField(scope) {
    // Look for Year-related inputs/comboboxes
    const candidates = Array.from(
      scope.querySelectorAll('input,textarea,[role="combobox"],[role="textbox"]')
    );

    const lowerMatch = (txt) =>
      (txt || "").toLowerCase().includes("Year"); // <-- fix: "year" lower-case

    for (const el of candidates) {
      const al = (el.getAttribute("aria-label") || "").toLowerCase();
      const ph = (el.getAttribute("placeholder") || "").toLowerCase();
      const id = (el.id || "").toLowerCase();

      if (lowerMatch(al) || lowerMatch(ph) || lowerMatch(id)) {
        const r = el.getBoundingClientRect();
        if (r.width && r.height) return el;
      }
    }

    // fallback: visible label text "Year"
    const labels = Array.from(
      scope.querySelectorAll("label,div,span,strong")
    ).filter((n) => {
      const t = (n.textContent || "").trim().toLowerCase();
      return t === "year" || t.includes("Year");
    });

    for (const lab of labels) {
      const container =
        lab.closest(
          'form,[role="group"],[data-visualcompletion],section,div,[aria-labelledby]'
        ) || lab.parentElement;
      if (!container) continue;
      const input = container.querySelector(
        'input,textarea,[role="combobox"],[role="textbox"]'
      );
      if (input) {
        const r = input.getBoundingClientRect();
        if (r.width && r.height) return input;
      }
    }

    return null;
  }

  async function selectYearFromDropdown(scope, yearValue) {
    const yearStr = String(yearValue || "").trim();
    if (!yearStr) {
      console.log("[fb-fill] No year value provided");
      return;
    }

    const yearField = findYearField(scope);
    if (!yearField) {
      console.log("[fb-fill] Year field not found");
      return;
    }

    console.log("[fb-fill] Year field:", yearField);

    // 1) Click the combobox/label to open the dropdown
    yearField.click();
    yearField.focus?.();

    // Give FB time to render the year list
    await new Promise((r) => setTimeout(r, 400));

    // 2) Find the listbox that contains the year options
    //    (Marketplace uses role="listbox" + role="option" for each year)
    const listboxes = Array.from(document.querySelectorAll('[role="listbox"]'));
    let option = null;

    for (const lb of listboxes) {
      const opts = Array.from(lb.querySelectorAll('[role="option"]'));
      option = opts.find((o) => {
        const txt = (o.textContent || "").trim();
        return txt === yearStr || txt.includes(yearStr);
      });
      if (option) {
        console.log("[fb-fill] Found year option:", option.textContent.trim());
        option.scrollIntoView({ block: "nearest" });
        option.click();
        break;
      }
    }

    if (!option) {
      console.log("[fb-fill] Year option not found for:", yearStr);
    } else {
      // Small delay to let selection register
      await new Promise((r) => setTimeout(r, 200));
    }
  }

  function findVehicleTypeField(scope) {
    const candidates = Array.from(
      scope.querySelectorAll('[role="combobox"],input,textarea,[role="textbox"]')
    );

    const lowerMatch = (txt) =>
      (txt || "").toLowerCase().includes("vehicle type");

    for (const el of candidates) {
      const al = (el.getAttribute("aria-label") || "").toLowerCase();
      const ph = (el.getAttribute("placeholder") || "").toLowerCase();
      const id = (el.id || "").toLowerCase();

      if (lowerMatch(al) || lowerMatch(ph) || lowerMatch(id)) {
        const r = el.getBoundingClientRect();
        if (r.width && r.height) return el;
      }
    }

    // fallback: label text "Vehicle type"
    const labels = Array.from(
      scope.querySelectorAll("label,div,span,strong")
    ).filter((n) => {
      const t = (n.textContent || "").trim().toLowerCase();
      return t === "vehicle type" || t.includes("vehicle type");
    });

    for (const lab of labels) {
      const container =
        lab.closest(
          'form,[role="group"],[data-visualcompletion],section,div,[aria-labelledby]'
        ) || lab.parentElement;
      if (!container) continue;
      const input = container.querySelector(
        '[role="combobox"],input,textarea,[role="textbox"]'
      );
      if (input) {
        const r = input.getBoundingClientRect();
        if (r.width && r.height) return input;
      }
    }

    return null;
  }

  async function selectVehicleTypeCarTruck(scope) {
    const targetText = "Car/Truck";

    const vtField = findVehicleTypeField(scope);
    if (!vtField) {
      LOG("Vehicle type field not found");
      return;
    }

    LOG("Vehicle type field:", vtField);
    vtField.click();
    vtField.focus?.();

    await sleep(400);

    const listboxes = Array.from(document.querySelectorAll('[role="listbox"]'));
    let option = null;

    for (const lb of listboxes) {
      const opts = Array.from(lb.querySelectorAll('[role="option"]'));
      option = opts.find((o) => {
        const txt = (o.textContent || "").trim().toLowerCase();
        return txt === targetText.toLowerCase() || txt.includes(targetText.toLowerCase());
      });
      if (option) {
        LOG("Found vehicle type option:", option.textContent.trim());
        option.scrollIntoView({ block: "nearest" });
        option.click();
        break;
      }
    }

    if (!option) {
      LOG("Vehicle type option 'Other' not found");
    } else {
      await sleep(200);
    }
  }


  // ---------- Generic dropdown helper (Car/Truck form fields) ----------

  // Resolve each combobox's OWN accessible label via aria-labelledby (or
  // aria-label) and match it to the requested field. This avoids matching a
  // broad wrapper element and grabbing the wrong (first) combobox.
  function comboboxLabelText(combo) {
    const labelledBy = combo.getAttribute("aria-labelledby");
    if (labelledBy) {
      const txt = labelledBy
        .split(/\s+/)
        .map((id) => document.getElementById(id))
        .filter(Boolean)
        .map((el) => (el.textContent || "").trim())
        .join(" ")
        .trim();
      if (txt) return txt;
    }
    return (combo.getAttribute("aria-label") || "").trim();
  }

  function findComboboxByLabel(scope, labelText) {
    const want = labelText.trim().toLowerCase();
    const combos = Array.from(scope.querySelectorAll('[role="combobox"]'));

    // 1) exact label match (preferred)
    for (const combo of combos) {
      if (comboboxLabelText(combo).toLowerCase() === want) {
        const r = combo.getBoundingClientRect();
        if (r.width && r.height) return combo;
      }
    }
    // 2) startsWith/contains on the combobox's OWN label only
    for (const combo of combos) {
      const txt = comboboxLabelText(combo).toLowerCase();
      if (txt && (txt.startsWith(want) || txt.includes(want))) {
        const r = combo.getBoundingClientRect();
        if (r.width && r.height) return combo;
      }
    }
    return null;
  }

  async function selectFromDropdown(scope, labelText, valueStr, opts = {}) {
    const exact = !!opts.exact;
    const val = String(valueStr || "").trim();
    if (!val) {
      LOG(`No value provided for ${labelText}`);
      return false;
    }

    const field = findComboboxByLabel(scope, labelText);
    if (!field) {
      LOG(`${labelText} field not found`);
      return false;
    }
    LOG(`${labelText} field:`, field);

    field.click();
    field.focus?.();
    await sleep(450);

    // Searchable comboboxes (e.g. Make) reveal a text input and virtualize
    // their option list. Type the value to filter so the option renders.
    let searchInput = null;
    const ae = document.activeElement;
    if (ae && (ae.tagName === "INPUT" || ae.tagName === "TEXTAREA") && ae !== field) {
      searchInput = ae;
    }
    if (!searchInput) {
      const openBoxes = Array.from(
        document.querySelectorAll('[role="listbox"],[role="dialog"]')
      );
      for (const box of openBoxes) {
        const inp = box.querySelector('input[type="text"],input:not([type])');
        if (inp) {
          const r = inp.getBoundingClientRect();
          if (r.width && r.height) { searchInput = inp; break; }
        }
      }
    }
    if (searchInput) {
      LOG(`${labelText} searchInput found, typing to filter`);
      await typeIntoInput(searchInput, val);
      await sleep(500);
    }

    const wantLower = val.toLowerCase();
    const matchOpt = (o) => {
      const txt = (o.textContent || "").trim().toLowerCase();
      if (!txt) return false;
      if (exact) return txt === wantLower;
      return (
        txt === wantLower || txt.includes(wantLower) || wantLower.includes(txt)
      );
    };

    // Scan options; if not found, scroll the (virtualized) listbox and retry.
    let option = null;
    let lastCount = -1;
    for (let attempt = 0; attempt < 14 && !option; attempt++) {
      const listboxes = Array.from(
        document.querySelectorAll('[role="listbox"]')
      );
      let optionEls = [];
      for (const lb of listboxes) {
        optionEls = optionEls.concat(
          Array.from(lb.querySelectorAll('[role="option"]'))
        );
      }
      option = optionEls.find(matchOpt);
      if (option) break;

      if (listboxes.length) {
        const lb = listboxes[listboxes.length - 1];
        lb.scrollTop = lb.scrollTop + Math.max(220, lb.clientHeight || 220);
        if (optionEls.length === lastCount && attempt > 2) break; // hit bottom
        lastCount = optionEls.length;
      }
      await sleep(180);
    }

    if (option) {
      LOG(`${labelText} option:`, option.textContent.trim());
      option.scrollIntoView({ block: "nearest" });
      option.click();
    } else {
      LOG(`${labelText} option not found for: ${val}`);
      const seen = [];
      document
        .querySelectorAll('[role="listbox"] [role="option"]')
        .forEach((o) => {
          const t = (o.textContent || "").trim();
          if (t) seen.push(t);
        });
      if (seen.length)
        LOG(`${labelText} available options:`, JSON.stringify(seen.slice(0, 20)));
    }
    await sleep(200);
    return !!option;
  }

  // ---------- Color mapping + clean-title helpers ----------

  function normalizeColor(raw) {
    const s = String(raw || "").toLowerCase();
    if (!s) return "";
    // order matters: check compound terms before bare ones
    const map = [
      ["off white", "Off white"],
      ["steel", "Gray"],
      ["charcoal", "Charcoal"],
      ["white", "White"],
      ["black", "Black"],
      ["silver", "Silver"],
      ["grey", "Gray"],
      ["gray", "Gray"],
      ["red", "Red"],
      ["blue", "Blue"],
      ["green", "Green"],
      ["brown", "Brown"],
      ["beige", "Beige"],
      ["tan", "Tan"],
      ["gold", "Gold"],
      ["orange", "Orange"],
      ["yellow", "Yellow"],
      ["purple", "Purple"],
      ["pink", "Pink"],
      ["burgundy", "Burgundy"],
      ["turquoise", "Turquoise"],
    ];
    for (const [k, v] of map) if (s.includes(k)) return v;
    return ""; // unknown -> leave blank for the user to pick
  }

  function mapVehicleCondition(raw) {
    const s = String(raw || "").toLowerCase().trim();
    if (!s || s === "new") return "Excellent";
    if (s.includes("like new") || s.includes("certified")) return "Very good";
    if (s.includes("excellent")) return "Excellent";
    if (s.includes("very good")) return "Very good";
    if (s.includes("fair")) return "Fair";
    if (s.includes("poor")) return "Poor";
    if (s.includes("good")) return "Good";
    if (s.includes("new")) return "Excellent";
    return "Good";
  }

  async function checkCleanTitle(scope) {
    const els = [
      ...scope.querySelectorAll(
        '[role="checkbox"],[role="switch"],input[type="checkbox"]'
      ),
    ];
    for (const el of els) {
      const al = (el.getAttribute("aria-label") || "").toLowerCase();
      const near = (el.closest("label")?.textContent || "").toLowerCase();
      if ((al + " " + near).includes("clean title")) {
        const checked =
          el.getAttribute("aria-checked") === "true" || el.checked === true;
        if (!checked) {
          el.click();
          LOG("Clean title checked");
        } else {
          LOG("Clean title already checked");
        }
        await sleep(120);
        return true;
      }
    }
    LOG("Clean title checkbox not found");
    return false;
  }

  // ---------- TEMP DIAGNOSTIC: dump remaining form labels (remove later) ----------

  function dumpVehicleFormLabels(scope) {
    try {
      const labels = [...scope.querySelectorAll("span,label")]
        .map((s) => (s.textContent || "").trim())
        .filter(
          (t) =>
            t.length > 1 &&
            t.length < 30 &&
            /exterior|interior|body style|body type|condition|fuel|transmission|clean title|title status/i.test(
              t
            )
        );
      LOG("FORM-LABELS:", JSON.stringify([...new Set(labels)]));

      const checks = [
        ...scope.querySelectorAll(
          '[role="checkbox"],[role="switch"],input[type="checkbox"]'
        ),
      ].map(
        (e) =>
          e.getAttribute("aria-label") ||
          (e.closest("label")?.textContent || "").trim() ||
          "(no label)"
      );
      LOG("FORM-CHECKBOXES:", JSON.stringify([...new Set(checks)]));
    } catch (e) {
      LOG("dumpVehicleFormLabels error:", e);
    }
  }

  // ---------- Special: Description finder ----------

  function findDescriptionEditable(scope = document) {
    // 1) Try input/textarea with description-like labels first
    const textInput = findInputByLabels(
      ["description", "describe your vehicle", "describe your listing"],
      scope
    );
    if (textInput) {
      LOG("Description as input/textarea:", textInput);
      return { el: textInput, isContentEditable: false };
    }

    // 2) Then contenteditable
    const root =
      scope.querySelector('[data-pagelet="MarketplaceComposerPagelet"]') ||
      scope.querySelector('[aria-label*="Marketplace"]') ||
      scope;

    const editables = Array.from(
      root.querySelectorAll('[contenteditable="true"],[role="textbox"]')
    );
    if (!editables.length) {
      LOG("No contenteditable/role=textboxes found for description searching");
      return null;
    }

    let candidate = editables.find((n) => {
      const label = (n.getAttribute("aria-label") || "").toLowerCase();
      const ph = (n.getAttribute("placeholder") || "").toLowerCase();
      const txt = (n.textContent || "").toLowerCase();
      return (
        label.includes("description") ||
        label.includes("describe") ||
        ph.includes("description") ||
        ph.includes("describe") ||
        txt.includes("describe your vehicle") ||
        txt.includes("describe your listing")
      );
    });

    if (!candidate) {
      // fallback: biggest editable block
      const scored = editables
        .map((n) => {
          const r = n.getBoundingClientRect();
          return { n, area: r.width * r.height };
        })
        .filter((x) => x.area > 50 * 50)
        .sort((a, b) => b.area - a.area);

      candidate = scored[0]?.n || null;
    }

    if (candidate) {
      LOG("Description as contenteditable:", candidate);
      return { el: candidate, isContentEditable: true };
    }
    LOG("No suitable description editable found");
    return null;
  }

  // ---------- Listing data from background ----------

  function normalizeListing(listingRaw) {
    // listingRaw from your logs looks like:
    // { title, year, make, model, price, description, ... }
    if (!listingRaw) listingRaw = {};

    const title =
      listingRaw.Title ||
      listingRaw.title ||
      "";

    const year =
      listingRaw.Year ||
      listingRaw.year ||
      "";

    const make =
      listingRaw.Make ||
      listingRaw.make ||
      "";

    const model =
      listingRaw.Model ||
      listingRaw.model ||
      "";

    const price =
      listingRaw.Price ||
      listingRaw.price ||
      "";

    const description =
      listingRaw.Description ||
      listingRaw.description ||
      "";

    const mileage =
      listingRaw.Mileage ||
      listingRaw.mileage ||
      "";

    const condition =
      listingRaw.Condition ||
      listingRaw.condition ||
      "";

    const exteriorColor = normalizeColor(
      listingRaw.ExteriorColor ||
        listingRaw.exterior_color ||
        listingRaw.exteriorColor ||
        ""
    );

    const interiorColor = normalizeColor(
      listingRaw.InteriorColor ||
        listingRaw.interior_color ||
        listingRaw.interiorColor ||
        ""
    );

    const bodyStyle =
      listingRaw.BodyStyle ||
      listingRaw.body_type ||
      listingRaw.bodyType ||
      listingRaw.body_style ||
      "";

    let fuelType =
      listingRaw.FuelType ||
      listingRaw.fuel_type ||
      listingRaw.fuelType ||
      "";
    if (!fuelType) fuelType = "Gasoline"; // sensible default; user reviews

    const normalized = {
      Title: title,
      Year: year,
      Make: make,
      Model: model,
      Price: price,
      Description: description,
      Mileage: mileage,
      Condition: condition,
      ExteriorColor: exteriorColor,
      InteriorColor: interiorColor,
      BodyStyle: bodyStyle,
      FuelType: fuelType,
    };

    LOG("Using normalized listing:", normalized);
    return normalized;
  }

  async function getListingFromBackground() {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ type: "FB_GET_VEHICLE_DATA" }, (resp) => {
          if (chrome.runtime.lastError) {
            LOG("chrome.runtime.lastError:", chrome.runtime.lastError.message);
          }
          resolve(resp || null);
        });
      } catch (e) {
        LOG("Error sending message to background:", e);
        resolve(null);
      }
    });
  }

  // ---------- IMAGE HELPERS (updated) ----------

  async function fetchImagesViaBackground(urls) {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage(
          { type: "FETCH_IMAGES", urls: urls || [] },
          (resp) => {
            if (chrome.runtime.lastError) {
              LOG("FETCH_IMAGES lastError:", chrome.runtime.lastError.message);
              resolve([]);
              return;
            }
            if (!resp || !Array.isArray(resp.images)) {
              resolve([]);
            } else {
              resolve(resp.images);
            }
          }
        );
      } catch (e) {
        LOG("Error sending FETCH_IMAGES:", e);
        resolve([]);
      }
    });
  }

  async function uploadImagesFromUrls(imageUrls, scope = document) {
    if (!Array.isArray(imageUrls) || !imageUrls.length) {
      LOG("[fb-fill] No image URLs to upload");
      return;
    }

    // Find the file input behind "Add photos"
    const fileInputs = Array.from(
      scope.querySelectorAll('input[type="file"]')
    ).filter((inp) => {
      const accept = (inp.getAttribute("accept") || "").toLowerCase();
      return accept.includes("image") || accept === "";
    });

    const fileInput = fileInputs[0];
    if (!fileInput) {
      LOG("[fb-fill] No file input for photos found");
      return;
    }

    LOG("[fb-fill] Using file input for images:", fileInput);

    // Bug 3 fix: fetch ALL images first, then assign to fileInput ONCE.
    // Assigning fileInput.files inside a loop overwrites the previous
    // assignment each iteration — Facebook's React handler may only see
    // the last (or first) assignment, producing inconsistent upload counts.
    const MAX_IMAGES = 20;
    const urls = imageUrls.slice(0, MAX_IMAGES);
    LOG(`[fb-fill] Fetching ${urls.length} images for batch upload`);

    // STEP 1 — fetch every image, collect File objects. Do NOT touch
    // fileInput.files inside this loop.
    const files = [];
    for (let i = 0; i < urls.length; i++) {
      const url = urls[i];
      try {
        const resp = await fetch(url, { mode: "cors" });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const blob = await resp.blob();
        const ext  = (blob.type || "image/jpeg").split("/")[1]?.split("+")[0] || "jpg";
        const name = `vehicle-${Date.now()}-${i}.${ext}`;
        files.push(new File([blob], name, { type: blob.type || "image/jpeg" }));
      } catch (e) {
        LOG(`[fb-fill] Failed to fetch image ${i + 1}/${urls.length}:`, url, e.message);
      }
    }

    if (!files.length) {
      LOG("[fb-fill] No images successfully fetched — aborting upload");
      return;
    }

    // STEP 2 — build ONE DataTransfer with ALL files, assign ONCE.
    const dt = new DataTransfer();
    files.forEach((f) => dt.items.add(f));

    LOG(`[fb-fill] Uploading ${files.length} images in a single batch`);
    fileInput.files = dt.files;
    fileInput.dispatchEvent(new Event("input", { bubbles: true }));
    fileInput.dispatchEvent(new Event("change", { bubbles: true }));

    // STEP 3 — wait proportionally to image count so Facebook has time to
    // process the full batch (base 2s + 300ms per image, capped at 12s).
    const waitMs = Math.min(2000 + files.length * 300, 12000);
    await sleep(waitMs);

    LOG("[fb-fill] Image upload sequence complete.");
  }

  // ---------- Main fill logic ----------

  async function fillFromListing(listingRaw) {
    const listing = normalizeListing(listingRaw);

    const composer = await waitForComposer(document, 20000);
    if (!composer) {
      LOG("No composer, aborting fill.");
      return;
    }

    await selectVehicleTypeCarTruck(composer)

    // Price
    if (listing.Price) {
      const priceInput = findInputByLabels(["price"], composer);
      LOG("Price input:", priceInput);
      if (priceInput) {
        await typeIntoInput(priceInput, String(listing.Price));
        await sleep(80);
      }
    }

    // Make – dropdown on the Car/Truck form
    if (listing.Make) {
      await selectFromDropdown(composer, "Make", listing.Make);
      await sleep(80);
    }

    // Model
    if (listing.Model) {
      const modelInput = findInputByLabels(["model"], composer);
      LOG("Model input:", modelInput);
      if (modelInput) {
        await typeIntoInput(modelInput, String(listing.Model));
        await sleep(80);
      }
    }

    // Mileage – text input; new vehicles default to a minimum
    {
      const NEW_CAR_MIN_MILEAGE = "300"; // change here if FB needs different
      let mileageVal = String(listing.Mileage || "").replace(/[^0-9]/g, "");
      const cond = String(listing.Condition || "").toLowerCase();
      if (!mileageVal || cond.includes("new")) {
        mileageVal = NEW_CAR_MIN_MILEAGE;
      }
      const mileageInput = findInputByLabels(["mileage"], composer);
      LOG("Mileage input:", mileageInput, "value:", mileageVal);
      if (mileageInput) {
        await typeIntoInput(mileageInput, mileageVal);
        await sleep(80);
      }
    }

    // Year – use dedicated finder
    if (listing.Year) {
      await selectYearFromDropdown(composer, listing.Year);
    }

    // Body style – dropdown
    if (listing.BodyStyle) {
      await selectFromDropdown(composer, "Body style", listing.BodyStyle);
      await sleep(80);
    }

    // Exterior color – dropdown
    if (listing.ExteriorColor) {
      await selectFromDropdown(composer, "Exterior color", listing.ExteriorColor);
      await sleep(80);
    }

    // Interior color – dropdown
    if (listing.InteriorColor) {
      await selectFromDropdown(composer, "Interior color", listing.InteriorColor);
      await sleep(80);
    }

    // Vehicle condition – dropdown (map New -> Excellent, etc.)
    if (listing.Condition) {
      await selectFromDropdown(
        composer,
        "Vehicle condition",
        mapVehicleCondition(listing.Condition)
      );
      await sleep(80);
    }

    // Fuel type – dropdown
    if (listing.FuelType) {
      await selectFromDropdown(composer, "Fuel type", listing.FuelType);
      await sleep(80);
    }

    // Clean title checkbox
    await checkCleanTitle(composer);

    // Description – textarea or contenteditable
    if (listing.Description) {
      await sleep(300);
      const desc = findDescriptionEditable(document);
      LOG("Description field:", desc);
      if (desc && desc.el) {
        if (desc.isContentEditable) {
          await typeContentEditable(desc.el, String(listing.Description));
        } else {
          await typeIntoInput(desc.el, String(listing.Description));
        }
      }
    }

    // >>> IMAGES (unchanged call, new behavior inside helper)
    if (listingRaw && Array.isArray(listingRaw.images) && listingRaw.images.length) {
      LOG("[fb-fill] Attempting to upload images:", listingRaw.images);
      try {
        await uploadImagesFromUrls(listingRaw.images, document);
      } catch (e) {
        LOG("[fb-fill] Image upload failed:", e);
      }
    }

    LOG("Fill routine completed.");
  }

  // ---------- Entry point ----------

  async function run() {
    LOG("run() starting...");
    await sleep(800); // let FB UI settle

    const payload = await getListingFromBackground();
    LOG("Background payload:", payload);

    const listingRaw = payload && payload.listing ? payload.listing : null;
    await fillFromListing(listingRaw);
  }

  run();

  // Retry once if FB hot-reloads composer
  const mo = new MutationObserver(() => {
    const composer = document.querySelector(
      '[data-pagelet="MarketplaceComposerPagelet"]'
    );
    if (composer && !window.__fbFillRanTwice) {
      window.__fbFillRanTwice = true;
      LOG("MutationObserver triggering second run()");
      run();
    }
  });
  mo.observe(document.documentElement, { childList: true, subtree: true });
})();
