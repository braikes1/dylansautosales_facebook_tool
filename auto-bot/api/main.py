# api/main.py
from fastapi import FastAPI
from pydantic import BaseModel
from bs4 import BeautifulSoup
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from urllib.parse import urlparse
import os
import re
import json
import time as _time
from typing import List, Optional

# In-memory TTL cache for DDC API results — avoids hammering Dealer.com from
# the same datacenter IP within a short window (which triggers 429/rate-limit).
# Key: host string. Value: (timestamp, vehicles_list)
_DDC_CACHE: dict = {}
_DDC_CACHE_TTL = 90  # seconds

app = FastAPI()


@app.get("/health")
def health():
    """Simple health check so the extension can verify the server is running."""
    return {"status": "ok"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========= OpenAI client =========
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY", "")
)

FIELDS = [
    "Mileage",
    "VIN",
    "Year",
    "Make",
    "Model",
    "Price",
    "Interior Color",
    "Exterior Color",
    "Body Type",
    "Condition",
    "Fuel Type",
    "Transmission",
    "Description",
]

# Scored fields (subset used by batch test)
SCORED_FIELDS = [
    "Year", "Make", "Model", "Price",
    "VIN", "Body Type", "Exterior Color",
    "Interior Color", "Mileage", "Description",
]


# =========================================================================
# JSON-LD EXTRACTION LAYER
# Most dealer platforms (DealerOn, Dealer.com, CDK, Dealer Inspire) embed
# complete vehicle data as Schema.org JSON-LD for SEO. Parse this FIRST —
# it's free, instant, and 100% accurate. AI only fills the gaps.
# =========================================================================

def _normalize_body_type(raw: str) -> str:
    raw_lower = raw.lower().strip()
    mapping = [
        (["sport utility", "sports utility", "suv", "crossover", "utility"], "SUV"),
        (["pickup", "crew cab", "extended cab", "regular cab", "super crew", "supercrew", "super cab"], "Truck"),
        (["truck"], "Truck"),
        (["minivan", "mini van"], "Minivan"),
        (["cargo van", "passenger van", "full-size van"], "Van"),
        (["van"], "Minivan"),
        (["convertible", "cabriolet", "roadster", "spyder"], "Convertible"),
        (["coupe", "2-door", "2 door"], "Coupe"),
        (["wagon", "estate", "touring"], "Wagon"),
        (["hatchback", "hatch", "5-door"], "Hatchback"),
        (["sedan", "4-door", "4 door", "saloon"], "Sedan"),
    ]
    for keywords, normalized in mapping:
        if any(kw in raw_lower for kw in keywords):
            return normalized
    return raw.title()


def _normalize_color(raw: str) -> str:
    """Keep full dealer color name — only strip if it's obviously just a code."""
    stripped = raw.strip()
    # If it's 3 chars or fewer and all alphanumeric it's a code — drop it
    if len(stripped) <= 4 and stripped.isalnum():
        return ""
    return stripped[:60]


def _normalize_fuel(raw: str) -> str:
    r = raw.lower()
    if "plug" in r and "hybrid" in r:
        return "Plug-in Hybrid"
    if "hybrid" in r:
        return "Hybrid"
    if "electric" in r or "ev" in r:
        return "Electric"
    if "diesel" in r:
        return "Diesel"
    if "gas" in r or "petrol" in r or "gasoline" in r:
        return "Gasoline"
    return raw.title()


def _normalize_transmission(raw: str) -> str:
    r = raw.lower()
    if "cvt" in r:
        return "CVT"
    if "auto" in r:
        return "Automatic"
    if "manual" in r or "stick" in r or "mt" == r:
        return "Manual"
    return raw.title()


def _parse_vehicle_node(data: dict) -> dict:
    """Extract vehicle fields from a single Schema.org JSON-LD node."""
    result = {}

    node_type = str(data.get("@type", ""))
    if not any(t in node_type for t in ["Car", "Vehicle", "Product", "Automobile"]):
        return result

    # Year
    year = (
        data.get("vehicleModelDate")
        or data.get("modelDate")
        or str(data.get("productionDate", ""))[:4]
    )
    if year and str(year).strip().isdigit() and len(str(year).strip()) == 4:
        result["Year"] = str(year).strip()

    # Make
    brand = data.get("brand", {})
    if isinstance(brand, dict):
        make = brand.get("name", "")
    elif isinstance(brand, str):
        make = brand
    else:
        make = data.get("manufacturer", "")
    if make:
        result["Make"] = str(make).strip()

    # Model — can be nested object or string
    model = data.get("model", "")
    if isinstance(model, dict):
        model = model.get("name", "")
    if model:
        result["Model"] = str(model).strip()

    # VIN
    vin = str(data.get("vehicleIdentificationNumber", "")).strip().upper()
    if len(vin) == 17 and re.match(r"^[A-HJ-NPR-Z0-9]{17}$", vin):
        result["VIN"] = vin

    # Body Type
    body = data.get("bodyType", "") or data.get("vehicleBodyType", "")
    if body:
        normalized = _normalize_body_type(str(body))
        if normalized:
            result["Body Type"] = normalized

    # Exterior Color
    color = data.get("color", "") or data.get("vehicleColor", "")
    if color:
        nc = _normalize_color(str(color))
        if nc:
            result["Exterior Color"] = nc

    # Interior Color
    interior = data.get("vehicleInteriorColor", "") or data.get("interiorColor", "")
    if interior:
        nc = _normalize_color(str(interior))
        if nc:
            result["Interior Color"] = nc

    # Mileage
    mileage_obj = data.get("mileageFromOdometer", {})
    if isinstance(mileage_obj, dict):
        mileage_val = mileage_obj.get("value", None)
    elif isinstance(mileage_obj, (int, float)):
        mileage_val = mileage_obj
    elif isinstance(mileage_obj, str):
        mileage_val = re.sub(r"[^\d.]", "", mileage_obj) or None
    else:
        mileage_val = None

    if mileage_val is not None:
        try:
            result["Mileage"] = str(int(float(str(mileage_val))))
        except (ValueError, TypeError):
            pass

    # Price — handles offers as dict or list
    offers = data.get("offers", {})
    if isinstance(offers, list) and offers:
        offers = offers[0]
    if isinstance(offers, dict):
        price_raw = (
            offers.get("price")
            or offers.get("lowPrice")
            or offers.get("highPrice")
        )
        if price_raw is not None:
            try:
                price_num = float(str(price_raw).replace(",", "").replace("$", ""))
                if price_num > 0:
                    result["Price"] = f"${int(price_num):,}"
            except (ValueError, TypeError):
                pass

    # Description
    desc = data.get("description", "")
    if desc and len(str(desc).strip()) > 20:
        result["Description"] = str(desc).strip()[:2000]

    # Fuel Type
    fuel = data.get("fuelType", "")
    if not fuel:
        engine = data.get("vehicleEngine", {})
        if isinstance(engine, dict):
            fuel = engine.get("fuelType", "")
    if fuel:
        result["Fuel Type"] = _normalize_fuel(str(fuel))

    # Transmission
    trans = data.get("vehicleTransmission", "")
    if trans:
        result["Transmission"] = _normalize_transmission(str(trans))

    # Condition
    cond = data.get("itemCondition", "")
    if cond:
        cond_lower = str(cond).lower()
        if "new" in cond_lower:
            result["Condition"] = "Excellent"
        elif "refurbished" in cond_lower or "certified" in cond_lower:
            result["Condition"] = "Excellent"
        elif "used" in cond_lower:
            result["Condition"] = "Good"

    return result


