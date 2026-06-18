# api/main.py
from fastapi import FastAPI
from pydantic import BaseModel
from bs4 import BeautifulSoup
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
import os
import re
import json
from typing import List, Optional

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
    Fetch a dealer inventory URL server-side (using Render's IP / UA) and
    run full field extraction.  Returns the same schema as /fb/extract_html.
    Useful for automated testing from WSL where Cloudflare blocks local requests.
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

    try:
        r = req_lib.get(url, headers=headers, timeout=25, verify=False)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        return {"error": f"fetch_failed: {e}", "url": url}

    # Reuse existing extract logic by building an HtmlPayload
    soup = BeautifulSoup(html, "html.parser")
    imgs = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if src:
            imgs.append(ImageCandidate(src=src, alt=img.get("alt") or ""))
        if len(imgs) >= 60:
            break

    payload = HtmlPayload(url=body.url, html=html, images=imgs)
    return extract_html(payload)


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
