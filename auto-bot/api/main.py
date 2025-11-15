# api/main.py
from fastapi import FastAPI
from pydantic import BaseModel
from bs4 import BeautifulSoup
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
import os
import json
from typing import List, Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========= OpenAI client =========
client = OpenAI(
    api_key=os.environ["OPENAI_API_KEY"]
)

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
]


class ImageCandidate(BaseModel):
    src: str
    alt: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None


class HtmlPayload(BaseModel):
    url: str
    html: str
    images: Optional[List[ImageCandidate]] = None


def extract_json_object(raw: str) -> dict:
    """
    Find the first {...} block in model output and parse as JSON.
    """
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"No JSON object found in model output: {raw!r}")
    return json.loads(raw[start : end + 1])


@app.post("/fb/extract_html")
def extract_html(body: HtmlPayload):
    """
    AI-only extractor:
    - Uses LLM on page text to fill vehicle fields.
    - Uses LLM on candidate images to pick the real car photos.
    Returns a single object with the fields plus `images: [urls]`.
    """
    soup = BeautifulSoup(body.html, "html.parser")
    text = soup.get_text(separator="\n")[:20000]

    # ---------- 1) Fields via LLM ----------
    base_fields = {k: "" for k in FIELDS}
    fields_prompt = (
        "You are a data extractor for vehicle listings.\n"
        "From the text below, extract ONLY these fields and return ONLY valid JSON.\n"
        "Do NOT include any explanation, only a JSON object.\n"
        f"{json.dumps(base_fields, indent=2)}\n\n"
        "If a value is not present in the text, leave it as an empty string.\n\n"
        f"TEXT:\n{text}"
    )

    result = {k: "" for k in FIELDS}
    try:
        resp = client.responses.create(
            model="gpt-4.1-mini",
            input=fields_prompt,
        )
        raw = resp.output_text
        data = extract_json_object(raw)
        for k in FIELDS:
            result[k] = data.get(k, "") or ""
    except Exception as e:
        # If LLM fails, keep fields empty but include error
        result["Description"] = f"(AI field extraction failed: {e})"

    # ---------- 2) Images via LLM ----------
    images_out: List[str] = []

    if body.images:
        # Build slim candidate list for the LLM
        candidates = [
            {
                "src": c.src,
                "alt": c.alt or "",
                "width": c.width or 0,
                "height": c.height or 0,
            }
            for c in body.images
            if c.src
        ]
        slim = candidates[:60]  # avoid too many tokens

        if slim:
            img_prompt = (
                "You are selecting vehicle photos from a dealership listing.\n"
                "You will be given a JSON array of candidate <img> elements.\n"
                "Each item includes a URL and metadata.\n\n"
                "Goal:\n"
                "- Keep images that are clearly the car itself (exterior/interior photos\n"
                "  in the main gallery or carousel).\n"
                "- Exclude logos, icons, badges, tiny thumbnails, social icons, brand\n"
                "  logos, profile pictures, 'no image' placeholders, dealer logos.\n\n"
                "Return ONLY valid JSON in this form:\n"
                '{\n  "images": ["url1", "url2", "..."]\n}\n\n'
                "Here are the candidates:\n"
                f"{json.dumps(slim, indent=2)}"
            )

            try:
                img_resp = client.responses.create(
                    model="gpt-4.1-mini",
                    input=img_prompt,
                )
                raw_img = img_resp.output_text
                img_obj = extract_json_object(raw_img)
                images_out = [u for u in img_obj.get("images", []) if isinstance(u, str)]
            except Exception:
                images_out = []

        # Fallback: if LLM gave nothing, choose the largest-area few
        if not images_out and candidates:
            candidates_sorted = sorted(
                candidates,
                key=lambda c: (c.get("width") or 0) * (c.get("height") or 0),
                reverse=True,
            )
            images_out = [
                c["src"] for c in candidates_sorted[:8] if c.get("src")
            ]

    result["images"] = images_out

    return result