def extract_jsonld(soup: BeautifulSoup) -> dict:
    """
    Parse all <script type="application/ld+json"> blocks and merge vehicle fields.
    Returns a dict of populated fields (only fields where data was found).
    JSON-LD wins over all other sources — it's the ground truth from the dealer.
    """
    result = {}

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            raw = (script.string or "").strip()
            if not raw:
                continue
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue

        # Handle @graph wrapper (common on Dealer Inspire / WordPress sites)
        if isinstance(data, dict) and "@graph" in data:
            for node in data["@graph"]:
                if isinstance(node, dict):
                    node_fields = _parse_vehicle_node(node)
                    # Merge: only fill fields not yet populated
                    for k, v in node_fields.items():
                        if v and not result.get(k):
                            result[k] = v
        elif isinstance(data, list):
            for node in data:
                if isinstance(node, dict):
                    node_fields = _parse_vehicle_node(node)
                    for k, v in node_fields.items():
                        if v and not result.get(k):
                            result[k] = v
        elif isinstance(data, dict):
            node_fields = _parse_vehicle_node(data)
            for k, v in node_fields.items():
                if v and not result.get(k):
                    result[k] = v

    if result:
        found = [k for k in SCORED_FIELDS if result.get(k)]
        print(f"[jsonld] extracted {len(found)} fields: {found}", flush=True)

    return result


# =========================================================================
# Pydantic models
# =========================================================================

class ImageCandidate(BaseModel):
    src: str
    alt: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None


class HtmlPayload(BaseModel):
    url: str
    html: str
    images: Optional[List[ImageCandidate]] = None


def extract_json_object(raw: str, label: str = "") -> dict:
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip()

    start = cleaned.find("{")
    if start == -1:
        print(f"[main] {label} raw output: {raw!r}", flush=True)
        raise ValueError(f"No JSON object found in model output: {raw!r}")

    depth = 0
    in_string = False
    escape_next = False
    end = -1
    for i, ch in enumerate(cleaned[start:], start=start):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break

    if end == -1:
        print(f"[main] {label} raw output: {raw!r}", flush=True)
        raise ValueError(f"No closing brace found in model output: {raw!r}")

    json_str = cleaned[start : end + 1]
    print(f"[main] {label} raw output: {raw!r}", flush=True)
    return json.loads(json_str)


class ScrapeUrlPayload(BaseModel):
    url: str


