// service_worker.js

let latestListing = null;

const API_BASE    = "https://dylansautosales-facebook-tool.onrender.com";
const API_EXTRACT = `${API_BASE}/fb/extract_html`;
const API_HEALTH  = `${API_BASE}/health`;

// ====== Bot-detection mitigations ======

// Rotate through realistic Chrome UAs so every scrape looks slightly different.
const USER_AGENTS = [
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15",
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
];

function randomUA() {
  return USER_AGENTS[Math.floor(Math.random() * USER_AGENTS.length)];
}

// Add human-like jitter (ms) so requests aren't perfectly periodic.
function jitter(base = 500, spread = 400) {
  return base + Math.floor(Math.random() * spread);
}

// ====== image download helper ======
async function downloadImageAsBase64(url) {
  console.log("[sw] downloadImageAsBase64:", url);
  const res = await fetch(url);

  if (!res.ok) {
    throw new Error(`HTTP ${res.status} for ${url}`);
  }

  const blob = await res.blob();

  const dataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });

  const [prefix, b64] = String(dataUrl).split(",", 2);
  const mimeMatch = prefix.match(/^data:(.*?);base64$/i);
  const mime = mimeMatch ? mimeMatch[1] : blob.type || "image/jpeg";

  const nameFromUrl = (() => {
    try {
      const u = new URL(url);
      const last = u.pathname.split("/").filter(Boolean).pop() || "image";
      return last.includes(".") ? last : last + ".jpg";
    } catch {
      return "image.jpg";
    }
  })();

  return { base64: b64, mime, name: nameFromUrl };
}

async function downloadImagesAsBase64(urls) {
  const out = [];
  for (const url of urls) {
    try {
      const img = await downloadImageAsBase64(url);
      if (img && img.base64) out.push(img);
    } catch (e) {
      console.error("[sw] Failed to download image:", url, e);
    }
  }
  console.log("[sw] downloadImagesAsBase64 ->", out.length, "images");
  return out;
}

