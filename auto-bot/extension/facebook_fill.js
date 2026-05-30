// facebook_fill.js
// Fills Facebook Marketplace Vehicle composer using data from the extension.
//
// It expects the background script to respond to:
//   { type: "FB_GET_VEHICLE_DATA" } -> { listing: { title, year, make, model, price, description, ... } }
//
// This script:
//   - Uses the *real* listing data
//   - Fills Price, Make, Model, Year (dropdown/combobox), Mileage, and Description
//   - Handles React-style inputs + contenteditable fields
//   - Vehicle Type maps to "Car/Truck" for standard vehicles
//   - Mileage defaults to 300 when blank (FB requires a value; new cars have 0)

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
      desc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");
    } else if (tag === "TEXTAREA") {
      desc = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value");
    }
    const proto = Object.getPrototypeOf(el);
    const protoDesc = proto && Object.getOwnPropertyDescriptor(proto, "value");
    if (protoDesc && desc && protoDesc.set && protoDesc.set !== desc.set) {
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
      el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
      await sleep(50);
      el.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", bubbles: true }));
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
    const all = Array.from(scope.querySelectorAll("input,textarea"));
    for (const el of all) {
      const ph = (el.getAttribute("placeholder") || "").toLowerCase();
      const al = (el.getAttribute("aria-label") || "").toLowerCase();
      if (lower.some((lbl) => ph === lbl || ph.includes(lbl) || al === lbl || al.includes(lbl))) {
        const r = el.getBoundingClientRect();
        if (r.width && r.height) return el;
      }
    }
    const labelsNodes = Array.from(scope.querySelectorAll("label,div,span,strong")).filter((n) => {
      const t = (n.textContent || "").trim().toLowerCase();
      return lower.some((lbl) => t === lbl || t.includes(lbl));
    });
    for (const lab of labelsNodes) {
      const container = lab.closest('form,[role="group"],[data-visualcompletion],section,div,[aria-labelledby]') || lab.parentElement;
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

  // ---------- Year finder ----------

  function findYearField(scope) {
    const candidates = Array.from(scope.querySelectorAll('input,textarea,[role="combobox"],[role="textbox"]'));
    const lowerMatch = (txt) => (txt || "").toLowerCase().includes("year");
    for (const el of candidates) {
      const al = (el.getAttribute("aria-label") || "").toLowerCase();
      const ph = (el.getAttribute("placeholder") || "").toLowerCase();
      const id = (el.id || "").toLowerCase();
      if (lowerMatch(al) || lowerMatch(ph) || lowerMatch(id)) {
        const r = el.getBoundingClientRect();
        if (r.width && r.height) return el;
      }
    }
    const labels = Array.from(scope.querySelectorAll("label,div,span,strong")).filter((n) => {
      const t = (n.textContent || "").trim().toLowerCase();
      return t === "year" || t.includes("year");
    });
    for (const lab of labels) {
      const container = lab.closest('form,[role="group"],[data-visualcompletion],section,div,[aria-labelledby]') || lab.parentElement;
      if (!container) continue;
      const input = container.querySelector('input,textarea,[role="combobox"],[role="textbox"]');
      if (input) {
        const r = input.getBoundingClientRect();
        if (r.width && r.height) return input;
      }
    }
    return null;
  }

  async function selectYearFromDropdown(scope, yearValue) {
    const yearStr = String(yearValue || "").trim();
    if (!yearStr) return;
    const yearField = findYearField(scope);
    if (!yearField) { LOG("Year field not found"); return; }

    // Click to focus/open, then TYPE the year so FB filters the listbox
    yearField.click();
    yearField.focus?.();
    await sleep(300);
    setNativeValue(yearField, yearStr);
    fireInputEvents(yearField);
    await sleep(500); // wait for FB to render matching options

    const listboxes = Array.from(document.querySelectorAll('[role="listbox"]'));
    let option = null;
    for (const lb of listboxes) {
      const opts = Array.from(lb.querySelectorAll('[role="option"]'));
      option = opts.find((o) => {
        const txt = (o.textContent || "").trim();
        return txt === yearStr || txt.includes(yearStr);
      });
      if (option) {
        option.scrollIntoView({ block: "nearest" });
        option.click();
        break;
      }
    }
    if (!option) LOG("Year option not found for:", yearStr);
    else await sleep(200);
  }

  // ---------- Vehicle Type ----------

  // Maps dealer body type to Facebook's vehicle type dropdown options.
  // Facebook options: Car/Truck, Motorcycle, RV/Camper, Boat, Powersports, Other
  function mapToFBVehicleType(bodyType) {
    const b = (bodyType || "").toLowerCase().trim();
    if (/motorcycle|bike|scooter|moped/.test(b)) return "Motorcycle";
    if (/rv|camper|motorhome|recreational/.test(b)) return "RV/Camper";
    if (/boat|yacht|marine|watercraft/.test(b)) return "Boat";
    if (/atv|utv|snowmobile|powersport|jet\s*ski/.test(b)) return "Powersports";
    // Everything else (sedan, suv, truck, van, coupe, hatchback, wagon, etc.)
    return "Car/Truck";
  }

  function findVehicleTypeField(scope) {
    const candidates = Array.from(scope.querySelectorAll('[role="combobox"],input,textarea,[role="textbox"]'));
    const lowerMatch = (txt) => (txt || "").toLowerCase().includes("vehicle type");
    for (const el of candidates) {
      const al = (el.getAttribute("aria-label") || "").toLowerCase();
      const ph = (el.getAttribute("placeholder") || "").toLowerCase();
      const id = (el.id || "").toLowerCase();
      if (lowerMatch(al) || lowerMatch(ph) || lowerMatch(id)) {
        const r = el.getBoundingClientRect();
        if (r.width && r.height) return el;
      }
    }
    const labels = Array.from(scope.querySelectorAll("label,div,span,strong")).filter((n) => {
      const t = (n.textContent || "").trim().toLowerCase();
      return t === "vehicle type" || t.includes("vehicle type");
    });
    for (const lab of labels) {
      const container = lab.closest('form,[role="group"],[data-visualcompletion],section,div,[aria-labelledby]') || lab.parentElement;
      if (!container) continue;
      const input = container.querySelector('[role="combobox"],input,textarea,[role="textbox"]');
      if (input) {
        const r = input.getBoundingClientRect();
        if (r.width && r.height) return input;
      }
    }
    return null;
  }

  async function selectVehicleType(scope, bodyType) {
    const targetText = mapToFBVehicleType(bodyType);
    const vtField = findVehicleTypeField(scope);
    if (!vtField) { LOG("Vehicle type field not found"); return; }
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
    if (!option) LOG("Vehicle type option not found:", targetText);
    else await sleep(200);
  }

  // ---------- Description finder ----------

  function findDescriptionEditable(scope = document) {
    const textInput = findInputByLabels(["description", "describe your vehicle", "describe your listing"], scope);
    if (textInput) return { el: textInput, isContentEditable: false };
    const root = scope.querySelector('[data-pagelet="MarketplaceComposerPagelet"]') ||
      scope.querySelector('[aria-label*="Marketplace"]') || scope;
    const editables = Array.from(root.querySelectorAll('[contenteditable="true"],[role="textbox"]'));
    if (!editables.length) return null;
    let candidate = editables.find((n) => {
      const label = (n.getAttribute("aria-label") || "").toLowerCase();
      const ph = (n.getAttribute("placeholder") || "").toLowerCase();
      const txt = (n.textContent || "").toLowerCase();
      return label.includes("description") || label.includes("describe") ||
        ph.includes("description") || ph.includes("describe") ||
        txt.includes("describe your vehicle") || txt.includes("describe your listing");
    });
    if (!candidate) {
      const scored = editables
        .map((n) => { const r = n.getBoundingClientRect(); return { n, area: r.width * r.height }; })
        .filter((x) => x.area > 50 * 50)
        .sort((a, b) => b.area - a.area);
      candidate = scored[0]?.n || null;
    }
    return candidate ? { el: candidate, isContentEditable: true } : null;
  }

  // ---------- Listing normalization ----------

  function normalizeListing(listingRaw) {
    if (!listingRaw) listingRaw = {};
    const raw = listingRaw;

    // Mileage — default to 300 for new cars (FB requires a value)
    let mileage = raw.Mileage || raw.mileage || raw.Miles || raw.miles || "";
    const mileageNum = parseInt(String(mileage).replace(/\D/g, ""), 10);
    if (!mileageNum || mileageNum < 300) mileage = "300";
    else mileage = String(mileageNum);

    const normalized = {
      Title:         raw.Title         || raw.title         || "",
      Year:          raw.Year          || raw.year          || "",
      Make:          raw.Make          || raw.make          || "",
      Model:         raw.Model         || raw.model         || "",
      Price:         raw.Price         || raw.price         || "",
      Description:   raw.Description   || raw.description   || "",
      BodyType:      raw["Body Type"]  || raw.bodyType      || raw.vehicleType || raw.VehicleType || "",
      Mileage:       mileage,
      ExteriorColor: raw["Exterior Color"] || raw.exteriorColor || raw.exterior_color || "",
      InteriorColor: raw["Interior Color"] || raw.interiorColor || raw.interior_color || "",
      Condition:     raw.Condition     || raw.condition     || "",
      FuelType:      raw["Fuel Type"]  || raw.fuelType      || raw.fuel_type   || "",
      Transmission:  raw["Transmission"] || raw.transmission || "",
    };

    LOG("Normalized listing:", normalized);
    return normalized;
  }

  // ---------- Background messaging ----------

  async function getListingFromBackground() {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ type: "FB_GET_VEHICLE_DATA" }, (resp) => {
          if (chrome.runtime.lastError) LOG("lastError:", chrome.runtime.lastError.message);
          resolve(resp || null);
        });
      } catch (e) {
        LOG("Error sending message:", e);
        resolve(null);
      }
    });
  }

  // ---------- Image upload ----------

  async function fetchImagesViaBackground(urls) {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ type: "FETCH_IMAGES", urls: urls || [] }, (resp) => {
          if (chrome.runtime.lastError) { resolve([]); return; }
          resolve((resp && Array.isArray(resp.images)) ? resp.images : []);
        });
      } catch (e) {
        LOG("Error sending FETCH_IMAGES:", e);
        resolve([]);
      }
    });
  }

  async function uploadImagesFromUrls(imageUrls, scope = document) {
    if (!Array.isArray(imageUrls) || !imageUrls.length) return;

    // Filter out video thumbnails and non-image URLs
    const cleanUrls = imageUrls.filter((u) => {
      if (!u || typeof u !== "string") return false;
      if (/video|\.mp4|blob:|\/play\//i.test(u)) return false;
      return true;
    });

    if (!cleanUrls.length) { LOG("No clean image URLs after filtering"); return; }

    const fileInputs = Array.from(scope.querySelectorAll('input[type="file"]')).filter((inp) => {
      const accept = (inp.getAttribute("accept") || "").toLowerCase();
      return accept.includes("image") || accept === "";
    });
    const fileInput = fileInputs[0];
    if (!fileInput) { LOG("No file input for photos found"); return; }

    const fetched = await fetchImagesViaBackground(cleanUrls);
    if (!fetched.length) { LOG("Background returned no images"); return; }

    for (let i = 0; i < fetched.length; i++) {
      const img = fetched[i];
      if (!img || !img.base64) continue;
      try {
        const bytes = Uint8Array.from(atob(img.base64), (c) => c.charCodeAt(0));
        const blob = new Blob([bytes], { type: img.mime || "image/jpeg" });
        const ext = (img.mime || "image/jpeg").split("/")[1] || "jpg";
        const file = new File([blob], img.name || `vehicle-${Date.now()}-${i}.${ext}`, { type: img.mime || "image/jpeg" });
        const dt = new DataTransfer();
        dt.items.add(file);
        fileInput.files = dt.files;
        fileInput.dispatchEvent(new Event("input", { bubbles: true }));
        fileInput.dispatchEvent(new Event("change", { bubbles: true }));
        LOG(`Uploaded image ${i + 1}/${fetched.length}`);
        await sleep(900);
      } catch (e) {
        LOG("Failed to upload image", i, e);
      }
    }
    LOG("Image upload complete.");
  }

  // ---------- Generic dropdown helper ----------
  // Finds a combobox by visible label text, clicks it, waits for the listbox,
  // then picks the best-matching option. Falls back gracefully if not found.

  async function selectLabelledDropdown(scope, labelKeywords, targetValue) {
    const val = String(targetValue || "").trim();
    if (!val) return;

    const lower = labelKeywords.map((l) => l.toLowerCase());

    // Find the combobox element by searching for visible label text nearby
    let field = null;
    const labelNodes = Array.from(scope.querySelectorAll("label,div,span,strong,legend")).filter((n) => {
      const t = (n.textContent || "").trim().toLowerCase();
      return lower.some((lbl) => t === lbl || t === lbl + "*" || t.startsWith(lbl));
    });
    for (const lab of labelNodes) {
      const container = lab.closest('[data-visualcompletion],[role="group"],form,section,div') || lab.parentElement;
      if (!container) continue;
      const el = container.querySelector('[role="combobox"],[role="button"],input,select');
      if (el && el !== lab) {
        const r = el.getBoundingClientRect();
        if (r.width && r.height) { field = el; break; }
      }
    }
    // Also try aria-label / placeholder directly on comboboxes
    if (!field) {
      const combos = Array.from(scope.querySelectorAll('[role="combobox"],[role="button"],select,input'));
      for (const el of combos) {
        const al = (el.getAttribute("aria-label") || "").toLowerCase();
        const ph = (el.getAttribute("placeholder") || "").toLowerCase();
        if (lower.some((lbl) => al.includes(lbl) || ph.includes(lbl))) {
          const r = el.getBoundingClientRect();
          if (r.width && r.height) { field = el; break; }
        }
      }
    }

    if (!field) { LOG("selectLabelledDropdown: field not found for", labelKeywords); return; }

    field.click();
    field.focus?.();
    await sleep(400);

    const valLower = val.toLowerCase();
    const listboxes = Array.from(document.querySelectorAll('[role="listbox"]'));
    let picked = false;
    for (const lb of listboxes) {
      const opts = Array.from(lb.querySelectorAll('[role="option"]'));
      const pick = opts.find((o) => (o.textContent || "").trim().toLowerCase() === valLower)
                || opts.find((o) => (o.textContent || "").trim().toLowerCase().startsWith(valLower))
                || opts.find((o) => (o.textContent || "").trim().toLowerCase().includes(valLower));
      if (pick) {
        LOG("selectLabelledDropdown: picked", pick.textContent.trim(), "for", labelKeywords);
        pick.scrollIntoView({ block: "nearest" });
        pick.click();
        await sleep(250);
        picked = true;
        break;
      }
    }
    if (!picked) LOG("selectLabelledDropdown: no match for", val, "in", labelKeywords);
  }

  // ---------- Main fill ----------

  async function fillFromListing(listingRaw) {
    const listing = normalizeListing(listingRaw);
    const composer = await waitForComposer(document, 20000);
    if (!composer) { LOG("No composer, aborting."); return; }

    // 1. Vehicle Type
    await selectVehicleType(composer, listing.BodyType);

    // 2. Price
    if (listing.Price) {
      const priceInput = findInputByLabels(["price"], composer);
      if (priceInput) { await typeIntoInput(priceInput, String(listing.Price)); await sleep(80); }
    }

    // 3. Mileage
    if (listing.Mileage) {
      const mileageInput = findInputByLabels(["mileage", "miles"], composer);
      if (mileageInput) { await typeIntoInput(mileageInput, String(listing.Mileage)); await sleep(80); }
    }

    // 4. Make — FB uses a combobox: type to filter, then pick from listbox
    if (listing.Make) {
      const makeInput = findInputByLabels(["make"], composer);
      if (makeInput) {
        await typeIntoInput(makeInput, String(listing.Make));
        await sleep(500); // wait for listbox to appear with filtered options
        const makeLower = listing.Make.toLowerCase();
        const makeListboxes = Array.from(document.querySelectorAll('[role="listbox"]'));
        for (const lb of makeListboxes) {
          const opts = Array.from(lb.querySelectorAll('[role="option"]'));
          const pick = opts.find((o) => (o.textContent || "").trim().toLowerCase() === makeLower)
                    || opts.find((o) => (o.textContent || "").trim().toLowerCase().startsWith(makeLower))
                    || opts.find((o) => (o.textContent || "").trim().toLowerCase().includes(makeLower));
          if (pick) {
            pick.scrollIntoView({ block: "nearest" });
            pick.click();
            await sleep(300);
            break;
          }
        }
      }
    }

    // 5. Model
    if (listing.Model) {
      const modelInput = findInputByLabels(["model"], composer);
      if (modelInput) { await typeIntoInput(modelInput, String(listing.Model)); await sleep(80); }
    }

    // 6. Year
    if (listing.Year) {
      await selectYearFromDropdown(composer, listing.Year);
    }

    // 7. Body style (e.g. "Sedan", "SUV", "Truck" — the dealer's actual body type)
    if (listing.BodyType) {
      await selectLabelledDropdown(composer, ["body style", "body type"], listing.BodyType);
      await sleep(200);
    }

    // 8. Exterior color
    if (listing.ExteriorColor) {
      await selectLabelledDropdown(composer, ["exterior color", "color", "ext. color"], listing.ExteriorColor);
      await sleep(200);
    }

    // 9. Interior color
    if (listing.InteriorColor) {
      await selectLabelledDropdown(composer, ["interior color", "int. color"], listing.InteriorColor);
      await sleep(200);
    }

    // 10. Vehicle condition (Bug #12)
    if (listing.Condition) {
      await selectLabelledDropdown(composer, ["condition", "vehicle condition"], listing.Condition);
      await sleep(200);
    }

    // 11. Fuel type (Bug #13)
    if (listing.FuelType) {
      await selectLabelledDropdown(composer, ["fuel type", "fuel"], listing.FuelType);
      await sleep(200);
    }

    // 12. Transmission
    if (listing.Transmission) {
      await selectLabelledDropdown(composer, ["transmission"], listing.Transmission);
      await sleep(200);
    }

    // 12. Description
    if (listing.Description) {
      await sleep(300);
      const desc = findDescriptionEditable(document);
      if (desc && desc.el) {
        if (desc.isContentEditable) {
          await typeContentEditable(desc.el, String(listing.Description));
        } else {
          await typeIntoInput(desc.el, String(listing.Description));
        }
      }
    }

    // 8. Images
    if (listingRaw && Array.isArray(listingRaw.images) && listingRaw.images.length) {
      try {
        await uploadImagesFromUrls(listingRaw.images, document);
      } catch (e) {
        LOG("Image upload failed:", e);
      }
    }

    LOG("Fill routine completed.");
  }

  // ---------- Entry point ----------

  async function run() {
    LOG("run() starting...");
    await sleep(800);
    const payload = await getListingFromBackground();
    LOG("Background payload:", payload);
    const listingRaw = payload && payload.listing ? payload.listing : null;
    await fillFromListing(listingRaw);
  }

  run();

  // Retry once if FB hot-reloads composer
  const mo = new MutationObserver(() => {
    const composer = document.querySelector('[data-pagelet="MarketplaceComposerPagelet"]');
    if (composer && !window.__fbFillRanTwice) {
      window.__fbFillRanTwice = true;
      LOG("MutationObserver triggering second run()");
      run();
    }
  });
  mo.observe(document.documentElement, { childList: true, subtree: true });
})();