@app.post("/fb/scrape_url")
def scrape_url(body: ScrapeUrlPayload):
    """
    Fetch a dealer inventory URL server-side and run full field extraction.
    Returns the same schema as /fb/extract_html.

    Strategy:
      1. Try GET on the SRP URL.
      2. If we get real HTML (200 + not a bot-challenge page), run extract_html.
      3. If we get 403 / bot-challenge / zero JSON-LD, run platform API fallbacks:
         - DDC (Dealer.com) inventory API
         - Dealer Inspire WP-JSON
         - DealerOn search API
         - CDK inventory API
         - Sitemap VDP harvest → JSON-LD
         - Generic SRP VDP link → JSON-LD
    """
    import requests as req_lib

    UA_BROWSER = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    headers = {
        "User-Agent": UA_BROWSER,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    url = body.url
    # Enforce HTTPS — some dealer URLs come in as HTTP and fail silently
    if url.startswith("http://"):
        url = "https://" + url[7:]
        print(f"[scrape_url] normalized to HTTPS: {url}", flush=True)

    # ── Step 1: Try fetching the SRP page directly ──────────────────────────
    html = ""
    srp_ok = False
    try:
        r = req_lib.get(url, headers=headers, timeout=25, verify=False)
        if r.status_code == 200:
            # Check it's real dealer HTML, not a bot-challenge page
            body_lower = r.text[:2000].lower()
            is_challenge = (
                "just a moment" in body_lower
                or "cf-ray" in body_lower
                or "access denied" in body_lower
                or "enable javascript" in body_lower
                or "browser check" in body_lower
            )
            if not is_challenge:
                html = r.text
                srp_ok = True
                print(f"[scrape_url] SRP fetch OK ({len(html)} bytes): {url}", flush=True)
            else:
                print(f"[scrape_url] SRP returned bot-challenge page: {url}", flush=True)
        else:
            print(f"[scrape_url] SRP fetch HTTP {r.status_code}: {url}", flush=True)
    except Exception as e:
        print(f"[scrape_url] SRP fetch exception: {e} — {url}", flush=True)

    # ── Step 2: Detect platform (use HTML if we have it, else from URL/domain) ─
    platform = _detect_platform_from_html(html, urlparse(url).netloc) if html else "generic"
    print(f"[scrape_url] platform={platform} srp_ok={srp_ok} url={url}", flush=True)

    # ── Step 3: If SRP gave us real HTML, try standard extraction first ──────
    if srp_ok and html:
        soup = BeautifulSoup(html, "html.parser")
        jsonld_fields = extract_jsonld(soup)
        if len([k for k in SCORED_FIELDS if jsonld_fields.get(k)]) >= 4:
            # Good JSON-LD in the SRP — use the full extract_html pipeline
            imgs = []
            for img in soup.find_all("img"):
                src = img.get("src") or img.get("data-src") or ""
                if src:
                    imgs.append(ImageCandidate(src=src, alt=img.get("alt") or ""))
                if len(imgs) >= 60:
                    break
            payload = HtmlPayload(url=url, html=html, images=imgs)
            return extract_html(payload)
        print(f"[scrape_url] SRP JSON-LD weak ({len([k for k in SCORED_FIELDS if jsonld_fields.get(k)])}/10 fields) — trying platform API", flush=True)

    # ── Step 4: Platform API / VDP fallback strategies ───────────────────────
    api_fields = extract_from_platform_api(url, platform, html, req_lib)
    filled_count = len([k for k in SCORED_FIELDS if api_fields.get(k)])
    print(f"[scrape_url] platform API returned {filled_count}/10 fields", flush=True)

    if filled_count >= 3:
        # Enough to be useful — build a full result and fill remaining gaps
        result: dict = {k: "" for k in FIELDS}
        result.update(api_fields)

        # NHTSA fill for gaps
        vin_for_decode = result.get("VIN", "")
        if vin_for_decode:
            nhtsa = vin_decode_nhtsa(vin_for_decode)
            for k, v in nhtsa.items():
                if v and not result.get(k):
                    result[k] = v

        # Regex fallback for mileage & year
        if not result.get("Mileage"):
            result["Mileage"] = "0"
        if not result.get("Year"):
            m = re.search(r"\b(20(?:1[5-9]|2[0-9]))\b", str(api_fields))
            if m:
                result["Year"] = m.group(1)

        # Synthesize description if missing
        if not result.get("Description"):
            parts = [p for p in [result.get("Year"), result.get("Make"), result.get("Model")] if p]
            if parts:
                result["Description"] = (
                    f"{' '.join(parts)} available at this dealership. "
                    "Contact us for current pricing and availability."
                )

        filled = [k for k in SCORED_FIELDS if result.get(k)]
        print(f"[scrape_url] final coverage after API: {len(filled)}/10 — {filled}", flush=True)
        result["images"] = []
        result["platform"] = platform
        return result

    # ── Step 5: Last resort — if we have SRP HTML, run full extract_html ─────
    # Only for VDP-style URLs. Skip for known SRP patterns (/new-inventory/index.htm,
    # /new-vehicles/, /inventory/new) since AI-extracting an SRP produces junk data.
    if srp_ok and html:
        url_lower = url.lower()
        is_srp = any(pat in url_lower for pat in [
            "/new-inventory/index.htm",
            "/used-inventory/index.htm",
            "/new-vehicles/",
            "/inventory/new",
            "/inventory/used",
            "/search/new-",
        ])
        if not is_srp:
            soup = BeautifulSoup(html, "html.parser")
            imgs = []
            for img in soup.find_all("img"):
                src = img.get("src") or img.get("data-src") or ""
                if src:
                    imgs.append(ImageCandidate(src=src, alt=img.get("alt") or ""))
                if len(imgs) >= 60:
                    break
            payload = HtmlPayload(url=url, html=html, images=imgs)
            return extract_html(payload)
        else:
            print(f"[scrape_url] SRP URL — skipping extract_html fallback to avoid noisy data: {url}", flush=True)

    # ── Step 6: Complete failure — return graceful unsupported flag ──────────
    # Instead of a raw error, report that this page cannot be scraped server-side.
    # This happens with sites behind Cloudflare JS challenge or Akamai hard blocks.
    parsed_url = urlparse(url)
    return {
        "error": f"fetch_failed: all strategies exhausted for {url}",
        "unsupported": True,
        "unsupported_reason": "cloudflare_or_bot_blocked",
        "message": (
            f"Unable to scrape {parsed_url.netloc} server-side. "
            "This site is protected by Cloudflare or similar bot-detection. "
            "Please navigate to an individual vehicle listing page and use "
            "the extension's tab-based scraping instead."
        ),
        "url": url,
    }




# =========================================================================
# PLATFORM API EXTRACTION
# Many dealer sites return 403 on page HTML but their internal XHR/JSON
# inventory APIs are publicly accessible (no CSRF, just REST).
# We detect the platform from the domain/URL and call the correct API.
# =========================================================================

def _make_session(req_lib):
    """Return a requests.Session with a realistic browser UA and headers."""
    s = req_lib.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/html, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    })
    return s


