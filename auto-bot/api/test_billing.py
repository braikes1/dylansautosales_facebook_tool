# api/test_billing.py
# TDD tests for /billing/create-checkout, /billing/webhook, /billing/portal
# Run: pytest api/test_billing.py -v

import os, sys

# Set dummy env vars before importing the app
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key")
os.environ.setdefault("JWT_SECRET", "test-secret-32-chars-long-padded!!")
os.environ.setdefault("OPENAI_API_KEY", "fake-openai-key")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_fakekey")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_fakesecret")
os.environ.setdefault("STRIPE_PRICE_STANDARD", "price_1TlzXPRvbsBXVbcqerMgexrZ")

import json
import time
import hmac
import hashlib
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import jwt as pyjwt


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_token(email: str, tier: str = "standard") -> str:
    """Issue a real JWT using the test secret."""
    return pyjwt.encode(
        {"email": email, "tier": tier},
        os.environ["JWT_SECRET"],
        algorithm="HS256"
    )

def _auth_header(email: str, tier: str = "standard") -> dict:
    return {"Authorization": f"Bearer {_make_token(email, tier)}"}

def _stripe_sig_header(payload: bytes, secret: str = "whsec_fakesecret") -> str:
    """Build a Stripe-Signature header for webhook testing."""
    ts = str(int(time.time()))
    signed = f"{ts}.{payload.decode()}"
    sig = hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"

def _mock_supabase_user(email: str, tier: str = "free", stripe_customer_id: str = None):
    mock = MagicMock()
    user_row = {"email": email, "tier": tier, "stripe_customer_id": stripe_customer_id}
    mock.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [user_row]
    mock.table.return_value.update.return_value.eq.return_value.execute.return_value.data = [user_row]
    return mock

def _mock_supabase_no_user():
    mock = MagicMock()
    mock.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    return mock


# ── POST /billing/create-checkout ────────────────────────────────────────────

class TestCreateCheckout:

    def test_returns_checkout_url_for_valid_jwt(self):
        """Valid JWT + user exists → 200 with checkout_url."""
        from api.main import app
        client = TestClient(app)

        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/pay/cs_test_fake123"

        with patch("api.main.supabase", _mock_supabase_user("user@test.com")), \
             patch("api.main.stripe.checkout.Session.create", return_value=mock_session):
            resp = client.post("/billing/create-checkout",
                               headers=_auth_header("user@test.com"))

        assert resp.status_code == 200
        assert "checkout_url" in resp.json()
        assert resp.json()["checkout_url"].startswith("https://checkout.stripe.com")

    def test_rejects_missing_jwt(self):
        """No Authorization header → 401."""
        from api.main import app
        client = TestClient(app)
        resp = client.post("/billing/create-checkout")
        assert resp.status_code == 401

    def test_rejects_invalid_jwt(self):
        """Garbage token → 401."""
        from api.main import app
        client = TestClient(app)
        resp = client.post("/billing/create-checkout",
                           headers={"Authorization": "Bearer notavalidtoken"})
        assert resp.status_code == 401

    def test_checkout_session_uses_correct_price(self):
        """Checkout session must use STRIPE_PRICE_STANDARD."""
        from api.main import app
        client = TestClient(app)

        captured = {}
        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/pay/cs_test_fake"

        def capture_create(**kwargs):
            captured.update(kwargs)
            return mock_session

        with patch("api.main.supabase", _mock_supabase_user("user@test.com")), \
             patch("api.main.stripe.checkout.Session.create", side_effect=capture_create):
            client.post("/billing/create-checkout", headers=_auth_header("user@test.com"))

        line_items = captured.get("line_items", [])
        assert any(
            item.get("price") == "price_1TlzXPRvbsBXVbcqerMgexrZ"
            for item in line_items
        ), f"Expected standard price in line_items, got: {line_items}"

    def test_checkout_session_sets_customer_email(self):
        """customer_email on the Stripe session must match the JWT email."""
        from api.main import app
        client = TestClient(app)

        captured = {}
        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/pay/cs_test_fake"

        def capture_create(**kwargs):
            captured.update(kwargs)
            return mock_session

        with patch("api.main.supabase", _mock_supabase_user("dealer@lot.com")), \
             patch("api.main.stripe.checkout.Session.create", side_effect=capture_create):
            client.post("/billing/create-checkout", headers=_auth_header("dealer@lot.com"))

        assert captured.get("customer_email") == "dealer@lot.com"
        assert captured.get("client_reference_id") == "dealer@lot.com"


# ── POST /billing/webhook ─────────────────────────────────────────────────────

