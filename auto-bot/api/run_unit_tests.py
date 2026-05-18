"""
Autonomous unit tests for AutoBot API extraction.
Tests AI extraction quality using static HTML snippets (no Cloudflare needed).
Saves results to /mnt/c/Users/NOBRAIKES/Desktop/DOMO/unit_test_results.md

Run: python3.11 run_unit_tests.py
"""
import requests, json, sys, os
from datetime import datetime

API = "https://dylansautosales-facebook-tool.onrender.com/fb/extract_html"
DOMO_DIR = "/mnt/c/Users/NOBRAIKES/Desktop/DOMO"

SCORED_FIELDS = ["Year","Make","Model","Price","VIN","Body Type","Mileage",
                 "Exterior Color","Interior Color","Description"]

def extract(html, url="https://test.example.com/", images=None):
    resp = requests.post(API, json={"url": url, "html": html, "images": images or []}, timeout=60)
    resp.raise_for_status()
    return resp.json()

def score(result):
    scores, total = {}, 0
    for f in SCORED_FIELDS:
        v = result.get(f, "")
        ok = bool(v and str(v).strip())
        scores[f] = "✓" if ok else "✗"
        if ok: total += 1
    return scores, round(total / len(SCORED_FIELDS) * 100)

TESTS = [

    # ── JSON-LD layer tests ───────────────────────────────────────────────────

    {
        "id": "JSONLD_full_car_node",
        "desc": "Full Schema.org Car JSON-LD — extract all fields from structured data",
        "html": """<!DOCTYPE html><html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Car",
  "name": "2023 Ford Mustang GT",
  "vehicleIdentificationNumber": "1FA6P8CF4N5130001",
  "vehicleModelDate": "2023",
  "brand": {"@type": "Brand", "name": "Ford"},
  "model": "Mustang GT",
  "bodyType": "Coupe",
  "color": "Race Red",
  "vehicleInteriorColor": "Ebony Black",
  "mileageFromOdometer": {"@type": "QuantitativeValue", "value": "12500", "unitCode": "SMI"},
  "offers": {"@type": "Offer", "price": 47995, "priceCurrency": "USD"},
  "description": "The iconic Ford Mustang GT with V8 power and premium features.",
  "fuelType": "Gasoline",
  "vehicleTransmission": "Manual"
}
</script>
</head><body><p>Loading...</p></body></html>""",
        "expect_field": "VIN",
        "expect_value_contains": "1FA6P8CF4N5130001",
    },

    {
        "id": "JSONLD_graph_wrapper",
        "desc": "JSON-LD @graph wrapper (Dealer Inspire) — should unwrap and extract",
        "html": """<!DOCTYPE html><html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@graph": [
    {"@type": "WebSite", "name": "Rick Case Honda"},
    {
      "@type": "Car",
      "vehicleIdentificationNumber": "2HGFE2F52RH999888",
      "vehicleModelDate": "2024",
      "brand": {"name": "Honda"},
      "model": "Civic Sport",
      "bodyType": "Sedan",
      "color": "Sonic Gray Pearl",
      "vehicleInteriorColor": "Black",
      "mileageFromOdometer": {"value": "0"},
      "offers": {"price": 28495},
      "description": "Brand new 2024 Honda Civic Sport with sport styling."
    }
  ]
}
</script>
</head><body><p>Loading...</p></body></html>""",
        "expect_field": "Make",
        "expect_value_contains": "Honda",
    },

    {
        "id": "JSONLD_body_type_sport_utility",
        "desc": "'Sport Utility' in JSON-LD should normalize to 'SUV'",
        "html": """<!DOCTYPE html><html><head>
<script type="application/ld+json">
{
  "@type": "Car",
  "vehicleIdentificationNumber": "5TDKRKEC5NS123456",
  "vehicleModelDate": "2022",
  "brand": {"name": "Toyota"},
  "model": "Highlander XLE",
  "bodyType": "Sport Utility",
  "color": "Midnight Black",
  "mileageFromOdometer": {"value": "24500"},
  "offers": {"price": 42995}
}
</script>
</head><body></body></html>""",
        "expect_field": "Body Type",
        "expect_value_contains": "SUV",
    },

    # ── Page state layer tests ────────────────────────────────────────────────

    {
        "id": "PAGESTATE_next_data",
        "desc": "__NEXT_DATA__ (Dealer Inspire / Next.js) — extract from embedded JSON",
        "html": """<!DOCTYPE html><html><head></head><body>
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"inventory":[
  {"vin":"1HGBH41JXMN100001","year":"2024","make":"Honda","model":"Accord EX-L",
   "bodyStyle":"Sedan","extColor":"Lunar Silver Metallic","intColor":"Black",
   "price":33995,"mileage":8}
]}}}
</script>
</body></html>""",
        "expect_field": "VIN",
        "expect_value_contains": "1HGBH41JXMN100001",
    },

    {
        "id": "PAGESTATE_window_inventory",
        "desc": "window.inventory array (Sincro/DealerFire pattern) — extract first vehicle",
        "html": """<!DOCTYPE html><html><head></head><body>
<script>
window.inventory = [{"vin":"2T1BURHE0JC100001","year":2025,"make":"Toyota",
  "model":"Corolla LE","body_style":"Sedan","ext_color":"Midnight Black Metallic",
  "int_color":"Black","price":24995,"mileage":0}];
</script>
</body></html>""",
        "expect_field": "VIN",
        "expect_value_contains": "2T1BURHE0JC100001",
    },

    {
        "id": "PAGESTATE_body_type_normalization",
        "desc": "Page state 'Sport Utility' body style should normalize to 'SUV'",
        "html": """<!DOCTYPE html><html><head></head><body>
<script>
window.vehicleData = {"vin":"5XYZU3LB8EG100001","year":2024,"make":"Hyundai",
  "model":"Tucson SEL","bodyStyle":"Sport Utility","extColor":"Shimmering Silver",
  "price":32995,"mileage":5};
</script>
</body></html>""",
        "expect_field": "Body Type",
        "expect_value_contains": "SUV",
    },

    {
        "id": "PAGESTATE_json_script_tag",
        "desc": "<script type='application/json'> block (Dealer.com/Cox) — extract vehicle",
        "html": """<!DOCTYPE html><html><head>
<script type="application/json" id="vehicle-data">
{"vin":"WBAJB9C51JB100001","year":2023,"make":"BMW","model":"540i xDrive",
 "bodyType":"Sedan","exteriorColor":"Black Sapphire Metallic",
 "interiorColor":"Cognac","price":68995,"mileage":12400}
</script>
</head><body></body></html>""",
        "expect_field": "Exterior Color",
        "expect_value_contains": "Sapphire",
    },

    # ── Original regression tests ─────────────────────────────────────────────

    {
        "id": "1A_new_car_mileage",
        "desc": "New car with no mileage shown — should return '0' or '0 miles'",
        "html": """
<html><body>
<h1>2024 Honda Civic Sport</h1>
<div class="price">$28,495</div>
<div class="vin">2HGFE2F52RH123456</div>
<div class="body-type">Sedan</div>
<div class="color">Sonic Gray Pearl</div>
<div class="int-color">Black</div>
<div class="fuel">Gasoline</div>
</body></html>""",
        "expect_field": "Mileage",
        "expect_nonempty": True,
    },

    {
        "id": "1B_vin_in_table",
        "desc": "VIN in spec table — should extract full 17-char VIN",
        "html": """
<html><body>
<h1>2023 Ford F-150 Lariat</h1>
<table class="specs">
<tr><td>VIN:</td><td>1FTEW1EP0PKD12345</td></tr>
<tr><td>Price:</td><td>$58,995</td></tr>
<tr><td>Mileage:</td><td>8,234 miles</td></tr>
<tr><td>Body:</td><td>Truck</td></tr>
<tr><td>Ext Color:</td><td>Star White Metallic</td></tr>
</table>
</body></html>""",
        "expect_field": "VIN",
        "expect_value_contains": "1FTEW1EP0PKD12345",
    },

    {
        "id": "2A_body_type_suv",
        "desc": "Body type SUV in text — should extract as 'SUV'",
        "html": """
<html><body>
<h1>2024 Chevrolet Tahoe Premier</h1>
<div class="price">$68,495</div>
<div class="body-type">SUV</div>
<div class="vin">1GNSKCKD5RR123456</div>
<div class="mileage">15 miles</div>
<div class="color">Iridescent Pearl Tricoat</div>
</body></html>""",
        "expect_field": "Body Type",
        "expect_value_contains": "SUV",
    },

    {
        "id": "2B_exterior_color_full_name",
        "desc": "Color with full name should extract full name, not code",
        "html": """
<html><body>
<h1>2023 BMW 3 Series 330i</h1>
<div class="price">$47,295</div>
<div class="vin">3MW5R7J04P8C12345</div>
<div class="mileage">5 miles</div>
<div class="body-type">Sedan</div>
<div class="color">Portimao Blue Metallic (code: C1M)</div>
<div class="int-color">Black SensaTec</div>
</body></html>""",
        "expect_field": "Exterior Color",
        "expect_value_contains": "Portimao",
    },

    {
        "id": "list_page_first_vehicle",
        "desc": "Inventory list page — should extract first vehicle, not mix multiple",
        "html": """
<html><body>
<h1>New Inventory | Dealer</h1>
<div class="vehicle">
  <h2>2024 Ram 1500 Big Horn</h2>
  <div class="price">$46,995</div>
  <div class="vin">1C6SRFFT8RN111111</div>
  <div class="mileage">7 miles</div>
</div>
<div class="vehicle">
  <h2>2024 Ram 1500 Laramie</h2>
  <div class="price">$62,995</div>
  <div class="vin">1C6SRFFT8RN222222</div>
  <div class="mileage">9 miles</div>
</div>
</body></html>""",
        "expect_field": "VIN",
        "expect_value_contains": "1111",
    },
]