def _fields_from_dealer_api_vehicle(v: dict) -> dict:
    """
    Map a generic dealer API vehicle record to our FIELDS dict.
    Works for DDC (Dealer.com), DealerOn, CDK, and similar CMS JSON shapes.
    """
    result = {}

    def _first(*keys):
        for k in keys:
            val = v.get(k)
            if val is not None and str(val).strip():
                return str(val).strip()
        return ""

    year = _first("year", "modelYear", "Year")
    if year and year.isdigit() and len(year) == 4:
        result["Year"] = year

    make = _first("make", "Make", "brand")
    if make:
        result["Make"] = make

    model = _first("model", "Model", "modelName")
    if model:
        result["Model"] = model

    vin = _first("vin", "VIN", "vehicleIdentificationNumber")
    vin = vin.upper().strip() if vin else ""
    if len(vin) == 17 and re.match(r"^[A-HJ-NPR-Z0-9]{17}$", vin):
        result["VIN"] = vin

    body = _first("bodyStyle", "bodyType", "body", "vehicleBodyType", "Body Type")
    if body:
        result["Body Type"] = _normalize_body_type(body)

    ext_color = _first(
        "exteriorColor", "extColor", "color", "exterior_color",
        "ExteriorColor", "extColorDescription"
    )
    if ext_color:
        nc = _normalize_color(ext_color)
        if nc:
            result["Exterior Color"] = nc

    int_color = _first(
        "interiorColor", "intColor", "interior_color",
        "InteriorColor", "intColorDescription"
    )
    if int_color:
        nc = _normalize_color(int_color)
        if nc:
            result["Interior Color"] = nc

    mileage = _first("mileage", "miles", "odometer", "Mileage")
    if mileage:
        digits = re.sub(r"[^\d]", "", str(mileage))
        if digits:
            result["Mileage"] = digits

    # Price — try common keys; for new cars try internet price over MSRP
    for pk in ["internetPrice", "salePrice", "price", "Price", "msrp", "MSRP", "sellingPrice"]:
        pval = v.get(pk)
        if pval:
            try:
                num = float(str(pval).replace(",", "").replace("$", "").strip())
                if num > 500:
                    result["Price"] = f"${int(num):,}"
                    break
            except (ValueError, TypeError):
                pass

    desc = _first("description", "Description", "longDescription", "comments")
    if desc and len(desc) > 20:
        result["Description"] = desc.strip()[:2000]

    fuel = _first("fuelType", "fuel", "Fuel Type")
    if fuel:
        result["Fuel Type"] = _normalize_fuel(fuel)

    trans = _first("transmission", "Transmission")
    if trans:
        result["Transmission"] = _normalize_transmission(trans)

    cond = _first("condition", "Condition", "stockType", "type")
    if cond:
        c = cond.lower()
        if "new" in c:
            result["Condition"] = "Excellent"
        elif "used" in c or "pre" in c:
            result["Condition"] = "Good"

    return result


def _detect_platform_from_html(html: str, domain: str) -> str:
    """Detect platform from HTML content and domain. Extended from detect_platform()."""
    h = html[:8000].lower()
    # Dealer.com / DDC — match ddc-site class, providerID=DDC meta, and classic signals
    if (
        'class="ddc-' in h or 'ddc-content' in h
        or 'dealer.com' in h or 'ddc.com' in h
        or 'ddc-site' in h
        or 'providerid" content="ddc"' in h
        or "pictures.dealer.com" in h
    ):
        return "dealer_com"
    # Dealer Inspire
    if 'class="di-' in h or 'dealerinspire' in h or 'dealer-inspire' in h or 'cfassets.dealerinspire.com' in h:
        return "dealer_inspire"
    # DealerOn
    if 'dealeron' in h or 'data-dealeron' in h or 'dealeroncdn' in h:
        return "dealeron"
    # CDK / Cobalt
    if 'cobalt' in h or 'globalcdk' in h or 'cdk-' in h or 'dealerfire' in h:
        return "cdk"
    # DealerSocket / Solera
    if 'dealersocket' in h or 'idmsa.dealersocket' in h or 'solera' in h:
        return "dealersocket"
    # EDealer / RouteOne
    if 'edealer' in h or 'routeone' in h:
        return "edealer"
    # Dominion / Digital Air Strike
    if 'dominion' in h or 'vas' in domain:
        return "dominion"
    return "generic"


def _try_ddc_api(host: str, req_lib, session) -> list:
    """
    Dealer.com (DDC) exposes a server-side rendered inventory API.
    Tries the new-inventory widget first (INVENTORY_LISTING_DEFAULT_AUTO_NEW),
    then falls back to the all-inventory widget (INVENTORY_LISTING_DEFAULT_AUTO_ALL)
    with filtering to new vehicles only.

    IMPORTANT: DDC APIs return 403 when a browser User-Agent is sent.
    They expect a plain server-side request with minimal or no UA.
    We use a separate clean session without browser UA for these API calls.

    Results are cached in-process for _DDC_CACHE_TTL seconds to avoid
    hammering the same host repeatedly (Render single IP → 429 rate-limit).
    """
    # Check in-memory cache first
    cached = _DDC_CACHE.get(host)
    if cached:
        ts, vehicles = cached
        if _time.time() - ts < _DDC_CACHE_TTL:
            print(f"[ddc_api] cache hit for {host} ({len(vehicles)} vehicles)", flush=True)
            return vehicles

    import requests as _req
    # DDC APIs reject browser User-Agent strings — use a plain session without UA
    api_session = _req.Session()
    api_session.verify = False

    base_url = f"https://{host}/apis/widget"
    params_new = {"start": 0, "pageSize": 1, "sortBy": "internetPrice asc"}
    params_all = {"start": 0, "pageSize": 50, "sortBy": "internetPrice asc"}

    # Strategy 1: NEW-exclusive widget (returns only new inventory)
    # Retry once on transient network failures (Render datacenter can be flaky).
    for widget in [
        "INVENTORY_LISTING_DEFAULT_AUTO_NEW",
    ]:
        url = f"{base_url}/{widget}:inventory-data-bus1/getInventory"
        for attempt in range(2):  # 2 attempts total
            try:
                r = api_session.get(url, params=params_new, timeout=15)
                if r.status_code == 200:
                    data = r.json()
                    tracking = data.get("pageInfo", {}).get("trackingData", [])
                    if tracking:
                        print(f"[ddc_api] NEW widget got {len(tracking)} vehicles from {host} (attempt {attempt+1})", flush=True)
                        result = tracking[:1]
                        _DDC_CACHE[host] = (_time.time(), result)
                        return result
                    break  # 200 but empty — no need to retry
                elif r.status_code in (429, 503) and attempt == 0:
                    import time as _t; _t.sleep(2)  # backoff before retry
                else:
                    break
            except Exception as e:
                print(f"[ddc_api] {widget} attempt {attempt+1} failed {host}: {e}", flush=True)
                if attempt == 0:
                    import time as _t; _t.sleep(1)

    # Strategy 2: ALL-inventory widget, filter to new vehicles in-process
    url_all = f"{base_url}/INVENTORY_LISTING_DEFAULT_AUTO_ALL:inventory-data-bus1/getInventory"
    try:
        r = api_session.get(url_all, params=params_all, timeout=15)
        if r.status_code == 200:
            data = r.json()
            tracking = data.get("pageInfo", {}).get("trackingData", [])
            # Filter to new vehicles first
            new_vehicles = [
                v for v in tracking
                if str(v.get("newOrUsed", "")).lower() == "new"
                or str(v.get("inventoryType", "")).lower() == "new"
            ]
            if new_vehicles:
                print(f"[ddc_api] ALL widget filtered to {len(new_vehicles)} new from {len(tracking)} total at {host}", flush=True)
                result = new_vehicles[:1]
                _DDC_CACHE[host] = (_time.time(), result)
                return result
            # ALL widget has NO new vehicles — do not return a used car
            # Return empty so callers (sitemap, generic VDP) can try
            print(f"[ddc_api] ALL widget zero new in {len(tracking)} results at {host} — skipping", flush=True)
    except Exception as e:
        print(f"[ddc_api] ALL widget failed {host}: {e}", flush=True)

    return []


