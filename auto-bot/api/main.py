# api/main.py
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from bs4 import BeautifulSoup
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
import os
import re
import json
from typing import List, Optional

import bcrypt
import jwt as pyjwt
from supabase import create_client, Client

app = FastAPI()


# ========= Supabase client =========
_SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
_SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
_JWT_SECRET = os.environ.get("JWT_SECRET", "")

supabase: Client = create_client(_SUPABASE_URL, _SUPABASE_SERVICE_KEY) if _SUPABASE_URL and _SUPABASE_SERVICE_KEY else None  # type: ignore


@app.get("/health")
def health():
    """Simple health check so the extension can verify the server is running."""
    return {"status": "ok"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========= OpenAI client =========
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY", "")
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


def extract_json_object(raw: str, label: str = "") -> dict:
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip()

    start = cleaned.find("{")
    if start == -1:
        print(f"[main] {label} raw output: {raw!r}", flush=True)
        raise ValueError(f"No JSON object found in model output: {raw!r}")

    depth = 0
    in_string = False
    escape_next = False
    end = -1
    for i, ch in enumerate(cleaned[start:], start=start):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break

    if end == -1:
        print(f"[main] {label} raw output: {raw!r}", flush=True)
        raise ValueError(f"No closing brace found in model output: {raw!r}")

    json_str = cleaned[start : end + 1]
    print(f"[main] {label} raw output: {raw!r}", flush=True)
    return json.loads(json_str)


@app.post("/fb/extract_html")
def extract_html(body: HtmlPayload):
    soup = BeautifulSoup(body.html, "html.parser")
    text = soup.get_text(separator="\n")[:20000]

    # ---------- 1) Fields via LLM ----------
    base_fields = {k: "" for k in FIELDS}
    fields_prompt = (
        "You are a data extractor for vehicle listings.\n"
        "From the text below, extract ONLY these fields and return ONLY valid JSON.\n"
        "Do NOT include any explanation, only a JSON object.\n"
        f"{json.dumps(base_fields, indent=2)}\n\n"
        "Rules:\n"
        "- Mileage: extract as shown (e.g. '54,233 miles'). Leave empty for new cars.\n"
        "- VIN: full 17-character VIN only.\n"
        "- Year/Make/Model: from the listing title or specs.\n"
        "- Price: formatted with currency symbol (e.g. '$44,175').\n"
        "- Exterior Color / Interior Color: use the full human-readable color name "
        "(e.g. 'Selenite Grey Metallic', not a short code like 'Ack' or 'Lic'). "
        "If you only see an abbreviation or code with no full name nearby, leave the field empty.\n"
        "- Body Type: use standard terms like Sedan, SUV, Truck, Van, Coupe, etc.\n"
        "- Description: write 2-3 sentences in a natural, sales-friendly tone "
        "highlighting the vehicle's key features, trim level, and standout qualities. "
        "Do NOT copy spec sheet text verbatim. Do NOT mention price or mileage.\n"
        "- If a value is not present in the text, leave it as an empty string.\n\n"
        f"TEXT:\n{text}"
    )

    result = {k: "" for k in FIELDS}
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": fields_prompt}],
        )
        raw = resp.choices[0].message.content
        data = extract_json_object(raw, label="fields")
        for k in FIELDS:
            result[k] = data.get(k, "") or ""
    except Exception as e:
        result["Description"] = f"(AI field extraction failed: {e})"

    # ---------- 2) Images via LLM ----------
    images_out: List[str] = []

    if body.images:
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
        slim = candidates[:60]

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
                img_resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": img_prompt}],
                )
                raw_img = img_resp.choices[0].message.content
                img_obj = extract_json_object(raw_img, label="images")
                images_out = [u for u in img_obj.get("images", []) if isinstance(u, str)]
            except Exception:
                images_out = []

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


# =========================================================================
# AUTH ENDPOINTS
# =========================================================================

class AuthBody(BaseModel):
    email: str
    password: str


def _issue_jwt(email: str, tier: str) -> str:
    """Sign a JWT containing email and tier using JWT_SECRET."""
    return pyjwt.encode({"email": email, "tier": tier}, _JWT_SECRET, algorithm="HS256")


@app.post("/auth/register")
def auth_register(body: AuthBody):
    """
    Register a new user.
    - Hashes password with bcrypt
    - Inserts into Supabase 'users' table (email, password_hash, tier='standard')
    - Returns a signed JWT on success
    - Returns 400 if the email is already registered
    """
    # Check for existing user
    existing = supabase.table("users").select("email").eq("email", body.email).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="An account with that email already exists.")

    # Hash password — never store plaintext
    password_hash = bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # Insert new user
    supabase.table("users").insert({
        "email": body.email,
        "password_hash": password_hash,
        "tier": "standard",
    }).execute()

    token = _issue_jwt(body.email, "standard")
    return {"token": token}


@app.post("/auth/login")
def auth_login(body: AuthBody):
    """
    Authenticate an existing user.
    - Looks up user by email in Supabase
    - Verifies password with bcrypt
    - Returns a signed JWT on success, 401 on failure
    """
    result = supabase.table("users").select("email, password_hash, tier").eq("email", body.email).execute()
    if not result.data:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    user = result.data[0]
    if not bcrypt.checkpw(body.password.encode("utf-8"), user["password_hash"].encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token = _issue_jwt(user["email"], user["tier"])
    return {"token": token}


@app.get("/auth/verify")
def auth_verify(authorization: Optional[str] = Header(default=None)):
    """
    Verify a JWT from the Authorization: Bearer <token> header.
    - Returns { email, tier } if valid
    - Returns 401 if missing, invalid, or expired
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header.")

    token = authorization.split(" ", 1)[1]
    try:
        payload = pyjwt.decode(token, _JWT_SECRET, algorithms=["HS256"])
    except pyjwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")

    return {"email": payload.get("email"), "tier": payload.get("tier")}