def run_tests():
    os.makedirs(DOMO_DIR, exist_ok=True)
    results = []
    passed = 0

    print(f"[unit_test] {len(TESTS)} tests | {datetime.utcnow().strftime('%H:%M UTC')}\n")

    for t in TESTS:
        try:
            result = extract(t["html"])
            scores, pct = score(result)
            field_val = result.get(t["expect_field"], "")

            if "expect_nonempty" in t:
                if t["expect_nonempty"]:
                    ok = bool(field_val and field_val.strip())
                    criterion = f"non-empty {t['expect_field']}"
                else:
                    ok = not bool(field_val and field_val.strip())
                    criterion = f"empty {t['expect_field']}"
            elif "expect_value_contains" in t:
                ok = t["expect_value_contains"].lower() in str(field_val).lower()
                criterion = f"{t['expect_field']} contains '{t['expect_value_contains']}'"
            else:
                ok = True
                criterion = "no specific check"

            status = "PASS" if ok else "FAIL"
            if ok:
                passed += 1

            icon = "✅" if ok else "❌"
            print(f"  {icon} {t['id']}: {status}")
            print(f"     {t['desc']}")
            print(f"     Check : {criterion}")
            print(f"     Got   : {t['expect_field']} = {repr(field_val[:80]) if field_val else '(empty)'}")
            print(f"     Score : {pct}%  {' '.join(f+':'+s for f,s in scores.items())}")
            print()

            results.append({
                "id": t["id"], "desc": t["desc"], "status": status,
                "field": t["expect_field"], "got": field_val, "overall_pct": pct,
            })

        except Exception as e:
            print(f"  ❌ {t['id']}: ERROR — {e}\n")
            results.append({"id": t["id"], "desc": t["desc"], "status": "ERROR",
                            "field": "", "got": str(e), "overall_pct": 0})

    print(f"{'='*55}")
    print(f"  RESULT: {passed}/{len(TESTS)} passed")
    print(f"{'='*55}\n")

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"# Unit Test Results — {now}\n\n**{passed}/{len(TESTS)} passed**\n\n"]
    for r in results:
        icon = "✅" if r["status"] == "PASS" else "❌"
        lines.append(f"## {icon} {r['id']} — {r['status']}\n")
        lines.append(f"- **Test:** {r['desc']}\n")
        lines.append(f"- **Field:** `{r['field']}`\n")
        lines.append(f"- **Got:** `{r['got'][:80] if r['got'] else '(empty)'}`\n")
        lines.append(f"- **Score:** {r['overall_pct']}%\n\n")

    report_path = os.path.join(DOMO_DIR, "unit_test_results.md")
    with open(report_path, "w") as f:
        f.writelines(lines)
    print(f"Report: {report_path}")

    return passed, len(TESTS)


if __name__ == "__main__":
    passed, total = run_tests()
    sys.exit(0 if passed == total else 1)
