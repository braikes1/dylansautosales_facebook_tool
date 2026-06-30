"""
Standalone test: import scrape logic directly (no server needed).
Run: python api/test_scrape.py
"""
import os
import sys
import json
import requests
from dotenv import load_dotenv

# Load .env from same dir as this script
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

HOLMAN_DETAIL_URL = "https://www.holmanhonda.com/inventory/new-2026-honda-civic-sedan-lx-fwd-4d-sedan-2hgfe2f26th600118/"

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


def scrape_vehicle(url: str, vin: str = None) -> dict:
    fc_api_key = os.environ["FIRECRAWL_API_KEY"]

    print(f"[test_scrape] Calling FireCrawl for: {url}", flush=True)
    fc_resp = requests.post(
        "https://api.firecrawl.dev/v1/scrape",
        headers={
            "Authorization": f"Bearer {fc_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "url": url,
            "formats": ["markdown", "extract"],
            "extract": {"schema": _FC_SCHEMA},
        },
        timeout=90,
    )

    if not fc_resp.ok:
        print(f"[test_scrape] FireCrawl error {fc_resp.status_code}: {fc_resp.text[:400]}", flush=True)
        sys.exit(1)

    fc_data = fc_resp.json()

    try:
        extract = fc_data["data"]["extract"]
        vehicles = extract["vehicles"]
    except (KeyError, TypeError) as e:
        print(f"[test_scrape] Unexpected structure: {json.dumps(fc_data, indent=2)[:1000]}")
        print(f"Error: {e}")
        sys.exit(1)

    if not vehicles:
        print("[test_scrape] No vehicles returned! Dumping extract:")
        print(json.dumps(fc_data.get("data", {}).get("extract"), indent=2))
        print("\nMarkdown snippet:")
        print(fc_data.get("data", {}).get("markdown", "")[:2000])
        sys.exit(1)

    # Pick vehicle
    vehicle = None
    if vin:
        for v in vehicles:
            if str(v.get("vin", "")).strip().upper() == vin.strip().upper():
                vehicle = v
                break
    if vehicle is None:
        vehicle = vehicles[0]

    # Map keys
    result = {}
    for fc_key, out_key in _FC_KEY_MAP.items():
        val = vehicle.get(fc_key) or ""
        result[out_key] = str(val).strip() if val else ""

    if not result["Fuel Type"]:
        result["Fuel Type"] = "Gasoline"

    raw_images = vehicle.get("images") or []
    result["images"] = [u for u in raw_images if isinstance(u, str) and u.startswith("http")]

    return result


if __name__ == "__main__":
    result = scrape_vehicle(HOLMAN_DETAIL_URL)
    print("\n=== RESULT ===")
    print(json.dumps(result, indent=2))
    print(f"\n=== SUMMARY ===")
    print(f"Body Type:       {result.get('Body Type')}")
    print(f"Mileage:         {result.get('Mileage')}")
    print(f"Condition:       {result.get('Condition')}")
    print(f"Fuel Type:       {result.get('Fuel Type')}")
    print(f"Exterior Color:  {result.get('Exterior Color')}")
    print(f"Interior Color:  {result.get('Interior Color')}")
    print(f"Images count:    {len(result.get('images', []))}")
    if result.get("images"):
        print(f"First image URL: {result['images'][0]}")
