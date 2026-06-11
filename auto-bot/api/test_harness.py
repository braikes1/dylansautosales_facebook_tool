"""
AutoBot Test Harness
====================
Calls the backend /fb/scrape_url endpoint for each dealer and scores
field extraction quality. Runs as a Render cron job nightly.
Outputs results to a CSV report.

NOTE: This harness uses backend scraping (not tab scraping) to avoid
Chrome throttling / "Frame with ID 0 is showing error page" false failures.
"""

import csv
import os
import time
import requests
from datetime import datetime

API_BASE = os.environ.get("API_BASE", "https://dylansautosales-facebook-tool.onrender.com")
REPORT_PATH = os.environ.get("REPORT_PATH", "/tmp/autobot_test_report.csv")
REQUEST_TIMEOUT = 45   # seconds per dealer (per task brief)
DELAY_BETWEEN = 2      # seconds between dealer requests (per task brief)

# ── Florida-Focused 35 Dealer List (South Florida + Florida franchise) ────────
# Domain corrections applied vs original list:
#   bramanbmw.com       -> bramanbmwwpb.com + bramanbmwjupiter.com (split into 2 real stores)
#   bramanmercedes.com  -> REMOVED (DNS dead, no live domain found)
#   bramanbentley.com   -> bentleynaples.com (confirmed live)
#   infinitiofnaples.com -> naplesinfiniti.com (confirmed live, VDP available)
#   porscheofnaples.com -> porschenaples.com (404 -> real domain)
#   rickcasehyundai.com -> rickcase.com/hyundai (old domain redirects)
#   rickcasevw.com      -> rickcasevolkswagen.com (confirmed redirect)
#   rickcasealfaromeo.com -> alfaromeousaofdavie.com (confirmed redirect)
# VDP URLs used where confirmed (better scoring than SRP index pages):
#   Lexus of Orlando, Toyota of Orlando, Naples Infiniti, Bentley Naples
DEALER_URLS = [
    # ── CORAL SPRINGS AREA ──────────────────────────────────────────
    "https://www.coralspringsautomall.com/new-inventory/index.htm",

    # ── RICK CASE AUTOMOTIVE GROUP ───────────────────────────────────
    "https://www.rickcasehonda.com/new-inventory/index.htm",
    "https://www.rickcaseacura.com/new-inventory/index.htm",
    "https://www.rickcasemazda.com/new-inventory/index.htm",
    # CORRECTED: rickcasehyundai.com -> rickcase.com/hyundai
    "https://www.rickcase.com/hyundai/new-inventory/index.htm",
    # CORRECTED: rickcasevw.com -> rickcasevolkswagen.com
    "https://www.rickcasevolkswagen.com/new-inventory/index.htm",
    # CORRECTED: rickcasealfaromeo.com -> alfaromeousaofdavie.com
    "https://www.alfaromeousaofdavie.com/new-inventory/index.htm",
    "https://www.rickcasemitsubishi.com/new-inventory/index.htm",

    # ── BROWARD / PALM BEACH ─────────────────────────────────────────
    "https://www.toyotaofcoconutcreek.com/new-inventory/index.htm",
    # CORRECTED: bramanbmw.com split into two real stores
    "https://www.bramanbmwwpb.com/new-inventory/index.htm",
    "https://www.bramanbmwjupiter.com/new-inventory/index.htm",
    "https://www.bramanmiamibmw.com/new-inventory/index.htm",
    # NOTE: bramanmercedes.com REMOVED — DNS dead, no live domain found
    "https://www.bramanporsche.com/new-inventory/index.htm",
    # CORRECTED: bramanbentley.com -> bentleynaples.com (VDP confirmed)
    "https://www.bentleynaples.com/used-Naples-2022-Bentley-Continental+GTC-Speed+Naples+Dragonfly+Collection-SCBDT4ZG6NC093132",
    "https://www.bramanhondapalmbeach.com/new-inventory/index.htm",

    # ── PHIL SMITH AUTOMOTIVE GROUP ──────────────────────────────────
    "https://www.philsmithkia.com/new-inventory/index.htm",
    "https://www.philsmithford.com/new-inventory/index.htm",
    "https://www.philsmithtoyota.com/new-inventory/index.htm",
    "https://www.philsmithnissan.com/new-inventory/index.htm",

    # ── OTHER SOUTH FLORIDA ──────────────────────────────────────────
    "https://www.holmanhonda.com/new-inventory/index.htm",
    "https://www.keatinghonda.com/new-inventory/index.htm",

    # ── TAMPA / CENTRAL FLORIDA ──────────────────────────────────────
    "https://www.mboftampa.com/new-inventory/index.htm",

    # ── NAPLES / SOUTHWEST FLORIDA ───────────────────────────────────
    "https://www.audinaples.com/new-inventory/index.htm",
    "https://www.mazdaofnaples.com/new-inventory/index.htm",
    # CORRECTED: porscheofnaples.com (404) -> porschenaples.com
    "https://www.porschenaples.com/new-inventory/index.htm",
    # CORRECTED: infinitiofnaples.com -> naplesinfiniti.com (VDP confirmed)
    "https://www.naplesinfiniti.com/used-Naples-2023-Jeep-Grand+Cherokee-Altitude-1C4RJGAG6PC551745",

    # ── BROWARD ──────────────────────────────────────────────────────
    "https://www.audibroward.com/new-inventory/index.htm",

    # ── ORLANDO AREA ─────────────────────────────────────────────────
    # VDP confirmed: 2019 Porsche Cayenne WP1AA2AY1KDA08006
    "https://lexusoforlando.com/inventory/Used-2019-Porsche-Cayenne-Base-WP1AA2AY1KDA08006",
    # VDP confirmed: 2026 Toyota Tacoma 3TYLC5LN9TT073236
    "https://www.toyotaoforlando.com/new-Orlando-2026-Toyota-Tacoma+i+FORCE+MAX-TRD+Pro-3TYLC5LN9TT073236",
    "https://www.kiaoforlando.com/new-inventory/index.htm",
    "https://www.hyundaioforlando.com/new-inventory/index.htm",
    "https://www.vwoforlando.com/new-inventory/index.htm",
    "https://www.genesisoforlando.com/new-inventory/index.htm",

    # ── CHRYSLER / DODGE / JEEP / RAM ────────────────────────────────
    # CANARY — must always pass
    "https://www.tavernachryslerdodgejeepramfiat.com/new-inventory/index.htm",

    # ── HENDRICK ─────────────────────────────────────────────────────
    "https://www.hendrickhonda.com/new-inventory/index.htm",
]