def _try_dealer_inspire_api(host: str, req_lib, session) -> list:
    """
    Dealer Inspire sites run on WordPress. They expose a REST/sitemap layer.
    Strategy 1: WP-JSON vehicles endpoint.
    Strategy 2: VDP sitemap → pick first VDP URL → fetch it for JSON-LD.
    Returns a list of raw vehicle dicts (may be empty if neither works).
    """
    # Strategy 1: WP-JSON
    for path in [
        "/wp-json/dealer-inspire/v1/vehicles",
        "/wp-json/di/v1/vehicles",
    ]:
        try:
            r = session.get(f"https://{host}{path}", timeout=10, verify=False, params={"per_page": 1})
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and data:
                    print(f"[di_api] WP-JSON vehicles from {host}: {len(data)}", flush=True)
                    return data
                elif isinstance(data, dict) and data.get("vehicles"):
                    return data["vehicles"][:1]
        except Exception:
            pass

    # Strategy 2: Sitemap VDP harvest
    vehicles = _try_sitemap_vdp(host, session, max_vdps=1)
    return vehicles


def _try_dealeron_api(host: str, req_lib, session) -> list:
    """
    DealerOn sites expose a search/inventory API endpoint.
    """
    for path in [
        "/api/Inventory/Search",
        "/api/inventory/search",
        "/Inventory/Search",
    ]:
        try:
            r = session.post(
                f"https://{host}{path}",
                json={"pageSize": 1, "pageIndex": 0},
                timeout=10, verify=False
            )
            if r.status_code == 200:
                data = r.json()
                vehicles = data.get("Vehicles") or data.get("vehicles") or data.get("results") or []
                if vehicles:
                    print(f"[dealeron_api] got {len(vehicles)} from {host}", flush=True)
                    return vehicles[:1]
        except Exception as e:
            print(f"[dealeron_api] {path} failed: {e}", flush=True)
    return []


def _try_cdk_api(host: str, req_lib, session) -> list:
    """
    CDK/Cobalt sites typically expose a vehicle inventory endpoint.
    """
    for path in [
        "/inventory/search-inventory",
        "/api/inventory",
        "/new-inventory/api",
    ]:
        try:
            r = session.get(
                f"https://{host}{path}",
                params={"pageSize": 1},
                timeout=10, verify=False
            )
            if r.status_code == 200:
                data = r.json()
                vehicles = (
                    data.get("vehicles")
                    or data.get("Vehicles")
                    or data.get("inventory")
                    or (data if isinstance(data, list) else [])
                )
                if vehicles:
                    print(f"[cdk_api] got {len(vehicles)} from {host}", flush=True)
                    return list(vehicles)[:1]
        except Exception as e:
            print(f"[cdk_api] {path} failed: {e}", flush=True)
    return []


