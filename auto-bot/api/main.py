# api/main.py
from fastapi import FastAPI, HTTPException, Header, Request
from pydantic import BaseModel
from bs4 import BeautifulSoup
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
import os
import re
import json
import requests
from typing import List, Optional

import bcrypt
import jwt as pyjwt
from supabase import create_client, Client
import stripe

app = FastAPI()


# ========= Supabase client =========
_SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
_SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
_JWT_SECRET = os.environ.get("JWT_SECRET", "")

supabase: Client = create_client(_SUPABASE_URL, _SUPABASE_SERVICE_KEY) if _SUPABASE_URL and _SUPABASE_SERVICE_KEY else None  # type: ignore

# ========= Stripe client =========
_STRIPE_SECRET_KEY     = os.environ.get("STRIPE_SECRET_KEY", "")
_STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
_STRIPE_PRICE_STANDARD = os.environ.get("STRIPE_PRICE_STANDARD", "price_1TlzXPRvbsBXVbcqerMgexrZ")
_WEBSITE_BASE          = "https://postbot-website.onrender.com"

stripe.api_key = _STRIPE_SECRET_KEY


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
def extract_html(body: HtmlPayload, authorization: Optional[str] = Header(default=None)):
    _require_jwt(authorization)
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


class ScrapeUrlPayload(BaseModel):
    url: str
    vin: Optional[str] = None


# FireCrawl key → result dict Title-Case key mapping
_BODY_TYPE_SUFFIXES = re.compile(
    r"\s+\b(Sedan|Hatchback|Coupe|Convertible|Wagon|SUV|Truck|Van|Minivan)\b.*$",
    re.IGNORECASE,
)


def _strip_body_type_suffix(model: str) -> str:
    """Strip trailing body-type words from a FireCrawl model string.
    E.g. 'Civic Sedan' -> 'Civic', 'HR-V SUV' -> 'HR-V'."""
    return _BODY_TYPE_SUFFIXES.sub("", model).strip()


_FC_KEY_MAP = {
    "mileage":        "Mileage",
    "vin":            "VIN",
    "year":           "Year",
    "make":           "Make",
    "model":          "Model",
    "price":          "Price",
    "interior_color": "Interior Color",
    "exterior_color": "Exterior Color",
    "body_type":      "Body Type",
    "description":    "Description",
    "condition":      "Condition",
    "fuel_type":      "Fuel Type",
}

_FC_SCHEMA = {
    "type": "object",
    "properties": {
        "vehicles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "year":           {"type": "string"},
                    "make":           {"type": "string"},
                    "model":          {"type": "string"},
                    "trim":           {"type": "string"},
                    "price":          {"type": "string"},
                    "mileage":        {"type": "string"},
                    "vin":            {"type": "string"},
                    "exterior_color": {"type": "string"},
                    "interior_color": {"type": "string"},
                    "description":    {"type": "string"},
                    "images":         {"type": "array", "items": {"type": "string"}},
                    "condition":      {"type": "string"},
                    "body_type":      {"type": "string"},
                    "fuel_type":      {"type": "string"},
                },
                "required": ["year", "make", "model", "price", "vin"],
            },
        }
    },
}


@app.post("/fb/scrape_url")
def scrape_url(body: ScrapeUrlPayload, authorization: Optional[str] = Header(default=None)):
    """
    Scrape a single vehicle detail page URL via FireCrawl and return the same
    result-dict shape as /fb/extract_html so the extension needs zero changes.
    """
    _require_jwt(authorization)
    fc_api_key = os.environ["FIRECRAWL_API_KEY"]

    fc_resp = requests.post(
        "https://api.firecrawl.dev/v1/scrape",
        headers={
            "Authorization": f"Bearer {fc_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "url": body.url,
            "formats": ["markdown", "extract"],
            "extract": {"schema": _FC_SCHEMA},
        },
        timeout=60,
    )

    if not fc_resp.ok:
        raise HTTPException(
            status_code=502,
            detail=f"FireCrawl error {fc_resp.status_code}: {fc_resp.text[:400]}",
        )

    fc_data = fc_resp.json()

    # Navigate to vehicles array — use bracket access per spec
    try:
        extract = fc_data["data"]["extract"]
        vehicles = extract["vehicles"]
    except (KeyError, TypeError) as e:
        print(f"[scrape_url] FireCrawl response structure unexpected: {fc_data}", flush=True)
        raise HTTPException(status_code=502, detail=f"FireCrawl extract missing: {e}")

    if not vehicles:
        raise HTTPException(status_code=404, detail="FireCrawl returned no vehicles for this URL.")

    # Pick vehicle: match by VIN if provided, else take first
    vehicle = None
    if body.vin:
        for v in vehicles:
            if str(v.get("vin", "")).strip().upper() == body.vin.strip().upper():
                vehicle = v
                break
    if vehicle is None:
        vehicle = vehicles[0]

    # Map FireCrawl lowercase keys → Title-Case result dict
    result: dict = {}
    for fc_key, out_key in _FC_KEY_MAP.items():
        val = vehicle.get(fc_key) or ""
        result[out_key] = str(val).strip() if val else ""

    # Default Fuel Type to Gasoline if blank
    if not result["Fuel Type"]:
        result["Fuel Type"] = "Gasoline"

    # Strip body-type suffix from Model (e.g. "Civic Sedan" -> "Civic")
    if result.get("Model"):
        result["Model"] = _strip_body_type_suffix(result["Model"])

    # Images — full gallery from FireCrawl
    raw_images = vehicle.get("images") or []
    result["images"] = [u for u in raw_images if isinstance(u, str) and u.startswith("http")]

    print(
        f"[scrape_url] url={body.url} | vehicle={result.get('Year')} {result.get('Make')} {result.get('Model')} "
        f"| images={len(result['images'])} | fields={list(result.keys())}",
        flush=True,
    )

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
    - Inserts into Supabase 'users' table (email, password_hash, tier='free')
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
        "tier": "free",
    }).execute()

    token = _issue_jwt(body.email, "free")
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

    email = payload.get("email")
    result = supabase.table("users").select("email, tier").eq("email", email).execute()
    if not result.data:
        raise HTTPException(status_code=401, detail="User not found.")

    user = result.data[0]
    return {"email": user["email"], "tier": user["tier"]}