assert len(DEALER_URLS) == 35, f"Expected 35 dealer URLs, got {len(DEALER_URLS)}"

SCORED_FIELDS = [
    "Year", "Make", "Model", "Price",
    "VIN", "Body Type", "Exterior Color",
    "Interior Color", "Mileage", "Description",
]


def call_scrape_url(url: str) -> tuple[str, int, dict, str]:
    """
    POST to /fb/scrape_url and return (status, score_pct, field_scores, error).

    status   : "OK" | "FAILED"
    score_pct: 0-100
    field_scores: dict of field -> "✓" or "✗"
    error    : "" on success, error description on failure
    """
    try:
        resp = requests.post(
            f"{API_BASE}/fb/scrape_url",
            json={"url": url},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.exceptions.Timeout:
        return "FAILED", 0, {f: "✗" for f in SCORED_FIELDS}, "timeout"
    except Exception as e:
        return "FAILED", 0, {f: "✗" for f in SCORED_FIELDS}, str(e)

    if resp.status_code != 200:
        return "FAILED", 0, {f: "✗" for f in SCORED_FIELDS}, f"HTTP {resp.status_code}"

    try:
        data = resp.json()
    except Exception:
        return "OK", 0, {f: "✗" for f in SCORED_FIELDS}, "empty_response"

    if not data:
        return "OK", 0, {f: "✗" for f in SCORED_FIELDS}, "empty_response"

    # Score the fields
    field_scores = {}
    total = 0
    for field in SCORED_FIELDS:
        val = data.get(field, "")
        populated = bool(val and str(val).strip())
        field_scores[field] = "✓" if populated else "✗"
        if populated:
            total += 1

    score_pct = round((total / len(SCORED_FIELDS)) * 100)
    return "OK", score_pct, field_scores, ""


def run():
    # Local report path: if running locally (Windows/WSL), save to Desktop DOMO folder
    local_path = r"C:\Users\NOBRAIKES\Desktop\DOMO"
    if os.path.isdir("/mnt/c/Users/NOBRAIKES/Desktop/DOMO"):
        report_path = "/mnt/c/Users/NOBRAIKES/Desktop/DOMO/autobot_test_report.csv"
    elif os.path.isdir(local_path):
        report_path = os.path.join(local_path, "autobot_test_report.csv")
    else:
        report_path = REPORT_PATH  # fallback to /tmp on Render

    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    print(f"[harness] Starting test run -- {len(DEALER_URLS)} dealers -- {ts}")
    print(f"[harness] API: {API_BASE}")
    print(f"[harness] Report will be saved to: {report_path}")

    rows = []
    for i, url in enumerate(DEALER_URLS):
        print(f"[harness] {i+1}/{len(DEALER_URLS)} -- {url}")

        status, score_pct, field_scores, error = call_scrape_url(url)

        row = {
            "url": url,
            "status": status,
            "score_pct": score_pct,
            **field_scores,
            "error": error,
        }
        rows.append(row)

        if status == "OK":
            ascii_scores = {k: ("OK" if v == "✓" else "--") for k, v in field_scores.items()}
            print(f"[harness]   Score: {score_pct}% -- {ascii_scores}")
        else:
            print(f"[harness]   FAILED -- {error}")

        time.sleep(DELAY_BETWEEN)

    # Write CSV (same core columns as before for backward compatibility)
    fieldnames = ["url", "status", "score_pct"] + SCORED_FIELDS + ["error"]
    with open(report_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    # Summary stats
    ok_rows     = [r for r in rows if r["status"] == "OK"]
    failed_rows = [r for r in rows if r["status"] != "OK"]
    avg_score   = round(sum(r["score_pct"] for r in ok_rows) / len(ok_rows)) if ok_rows else 0
    above_80    = [r for r in ok_rows if r["score_pct"] >= 80]
    below_50    = [r for r in ok_rows if r["score_pct"] < 50]
    perfect     = [r for r in ok_rows if r["score_pct"] == 100]

    print("\n" + "=" * 60)
    print(f"[harness] COMPLETE — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"[harness] Total dealers tested     : {len(DEALER_URLS)}")
    print(f"[harness] OK (HTTP 200)             : {len(ok_rows)}")
    print(f"[harness] FAILED                   : {len(failed_rows)}")
    print(f"[harness] Average score (OK only)  : {avg_score}%")
    print(f"[harness] Above 80%                : {len(above_80)}")
    print(f"[harness] Below 50%                : {len(below_50)}")
    print(f"[harness] Perfect (100%)           : {len(perfect)}")
    print(f"[harness] Report saved to          : {report_path}")
    print("=" * 60)


if __name__ == "__main__":
    run()
