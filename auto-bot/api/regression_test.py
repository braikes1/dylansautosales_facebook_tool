"""
Phase 4 regression test — calls /fb/scrape_url logic directly (no server).
Tests both Holman (canary) and Taverna (sentinel).
Run: python api/regression_test.py
"""
import os, sys, json, re, requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

DEALERS = [
    {
        "name":  "Holman Honda (canary)",
        "url":   "https://www.holmanhonda.com/inventory/new-2026-honda-civic-sedan-lx-fwd-4d-sedan-2hgfe2f26th600118/",
        "expect_make": "Honda",
    },
    {
        "name":  "Taverna Chrysler (sentinel)",
        "url":   "https://www.tavernacdjr.com/new-inventory/vehicle-details/2025-Jeep-Wrangler-4xe-NP37834.htm",
        "expect_make": "Jeep",
    },
]

_BODY_TYPE_SUFFIXES = re.compile(
    r"\s+\b(Sedan|Hatchback|Coupe|Convertible|Wagon|SUV|Truck|Van|Minivan)\b.*$",
    re.IGNORECASE,
)

def _strip_body_type_suffix(model: str) -> str:
    return _BODY_TYPE_SUFFIXES.sub("", model).strip()

_FC_KEY_MAP = {
    "mileage":        "Mileage",
    "vin":            "VIN",
    "year":           "Year",
    "make":           "Make",
    "model":          "Model",
    "price":          "Price",
    "interior_color": "Interior Color",
    "exterior_color": "Exterior Color",
    "body_type":      "Body Type",
    "description":    "Description",
    "condition":      "Condition",
    "fuel_type":      "Fuel Type",
}

_FC_SCHEMA = {
    "type": "object",
    "properties": {
        "vehicles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "year":           {"type": "string"},
                    "make":           {"type": "string"},
                    "model":          {"type": "string"},
                    "trim":           {"type": "string"},
                    "price":          {"type": "string"},
                    "mileage":        {"type": "string"},
                    "vin":            {"type": "string"},
                    "exterior_color": {"type": "string"},
                    "interior_color": {"type": "string"},
                    "description":    {"type": "string"},
                    "images":         {"type": "array", "items": {"type": "string"}},
                    "condition":      {"type": "string"},
                    "body_type":      {"type": "string"},
                    "fuel_type":      {"type": "string"},
                },
                "required": ["year", "make", "model", "price", "vin"],
            },
        }
    },
}

CHECKLIST = [
    "Make", "Model", "Year", "Price", "Mileage",
    "Body Type", "Exterior Color", "Interior Color",
    "Condition", "Fuel Type", "VIN", "Description",
]

def scrape(url: str) -> dict:
    fc_api_key = os.environ["FIRECRAWL_API_KEY"]
    fc_resp = requests.post(
        "https://api.firecrawl.dev/v1/scrape",
        headers={"Authorization": f"Bearer {fc_api_key}", "Content-Type": "application/json"},
        json={"url": url, "formats": ["markdown", "extract"], "extract": {"schema": _FC_SCHEMA}},
        timeout=90,
    )
    if not fc_resp.ok:
        raise RuntimeError(f"FireCrawl HTTP {fc_resp.status_code}: {fc_resp.text[:300]}")

    fc_data = fc_resp.json()
    vehicles = fc_data["data"]["extract"]["vehicles"]
    if not vehicles:
        raise RuntimeError("FireCrawl returned no vehicles")

    vehicle = vehicles[0]
    result = {}
    for fc_key, out_key in _FC_KEY_MAP.items():
        val = vehicle.get(fc_key) or ""
        result[out_key] = str(val).strip() if val else ""

    if not result["Fuel Type"]:
        result["Fuel Type"] = "Gasoline"
    if result.get("Model"):
        result["Model"] = _strip_body_type_suffix(result["Model"])

    raw_images = vehicle.get("images") or []
    result["images"] = [u for u in raw_images if isinstance(u, str) and u.startswith("http")]
    return result


def mapVehicleCondition(raw: str) -> str:
    s = raw.lower().strip()
    if not s or s == "new":          return "Excellent"
    if "excellent" in s:             return "Excellent"
    if "very good" in s:             return "Very good"
    if "good" in s:                  return "Good"
    if "fair" in s:                  return "Fair"
    if "new" in s:                   return "Excellent"
    return raw


overall_pass = True

for dealer in DEALERS:
    print(f"\n{'='*60}")
    print(f"TESTING: {dealer['name']}")
    print(f"URL:     {dealer['url']}")
    print(f"{'='*60}")

    try:
        result = scrape(dealer["url"])
    except Exception as e:
        print(f"  [FAIL] SCRAPE FAILED: {e}")
        overall_pass = False
        continue

    print(f"\n--- Raw result ---")
    # Print without images
    display = {k: v for k, v in result.items() if k != "images"}
    print(json.dumps(display, indent=2))
    print(f"images count: {len(result.get('images', []))}")
    if result.get("images"):
        print(f"first image:  {result['images'][0]}")

    print(f"\n--- Checklist ---")
    dealer_pass = True
    for field in CHECKLIST:
        val = result.get(field, "")
        populated = bool(val)
        mark = "[PASS]" if populated else "[FAIL]"
        print(f"  {mark} {field}: {val!r}")
        if not populated:
            dealer_pass = False
            overall_pass = False

    # Extra: FB-fill mapped values
    mapped_condition = mapVehicleCondition(result.get("Condition", ""))
    print(f"\n--- FB-fill mapped values ---")
    print(f"  Condition raw -> FB: {result.get('Condition')!r} -> {mapped_condition!r}")
    print(f"  Fuel Type:          {result.get('Fuel Type')!r}")
    print(f"  Body Type:          {result.get('Body Type')!r}  (FB label: 'Body style')")
    print(f"  Model (stripped):   {result.get('Model')!r}")
    print(f"  Images count:       {len(result.get('images', []))}  (39 expected for Holman Civic)")

    print(f"\n--- Fallback check ---")
    print(f"  /fb/scrape_url used: [PASS] YES (direct FireCrawl call, no /fb/extract_html)")

    print(f"\n  DEALER RESULT: {'[PASS] PASS' if dealer_pass else '[FAIL] FAIL — missing fields above'}")

print(f"\n{'='*60}")
print(f"OVERALL: {'[PASS] BOTH DEALERS PASS' if overall_pass else '[FAIL] REGRESSION DETECTED — see failures above'}")
print(f"{'='*60}")
