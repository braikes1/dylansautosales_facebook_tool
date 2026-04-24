// service_worker.js

let latestListing = null;

const API_BASE    = "https://dylansautosales-facebook-tool.onrender.com";
const API_EXTRACT = `${API_BASE}/fb/extract_html`;
const API_HEALTH  = `${API_BASE}/health`;

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
    console.log("[sw] FETCH_DETAIL_VIA_API received. URL:", msg.detailUrl);
    (async () => {
      try {
        const data = await fetchDetailDataViaApi(msg.detailUrl);
        console.log("[sw] FETCH_DETAIL_VIA_API success. Fields keys:", Object.keys(data.fields || {}));
        sendResponse({ ok: true, ...data });
      } catch (err) {
        console.error("[sw] FETCH_DETAIL_VIA_API error:", err.message, err);
        sendResponse({ ok: false, error: err.message || String(err) });
      }
    })();
    return true;
  }

  if (msg.type === "FETCH_IMAGES" && Array.isArray(msg.urls)) {
    (async () => {
      try {
        console.log("[sw] FETCH_IMAGES for", msg.urls.length, "urls");
        const images = await downloadImagesAsBase64(msg.urls);
        sendResponse({ images });
      } catch (err) {
        console.error("[sw] FETCH_IMAGES error:", err);
        sendResponse({ images: [], error: err.message || String(err) });
      }
    })();
    return true;
  }

  return false;
});

async function fetchDetailDataViaApi(detailUrl) {
  // Verify the local server is reachable
  console.log("[sw] Pinging health check:", API_HEALTH);
  try {
    const ping = await fetch(API_HEALTH, { signal: AbortSignal.timeout(5000) });
    console.log("[sw] Health check status:", ping.status);
    if (!ping.ok) throw new Error("Server returned " + ping.status);
  } catch (e) {
    console.error("[sw] Health check failed:", e.message);
    throw new Error(
      "Cannot reach the AutoBot server. Make sure the AutoBot launcher is open and showing the green dot."
    );
  }

  const tab = await chrome.tabs.create({ url: detailUrl, active: false });

  return new Promise((resolve, reject) => {
    const onUpdated = async (tabId, info) => {
      if (tabId !== tab.id || info.status !== "complete") return;
      chrome.tabs.onUpdated.removeListener(onUpdated);

      try {
        const [inj] = await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          func: () => {
            const html = document.documentElement.outerHTML;
            const url = location.href;

            const abs = (u) => {
              try {
                if (!u) return null;
                return new URL(u, location.href).href;
              } catch {
                return null;
              }
            };

            const nodes = Array.from(document.querySelectorAll("img"));
            const images = nodes
              .map((img) => {
                const raw =
                  img.currentSrc ||
                  img.getAttribute("src") ||
                  img.getAttribute("data-src") ||
                  img.getAttribute("data-lazy") ||
                  img.getAttribute("data-original") ||
                  "";
                const src = abs(raw);
                const w = img.naturalWidth || img.width || 0;
                const h = img.naturalHeight || img.height || 0;
                return { src, alt: img.alt || "", width: w, height: h };
              })
              .filter((img) => img.src);

            return { url, html, images };
          },
        });

        const { url, html, images } = inj.result || {};

        console.log("[sw] Calling API extract:", API_EXTRACT, "| page URL:", url, "| images:", images.length);
        const resp = await fetch(API_EXTRACT, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url, html, images }),
        });

        console.log("[sw] API extract response status:", resp.status);
        const fields = await resp.json().catch(() => ({}));
        console.log("[sw] API extract fields received:", fields);
        const aiImages = Array.isArray(fields.images) ? fields.images : [];

        chrome.tabs.remove(tab.id);

        resolve({
          fields,
          images: aiImages.length ? aiImages : (images || []).map((i) => i.src),
          html,
        });
      } catch (err) {
        console.error("[sw] fetchDetailDataViaApi inner error:", err.message, err);
        try { chrome.tabs.remove(tab.id); } catch (e) {}
        reject(err);
      }
    };

    chrome.tabs.onUpdated.addListener(onUpdated);
  });
}

// Side panel wiring
chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setOptions({ path: "panel.html", enabled: true });
});

chrome.action.onClicked.addListener((tab) => {
  chrome.sidePanel.open({ tabId: tab.id });
});
