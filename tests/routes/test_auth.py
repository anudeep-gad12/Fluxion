"""Tests for ChatGPT OAuth auth routes."""

import base64
import hashlib
import json
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from orchestrator.routes.auth import (
    _generate_pkce_pair,
    _extract_account_id_from_jwt,
)


class TestPKCE:
    """Tests for PKCE code generation."""

    def test_generate_pkce_pair(self):
        """PKCE pair should have valid verifier and S256 challenge."""
        verifier, challenge = _generate_pkce_pair()

        # Verifier should be between 43 and 128 characters
        assert 43 <= len(verifier) <= 128

        # Challenge should be base64url-encoded SHA256 of verifier
        expected_digest = hashlib.sha256(verifier.encode("ascii")).digest()
        expected_challenge = base64.urlsafe_b64encode(expected_digest).rstrip(b"=").decode("ascii")
        assert challenge == expected_challenge

    def test_pkce_pairs_are_unique(self):
        """Each PKCE pair should be unique."""
        pair1 = _generate_pkce_pair()
        pair2 = _generate_pkce_pair()
        assert pair1[0] != pair2[0]
        assert pair1[1] != pair2[1]


class TestJWTExtraction:
    """Tests for JWT account ID extraction."""

    def _make_jwt(self, payload: dict) -> str:
        """Create a minimal JWT with the given payload."""
        header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256"}).encode()).rstrip(b"=").decode()
        body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
        sig = base64.urlsafe_b64encode(b"fake-signature").rstrip(b"=").decode()
        return f"{header}.{body}.{sig}"

    def test_extract_account_id(self):
        """Should extract chatgpt_account_id from auth claim."""
        token = self._make_jwt({
            "https://api.openai.com/auth": {
                "chatgpt_account_id": "acct_abc123",
            },
            "sub": "user123",
        })

        account_id = _extract_account_id_from_jwt(token)
        assert account_id == "acct_abc123"

    def test_extract_account_id_missing_claim(self):
        """Should return None when auth claim is missing."""
        token = self._make_jwt({"sub": "user123"})
        account_id = _extract_account_id_from_jwt(token)
        assert account_id is None

    def test_extract_account_id_empty_auth_claim(self):
        """Should return None when auth claim exists but has no account_id."""
        token = self._make_jwt({
            "https://api.openai.com/auth": {},
        })
        account_id = _extract_account_id_from_jwt(token)
        assert account_id is None

    def test_extract_account_id_invalid_token(self):
        """Should return None for invalid JWT strings."""
        assert _extract_account_id_from_jwt("not-a-jwt") is None
        assert _extract_account_id_from_jwt("") is None
        assert _extract_account_id_from_jwt("a.b") is None

    def test_extract_account_id_malformed_payload(self):
        """Should return None when payload is not valid JSON."""
        header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
        bad_body = base64.urlsafe_b64encode(b"not-json").rstrip(b"=").decode()
        sig = base64.urlsafe_b64encode(b"sig").rstrip(b"=").decode()
        token = f"{header}.{bad_body}.{sig}"

        assert _extract_account_id_from_jwt(token) is None
