"""
SFL batch test runner — scores only South Florida priority dealers.
Usage:
    python run_sfl_test.py [--label LABEL]
Outputs CSV to: C:/Users/NOBRAIKES/Desktop/DOMO/batch_test_<timestamp>.csv
"""

import csv, os, sys, time, json, re, argparse
import requests
import urllib3
from datetime import datetime
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_BASE        = os.environ.get("API_BASE", "https://dylansautosales-facebook-tool.onrender.com")
DOMO_DIR        = "/mnt/c/Users/NOBRAIKES/Desktop/DOMO"
REQUEST_TIMEOUT = 45
DELAY_BETWEEN   = 4  # seconds

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Priority SFL dealers + canary
SFL_DEALERS = [
    # Canary — must stay 100%
    "https://www.tavernachryslerdodgejeepramfiat.com/new-inventory/index.htm",

    # Rick Case Group
    "https://www.rickcasehonda.com/new-inventory/index.htm",
    "https://www.rickcasehyundai.com/new-inventory/index.htm",
    "https://www.rickcaseacura.com/new-inventory/index.htm",
    "https://www.rickcasevw.com/new-inventory/index.htm",
    "https://www.rickcasemazda.com/new-inventory/index.htm",
    "https://www.rickcasemitsubishi.com/new-inventory/index.htm",

    # Phil Smith Group
    "https://www.philsmithford.com/new-inventory/index.htm",
    "https://www.philsmithtoyota.com/new-inventory/index.htm",
    "https://www.philsmithnissan.com/new-inventory/index.htm",
    "https://www.philsmithkia.com/new-inventory/index.htm",

    # Other SFL
    "https://www.coralspringsautomall.com/new-inventory/index.htm",
    "https://www.toyotaofcoconutcreek.com/new-inventory/index.htm",
    "https://www.holmanhonda.com/new-inventory/index.htm",

    # Braman Group
    "https://www.bramanbmw.com/new-inventory/index.htm",
    "https://www.bramanmiamibmw.com/new-inventory/index.htm",
    "https://www.bramanmercedes.com/new-inventory/index.htm",
    "https://www.bramanporsche.com/new-inventory/index.htm",
    "https://www.bramanhondapalmbeach.com/new-inventory/index.htm",

    # National reference
    "https://www.keatinghonda.com/new-inventory/index.htm",
    "https://www.subaruofwakefield.com/new-inventory/index.htm",
]

SCORED_FIELDS = [
    "Year", "Make", "Model", "Price",
    "VIN", "Body Type", "Exterior Color",
    "Interior Color", "Mileage", "Description",
]


def fetch_html(url):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=REQUEST_TIMEOUT, verify=False)
        r.raise_for_status()
        return r.text
    except Exception as e:
        return None


def fetch_images(html):
    soup = BeautifulSoup(html, "html.parser")
    imgs = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if src:
            imgs.append({"src": src, "alt": img.get("alt") or "", "width": 0, "height": 0})
        if len(imgs) >= 60:
            break
    return imgs


def call_api(url, html, images):
    try:
        resp = requests.post(
            f"{API_BASE}/fb/extract_html",
            json={"url": url, "html": html, "images": images},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  [api] ERROR: {e}")
        return None


def score_result(result):
    scores = {}
    total = 0
    for field in SCORED_FIELDS:
        val = result.get(field, "")
        populated = bool(val and str(val).strip())
        scores[field] = "✓" if populated else "✗"
        if populated:
            total += 1
    return {"scores": scores, "total": total, "pct": round((total / len(SCORED_FIELDS)) * 100)}


def run(label=""):
    os.makedirs(DOMO_DIR, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
    filename  = f"batch_test_{timestamp}{('_' + label) if label else ''}.csv"
    filepath  = os.path.join(DOMO_DIR, filename)

    print(f"[runner] Testing {len(SFL_DEALERS)} dealers | API: {API_BASE}")
    print(f"[runner] Output: {filepath}\n")

    rows = []
    for i, url in enumerate(SFL_DEALERS):
        short = url.split("//")[1].split("/")[0]
        print(f"[{i+1:02d}/{len(SFL_DEALERS)}] {short}")

        html = fetch_html(url)
        if not html:
            print("  → FETCH_FAILED")
            rows.append({"url": url, "status": "FETCH_FAILED", "score_pct": 0,
                         **{f: "✗" for f in SCORED_FIELDS}})
            time.sleep(DELAY_BETWEEN)
            continue

        images = fetch_images(html)
        result = call_api(url, html, images)
        if not result:
            print("  → API_FAILED")
            rows.append({"url": url, "status": "API_FAILED", "score_pct": 0,
                         **{f: "✗" for f in SCORED_FIELDS}})
            time.sleep(DELAY_BETWEEN)
            continue

        scored = score_result(result)
        row    = {"url": url, "status": "OK", "score_pct": scored["pct"]}
        for f in SCORED_FIELDS:
            row[f] = scored["scores"][f]
        row["raw_fields"] = json.dumps({f: result.get(f, "") for f in SCORED_FIELDS})

        rows.append(row)
        checks = " ".join(f"{f[:3]}:{scored['scores'][f]}" for f in SCORED_FIELDS)
        print(f"  → {scored['pct']}%  |  {checks}")
        time.sleep(DELAY_BETWEEN)

    # ── Write CSV ─────────────────────────────────────────────────────────────
    fieldnames = ["url", "status", "score_pct"] + SCORED_FIELDS + ["raw_fields"]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # ── Summary ───────────────────────────────────────────────────────────────
    ok_rows = [r for r in rows if r["status"] == "OK"]
    avg     = round(sum(r["score_pct"] for r in ok_rows) / len(ok_rows)) if ok_rows else 0
    failed  = len([r for r in rows if r["status"] != "OK"])
    p100    = len([r for r in ok_rows if r["score_pct"] == 100])

    # Canary check
    canary = next((r for r in rows if "taverna" in r["url"]), None)
    canary_ok = canary and canary["score_pct"] == 100

    # Per-field totals
    field_totals = {f: sum(1 for r in rows if r.get(f) == "✓") for f in SCORED_FIELDS}

    print("\n" + "="*55)
    print(f"  DONE  {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Dealers tested : {len(SFL_DEALERS)}")
    print(f"  Fetch/API fail : {failed}")
    print(f"  Average score  : {avg}%")
    print(f"  Perfect (100%) : {p100}/{len(ok_rows)}")
    print(f"  Canary Taverna : {'✅ 100%' if canary_ok else '🔴 REGRESSION!'}")
    print(f"\n  Field coverage:")
    for f, cnt in field_totals.items():
        bar = "█" * cnt + "░" * (len(SFL_DEALERS) - cnt)
        print(f"    {f:<16} {cnt:>2}/{len(SFL_DEALERS)}  {bar}")
    print(f"\n  CSV: {filepath}")
    print("="*55)

    # Return machine-readable summary dict for caller
    return {
        "filepath": filepath,
        "avg_pct": avg,
        "failed": failed,
        "canary_ok": canary_ok,
        "field_totals": field_totals,
        "rows": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="")
    args = parser.parse_args()
    result = run(label=args.label)
    # Exit 1 if canary regressed
    sys.exit(0 if result["canary_ok"] else 1)
