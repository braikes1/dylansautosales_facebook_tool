// service_worker.js

let latestListing = null;

const API_EXTRACT = "http://127.0.0.1:8000/fb/extract_html";

// ====== image download helper (NEW) ======
async function downloadImageAsBase64(url) {
  console.log("[sw] downloadImageAsBase64:", url);
  const res = await fetch(url);

  if (!res.ok) {
    throw new Error(`HTTP ${res.status} for ${url}`);
  }

  const blob = await res.blob();

  // Convert blob -> data URL -> base64
  const dataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });

  // "data:image/jpeg;base64,AAAA..."
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

  return {
    base64: b64,
    mime,
    name: nameFromUrl,
  };
}

async function downloadImagesAsBase64(urls) {
  const out = [];
  for (const url of urls) {
    try {
      const img = await downloadImageAsBase64(url);
      if (img && img.base64) {
        out.push(img);
      }
    } catch (e) {
      console.error("[sw] Failed to download image:", url, e);
    }
  }
  console.log("[sw] downloadImagesAsBase64 ->", out.length, "images");
  return out;
}

// ====== Message router ======
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  // Open Facebook Marketplace and stash listing data
  if (msg.type === "FB_OPEN_MARKETPLACE") {
    latestListing = msg.payload || null;
    chrome.tabs.create({
      url: "https://www.facebook.com/marketplace/create/vehicle",
    });
    sendResponse && sendResponse({ ok: true });
    return true;
  }

  // Facebook content script asks for latest listing
  if (msg.type === "FB_GET_VEHICLE_DATA") {
    sendResponse && sendResponse({ listing: latestListing });
    return true;
  }

  // Panel asks to fetch detail info via AI API
  if (msg.type === "FETCH_DETAIL_VIA_API" && msg.detailUrl) {
    (async () => {
      try {
        const data = await fetchDetailDataViaApi(msg.detailUrl);
        sendResponse({ ok: true, ...data });
      } catch (err) {
        console.error("FETCH_DETAIL_VIA_API error:", err);
        sendResponse({ ok: false, error: err.message || String(err) });
      }
    })();
    return true; // keep the channel open for async
  }

  // >>> NEW: facebook_fill.js asks us to turn image URLs into base64 files
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
    return true; // async response
  }

  return false;
});

/**
 * Open detailUrl in a background tab, grab HTML + image candidates,
 * send them to the FastAPI AI endpoint, then return { fields, images }.
 */
async function fetchDetailDataViaApi(detailUrl) {
  const tab = await chrome.tabs.create({ url: detailUrl, active: false });

  return new Promise((resolve, reject) => {
    const onUpdated = async (tabId, info, tabInfo) => {
      if (tabId !== tab.id || info.status !== "complete") return;

      chrome.tabs.onUpdated.removeListener(onUpdated);

      try {
        // 1) Grab HTML + image candidates on that tab
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
                return {
                  src,
                  alt: img.alt || "",
                  width: w,
                  height: h,
                };
              })
              .filter(
                (img) =>
                  img.src && (img.width >= 200 || img.height >= 150)
              );

            return { url, html, images };
          },
        });

        const { url, html, images } = inj.result || {};

        // 2) Call FastAPI with HTML + image candidates
        const resp = await fetch(API_EXTRACT, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url, html, images }),
        });

        const fields = await resp.json().catch(() => ({}));

        // The API already returns `images` picked by AI
        const aiImages = Array.isArray(fields.images) ? fields.images : [];

        // 3) Close the detail tab (optional but nicer UX)
        chrome.tabs.remove(tab.id);

        resolve({
          fields,
          images: aiImages.length ? aiImages : (images || []).map((i) => i.src),
          html,
        });
      } catch (err) {
        try {
          chrome.tabs.remove(tab.id);
        } catch (e) {}
        reject(err);
      }
    };

    chrome.tabs.onUpdated.addListener(onUpdated);
  });
}

// Side panel wiring
chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setOptions({
    path: "panel.html",
    enabled: true,
  });
});

chrome.action.onClicked.addListener((tab) => {
  chrome.sidePanel.open({ tabId: tab.id });
});
