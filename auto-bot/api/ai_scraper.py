import os
import json
import re
from typing import Dict, List

import requests
from bs4 import BeautifulSoup
from openai import OpenAI

FIELDS = [
    "Mileage",
    "VIN",
    "Year",
    "Make",
    "Model",
    "Price",
    "Interior Color",
    "Exterior Color",
    "Body Type",
    "Description",
    "Photos",
]

DEFAULT_RESULT: Dict[str, object] = {
    "Mileage": "",
    "VIN": "",
    "Year": "",
    "Make": "",
    "Model": "",
    "Price": "",
    "Interior Color": "",
    "Exterior Color": "",
    "Body Type": "",
    "Description": "",
    "Photos": [],
}

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)


def get_client() -> OpenAI:
    key = "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"
    if not key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set.")
    return OpenAI(api_key=key)


def collect_image_candidates(soup: BeautifulSoup) -> List[dict]:
    """Collect a small set of <img> candidates for the LLM to choose vehicle photos."""
    candidates = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-original")
        if not src:
            continue
        alt = img.get("alt") or ""
        cls = " ".join(img.get("class") or [])
        candidates.append(
            {
                "src": src,
                "alt": alt,
                "class": cls,
            }
        )
        if len(candidates) >= 80:
            break
    return candidates


def call_llm(text: str, candidates: List[dict]) -> Dict[str, object]:
    client = get_client()

    prompt = (
        "You are a data extractor for vehicle listings.\n"
        "You will receive raw page text and a list of image candidates.\n"
        "Extract as many of these fields as you can and return ONLY valid JSON.\n"
        "Do not include markdown, backticks, or explanations. Just a JSON object.\n"
        "{\n"
        '  "Mileage": "",\n'
        '  "VIN": "",\n'
        '  "Year": "",\n'
        '  "Make": "",\n'
        '  "Model": "",\n'
        '  "Price": "",\n'
        '  "Interior Color": "",\n'
        '  "Exterior Color": "",\n'
        '  "Body Type": "",\n'
        '  "Description": "",\n'
        '  "Photos": []\n'
        "}\n"
        "Rules:\n"
        "- Put mileage as it appears (e.g. '54,233 miles').\n"
        "- Use full VIN if present.\n"
        "- Year/Make/Model from the listing.\n"
        "- Price as a single formatted string with currency symbol if present.\n"
        "- For Photos, pick only URLs that appear to be the real vehicle photos "
        "(not icons or logos), most likely from the vehicle gallery/carousel.\n"
        "Return an array of photo URLs under 'Photos'.\n"
        "\n"
        "IMAGE CANDIDATES (JSON):\n"
        f"{json.dumps(candidates)[:6000]}\n"
        "\n"
        "PAGE TEXT (truncated):\n"
        f"{text[:12000]}\n"
    )

    resp = client.responses.create(
        model="gpt-4o-mini",
        input=prompt,
    )

    raw = getattr(resp, "output_text", None) or ""
    # Log for debugging if needed
    print("RAW LLM OUTPUT:", raw[:4000], flush=True)

    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"LLM did not return JSON: {raw!r}")
    parsed = json.loads(raw[start : end + 1])

    # ensure all keys exist
    out: Dict[str, object] = dict(DEFAULT_RESULT)
    for k in FIELDS:
        if k in parsed:
            out[k] = parsed[k]
    # ensure Photos is a list
    if not isinstance(out.get("Photos"), list):
        out["Photos"] = []
    return out


def scrape_vehicle(url: str) -> Dict[str, object]:
    """
    Fetch a vehicle detail page with requests, parse basic fields with regex,
    then call LLM to refine and pick photos.
    """
    resp = requests.get(url, headers={"User-Agent": UA}, timeout=20)
    resp.raise_for_status()
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n")

    result: Dict[str, object] = dict(DEFAULT_RESULT)

    # quick regex-based hints
    mileage_match = re.search(r"\b([\d,]+)\s*(?:mi|miles)\b", text, re.IGNORECASE)
    if mileage_match:
        result["Mileage"] = mileage_match.group(0)

    vin_match = re.search(r"\b[A-HJ-NPR-Z0-9]{17}\b", text)
    if vin_match:
        result["VIN"] = vin_match.group(0)

    price_match = re.search(r"\$\s*\d[\d,]*(?:\.\d{2})?", text)
    if price_match:
        result["Price"] = price_match.group(0)

    # LLM assists for full struct + photos
    candidates = collect_image_candidates(soup)
    try:
        ai = call_llm(text, candidates)
        for k in FIELDS:
            if ai.get(k):
                result[k] = ai[k]
    except Exception as e:
        # log but keep partial data
        print("LLM error:", e, flush=True)

    return result