class TestWebhook:

    def _build_event(self, event_type: str, data: dict) -> bytes:
        event = {
            "type": event_type,
            "data": {"object": data}
        }
        return json.dumps(event).encode()

    def test_checkout_completed_upgrades_tier(self):
        """checkout.session.completed → user tier updated to 'standard', customer_id stored."""
        from api.main import app
        client = TestClient(app)

        payload = self._build_event("checkout.session.completed", {
            "client_reference_id": "paiduser@test.com",
            "customer": "cus_test123",
            "subscription": "sub_test123",
        })
        sig = _stripe_sig_header(payload)

        mock_event = {
            "type": "checkout.session.completed",
            "data": {"object": {
                "client_reference_id": "paiduser@test.com",
                "customer": "cus_test123",
                "subscription": "sub_test123",
            }}
        }

        mock_sb = _mock_supabase_user("paiduser@test.com", tier="free")

        with patch("api.main.supabase", mock_sb), \
             patch("api.main.stripe.Webhook.construct_event", return_value=mock_event):
            resp = client.post(
                "/billing/webhook",
                content=payload,
                headers={"stripe-signature": sig, "content-type": "application/json"}
            )

        assert resp.status_code == 200
        # Verify update was called on the users table
        mock_sb.table.return_value.update.assert_called()

    def test_subscription_deleted_downgrades_tier(self):
        """customer.subscription.deleted → user tier set to 'free'."""
        from api.main import app
        client = TestClient(app)

        payload = self._build_event("customer.subscription.deleted", {
            "customer": "cus_test123",
        })
        sig = _stripe_sig_header(payload)

        mock_event = {
            "type": "customer.subscription.deleted",
            "data": {"object": {"customer": "cus_test123"}}
        }

        mock_sb = _mock_supabase_user("paiduser@test.com", tier="standard",
                                      stripe_customer_id="cus_test123")
        # Make the lookup-by-stripe_customer_id path work
        mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"email": "paiduser@test.com", "tier": "standard", "stripe_customer_id": "cus_test123"}
        ]

        with patch("api.main.supabase", mock_sb), \
             patch("api.main.stripe.Webhook.construct_event", return_value=mock_event):
            resp = client.post(
                "/billing/webhook",
                content=payload,
                headers={"stripe-signature": sig, "content-type": "application/json"}
            )

        assert resp.status_code == 200
        mock_sb.table.return_value.update.assert_called()

    def test_invalid_signature_returns_400(self):
        """Bad Stripe signature → 400."""
        import stripe as stripe_lib
        from api.main import app
        client = TestClient(app)

        payload = self._build_event("checkout.session.completed", {})

        with patch("api.main.stripe.Webhook.construct_event",
                   side_effect=stripe_lib.error.SignatureVerificationError("bad sig", "sig_header")):
            resp = client.post(
                "/billing/webhook",
                content=payload,
                headers={"stripe-signature": "t=bad,v1=bad",
                         "content-type": "application/json"}
            )

        assert resp.status_code == 400

    def test_unknown_event_type_returns_200(self):
        """Unhandled event type → still return 200 (don't fail Stripe retry loop)."""
        from api.main import app
        client = TestClient(app)

        payload = self._build_event("payment_intent.created", {"id": "pi_test"})
        mock_event = {"type": "payment_intent.created", "data": {"object": {}}}

        with patch("api.main.stripe.Webhook.construct_event", return_value=mock_event):
            resp = client.post(
                "/billing/webhook",
                content=payload,
                headers={"stripe-signature": "t=1,v1=x", "content-type": "application/json"}
            )

        assert resp.status_code == 200


# ── POST /billing/portal ──────────────────────────────────────────────────────

class TestPortal:

    def test_returns_portal_url_for_valid_user(self):
        """Valid JWT + user has stripe_customer_id → 200 with portal_url."""
        from api.main import app
        client = TestClient(app)

        mock_session = MagicMock()
        mock_session.url = "https://billing.stripe.com/session/test_portal"

        with patch("api.main.supabase",
                   _mock_supabase_user("user@test.com", stripe_customer_id="cus_abc")), \
             patch("api.main.stripe.billing_portal.Session.create",
                   return_value=mock_session):
            resp = client.post("/billing/portal", headers=_auth_header("user@test.com"))

        assert resp.status_code == 200
        assert "portal_url" in resp.json()
        assert resp.json()["portal_url"].startswith("https://billing.stripe.com")

    def test_rejects_user_with_no_stripe_customer(self):
        """User has no stripe_customer_id → 400."""
        from api.main import app
        client = TestClient(app)

        with patch("api.main.supabase",
                   _mock_supabase_user("user@test.com", stripe_customer_id=None)):
            resp = client.post("/billing/portal", headers=_auth_header("user@test.com"))

        assert resp.status_code == 400

    def test_rejects_missing_jwt(self):
        """No JWT → 401."""
        from api.main import app
        client = TestClient(app)
        resp = client.post("/billing/portal")
        assert resp.status_code == 401


# ── Existing endpoints not broken ─────────────────────────────────────────────

class TestExistingEndpointsUntouched:

    def test_health_still_works(self):
        from api.main import app
        client = TestClient(app)
        assert client.get("/health").status_code == 200

    def test_auth_verify_still_works(self):
        from api.main import app
        client = TestClient(app)
        resp = client.get("/auth/verify", headers=_auth_header("x@y.com"))
        assert resp.status_code == 200
        assert resp.json()["email"] == "x@y.com"
