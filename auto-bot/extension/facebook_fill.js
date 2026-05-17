// facebook_fill.js
// Fills Facebook Marketplace Vehicle composer using data from the extension.
//
// It expects the background script to respond to:
//   { type: "FB_GET_VEHICLE_DATA" } -> { listing: { title, year, make, model, price, description, ... } }
//
// This script:
//   - Uses the *real* listing data (no more Toyota/Camry defaults)
//   - Fills: Vehicle Type, Price, Mileage, Make, Model, Year, Body Style,
//            Exterior Color, Interior Color, Condition, Fuel Type, Clean Title,
//            and Description
//   - Handles React-style inputs + contenteditable fields
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

  // Find a combobox/combobox-like element by label keywords
  function findComboboxByLabels(labels, scope = document) {
    const lower = labels.map((l) => l.toLowerCase());

    // 1) Look for [role="combobox"] or [role="listbox"] elements
    const combos = Array.from(
      scope.querySelectorAll('[role="combobox"],[role="button"],[role="textbox"],input')
    );

    for (const el of combos) {
      const al = (el.getAttribute("aria-label") || "").toLowerCase();
      const ph = (el.getAttribute("placeholder") || "").toLowerCase();
      const id = (el.id || "").toLowerCase();
      const name = (el.getAttribute("name") || "").toLowerCase();

      if (lower.some((lbl) =>
        al === lbl || al.includes(lbl) ||
        ph === lbl || ph.includes(lbl) ||
        id === lbl || id.includes(lbl) ||
        name === lbl || name.includes(lbl)
      )) {
        const r = el.getBoundingClientRect();
        if (r.width && r.height) return el;
      }
    }

    // 2) Look for visible label text near comboboxes
    const labelNodes = Array.from(
      scope.querySelectorAll("label,div,span,strong,legend")
    ).filter((n) => {
      const t = (n.textContent || "").trim().toLowerCase();
      return lower.some((lbl) => t === lbl || t.startsWith(lbl) || t.includes(lbl));
    });

    for (const lab of labelNodes) {
      const container =
        lab.closest(
          'form,[role="group"],[data-visualcompletion],section,div,[aria-labelledby]'
        ) || lab.parentElement;
      if (!container) continue;
      const combo = container.querySelector(
        '[role="combobox"],[role="button"],input'
      );
      if (combo && combo !== lab) {
        const r = combo.getBoundingClientRect();
        if (r.width && r.height) return combo;
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

  // ---------- Generic dropdown selector ----------
  // Opens a combobox and picks the option whose text best matches targetValue.
  // labelKeywords: array of strings to find the field (e.g. ["year"], ["make"])
  // targetValue:   the value to select (e.g. "2021", "Toyota", "Sedan")
  // typeToFilter:  whether to type targetValue into the field first to filter options

  async function selectDropdownOption(scope, labelKeywords, targetValue, typeToFilter = false) {
    const val = String(targetValue || "").trim();
    if (!val) {
      LOG("selectDropdownOption: no value for", labelKeywords);
      return false;
    }

    // Find the field
    const field = findComboboxByLabels(labelKeywords, scope)
      || findInputByLabels(labelKeywords, scope);

    if (!field) {
      LOG("selectDropdownOption: field not found for", labelKeywords);
      return false;
    }

    LOG("selectDropdownOption: field found for", labelKeywords, field);

    // Open the dropdown
    field.focus?.();
    field.click();
    await sleep(300);

    // Optionally type to filter options (useful for Make / Model)
    if (typeToFilter) {
      setNativeValue(field, val);
      fireInputEvents(field);
      await sleep(400);
    }

    // Find the matching option in any open listbox
    const valLower = val.toLowerCase();
    let picked = false;

    const listboxes = Array.from(document.querySelectorAll('[role="listbox"]'));
    for (const lb of listboxes) {
      const opts = Array.from(lb.querySelectorAll('[role="option"]'));

      // Try exact match first
      let option = opts.find((o) =>
        (o.textContent || "").trim().toLowerCase() === valLower
      );
      // Fall back to starts-with
      if (!option) {
        option = opts.find((o) =>
          (o.textContent || "").trim().toLowerCase().startsWith(valLower)
        );
      }
      // Fall back to includes
      if (!option) {
        option = opts.find((o) =>
          (o.textContent || "").trim().toLowerCase().includes(valLower)
        );
      }

      if (option) {
        LOG("selectDropdownOption: picked option", option.textContent.trim(), "for", labelKeywords);
        option.scrollIntoView({ block: "nearest" });
        option.click();
        await sleep(250);
        picked = true;
        break;
      }
    }

    if (!picked) {
      LOG("selectDropdownOption: no option matched", val, "for", labelKeywords);
      // Press Escape to close any open listbox cleanly
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
      await sleep(100);
    }

    return picked;
  }

  // ---------- Special: Year finder (dropdown / combobox) ----------

  function findYearField(scope) {
    const candidates = Array.from(
      scope.querySelectorAll('input,textarea,[role="combobox"],[role="textbox"]')
    );

    const lowerMatch = (txt) =>
      (txt || "").toLowerCase().includes("year");

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
      return t === "year" || t.includes("year");
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
      LOG("No year value provided");
      return;
    }

    const yearField = findYearField(scope);
    if (!yearField) {
      LOG("Year field not found");
      return;
    }

    LOG("Year field:", yearField);

    // Click to open, then type to filter to this year
    yearField.click();
    yearField.focus?.();
    await sleep(300);

    // Type the year to filter the dropdown
    setNativeValue(yearField, yearStr);
    fireInputEvents(yearField);
    await sleep(400);

    // Find the option in any open listbox
    const listboxes = Array.from(document.querySelectorAll('[role="listbox"]'));
    let option = null;

    for (const lb of listboxes) {
      const opts = Array.from(lb.querySelectorAll('[role="option"]'));
      // Exact match first
      option = opts.find((o) => (o.textContent || "").trim() === yearStr);
      // Then includes
      if (!option) {
        option = opts.find((o) => (o.textContent || "").trim().includes(yearStr));
      }
      if (option) {
        LOG("Found year option:", option.textContent.trim());
        option.scrollIntoView({ block: "nearest" });
        option.click();
        break;
      }
    }

    if (!option) {
      LOG("Year option not found for:", yearStr);
    } else {
      await sleep(200);
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

  async function selectVehicleType(scope, vehicleType) {
    // Facebook Marketplace "Vehicle type" dropdown has exactly these options:
    //   Car/Truck, Motorcycle, RV/Camper, Boat, Powersports, Other
    // Almost every standard dealer vehicle = "Car/Truck".
    // SUV, Sedan, Truck, Coupe, etc. all map to "Car/Truck".
    const FB_TYPE_MAP = {
      // Standard passenger vehicles → Car/Truck
      sedan:              "Car/Truck",
      suv:                "Car/Truck",
      "sport utility":    "Car/Truck",
      "sport utility vehicle": "Car/Truck",
      crossover:          "Car/Truck",
      truck:              "Car/Truck",
      pickup:             "Car/Truck",
      "pickup truck":     "Car/Truck",
      minivan:            "Car/Truck",
      van:                "Car/Truck",
      cargo:              "Car/Truck",
      coupe:              "Car/Truck",
      convertible:        "Car/Truck",
      cabriolet:          "Car/Truck",
      roadster:           "Car/Truck",
      wagon:              "Car/Truck",
      "station wagon":    "Car/Truck",
      hatchback:          "Car/Truck",
      hatch:              "Car/Truck",
      car:                "Car/Truck",
      vehicle:            "Car/Truck",
      // Motorcycles
      motorcycle:         "Motorcycle",
      moto:               "Motorcycle",
      scooter:            "Motorcycle",
      // RV
      rv:                 "RV/Camper",
      camper:             "RV/Camper",
      motorhome:          "RV/Camper",
      "travel trailer":   "RV/Camper",
      // Boat
      boat:               "Boat",
      // Powersports
      atv:                "Powersports",
      utv:                "Powersports",
      "side by side":     "Powersports",
      snowmobile:         "Powersports",
      "personal watercraft": "Powersports",
      pwc:                "Powersports",
    };

    // Default to Car/Truck for any unrecognised dealer body type — right 95% of the time
    const raw = (vehicleType || "").trim().toLowerCase();
    let targetText = "Car/Truck";

    if (raw) {
      if (FB_TYPE_MAP[raw]) {
        targetText = FB_TYPE_MAP[raw];
      } else {
        for (const [key, label] of Object.entries(FB_TYPE_MAP)) {
          if (raw.includes(key)) {
            targetText = label;
            break;
          }
        }
      }
    }

    LOG("Vehicle type:", raw, "->", targetText);

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
      LOG("Vehicle type option not found for:", targetText, "- falling back to Car/Truck");
      // Try "Car/Truck" as a last resort
      for (const lb of listboxes) {
        const opts = Array.from(lb.querySelectorAll('[role="option"]'));
        const fallback = opts.find((o) =>
          (o.textContent || "").trim().toLowerCase().includes("car")
        );
        if (fallback) {
          fallback.scrollIntoView({ block: "nearest" });
          fallback.click();
          break;
        }
      }
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

  // ---------- Color normalizer ----------
  // Facebook's color dropdown uses simple color names.
  // This maps common dealer color strings to FB-friendly values.
  function normalizeColor(raw) {
    if (!raw) return "";
    const r = raw.toLowerCase();
    // Common multi-word → simple name
    const MAP = {
      "jet black":        "Black",
      "pearl white":      "White",
      "pearl":            "White",
      "oxford white":     "White",
      "arctic white":     "White",
      "super white":      "White",
      "alpine white":     "White",
      "brilliant black":  "Black",
      "midnight black":   "Black",
      "phantom black":    "Black",
      "tuxedo black":     "Black",
      "deep blue":        "Blue",
      "navy blue":        "Blue",
      "midnight blue":    "Blue",
      "steel blue":       "Blue",
      "dark blue":        "Blue",
      "bright blue":      "Blue",
      "cobalt blue":      "Blue",
      "silver ice":       "Silver",
      "blade silver":     "Silver",
      "lunar silver":     "Silver",
      "ingot silver":     "Silver",
      "sonic silver":     "Silver",
      "sterling gray":    "Gray",
      "magnetic gray":    "Gray",
      "dark gray":        "Gray",
      "machine gray":     "Gray",
      "charcoal":         "Gray",
      "graphite":         "Gray",
      "shadow gray":      "Gray",
      "rapid red":        "Red",
      "ruby red":         "Red",
      "deep cherry":      "Red",
      "crimson red":      "Red",
      "inferno red":      "Red",
      "hot lava":         "Red",
      "lava red":         "Red",
      "hunter green":     "Green",
      "forest green":     "Green",
      "midnight green":   "Green",
      "dark green":       "Green",
      "cyber gray":       "Gray",
      "summit white":     "White",
      "iridescent pearl": "White",
      "off white":        "White",
      "cream":            "White",
      "beige":            "Beige",
      "tan":              "Tan",
      "brown":            "Brown",
      "dark chocolate":   "Brown",
      "mocha":            "Brown",
      "champagne":        "Gold",
      "gold":             "Gold",
      "yellow":           "Yellow",
      "orange":           "Orange",
      "purple":           "Purple",
      "maroon":           "Maroon",
      "burgundy":         "Maroon",
    };

    for (const [key, val] of Object.entries(MAP)) {
      if (r.includes(key)) return val;
    }

    // Single-word: capitalize first letter
    const simple = raw.trim();
    return simple.charAt(0).toUpperCase() + simple.slice(1).toLowerCase();
  }

  // ---------- Condition normalizer ----------
  function normalizeCondition(raw) {
    const r = (raw || "").toLowerCase();
    if (r.includes("excellent") || r.includes("like new")) return "Excellent";
    if (r.includes("good"))       return "Good";
    if (r.includes("fair"))       return "Fair";
    if (r.includes("poor"))       return "Poor";
    if (r.includes("new"))        return "Excellent"; // new cars → Excellent
    return "Good"; // safe default
  }

  // ---------- Fuel type normalizer ----------
  function normalizeFuelType(raw) {
    const r = (raw || "").toLowerCase();
    if (r.includes("electric") || r.includes("ev") || r.includes("bev")) return "Electric";
    if (r.includes("hybrid") && r.includes("plug")) return "Plug-in Hybrid";
    if (r.includes("hybrid"))   return "Hybrid";
    if (r.includes("diesel"))   return "Diesel";
    if (r.includes("gas") || r.includes("gasoline") || r.includes("petrol")) return "Gasoline";
    return "Gasoline"; // safest default
  }

  // ---------- Clean title checkbox ----------
  async function checkCleanTitle(scope) {
    // Look for a checkbox labelled "Clean title"
    const labels = Array.from(
      scope.querySelectorAll("label,div,span,strong")
    ).filter((n) => {
      const t = (n.textContent || "").trim().toLowerCase();
      return t === "clean title" || t.includes("clean title");
    });

    for (const lab of labels) {
      // Look for a checkbox sibling or child
      const container = lab.closest('label,[role="checkbox"],div') || lab.parentElement;
      if (!container) continue;

      // Try direct checkbox
      let cb = container.querySelector('input[type="checkbox"]');
      if (!cb) {
        // Try [role="checkbox"]
        cb = container.querySelector('[role="checkbox"]');
      }
      if (!cb && lab.tagName === "LABEL") {
        // The label itself may wrap the checkbox
        cb = lab.querySelector('input[type="checkbox"]');
      }
      if (cb) {
        const r = cb.getBoundingClientRect();
        if (r.width >= 0 && r.height >= 0) {
          LOG("Clean title checkbox found:", cb);
          if (!cb.checked) {
            cb.click();
            await sleep(100);
          }
          return true;
        }
      }
    }

    // Fallback: search entire document for a "clean title" checkbox
    const allCheckboxes = Array.from(
      scope.querySelectorAll('input[type="checkbox"],[role="checkbox"]')
    );
    for (const cb of allCheckboxes) {
      const al = (cb.getAttribute("aria-label") || "").toLowerCase();
      const id = (cb.id || "").toLowerCase();
      if (al.includes("clean") || id.includes("clean")) {
        LOG("Clean title checkbox (aria/id match):", cb);
        if (!cb.checked) {
          cb.click();
          await sleep(100);
        }
        return true;
      }
      // Check nearby label text
      const lbl = cb.closest("label") || document.querySelector(`label[for="${cb.id}"]`);
      if (lbl && (lbl.textContent || "").toLowerCase().includes("clean")) {
        LOG("Clean title checkbox (label match):", cb);
        if (!cb.checked) {
          cb.click();
          await sleep(100);
        }
        return true;
      }
    }

    LOG("Clean title checkbox not found");
    return false;
  }

  // ---------- Listing data from background ----------

  function normalizeListing(listingRaw) {
    // listingRaw from panel.js sendToFacebookFromDetail:
    // { title, year, make, model, price, mileage, vin, bodyType,
    //   exteriorColor, interiorColor, description, images, sourceUrl }
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

    // Vehicle type / body type
    const vehicleType =
      listingRaw["Body Type"] ||
      listingRaw.bodyType ||
      listingRaw.vehicleType ||
      listingRaw["Vehicle Type"] ||
      listingRaw.vehicle_type ||
      "";

    // Mileage — strip non-numeric suffix for FB's numeric input field.
    // Default to 300 if blank or zero: new cars have 0 but FB requires a value.
    const mileageRaw =
      listingRaw.Mileage ||
      listingRaw.mileage ||
      "";
    const mileageParsed = parseInt(String(mileageRaw).replace(/[^\d]/g, "") || "0", 10);
    const mileage = String(Math.max(mileageParsed, 300));

    // Colors
    const exteriorColor =
      listingRaw["Exterior Color"] ||
      listingRaw.exteriorColor ||
      listingRaw.exterior_color ||
      "";

    const interiorColor =
      listingRaw["Interior Color"] ||
      listingRaw.interiorColor ||
      listingRaw.interior_color ||
      "";

    // Condition — not always in the listing; default to "Good"
    const conditionRaw =
      listingRaw.Condition ||
      listingRaw.condition ||
      "";

    // Fuel type
    const fuelTypeRaw =
      listingRaw["Fuel Type"] ||
      listingRaw.fuelType ||
      listingRaw.fuel_type ||
      "";

    const normalized = {
      Title: title,
      Year: year,
      Make: make,
      Model: model,
      Price: price,
      Description: description,
      VehicleType: vehicleType,
      Mileage: mileage,
      ExteriorColor: normalizeColor(exteriorColor),
      InteriorColor: normalizeColor(interiorColor),
      Condition: normalizeCondition(conditionRaw),
      FuelType: normalizeFuelType(fuelTypeRaw),
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

  // ---------- IMAGE HELPERS ----------

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

    // 1. Vehicle Type (Car/Truck for nearly all dealer vehicles)
    await selectVehicleType(composer, listing.VehicleType);
    await sleep(300);

    // 2. Price
    if (listing.Price) {
      const priceInput = findInputByLabels(["price"], composer);
      LOG("Price input:", priceInput);
      if (priceInput) {
        await typeIntoInput(priceInput, String(listing.Price));
        await sleep(100);
      }
    }

    // 3. Mileage — always fill; defaults to 300 for new/blank vehicles
    {
      const mileageInput = findInputByLabels(["mileage", "miles"], composer);
      LOG("Mileage input:", mileageInput);
      if (mileageInput) {
        await typeIntoInput(mileageInput, listing.Mileage);
        await sleep(100);
      }
    }

    // 4. Make — combobox: type to filter then pick
    if (listing.Make) {
      await selectDropdownOption(composer, ["make"], listing.Make, true);
      await sleep(300);
    }

    // 5. Model — plain text input (FB lets you type freely after Make is set)
    if (listing.Model) {
      const modelInput = findInputByLabels(["model"], composer)
        || findComboboxByLabels(["model"], composer);
      LOG("Model input:", modelInput);
      if (modelInput) {
        await typeIntoInput(modelInput, String(listing.Model));
        await sleep(100);
      }
    }

    // 6. Year — combobox dropdown
    if (listing.Year) {
      await selectYearFromDropdown(composer, listing.Year);
      await sleep(300);
    }

    // 7. Body style (Sedan, SUV, Truck, etc.)
    if (listing.VehicleType) {
      // The "Body style" field maps the *dealer* body type string directly
      const bodyStyleLabels = ["body style", "body type", "style"];
      await selectDropdownOption(composer, bodyStyleLabels, listing.VehicleType, false);
      await sleep(200);
    }

    // 8. Exterior color
    if (listing.ExteriorColor) {
      const extColorLabels = ["exterior color", "exterior", "color", "ext. color", "outside color"];
      await selectDropdownOption(composer, extColorLabels, listing.ExteriorColor, false);
      await sleep(200);
    }

    // 9. Interior color
    if (listing.InteriorColor) {
      const intColorLabels = ["interior color", "interior", "int. color", "inside color"];
      await selectDropdownOption(composer, intColorLabels, listing.InteriorColor, false);
      await sleep(200);
    }

    // 10. Vehicle condition
    {
      const conditionLabels = ["condition", "vehicle condition"];
      await selectDropdownOption(composer, conditionLabels, listing.Condition, false);
      await sleep(200);
    }

    // 11. Fuel type
    {
      const fuelLabels = ["fuel type", "fuel", "fuel economy"];
      await selectDropdownOption(composer, fuelLabels, listing.FuelType, false);
      await sleep(200);
    }

    // 12. Clean title checkbox — always check by default
    await checkCleanTitle(document);
    await sleep(200);

    // 13. Description – textarea or contenteditable
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

    // 14. Images
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

    // Guard: if FB landed on the "choose listing type" page instead of the
    // vehicle form, wait up to 5 seconds for the URL to reach create/vehicle.
    if (location.href.includes("marketplace") && !location.href.includes("create/vehicle")) {
      LOG("Not on vehicle form yet — current URL:", location.href, "— waiting up to 5s...");
      const deadline = Date.now() + 5000;
      while (Date.now() < deadline) {
        await sleep(250);
        if (location.href.includes("create/vehicle")) {
          LOG("URL is now vehicle form, proceeding.");
          break;
        }
      }
      if (!location.href.includes("create/vehicle")) {
        LOG("WARNING: URL did not reach create/vehicle after 5s — aborting fill. Current URL:", location.href);
        return;
      }
      await sleep(500); // small extra settle after navigation
    }

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