// ====== Shared tab scraper ======
// activeTab: true = visible tab (batch test mode, bypasses bot detection)
//            false = background tab (normal detail flow)
async function scrapeDetailTab(detailUrl, activeTab = false) {
  const tab = await chrome.tabs.create({ url: detailUrl, active: activeTab });

  return new Promise((resolve, reject) => {
    const onUpdated = async (tabId, info) => {
      if (tabId !== tab.id || info.status !== "complete") return;
      chrome.tabs.onUpdated.removeListener(onUpdated);

      // ── Step 1: Cookie / GDPR banner dismiss ───────────────────────────────
      // Do this FIRST — banners block JS execution and image loading.
      // Dismiss immediately on page-complete, before any wait.
      try {
        await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          func: () => {
            const ACCEPT_RE = /\b(accept\s*(all(\s*cookies)?)?|i\s*agree|got\s*it|ok\b|allow\s*(all)?|continue|agree\s*&?\s*proceed|close|dismiss|yes,?\s*i\s*accept)\b/i;
            const REJECT_RE = /\b(reject|decline|refuse|no\s*thanks|manage\s*(preferences|settings)|customize)\b/i;
            const candidates = Array.from(
              document.querySelectorAll(
                'button,a,[role="button"],[id*="consent"],[id*="cookie"],[class*="consent"],[class*="cookie"],[id*="gdpr"],[class*="gdpr"],[id*="privacy-banner"],[class*="privacy-banner"]'
              )
            );
            for (const el of candidates) {
              const txt = (el.textContent || el.getAttribute("aria-label") || el.value || "").trim();
              if (REJECT_RE.test(txt)) continue; // never click Reject/Decline
              if (ACCEPT_RE.test(txt)) {
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                  el.click();
                  return `dismissed: "${txt}"`;
                }
              }
            }
            return "no banner";
          },
        });
        // Short settle — banner animation + JS teardown
        await new Promise(r => setTimeout(r, 600));
      } catch { /* non-fatal */ }

      // ── Step 2: Signal-based wait for vehicle content ──────────────────────
      // Poll every 500ms for up to 10s waiting for vehicle-specific signals:
      //   - A 17-char VIN in the page text
      //   - A price pattern ($XX,XXX)
      //   - A vehicle title matching "YYYY Make Model"
      //   - OR at least 4 gallery-sized images (≥300px)
      // This eliminates the flat-wait race condition — we proceed as soon as
      // the page has meaningful content, never earlier, never later than 10s.
      const CONTENT_TIMEOUT = 10000;
      const POLL_INTERVAL   = 500;
      const contentStart = Date.now();
      let contentReady = false;

      while (Date.now() - contentStart < CONTENT_TIMEOUT) {
        try {
          const [check] = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: () => {
              const text = document.body.innerText || "";
              const hasVIN   = /\b[A-HJ-NPR-Z0-9]{17}\b/.test(text);
              const hasPrice = /\$\s*\d[\d,]{3,}/.test(text);
              const hasTitle = /\b(19|20)\d{2}\s+[A-Z][a-zA-Z\-]+\s+[A-Za-z0-9\-]+/.test(text);
              const galleryImgs = Array.from(document.querySelectorAll("img"))
                .filter(i => (i.naturalWidth || i.width || 0) >= 300).length;
              return { hasVIN, hasPrice, hasTitle, galleryImgs };
            },
          });
          const s = check?.result || {};
          console.log("[sw] content poll:", s, `(${Date.now() - contentStart}ms)`);
          if (s.hasVIN || s.hasPrice || s.hasTitle || s.galleryImgs >= 4) {
            contentReady = true;
            console.log("[sw] content signals found — proceeding");
            break;
          }
        } catch { /* tab may still be loading — keep polling */ }
        await new Promise(r => setTimeout(r, POLL_INTERVAL));
      }

      if (!contentReady) {
        console.log("[sw] content timeout after 10s — scraping whatever is loaded");
      }

      // ── Step 3: Viewport scroll to trigger lazy-loaded gallery images ───────
      // Now that content is confirmed (or timeout), scroll to trigger any
      // intersection-observer-based lazy loading. We await the full scroll
      // duration synchronously using a Promise that resolves when done.
      try {
        await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          func: () => new Promise(resolve => {
            const total = document.body.scrollHeight;
            const step  = 600;
            let pos = 0;
            const tick = () => {
              pos = Math.min(pos + step, total);
              window.scrollTo(0, pos);
              if (pos < total) {
                requestAnimationFrame(tick);
              } else {
                // Scroll back to top so the scrape captures the full page
                setTimeout(() => { window.scrollTo(0, 0); resolve(); }, 300);
              }
            };
            tick();
          }),
          world: "MAIN", // needs access to page's rAF
        });
        // Wait for lazy images triggered by scroll to actually load
        await new Promise(r => setTimeout(r, 2000));
      } catch { /* non-fatal */ }

      // ── Step 4: Gallery readiness check with one retry ─────────────────────
      // After scroll, count gallery-sized images. If still too few,
      // wait 3 more seconds (covers sites with slow CDN response).
      try {
        const [gc] = await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          func: () => Array.from(document.querySelectorAll("img"))
            .filter(i => (i.naturalWidth || i.width || 0) >= 200).length,
        });
        const galleryCount = gc?.result ?? 0;
        console.log("[sw] gallery images after scroll:", galleryCount);
        if (galleryCount < 4) {
          console.log("[sw] low gallery count — waiting 3s more");
          await new Promise(r => setTimeout(r, 3000));
        }
      } catch { /* non-fatal */ }

      // ── Step 5: Scrape HTML + images ───────────────────────────────────────
      try {
        const [inj] = await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          func: () => {
            const html = document.documentElement.outerHTML;
            const url  = location.href;
            const abs  = (u) => { try { return u ? new URL(u, location.href).href : null; } catch { return null; } };

            // Exclude images that belong to <video> elements
            const videoSrcs = new Set();
            document.querySelectorAll("video").forEach(v => {
              [v.src, v.getAttribute("poster"), v.getAttribute("data-src")]
                .filter(Boolean)
                .forEach(s => { try { videoSrcs.add(new URL(s, location.href).href); } catch {} });
              v.querySelectorAll("source").forEach(src => {
                const s = src.getAttribute("src");
                if (s) { try { videoSrcs.add(new URL(s, location.href).href); } catch {} }
              });
            });

            const VIDEO_URL_RE = /video|\.mp4|blob:|\/play\b/i;

            const images = Array.from(document.querySelectorAll("img"))
              .map(img => {
                const raw = img.currentSrc || img.getAttribute("src") || img.getAttribute("data-src") ||
                            img.getAttribute("data-lazy") || img.getAttribute("data-original") || "";
                return {
                  src:    abs(raw),
                  alt:    img.alt || "",
                  width:  img.naturalWidth  || img.width  || 0,
                  height: img.naturalHeight || img.height || 0,
                };
              })
              .filter(i => {
                if (!i.src)                              return false;
                if (videoSrcs.has(i.src))                return false;
                if (VIDEO_URL_RE.test(i.src))            return false;
                if (i.width  > 0 && i.width  < 200)     return false;
                if (i.height > 0 && i.height < 200)     return false;
                return true;
              });

            return { url, html, images };
          },
        });

        const { url, html, images } = inj.result || {};

        const resp = await fetch(API_EXTRACT, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "User-Agent": randomUA(),
          },
          body: JSON.stringify({ url, html, images }),
        });

        const fields   = await resp.json().catch(() => ({}));
        const aiImages = Array.isArray(fields.images) ? fields.images : [];

        chrome.tabs.remove(tab.id);
        resolve({ fields, images: aiImages.length ? aiImages : (images || []).map(i => i.src), html });
      } catch (err) {
        try { chrome.tabs.remove(tab.id); } catch {}
        reject(err);
      }
    };

    chrome.tabs.onUpdated.addListener(onUpdated);
  });
}

