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

# ──────────────── Test cases ────────────────────────────────────────────────

TESTS = [

    # Issue 1A: New car with 0 miles — Mileage should default to "0"
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
<!-- No mileage field — brand new car -->
</body></html>""",
        "expect_field": "Mileage",
        "expect_nonempty": True,
    },

    # Issue 1A: New car explicitly showing "0 miles"
    {
        "id": "1A_explicit_zero_miles",
        "desc": "New car showing '0 miles' — should extract as-is",
        "html": """
<html><body>
<h1>2024 Toyota Camry XSE V6</h1>
<div class="price">$35,720</div>
<div class="mileage">0 miles</div>
<div class="vin">4T1K61AK5RU123456</div>
<div class="body-type">Sedan</div>
<div class="color">Midnight Black</div>
</body></html>""",
        "expect_field": "Mileage",
        "expect_value_contains": "0",
    },

    # Issue 1B: VIN extraction from multiple formats
    {
        "id": "1B_vin_in_table",
        "desc": "VIN in spec table — should extract full 17-char VIN",
        "html": """
<html><body>
<h1>2023 Ford F-150 Lariat</h1>
<table class="specs">
<tr><td>VIN:</td><td>1FTEW1EP0PKD12345</td></tr>
<tr><td>Stock:</td><td>F23456</td></tr>
<tr><td>Price:</td><td>$58,995</td></tr>
<tr><td>Mileage:</td><td>8,234 miles</td></tr>
<tr><td>Body:</td><td>Truck</td></tr>
<tr><td>Ext Color:</td><td>Star White Metallic</td></tr>
</table>
</body></html>""",
        "expect_field": "VIN",
        "expect_value_contains": "1FTEW1EP0PKD12345",
    },

    # Issue 2A: Body Type extraction
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

    # Issue 2B: Exterior Color with full name
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

    # Issue 2B: Color abbreviation only — should leave empty
    {
        "id": "2B_color_abbrev_only",
        "desc": "Color code only (no full name) — should leave Exterior Color empty",
        "html": """
<html><body>
<h1>2023 Mercedes GLC 300</h1>
<div class="price">$55,495</div>
<div class="vin">W1N0G8EB0PF123456</div>
<div class="mileage">3 miles</div>
<div class="body-type">SUV</div>
<div class="color">Ack</div>
</body></html>""",
        "expect_field": "Exterior Color",
        "expect_nonempty": False,  # should be empty (just a code)
    },

    # List page: extract FIRST vehicle only
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
<div class="vehicle">
  <h2>2023 Jeep Wrangler</h2>
  <div class="price">$41,995</div>
  <div class="vin">1C4HJXFN8PW333333</div>
</div>
</body></html>""",
        "expect_field": "VIN",
        "expect_value_contains": "1111",  # should be first vehicle's VIN
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

            # Evaluate pass/fail
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

            print(f"  {'✅' if ok else '❌'} {t['id']}: {status}")
            print(f"     {t['desc']}")
            print(f"     Check: {criterion}")
            print(f"     Got: {t['expect_field']} = {repr(field_val[:80]) if field_val else '(empty)'}")
            print(f"     Overall: {pct}% ({' '.join(f+':'+s for f,s in scores.items())})")
            print()

            results.append({
                "id": t["id"],
                "desc": t["desc"],
                "status": status,
                "field": t["expect_field"],
                "got": field_val,
                "overall_pct": pct,
            })

        except Exception as e:
            print(f"  ❌ {t['id']}: ERROR — {e}\n")
            results.append({"id": t["id"], "desc": t["desc"], "status": "ERROR", "field": "", "got": str(e), "overall_pct": 0})

    print(f"{'='*55}")
    print(f"  RESULT: {passed}/{len(TESTS)} passed")
    print(f"{'='*55}\n")

    # Write markdown report
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"# Unit Test Results — {now}\n", f"**{passed}/{len(TESTS)} passed**\n\n"]
    for r in results:
        icon = "✅" if r["status"] == "PASS" else "❌"
        lines.append(f"## {icon} {r['id']} — {r['status']}\n")
        lines.append(f"- **Test:** {r['desc']}\n")
        lines.append(f"- **Field:** `{r['field']}`\n")
        lines.append(f"- **Got:** `{r['got'][:80] if r['got'] else '(empty)'}`\n")
        lines.append(f"- **Overall score:** {r['overall_pct']}%\n\n")

    report_path = os.path.join(DOMO_DIR, "unit_test_results.md")
    with open(report_path, "w") as f:
        f.writelines(lines)
    print(f"Report: {report_path}")

    return passed, len(TESTS)


if __name__ == "__main__":
    passed, total = run_tests()
    sys.exit(0 if passed == total else 1)