# =========================================================================
# BILLING ENDPOINTS
# =========================================================================

def _require_jwt(authorization: Optional[str]) -> dict:
    """Decode and validate a Bearer JWT. Returns payload dict or raises 401."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header.")
    token = authorization.split(" ", 1)[1]
    try:
        return pyjwt.decode(token, _JWT_SECRET, algorithms=["HS256"])
    except pyjwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")


@app.post("/billing/create-checkout")
def billing_create_checkout(authorization: Optional[str] = Header(default=None)):
    """
    Create a Stripe Checkout Session (subscription mode) for the Standard plan.
    - Requires valid JWT in Authorization: Bearer header
    - Sets customer_email and client_reference_id to the user's email
    - Returns { checkout_url }
    """
    payload = _require_jwt(authorization)
    email = payload.get("email")

    session = stripe.checkout.Session.create(
        mode="subscription",
        payment_method_types=["card"],
        line_items=[{"price": _STRIPE_PRICE_STANDARD, "quantity": 1}],
        customer_email=email,
        client_reference_id=email,
        success_url=f"{_WEBSITE_BASE}/success.html?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{_WEBSITE_BASE}/cancel.html",
    )
    return {"checkout_url": session.url}


@app.post("/billing/webhook")
async def billing_webhook(request: Request,
                          stripe_signature: Optional[str] = Header(default=None)):
    """
    Stripe webhook receiver.
    - Verifies Stripe signature using STRIPE_WEBHOOK_SECRET
    - checkout.session.completed → set user tier='standard', store stripe_customer_id
    - customer.subscription.deleted → find user by stripe_customer_id, set tier='free'
    - Always returns 200 to prevent Stripe retry storms
    """
    body = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            body, stripe_signature, _STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature.")

    event_type = event["type"]
    obj = event["data"]["object"]

    if event_type == "checkout.session.completed":
        email = obj["client_reference_id"]
        customer_id = obj["customer"]
        if email:
            supabase.table("users").update({
                "tier": "standard",
                "stripe_customer_id": customer_id,
            }).eq("email", email).execute()
            print(f"[billing] checkout.session.completed: {email} tier=standard, customer={customer_id}", flush=True)

    elif event_type == "customer.subscription.deleted":
        customer_id = obj["customer"]
        if customer_id:
            result = supabase.table("users").select("email").eq(
                "stripe_customer_id", customer_id
            ).execute()
            if result.data:
                email = result.data[0]["email"]
                supabase.table("users").update({"tier": "free"}).eq(
                    "email", email
                ).execute()
                print(f"[billing] subscription.deleted: {email} → tier=free", flush=True)

    return {"received": True}


@app.post("/billing/portal")
def billing_portal(authorization: Optional[str] = Header(default=None)):
    """
    Create a Stripe Customer Portal session so users can manage/cancel.
    - Requires valid JWT
    - Looks up the user's stripe_customer_id in Supabase
    - Returns { portal_url }
    """
    payload = _require_jwt(authorization)
    email = payload.get("email")

    result = supabase.table("users").select("stripe_customer_id").eq("email", email).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="User not found.")

    customer_id = result.data[0].get("stripe_customer_id")
    if not customer_id:
        raise HTTPException(status_code=400, detail="No active subscription found for this account.")

    portal_session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{_WEBSITE_BASE}/account.html",
    )
    return {"portal_url": portal_session.url}