// ====== Message router ======
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "FB_OPEN_MARKETPLACE") {
    latestListing = msg.payload || null;
    chrome.tabs.create({ url: "https://www.facebook.com/marketplace/create/vehicle" });
    sendResponse && sendResponse({ ok: true });
    return true;
  }

  if (msg.type === "FB_GET_VEHICLE_DATA") {
    sendResponse && sendResponse({ listing: latestListing });
    return true;
  }

  if (msg.type === "FETCH_DETAIL_VIA_API" && msg.detailUrl) {
    (async () => {
      try {
        // Wake server / confirm it's alive
        const ping = await fetch(API_HEALTH, { signal: AbortSignal.timeout(30000) });
        if (!ping.ok) throw new Error("Server returned " + ping.status);

        // PRIMARY: backend server-side fetch (fast, no tab needed, works on 80% of dealers)
        const serverResp = await fetch(`${API_BASE}/fb/scrape_url`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: msg.detailUrl }),
          signal: AbortSignal.timeout(40000),
        });

        if (!serverResp.ok) throw new Error("scrape_url HTTP " + serverResp.status);
        const serverData = await serverResp.json();

        // If backend extracted a VIN, the page was fully parseable — use it directly
        if (serverData.VIN || serverData.vin) {
          const images = Array.isArray(serverData.images) ? serverData.images : [];
          sendResponse({ ok: true, fields: serverData, images, html: "" });
          return;
        }

        // FALLBACK: JS-heavy site, backend got no VIN — open tab to render JS
        console.log("[sw] backend no VIN — falling back to tab scrape for:", msg.detailUrl);
        const tabTimeout = new Promise((_, reject) =>
          setTimeout(() => reject(new Error("Tab scrape timed out after 45s")), 45000)
        );
        const tabData = await Promise.race([
          scrapeDetailTab(msg.detailUrl, false),
          tabTimeout,
        ]);
        sendResponse({ ok: true, ...tabData });

      } catch (err) {
        const isHealthFail =
          err.message?.includes("Server returned") || err.name === "TimeoutError";
        sendResponse({
          ok: false,
          error: isHealthFail
            ? "Cannot reach the AutoBot server. Try again in 30 seconds."
            : err.message || String(err),
        });
      }
    })();
    return true;
  }

  if (msg.type === "FETCH_IMAGES" && Array.isArray(msg.urls)) {
    (async () => {
      try {
        const images = await downloadImagesAsBase64(msg.urls);
        sendResponse({ images });
      } catch (err) {
        sendResponse({ images: [], error: err.message || String(err) });
      }
    })();
    return true;
  }

  // ====== BATCH TEST handler — active tab to bypass bot detection ======
  if (msg.type === "BATCH_SCRAPE_URL" && msg.url) {
    (async () => {
      try {
        const data = await scrapeDetailTab(msg.url, true); // active tab — looks like real user
        sendResponse({ ok: true, fields: data.fields || {} });
      } catch (err) {
        sendResponse({ ok: false, error: err.message || String(err) });
      }
    })();
    return true;
  }

  return false;
});

// Side panel wiring
chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setOptions({ path: "panel.html", enabled: true });
});

chrome.action.onClicked.addListener((tab) => {
  chrome.sidePanel.open({ tabId: tab.id });
});
