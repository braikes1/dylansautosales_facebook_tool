"""
Lightweight autonomous test runner — only tests dealers that respond to server-side requests.
Uses the live Render API for extraction.

Usage:
    python3.11 run_available_test.py --label baseline
"""
import csv, os, sys, time, json, argparse
import requests, urllib3
from datetime import datetime
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_BASE        = os.environ.get("API_BASE", "https://dylansautosales-facebook-tool.onrender.com")
DOMO_DIR        = "/mnt/c/Users/NOBRAIKES/Desktop/DOMO"
REQUEST_TIMEOUT = 45
DELAY_BETWEEN   = 3

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Dealers confirmed to respond to server-side requests (no Cloudflare block)
TESTABLE_DEALERS = [
    # Canary — must stay 100%
    ("taverna",   "https://www.tavernachryslerdodgejeepramfiat.com/new-inventory/index.htm"),
    # National reference
    ("subaru",    "https://www.subaruofwakefield.com/new-inventory/index.htm"),
    ("hendrick",  "https://www.hendrickcars.com/new-inventory/index.htm"),
]

SCORED_FIELDS = [
    "Year", "Make", "Model", "Price",
    "VIN", "Body Type", "Exterior Color",
    "Interior Color", "Mileage", "Description",
]


def fetch_html(url):
    r = requests.get(url, headers={"User-Agent": UA}, timeout=REQUEST_TIMEOUT, verify=False)
    r.raise_for_status()
    return r.text


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
    resp = requests.post(
        f"{API_BASE}/fb/extract_html",
        json={"url": url, "html": html, "images": images},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def score(result):
    scores, total = {}, 0
    for f in SCORED_FIELDS:
        val = result.get(f, "")
        ok = bool(val and str(val).strip())
        scores[f] = "✓" if ok else "✗"
        if ok:
            total += 1
    return scores, round(total / len(SCORED_FIELDS) * 100)


def run(label=""):
    os.makedirs(DOMO_DIR, exist_ok=True)
    ts       = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"batch_test_{ts}{('_' + label) if label else ''}.csv"
    filepath = os.path.join(DOMO_DIR, filename)

    print(f"[runner] {len(TESTABLE_DEALERS)} testable dealers | {API_BASE}")

    rows = []
    for name, url in TESTABLE_DEALERS:
        print(f"\n  [{name}] {url}")
        try:
            html   = fetch_html(url)
            images = fetch_images(html)
            result = call_api(url, html, images)
            scores, pct = score(result)
            status = "OK"
        except Exception as e:
            print(f"    ERROR: {e}")
            scores = {f: "✗" for f in SCORED_FIELDS}
            pct    = 0
            status = "FAILED"
            result = {}

        row = {"dealer": name, "url": url, "status": status, "score_pct": pct}
        row.update(scores)
        row["raw_fields"] = json.dumps({f: result.get(f, "") for f in SCORED_FIELDS}) if result else ""
        rows.append(row)

        checks = " ".join(f"{f[:3]}:{scores[f]}" for f in SCORED_FIELDS)
        print(f"    → {pct}%  |  {checks}")
        if result.get("Mileage"):
            print(f"    Mileage raw: {result['Mileage']!r}")
        if result.get("VIN"):
            print(f"    VIN raw:     {result['VIN']!r}")
        time.sleep(DELAY_BETWEEN)

    # Write CSV
    fieldnames = ["dealer", "url", "status", "score_pct"] + SCORED_FIELDS + ["raw_fields"]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    ok_rows = [r for r in rows if r["status"] == "OK"]
    avg     = round(sum(r["score_pct"] for r in ok_rows) / len(ok_rows)) if ok_rows else 0
    canary  = next((r for r in rows if r["dealer"] == "taverna"), None)
    canary_ok = canary and canary["score_pct"] == 100

    field_totals = {f: sum(1 for r in rows if r.get(f) == "✓") for f in SCORED_FIELDS}

    print("\n" + "=" * 55)
    print(f"  DONE  {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Avg score  : {avg}%")
    print(f"  Canary     : {'✅ 100%' if canary_ok else '🔴 REGRESSION!'}")
    print(f"\n  Field coverage ({len(rows)} dealers):")
    for f, cnt in field_totals.items():
        bar = "█" * cnt + "░" * (len(rows) - cnt)
        print(f"    {f:<16} {cnt}/{len(rows)}  {bar}")
    print(f"\n  CSV: {filepath}")
    print("=" * 55)

    return {
        "filepath": filepath, "avg_pct": avg, "canary_ok": canary_ok,
        "field_totals": field_totals, "rows": rows,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--label", default="")
    args = p.parse_args()
    r = run(label=args.label)
    sys.exit(0 if r["canary_ok"] else 1)
