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

  async function selectVehicleTypeOther(scope) {
    const targetText = "Other";

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

    const normalized = {
      Title: title,
      Year: year,
      Make: make,
      Model: model,
      Price: price,
      Description: description,
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
      const r = inp.getBoundingClientRect();
      // Likely visible/used input with image accept or empty accept
      return (accept.includes("image") || accept === "") && r.width >= 0 && r.height >= 0;
    });

    const fileInput = fileInputs[0];
    if (!fileInput) {
      LOG("[fb-fill] No file input for photos found");
      return;
    }

    LOG("[fb-fill] Using file input for images:", fileInput);

    const fetched = await fetchImagesViaBackground(imageUrls);
    if (!fetched.length) {
      LOG("[fb-fill] Background returned no images");
      return;
    }

    // Upload images one-by-one so Facebook actually processes each file
    for (let i = 0; i < fetched.length; i++) {
      const img = fetched[i];
      if (!img || !img.base64) continue;

      try {
        const bytes = Uint8Array.from(
          atob(img.base64),
          (c) => c.charCodeAt(0)
        );
        const blob = new Blob([bytes], { type: img.mime || "image/jpeg" });
        const ext = (img.mime || "image/jpeg").split("/")[1] || "jpg";
        const name = img.name || `vehicle-${Date.now()}-${i}.${ext}`;
        const file = new File([blob], name, { type: img.mime || "image/jpeg" });

        const dt = new DataTransfer();
        dt.items.add(file);

        fileInput.files = dt.files;
        fileInput.dispatchEvent(new Event("input", { bubbles: true }));
        fileInput.dispatchEvent(new Event("change", { bubbles: true }));

        LOG(`[fb-fill] Uploaded image ${i + 1}/${fetched.length}`);
        // Give FB time to recognize & start uploading this image
        await sleep(900);
      } catch (e) {
        LOG("[fb-fill] Failed to upload image", i, e);
      }
    }

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

    await selectVehicleTypeOther(composer)

    // Price
    if (listing.Price) {
      const priceInput = findInputByLabels(["price"], composer);
      LOG("Price input:", priceInput);
      if (priceInput) {
        await typeIntoInput(priceInput, String(listing.Price));
        await sleep(80);
      }
    }

    // Make
    if (listing.Make) {
      const makeInput = findInputByLabels(["make"], composer);
      LOG("Make input:", makeInput);
      if (makeInput) {
        await typeIntoInput(makeInput, String(listing.Make));
        await sleep(80);
      }
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

    // Year – use dedicated finder
    if (listing.Year) {
      await selectYearFromDropdown(composer, listing.Year);
    }

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