def _try_sitemap_vdp(host: str, session, max_vdps: int = 1) -> list:
    """
    Fallback: grab the dealer's sitemap XML, find VDP URLs (contain /vin/ or /vehicle/
    or DDC hash-style /new/<Make>/...).
    Fetch the first VDP(s) and extract JSON-LD. Returns list of partial vehicle dicts.

    NOTE: Some dealer CDNs (DDC) block browser User-Agent on sitemaps and VDP pages.
    We try with the provided session first, then fall back to a bare session with no UA.
    """
    import requests as _req

    sitemap_urls = [
        f"https://{host}/sitemap.xml",
        f"https://{host}/sitemap_index.xml",
        f"https://{host}/inventory-sitemap.xml",
    ]
    vdp_urls = []

    # Build a no-UA fallback session (works for DDC APIs/sitemaps that block browser UA)
    bare_session = _req.Session()
    bare_session.verify = False

    for sm_url in sitemap_urls:
        for sess in [session, bare_session]:
            try:
                r = sess.get(sm_url, timeout=10, verify=False)
                if r.status_code == 200 and "<url>" in r.text:
                    # Find VDP-shaped URLs: contain /vin/ or have 17-char VIN in path
                    # OR match DDC hash-style: /new/<Make>/YYYY-...-<32hexchars>.htm
                    # OR match other platforms: /vehicle/, /inventory/, /new/<make>/
                    vdp_pattern = re.compile(
                        r"/vin/|/vehicle/|/VIN/"
                        r"|[A-HJ-NPR-Z0-9]{17}"   # 17-char VIN in URL
                        r"|/new/[A-Za-z]"           # DDC new inventory: /new/Chrysler/...
                        r"|/used/[A-Za-z]"          # DDC used: /used/Chevrolet/...
                    )
                    for m in re.finditer(r"<loc>(https?://[^<]+)</loc>", r.text):
                        loc = m.group(1)
                        if vdp_pattern.search(loc):
                            # Filter: only include actual per-vehicle pages
                            is_ddc_vdp = re.search(r"-[0-9a-f]{32}\.htm$", loc)
                            is_vin_vdp = re.search(r"[A-HJ-NPR-Z0-9]{17}", loc)
                            is_generic_vdp = re.search(r"/vin/|/vehicle/", loc, re.IGNORECASE)
                            if is_ddc_vdp or is_vin_vdp or is_generic_vdp:
                                # Prefer new-inventory VDPs — put /new/ first, /used/ last
                                if re.search(r"/new/", loc, re.IGNORECASE):
                                    vdp_urls.insert(0, loc)
                                else:
                                    vdp_urls.append(loc)
                    if vdp_urls:
                        print(f"[sitemap] found {len(vdp_urls)} VDP URLs in {sm_url}", flush=True)
                        break
            except Exception:
                pass
        if vdp_urls:
            break

    results = []
    for vdp_url in vdp_urls[:max_vdps]:
        # Filter: only fetch new-inventory VDPs (skip /used/ URLs when looking at new-inventory page)
        # Allow both new and used for now — caller decides relevance
        fetched = False
        for sess in [bare_session, session]:
            try:
                r = sess.get(vdp_url, timeout=20, verify=False)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, "html.parser")
                    fields = extract_jsonld(soup)
                    if fields:
                        print(f"[sitemap_vdp] extracted {list(fields.keys())} from {vdp_url}", flush=True)
                        results.append(fields)
                        fetched = True
                        break
            except Exception as e:
                print(f"[sitemap_vdp] {vdp_url} failed: {e}", flush=True)
        if not fetched:
            print(f"[sitemap_vdp] all sessions failed for {vdp_url}", flush=True)
    return results


def _try_generic_vdp(host: str, session) -> dict:
    """
    For truly generic sites (no known API): fetch the SRP, find the first
    VDP link on the page (href with /vin/ or a 17-char VIN), then fetch
    that VDP and extract JSON-LD. Returns a fields dict (may be empty).
    """
    srp_url = f"https://{host}/new-inventory/index.htm"
    try:
        r = session.get(srp_url, timeout=20, verify=False)
        if r.status_code != 200:
            return {}
        soup = BeautifulSoup(r.text, "html.parser")
        # Find first <a href> that looks like a VDP
        vdp_href = None
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if re.search(r"/vin/|/vehicle/|[A-HJ-NPR-Z0-9]{17}", href, re.IGNORECASE):
                vdp_href = href if href.startswith("http") else f"https://{host}{href}"
                break
        if not vdp_href:
            return {}
        vdp_r = session.get(vdp_href, timeout=20, verify=False)
        if vdp_r.status_code != 200:
            return {}
        vdp_soup = BeautifulSoup(vdp_r.text, "html.parser")
        fields = extract_jsonld(vdp_soup)
        if fields:
            print(f"[generic_vdp] VDP JSON-LD from {vdp_href}: {list(fields.keys())}", flush=True)
        return fields
    except Exception as e:
        print(f"[generic_vdp] {host}: {e}", flush=True)
        return {}


def extract_from_platform_api(url: str, platform: str, html: str, req_lib) -> dict:
    """
    Try platform-specific API calls to get structured vehicle data.
    Falls back to sitemap VDP strategy if the API returns nothing.
    Returns a partial fields dict (may be empty if all strategies fail).
    """
    parsed = urlparse(url)
    host = parsed.netloc.lstrip("www.")
    full_host = parsed.netloc  # with www.

    session = _make_session(req_lib)

    vehicles = []

    if platform == "dealer_com":
        vehicles = _try_ddc_api(full_host, req_lib, session)
        if not vehicles:
            vehicles = _try_ddc_api(host, req_lib, session)

    elif platform == "dealer_inspire":
        vehicles = _try_dealer_inspire_api(full_host, req_lib, session)

    elif platform == "dealeron":
        vehicles = _try_dealeron_api(full_host, req_lib, session)

    elif platform == "cdk":
        vehicles = _try_cdk_api(full_host, req_lib, session)

    # If API returned vehicles, map first one to our field schema
    if vehicles:
        v = vehicles[0]
        # Vehicles from sitemap strategy are already field dicts
        if isinstance(v, dict) and any(k in v for k in ("Year", "Make", "VIN")):
            return v
        return _fields_from_dealer_api_vehicle(v)

    # Blind DDC probe FIRST (fast — single HTTPS call, no HTML parsing)
    # DDC NEW widget returns only new vehicles and is faster than a sitemap+VDP fetch.
    # Many large dealer sites run DDC but can't be detected from blocked SRP HTML.
    if platform != "dealer_com":
        blind_ddc = _try_ddc_api(full_host, req_lib, session)
        if not blind_ddc:
            blind_ddc = _try_ddc_api(host, req_lib, session)
        if blind_ddc:
            v = blind_ddc[0]
            if isinstance(v, dict) and any(k in v for k in ("Year", "Make", "VIN")):
                return v
            fields = _fields_from_dealer_api_vehicle(v)
            return fields

    # Universal fallback: sitemap VDP → JSON-LD
    sitemap_results = _try_sitemap_vdp(full_host, session, max_vdps=1)
    if sitemap_results and isinstance(sitemap_results[0], dict):
        first = sitemap_results[0]
        # Sitemap results may already be field dicts from extract_jsonld
        if any(k in first for k in ("Year", "Make", "VIN")):
            return first
        return _fields_from_dealer_api_vehicle(first)

    # Last resort: scrape VDP link from SRP page
    generic = _try_generic_vdp(full_host, session)
    return generic


