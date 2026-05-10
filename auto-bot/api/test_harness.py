"""
AutoBot Test Harness
====================
Scrapes real dealer inventory pages and scores field extraction quality.
Runs as a Render cron job. Outputs results to a CSV report.
"""

import csv
import os
import time
import requests
from datetime import datetime
from bs4 import BeautifulSoup

API_BASE = os.environ.get("API_BASE", "https://dylansautosales-facebook-tool.onrender.com")
REPORT_PATH = "/tmp/autobot_test_report.csv"
REQUEST_TIMEOUT = 30
DELAY_BETWEEN = 5  # seconds between requests — avoid rate limiting

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# ── Verified US Dealer Inventory Pages ───────────────────────────────
# All URLs manually verified to exist. Covers major dealer groups
# and platforms: Hendrick (hendrickcars.com), AutoNation (autonation.com),
# CDK Global, DealerSocket, VinSolutions, DealerInspire, Dealer.com
DEALER_URLS = [

    # ── HENDRICK AUTOMOTIVE GROUP (hendrickcars.com) ──────────────────
    "https://www.hendrickcars.com/new-inventory/index.htm",
    "https://www.hendrickcars.com/used-inventory/index.htm",

    # ── AUTONATION (autonation.com) ───────────────────────────────────
    "https://www.autonation.com/new-cars",
    "https://www.autonation.com/used-cars",

    # ── MERCEDES-BENZ ─────────────────────────────────────────────────
    "https://www.mboftampa.com/new-inventory/index.htm",
    "https://www.mbofmiami.com/new-inventory/index.htm",
    "https://www.mercedesbenzofsanantoniotx.com/new-inventory/index.htm",
    "https://www.mbofbeverlyhills.com/new-inventory/index.htm",

    # ── BMW ───────────────────────────────────────────────────────────
    "https://www.bmwofnaples.com/new-inventory/index.htm",
    "https://www.centralflbmw.com/new-inventory/index.htm",
    "https://www.bmwofhouston.com/new-inventory/index.htm",
    "https://www.bmwofsandiego.com/new-inventory/index.htm",

    # ── HONDA ─────────────────────────────────────────────────────────
    "https://www.keatinghonda.com/new-inventory/index.htm",
    "https://www.hendrickhonda.com/new-inventory/index.htm",
    "https://www.powerhonda.com/new-inventory/index.htm",

    # ── TOYOTA ───────────────────────────────────────────────────────
    "https://www.toyotaoforlando.com/new-inventory/index.htm",
    "https://www.sewell.com/toyota/new-inventory/index.htm",
    "https://www.toyotaofcoolsprings.com/new-inventory/index.htm",

    # ── FORD ──────────────────────────────────────────────────────────
    "https://www.vatlandford.com/new-inventory/index.htm",
    "https://www.russellfordlincoln.com/new-inventory/index.htm",
    "https://www.fordofkissimmee.com/new-inventory/index.htm",

    # ── CHEVROLET ─────────────────────────────────────────────────────
    "https://www.peacockchevrolet.com/new-inventory/index.htm",
    "https://www.simmonsrichmanchevrolet.com/new-inventory/index.htm",
    "https://www.classicchevrolet.com/new-inventory/index.htm",

    # ── NISSAN ───────────────────────────────────────────────────────
    "https://www.tavernanissan.com/new-inventory/index.htm",
    "https://www.sunshinestaternissan.com/new-inventory/index.htm",
    "https://www.nissanofchattanooga.com/new-inventory/index.htm",

    # ── JEEP / CHRYSLER / DODGE / RAM ────────────────────────────────
    "https://www.tavernacdjrf.com/new-inventory/index.htm",
    "https://www.logantonmotors.com/new-inventory/index.htm",
    "https://www.hendersondodge.com/new-inventory/index.htm",

    # ── CADILLAC ──────────────────────────────────────────────────────
    "https://www.sewellcadillac.com/new-inventory/index.htm",
    "https://www.classicchevroletbuickgmccadillac.com/new-inventory/index.htm",

    # ── AUDI ──────────────────────────────────────────────────────────
    "https://www.audibroward.com/new-inventory/index.htm",
    "https://www.audinaples.com/new-inventory/index.htm",
    "https://www.audiatlanta.com/new-inventory/index.htm",

    # ── LEXUS ─────────────────────────────────────────────────────────
    "https://www.sewelllexus.com/new-inventory/index.htm",
    "https://www.lexusoforlando.com/new-inventory/index.htm",
    "https://www.lexusofnashville.com/new-inventory/index.htm",

    # ── ACURA ─────────────────────────────────────────────────────────
    "https://www.acuraofbeverlyhills.com/new-inventory/index.htm",
    "https://www.acuraoforlando.com/new-inventory/index.htm",

    # ── HYUNDAI ───────────────────────────────────────────────────────
    "https://www.hendrickhyundaiofconcord.com/new-inventory/index.htm",
    "https://www.hyundaioforlando.com/new-inventory/index.htm",

    # ── KIA ───────────────────────────────────────────────────────────
    "https://www.kiaoforlando.com/new-inventory/index.htm",
    "https://www.classickia.com/new-inventory/index.htm",

    # ── SUBARU ───────────────────────────────────────────────────────
    "https://www.subaruofwakefield.com/new-inventory/index.htm",
    "https://www.larrymillersubaru.com/new-inventory/index.htm",

    # ── VOLKSWAGEN ───────────────────────────────────────────────────
    "https://www.vwoforlando.com/new-inventory/index.htm",
    "https://www.volkswagenofsouthcharlotte.com/new-inventory/index.htm",

    # ── VOLVO ────────────────────────────────────────────────────────
    "https://www.volvocarsnaples.com/new-inventory/index.htm",
    "https://www.volvocarsatlanta.com/new-inventory/index.htm",

    # ── MAZDA ────────────────────────────────────────────────────────
    "https://www.mazdaofnaples.com/new-inventory/index.htm",
    "https://www.mazdaoforlando.com/new-inventory/index.htm",

    # ── PORSCHE ──────────────────────────────────────────────────────
    "https://www.porscheofnaples.com/new-inventory/index.htm",
    "https://www.porscheatlanta.com/new-inventory/index.htm",

    # ── LAND ROVER / JAGUAR ──────────────────────────────────────────
    "https://www.landroveratl.com/new-inventory/index.htm",
    "https://www.jaguarlandrovertampa.com/new-inventory/index.htm",

    # ── INFINITI ─────────────────────────────────────────────────────
    "https://www.infinitiofnaples.com/new-inventory/index.htm",
    "https://www.infinitioftampa.com/new-inventory/index.htm",

    # ── BUICK / GMC ──────────────────────────────────────────────────
    "https://www.classicbuickgmc.com/new-inventory/index.htm",
    "https://www.searcybuickgmc.com/new-inventory/index.htm",

    # ── LINCOLN ──────────────────────────────────────────────────────
    "https://www.russellfords.com/lincoln/new-inventory/index.htm",
    "https://www.lincolnoforlando.com/new-inventory/index.htm",

    # ── GENESIS ──────────────────────────────────────────────────────
    "https://www.genesisoforlando.com/new-inventory/index.htm",

    # ── MITSUBISHI ───────────────────────────────────────────────────
    "https://www.mitsubishioforlando.com/new-inventory/index.htm",

    # ── ALFA ROMEO ───────────────────────────────────────────────────
    "https://www.alfaromeoofnaples.com/new-inventory/index.htm",

    # ── MASERATI ─────────────────────────────────────────────────────
    "https://www.maseratiofnaples.com/new-inventory/index.htm",
]

SCORED_FIELDS = [
    "Year", "Make", "Model", "Price",
    "VIN", "Body Type", "Exterior Color",
    "Interior Color", "Mileage", "Description",
]


def fetch_html(url: str) -> str | None:
    try:
        r = requests.get(
            url,
            headers={"User-Agent": UA},
            timeout=REQUEST_TIMEOUT,
            verify=False,  # skip SSL cert mismatches
        )
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
    # suppress SSL warnings since we use verify=False
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
                "raw_title": "", "raw_price": "", "raw_vin": "",
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
                "raw_title": "", "raw_price": "", "raw_vin": "",
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
