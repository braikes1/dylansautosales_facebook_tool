"""
AutoBot Test Harness
====================
Scrapes real dealer inventory pages and scores field extraction quality.
Runs as a Render cron job. Outputs results to a CSV report.
"""

import csv
import json
import os
import time
import requests
from datetime import datetime
from bs4 import BeautifulSoup

API_BASE = os.environ.get("API_BASE", "https://dylansautosales-facebook-tool.onrender.com")
REPORT_PATH = "/tmp/autobot_test_report.csv"
REQUEST_TIMEOUT = 30
DELAY_BETWEEN = 3  # seconds between requests to avoid rate limiting

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)

# ── US Franchise Dealer Inventory Pages ──────────────────────────────
# Covers major dealer platforms: CDK, DealerSocket, VinSolutions,
# DealerInspire, Dealer.com, eDealer, Cars Commerce
DEALER_URLS = [
    # BMW
    "https://www.bmwofnaples.com/new-inventory/index.htm",
    "https://www.bmwofmobile.com/new-inventory/index.htm",
    "https://www.ultimatebmw.com/new-vehicles/",
    # Mercedes-Benz
    "https://www.mboftampa.com/new-inventory/index.htm",
    "https://www.mercedesbenzofmiami.com/new-inventory/index.htm",
    "https://www.mbofbeverlyhills.com/new-vehicles/",
    # Honda
    "https://www.autonationhondabrowardblvd.com/new-inventory/index.htm",
    "https://www.keatinghonda.com/new-inventory/index.htm",
    "https://www.hendrickhondaconcord.com/new-inventory/",
    # Toyota
    "https://www.toyotaoforlando.com/new-inventory/index.htm",
    "https://www.hendricktoyota.com/new-inventory/",
    "https://www.lextontoyota.com/new-vehicles/",
    # Ford
    "https://www.autonationfordsouthbroward.com/new-inventory/index.htm",
    "https://www.hendrickford.com/new-inventory/",
    "https://www.vatlandford.com/new-inventory/index.htm",
    # Chevrolet
    "https://www.autonationchevroletsouthbroward.com/new-inventory/index.htm",
    "https://www.hendrickchevy.com/new-inventory/",
    "https://www.peacockchevrolet.com/new-inventory/index.htm",
    # Nissan
    "https://www.autonation nissan.com/new-inventory/index.htm",
    "https://www.hendricknissan.com/new-inventory/",
    "https://www.nissan ofmobile.com/new-inventory/index.htm",
    # Cadillac
    "https://www.hendrickcadillac.com/new-inventory/",
    "https://www.peacockcadillac.com/new-inventory/index.htm",
    # Audi
    "https://www.audinaples.com/new-inventory/index.htm",
    "https://www.audibroward.com/new-inventory/index.htm",
    "https://www.audimiami.com/new-vehicles/",
    # Porsche
    "https://www.porscheofnaples.com/new-inventory/index.htm",
    "https://www.porschebroward.com/new-inventory/index.htm",
    # Jeep / Chrysler / Dodge / Ram (CDJR)
    "https://www.tavernacdjrf.com/new-inventory/index.htm",
    "https://www.hendrickcdjr.com/new-inventory/",
    "https://www.peacockcdjr.com/new-inventory/index.htm",
    # Acura
    "https://www.hendrickacura.com/new-inventory/",
    "https://www.acuraofbroward.com/new-inventory/index.htm",
    # Lexus
    "https://www.hendricklexus.com/new-inventory/",
    "https://www.lexusofnaples.com/new-inventory/index.htm",
    # Hyundai
    "https://www.hendrickhyundai.com/new-inventory/",
    "https://www.autonationhyundai.com/new-inventory/index.htm",
    # Kia
    "https://www.hendrickkia.com/new-inventory/",
    "https://www.kiaofstuart.com/new-inventory/index.htm",
    # Volvo
    "https://www.volvocarsbroward.com/new-inventory/index.htm",
    "https://www.volvocarsnaples.com/new-inventory/index.htm",
    # Genesis
    "https://www.genesisofbroward.com/new-inventory/index.htm",
    # Infiniti
    "https://www.infinitiofbroward.com/new-inventory/index.htm",
    # Land Rover
    "https://www.landroverofsarasota.com/new-inventory/index.htm",
    "https://www.jaguarlandroverorlando.com/new-inventory/index.htm",
    # Tesla (direct)
    "https://www.tesla.com/inventory/new/ms",
    # Subaru
    "https://www.hendricksubaru.com/new-inventory/",
    "https://www.subaruofweston.com/new-inventory/index.htm",
    # Mazda
    "https://www.mazdaofnaples.com/new-inventory/index.htm",
    "https://www.hendrickmazda.com/new-inventory/",
    # Volkswagen
    "https://www.vwbroward.com/new-inventory/index.htm",
    "https://www.hendrickvw.com/new-inventory/",
    # Buick / GMC
    "https://www.hendrickbuickgmc.com/new-inventory/",
    "https://www.peacockbuickgmc.com/new-inventory/index.htm",
    # Lincoln
    "https://www.hendricklincoln.com/new-inventory/",
    # Ram
    "https://www.hendrickram.com/new-inventory/",
    # Alfa Romeo
    "https://www.alfaromeobroward.com/new-inventory/index.htm",
    # Maserati
    "https://www.maseratiofnaples.com/new-inventory/index.htm",
    # Mitsubishi
    "https://www.mitsubishiofweston.com/new-inventory/index.htm",
]