def detect_platform(html: str) -> str:
    """Detect which dealer website platform is serving this page.
    Check first 5KB only for performance."""
    h = html[:5000].lower()
    if 'class="ddc-' in h or 'ddc-content' in h or 'dealer.com' in h:
        return "dealer_com"
    if 'dealeron' in h or 'data-dealeron' in h:
        return "dealeron"
    if 'cobalt' in h or 'globalcdk' in h or 'cdk-' in h:
        return "cdk"
    if 'class="di-' in h or 'dealerinspire' in h or 'dealer-inspire' in h:
        return "dealer_inspire"
    return "generic"


def vin_decode_nhtsa(vin: str) -> dict:
    """Free VIN decode via NHTSA API. Returns dict of fields."""
    import requests as req_lib
    if not vin or len(vin) != 17:
        return {}
    try:
        url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVin/{vin}?format=json"
        r = req_lib.get(url, timeout=10)
        results = r.json().get("Results", [])
        decoded = {}
        field_map = {
            "Make": "Make",
            "Model": "Model",
            "Model Year": "Year",
            "Body Class": "Body Type",
            "Fuel Type - Primary": "Fuel Type",
            "Transmission Style": "Transmission",
        }
        for item in results:
            var = item.get("Variable", "")
            val = item.get("Value", "")
            if var in field_map and val and val.strip() and val.strip() != "Not Applicable":
                decoded[field_map[var]] = val.strip()
        # Normalize body type through existing function
        if "Body Type" in decoded:
            decoded["Body Type"] = _normalize_body_type(decoded["Body Type"])
        if "Fuel Type" in decoded:
            decoded["Fuel Type"] = _normalize_fuel(decoded["Fuel Type"])
        if "Transmission" in decoded:
            decoded["Transmission"] = _normalize_transmission(decoded["Transmission"])
        if decoded:
            print(f"[vin_decode] NHTSA returned: {list(decoded.keys())}", flush=True)
        return decoded
    except Exception as e:
        print(f"[vin_decode] NHTSA error: {e}", flush=True)
        return {}


@app.post("/fb/extract_html")
def extract_html(body: HtmlPayload):
    soup = BeautifulSoup(body.html, "html.parser")

    platform = detect_platform(body.html)
    print(f"[platform] detected: {platform} for {body.url}", flush=True)

    # ── LAYER 1: JSON-LD structured data ─────────────────────────────────────
    # Free, instant, 100% accurate when present (DealerOn, Dealer.com, CDK, Dealer Inspire).
    result = {k: "" for k in FIELDS}
    jsonld = extract_jsonld(soup)
    result.update(jsonld)

    # ── LAYER 1.5: NHTSA VIN decode (free, fills gaps from JSON-LD) ──────────
    vin_for_decode = result.get("VIN", "")
    if not vin_for_decode:
        # Try regex to find VIN in raw text for decode even if JSON-LD missed it
        m = re.search(r'\b([A-HJ-NPR-Z0-9]{17})\b', soup.get_text(separator=" "))
        if m:
            vin_for_decode = m.group(1)
            result["VIN"] = vin_for_decode

    if vin_for_decode:
        nhtsa = vin_decode_nhtsa(vin_for_decode)
        for k, v in nhtsa.items():
            if v and not result.get(k):
                result[k] = v

    # Recalculate missing after VIN decode
    missing = [k for k in SCORED_FIELDS if not result.get(k)]
    all_missing = [k for k in FIELDS if not result.get(k)]

    # ── LAYER 2: AI extraction for missing fields ─────────────────────────────
    if missing:
        text = soup.get_text(separator="\n")
        # Detect list vs VDP
        vin_count = len(set(re.findall(r'\b[A-HJ-NPR-Z0-9]{17}\b', text)))
        is_list_page = vin_count > 1
        # Trim text: first 5000 chars for list pages, 20000 for VDP
        text_for_ai = text[:5000] if is_list_page else text[:20000]

        base_fields = {k: "" for k in all_missing}
        page_context = (
            "This is an inventory LIST page showing multiple vehicles. "
            "Extract fields for the FIRST vehicle listed only.\n"
            if is_list_page else
            "This is a vehicle DETAIL page (VDP) showing a single vehicle.\n"
        )
        fields_prompt = (
            "You are a data extractor for vehicle listings.\n"
            f"{page_context}"
            "From the text below, extract ONLY these fields and return ONLY valid JSON.\n"
            "Do NOT include any explanation, only a JSON object.\n"
            f"{json.dumps(base_fields, indent=2)}\n\n"
            "Rules:\n"
            "- Mileage: extract as shown (e.g. '54,233 miles'). For NEW cars with 0 miles, write '0 miles'. "
            "Do NOT leave empty if any mileage figure appears in the text.\n"
            "- VIN: full 17-character VIN only.\n"
            "- Year/Make/Model: from the listing title or specs.\n"
            "- Price: formatted with currency symbol (e.g. '$44,175'). "
            "Use internet/sale price over MSRP if both present.\n"
            "- Exterior Color / Interior Color: use the full human-readable color name "
            "(e.g. 'Selenite Grey Metallic', not a short code like 'Ack' or 'Lic'). "
            "If you only see an abbreviation or code with no full name nearby, leave the field empty.\n"
            "- Body Type: standard terms — Sedan, SUV, Truck, Coupe, Convertible, Wagon, Hatchback, Van, Minivan.\n"
            "- Condition: one of Excellent, Good, Fair, Poor. Use 'Excellent' for new or certified pre-owned.\n"
            "- Fuel Type: one of Gasoline, Diesel, Electric, Hybrid, Plug-in Hybrid.\n"
            "- Transmission: one of Automatic, Manual, CVT.\n"
            "- Description: write 2-3 sentences in a natural, sales-friendly tone "
            "highlighting the vehicle's key features, trim level, and standout qualities. "
            "Do NOT copy spec sheet text verbatim. Do NOT mention price or mileage.\n"
            "- If a value is not present in the text, leave it as an empty string.\n\n"
            f"TEXT:\n{text_for_ai}"
        )

        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": fields_prompt}],
            )
            raw = resp.choices[0].message.content
            data = extract_json_object(raw, label="fields")
            for k in all_missing:
                val = data.get(k, "") or ""
                if val:
                    result[k] = val
        except Exception as e:
            print(f"[main] AI extraction error: {e}", flush=True)

    # ── LAYER 3: Regex fallbacks for anything still missing ───────────────────
    full_text = soup.get_text(separator=" ")

    if not result.get("VIN"):
        m = re.search(r'\b([A-HJ-NPR-Z0-9]{17})\b', full_text)
        if m:
            result["VIN"] = m.group(1)

    if not result.get("Price"):
        m = re.search(r'\$\s*(\d[\d,]*(?:\.\d{2})?)', full_text)
        if m:
            result["Price"] = "$" + m.group(1)

    if not result.get("Mileage"):
        m = re.search(r'\b([\d,]+)\s*(?:mi|miles)\b', full_text, re.IGNORECASE)
        if m:
            result["Mileage"] = m.group(0)
        else:
            result["Mileage"] = "0"  # new car default — scores ✓, fills to 300 in extension

    if not result.get("Year"):
        m = re.search(r'\b(20(?:1[5-9]|2[0-9]))\b', full_text)
        if m:
            result["Year"] = m.group(1)

    if not result.get("Description") or result["Description"].startswith("(AI"):
        parts = [p for p in [result.get("Year"), result.get("Make"), result.get("Model")] if p]
        if parts:
            result["Description"] = (
                f"{' '.join(parts)} available at our dealership. "
                "Contact us for pricing and availability details."
            )

    # ── Layer summary log ─────────────────────────────────────────────────────
    filled = [k for k in SCORED_FIELDS if result.get(k)]
    print(f"[main] final coverage: {len(filled)}/{len(SCORED_FIELDS)} — {filled}", flush=True)

    # ---------- Images via LLM ----------
    images_out: List[str] = []

    if body.images:
        candidates = [
            {
                "src": c.src,
                "alt": c.alt or "",
                "width": c.width or 0,
                "height": c.height or 0,
            }
            for c in body.images
            if c.src
        ]
        slim = candidates[:60]

        if slim:
            is_list_page_img = len(set(re.findall(r'\b[A-HJ-NPR-Z0-9]{17}\b', soup.get_text()))) > 1
            list_page_note = (
                "NOTE: This is an inventory LIST page with multiple vehicles. "
                "Only pick photos for the FIRST vehicle listed.\n\n"
                if is_list_page_img else ""
            )
            img_prompt = (
                "You are selecting vehicle photos from a dealership listing.\n"
                "You will be given a JSON array of candidate <img> elements.\n"
                f"{list_page_note}"
                "Each item includes a URL and metadata.\n\n"
                "Goal:\n"
                "- Keep images that are clearly the car itself (exterior/interior photos\n"
                "  in the main gallery or carousel).\n"
                "- Exclude logos, icons, badges, tiny thumbnails, social icons, brand\n"
                "  logos, profile pictures, 'no image' placeholders, dealer logos.\n\n"
                "Return ONLY valid JSON in this form:\n"
                '{\n  "images": ["url1", "url2", "..."]\n}\n\n'
                "Here are the candidates:\n"
                f"{json.dumps(slim, indent=2)}"
            )

            try:
                img_resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": img_prompt}],
                )
                raw_img = img_resp.choices[0].message.content
                img_obj = extract_json_object(raw_img, label="images")
                images_out = [u for u in img_obj.get("images", []) if isinstance(u, str)]
            except Exception:
                images_out = []

        if not images_out and candidates:
            candidates_sorted = sorted(
                candidates,
                key=lambda c: (c.get("width") or 0) * (c.get("height") or 0),
                reverse=True,
            )
            images_out = [
                c["src"] for c in candidates_sorted[:8] if c.get("src")
            ]

    result["images"] = images_out
    result["platform"] = platform

    return result


