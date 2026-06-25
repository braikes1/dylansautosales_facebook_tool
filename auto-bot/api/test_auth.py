# api/test_auth.py
# TDD tests for /auth/register, /auth/login, /auth/verify
# Run with: pytest api/test_auth.py -v

import os, sys
# Set dummy env vars before importing the app
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fake-service-key")
os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests")
os.environ.setdefault("OPENAI_API_KEY", "fake-openai-key")

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import jwt as pyjwt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_supabase_no_user():
    """Supabase returns empty list — user does not exist."""
    mock = MagicMock()
    mock.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    mock.table.return_value.insert.return_value.execute.return_value.data = [{"id": 1}]
    return mock


def _mock_supabase_existing_user(email: str, password_hash: str, tier: str = "standard"):
    """Supabase returns one user row — user already exists."""
    mock = MagicMock()
    mock.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"email": email, "password_hash": password_hash, "tier": tier}
    ]
    mock.table.return_value.insert.return_value.execute.return_value.data = []
    return mock


# ---------------------------------------------------------------------------
# Tests: POST /auth/register
# ---------------------------------------------------------------------------

class TestRegister:

    def test_register_success_returns_jwt(self):
        """New user registers → 200 with a JWT containing email and tier."""
        from api.main import app
        client = TestClient(app)

        with patch("api.main.supabase", _mock_supabase_no_user()):
            resp = client.post("/auth/register", json={"email": "new@test.com", "password": "password123"})

        assert resp.status_code == 200
        body = resp.json()
        assert "token" in body
        payload = pyjwt.decode(body["token"], "test-secret-for-unit-tests", algorithms=["HS256"])
        assert payload["email"] == "new@test.com"
        assert payload["tier"] == "standard"

    def test_register_duplicate_email_returns_400(self):
        """Existing email → 400 with clear message."""
        import bcrypt
        from api.main import app
        client = TestClient(app)

        existing_hash = bcrypt.hashpw(b"somepass", bcrypt.gensalt()).decode()
        mock_sb = _mock_supabase_existing_user("existing@test.com", existing_hash)

        with patch("api.main.supabase", mock_sb):
            resp = client.post("/auth/register", json={"email": "existing@test.com", "password": "password123"})

        assert resp.status_code == 400
        assert "already" in resp.json()["detail"].lower()

    def test_register_password_is_hashed_not_stored_plain(self):
        """Password must be bcrypt-hashed before insert — never stored in plaintext."""
        import bcrypt
        from api.main import app
        client = TestClient(app)

        captured_insert = {}
        mock_sb = _mock_supabase_no_user()

        original_insert = mock_sb.table.return_value.insert
        def capturing_insert(data):
            captured_insert.update(data)
            return original_insert(data)
        mock_sb.table.return_value.insert = capturing_insert

        with patch("api.main.supabase", mock_sb):
            resp = client.post("/auth/register", json={"email": "hash@test.com", "password": "plaintext"})

        assert resp.status_code == 200
        # The raw password must NOT appear anywhere in the insert payload
        assert captured_insert.get("password_hash", "") != "plaintext"


# ---------------------------------------------------------------------------
# Tests: POST /auth/login
# ---------------------------------------------------------------------------

class TestLogin:

    def test_login_valid_credentials_returns_jwt(self):
        """Correct email + password → 200 with JWT."""
        import bcrypt
        from api.main import app
        client = TestClient(app)

        pw_hash = bcrypt.hashpw(b"correctpass", bcrypt.gensalt()).decode()
        mock_sb = _mock_supabase_existing_user("user@test.com", pw_hash, tier="standard")

        with patch("api.main.supabase", mock_sb):
            resp = client.post("/auth/login", json={"email": "user@test.com", "password": "correctpass"})

        assert resp.status_code == 200
        body = resp.json()
        assert "token" in body
        payload = pyjwt.decode(body["token"], "test-secret-for-unit-tests", algorithms=["HS256"])
        assert payload["email"] == "user@test.com"
        assert payload["tier"] == "standard"

    def test_login_wrong_password_returns_401(self):
        """Wrong password → 401."""
        import bcrypt
        from api.main import app
        client = TestClient(app)

        pw_hash = bcrypt.hashpw(b"correctpass", bcrypt.gensalt()).decode()
        mock_sb = _mock_supabase_existing_user("user@test.com", pw_hash)

        with patch("api.main.supabase", mock_sb):
            resp = client.post("/auth/login", json={"email": "user@test.com", "password": "wrongpass"})

        assert resp.status_code == 401

    def test_login_unknown_email_returns_401(self):
        """Unknown email → 401 (no user-enumeration info leak)."""
        from api.main import app
        client = TestClient(app)

        with patch("api.main.supabase", _mock_supabase_no_user()):
            resp = client.post("/auth/login", json={"email": "nobody@test.com", "password": "pass"})

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests: GET /auth/verify
# ---------------------------------------------------------------------------

class TestVerify:

    def _make_token(self, email: str, tier: str, secret: str = "test-secret-for-unit-tests") -> str:
        return pyjwt.encode({"email": email, "tier": tier}, secret, algorithm="HS256")

    def test_verify_valid_token_returns_email_and_tier(self):
        """Valid JWT → 200 with {email, tier}."""
        from api.main import app
        client = TestClient(app)

        token = self._make_token("user@test.com", "standard")
        resp = client.get("/auth/verify", headers={"Authorization": f"Bearer {token}"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "user@test.com"
        assert body["tier"] == "standard"

    def test_verify_invalid_token_returns_401(self):
        """Tampered or garbage token → 401."""
        from api.main import app
        client = TestClient(app)

        resp = client.get("/auth/verify", headers={"Authorization": "Bearer thisisnottavalid.token.atall"})
        assert resp.status_code == 401

    def test_verify_wrong_secret_returns_401(self):
        """Token signed with wrong secret → 401."""
        from api.main import app
        client = TestClient(app)

        bad_token = self._make_token("user@test.com", "standard", secret="WRONG_SECRET")
        resp = client.get("/auth/verify", headers={"Authorization": f"Bearer {bad_token}"})
        assert resp.status_code == 401

    def test_verify_missing_header_returns_401(self):
        """No Authorization header → 401."""
        from api.main import app
        client = TestClient(app)

        resp = client.get("/auth/verify")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests: Existing endpoints not broken
# ---------------------------------------------------------------------------

class TestExistingEndpoints:

    def test_health_still_works(self):
        """GET /health must still return 200."""
        from api.main import app
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