SCORED_FIELDS = [
    "Year", "Make", "Model", "Price",
    "VIN", "Body Type", "Exterior Color",
    "Interior Color", "Mileage", "Description",
]


def fetch_html(url: str) -> str | None:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"[fetch] FAILED {url}: {e}")
        return None


def fetch_images(html: str) -> list:
    soup = BeautifulSoup(html, "html.parser")
    imgs = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if src:
            imgs.append({
                "src": src,
                "alt": img.get("alt") or "",
                "width": 0,
                "height": 0,
            })
        if len(imgs) >= 60:
            break
    return imgs


def call_api(url: str, html: str, images: list) -> dict | None:
    try:
        resp = requests.post(
            f"{API_BASE}/fb/extract_html",
            json={"url": url, "html": html, "images": images},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[api] FAILED {url}: {e}")
        return None


def score_result(result: dict) -> dict:
    scores = {}
    total = 0
    for field in SCORED_FIELDS:
        val = result.get(field, "")
        populated = bool(val and str(val).strip())
        scores[field] = "✓" if populated else "✗"
        if populated:
            total += 1
    score_pct = round((total / len(SCORED_FIELDS)) * 100)
    return {"scores": scores, "total": total, "pct": score_pct}


def run():
    print(f"[harness] Starting test run — {len(DEALER_URLS)} dealers")
    print(f"[harness] API: {API_BASE}")

    rows = []
    for i, url in enumerate(DEALER_URLS):
        print(f"[harness] {i+1}/{len(DEALER_URLS)} — {url}")

        html = fetch_html(url)
        if not html:
            rows.append({
                "url": url,
                "status": "FETCH_FAILED",
                "score_pct": 0,
                **{f: "✗" for f in SCORED_FIELDS},
            })
            time.sleep(DELAY_BETWEEN)
            continue

        images = fetch_images(html)
        result = call_api(url, html, images)

        if not result:
            rows.append({
                "url": url,
                "status": "API_FAILED",
                "score_pct": 0,
                **{f: "✗" for f in SCORED_FIELDS},
            })
            time.sleep(DELAY_BETWEEN)
            continue

        scored = score_result(result)
        row = {
            "url": url,
            "status": "OK",
            "score_pct": scored["pct"],
        }
        for field in SCORED_FIELDS:
            row[field] = scored["scores"][field]

        # Include raw values for review
        row["raw_title"] = result.get("Title", "")
        row["raw_price"] = result.get("Price", "")
        row["raw_vin"]   = result.get("VIN", "")

        rows.append(row)
        print(f"[harness] Score: {scored['pct']}% — {scored['scores']}")
        time.sleep(DELAY_BETWEEN)

    # Write CSV
    fieldnames = ["url", "status", "score_pct"] + SCORED_FIELDS + ["raw_title", "raw_price", "raw_vin"]
    with open(REPORT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Summary
    ok_rows    = [r for r in rows if r["status"] == "OK"]
    avg_score  = round(sum(r["score_pct"] for r in ok_rows) / len(ok_rows)) if ok_rows else 0
    failed     = len([r for r in rows if r["status"] != "OK"])
    passed_100 = len([r for r in ok_rows if r["score_pct"] == 100])

    print("\n" + "="*50)
    print(f"[harness] COMPLETE — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"[harness] Total dealers tested : {len(DEALER_URLS)}")
    print(f"[harness] Fetch/API failures   : {failed}")
    print(f"[harness] Average score        : {avg_score}%")
    print(f"[harness] Perfect scores (100%): {passed_100}")
    print(f"[harness] Report saved to      : {REPORT_PATH}")
    print("="*50)


if __name__ == "__main__":
    run()