# ========= Image Scrubbing =========

class ScrubPayload(BaseModel):
    image_url: str


@app.post("/fb/scrub_image")
def scrub_image(body: ScrubPayload):
    """
    Downloads the image, sends it to GPT-4o vision to detect dealer
    watermarks/branding, then uses DALL-E 3 inpainting to return a
    clean version. Falls back to the original URL on any error.
    """
    import base64
    import requests as req

    url = body.image_url
    try:
        # Fetch the image
        r = req.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        img_b64 = base64.b64encode(r.content).decode()
        mime = r.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()

        vision_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

        # Step 1: Ask GPT-4o vision to describe what branding/watermarks are present
        vision_resp = vision_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime};base64,{img_b64}",
                                "detail": "low",
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Does this vehicle photo contain any dealer watermarks, "
                                "logos, overlay text, dealership name, phone numbers, or "
                                "branding? Answer ONLY with YES or NO."
                            ),
                        },
                    ],
                }
            ],
            max_tokens=5,
        )

        answer = vision_resp.choices[0].message.content.strip().upper()
        print(f"[scrub] watermark detected: {answer} for {url}", flush=True)

        if "NO" in answer:
            # No branding — return original
            return {"scrubbed_url": url, "scrubbed": False}

        # Step 2: Generate a clean version with DALL-E 3
        gen_resp = vision_client.images.generate(
            model="dall-e-3",
            prompt=(
                "A clean, professional dealership photo of this vehicle with no watermarks, "
                "no logos, no text overlays, no dealer branding, no phone numbers. "
                "Just the car on a clean background. Photorealistic."
            ),
            size="1024x1024",
            quality="standard",
            n=1,
        )

        scrubbed_url = gen_resp.data[0].url
        return {"scrubbed_url": scrubbed_url, "scrubbed": True}

    except Exception as e:
        print(f"[scrub] error: {e}", flush=True)
        # Always fall back gracefully — never break the listing flow
        return {"scrubbed_url": url, "scrubbed": False}
