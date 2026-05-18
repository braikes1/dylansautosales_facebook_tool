"""
Autonomous test runner — delegates HTML fetching to the Render backend (/fb/scrape_url)
so Cloudflare-blocked dealers are tested from Render's IP, not WSL.

Usage:
    python3.11 run_auto_test.py --label baseline
    python3.11 run_auto_test.py --label after_fix_1a
"""
import csv, os, sys, time, json, argparse
import requests, urllib3
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_BASE        = os.environ.get("API_BASE", "https://dylansautosales-facebook-tool.onrender.com")
DOMO_DIR        = "/mnt/c/Users/NOBRAIKES/Desktop/DOMO"
REQUEST_TIMEOUT = 60
DELAY_BETWEEN   = 5  # seconds between dealers (avoid hammering Render + GPT rate limits)

# Priority SFL dealers + canary + national references
DEALERS = [
    # Canary — must stay 100%
    ("taverna",        "https://www.tavernachryslerdodgejeepramfiat.com/new-inventory/index.htm"),
    # Rick Case Group
    ("rc_honda",       "https://www.rickcasehonda.com/new-inventory/index.htm"),
    ("rc_hyundai",     "https://www.rickcasehyundai.com/new-inventory/index.htm"),
    ("rc_acura",       "https://www.rickcaseacura.com/new-inventory/index.htm"),
    ("rc_vw",          "https://www.rickcasevw.com/new-inventory/index.htm"),
    ("rc_mazda",       "https://www.rickcasemazda.com/new-inventory/index.htm"),
    ("rc_mitsubishi",  "https://www.rickcasemitsubishi.com/new-inventory/index.htm"),
    # Phil Smith Group
    ("ps_ford",        "https://www.philsmithford.com/new-inventory/index.htm"),
    ("ps_toyota",      "https://www.philsmithtoyota.com/new-inventory/index.htm"),
    ("ps_nissan",      "https://www.philsmithnissan.com/new-inventory/index.htm"),
    ("ps_kia",         "https://www.philsmithkia.com/new-inventory/index.htm"),
    # Other SFL
    ("coral_springs",  "https://www.coralspringsautomall.com/new-inventory/index.htm"),
    ("toyota_coconut", "https://www.toyotaofcoconutcreek.com/new-inventory/index.htm"),
    ("holman_honda",   "https://www.holmanhonda.com/new-inventory/index.htm"),
    # Braman Group
    ("braman_bmw",     "https://www.bramanbmw.com/new-inventory/index.htm"),
    ("braman_mb",      "https://www.bramanmercedes.com/new-inventory/index.htm"),
    ("braman_honda",   "https://www.bramanhondapalmbeach.com/new-inventory/index.htm"),
    # National reference
    ("subaru",         "https://www.subaruofwakefield.com/new-inventory/index.htm"),
    ("keating_honda",  "https://www.keatinghonda.com/new-inventory/index.htm"),
    ("hendrick",       "https://www.hendrickcars.com/new-inventory/index.htm"),
]

SCORED_FIELDS = [
    "Year", "Make", "Model", "Price",
    "VIN", "Body Type", "Exterior Color",
    "Interior Color", "Mileage", "Description",
]


def scrape_and_extract(url):
    """Ask Render to fetch + extract in one shot (avoids Cloudflare on WSL)."""
    resp = requests.post(
        f"{API_BASE}/fb/scrape_url",
        json={"url": url},
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

    print(f"[runner] {len(DEALERS)} dealers | via {API_BASE}/fb/scrape_url")

    rows = []
    for idx, (name, url) in enumerate(DEALERS):
        print(f"\n  [{idx+1:02d}/{len(DEALERS)}] {name}")
        try:
            result = scrape_and_extract(url)
            if result.get("error"):
                raise RuntimeError(result["error"])
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
        print(f"    → {pct}%  {checks}")
        for key in ("Mileage", "VIN", "Body Type", "Exterior Color"):
            if result.get(key):
                print(f"    {key}: {result[key]!r}")
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

    print("\n" + "=" * 60)
    print(f"  DONE   {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Label  : {label or '(none)'}")
    print(f"  Avg    : {avg}%  |  OK: {len(ok_rows)}/{len(rows)}  |  Canary: {'✅' if canary_ok else '🔴 REGRESSION!'}")
    print(f"\n  Field coverage ({len(rows)} dealers):")
    for f, cnt in field_totals.items():
        bar = "█" * cnt + "░" * (len(rows) - cnt)
        print(f"    {f:<16} {cnt:>2}/{len(rows)}  {bar}")
    print(f"\n  CSV: {filepath}")
    print("=" * 60)

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
