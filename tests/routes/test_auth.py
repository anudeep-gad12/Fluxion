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
    _cancel_pending_auth_for_session,
    _pending_auth,
    chatgpt_callback,
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


@pytest.mark.asyncio
async def test_callback_releases_oauth_port_on_missing_params():
    """Callback errors should release the temporary Codex OAuth port."""
    with patch("orchestrator.routes.auth.stop_callback_server", new_callable=AsyncMock) as mock_stop:
        response = await chatgpt_callback()

    assert response.status_code == 400
    mock_stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_callback_releases_oauth_port_after_processing():
    """Successful/processed callbacks release the temporary Codex OAuth port."""
    with (
        patch("orchestrator.routes.auth._process_oauth_callback", new_callable=AsyncMock) as mock_process,
        patch("orchestrator.routes.auth.stop_callback_server", new_callable=AsyncMock) as mock_stop,
    ):
        mock_process.return_value = ("ok", 200)
        response = await chatgpt_callback(code="code", state="state")

    assert response.status_code == 200
    mock_process.assert_awaited_once_with("code", "state")
    mock_stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_pending_oauth_for_session_only_removes_matching_states():
    """Cancelling login should remove only this session's pending OAuth states."""
    _pending_auth.clear()
    _pending_auth.update(
        {
            "state-a": {"session_id": "session-a", "created_at": time.time()},
            "state-b": {"session_id": "session-b", "created_at": time.time()},
        }
    )

    with patch("orchestrator.routes.auth.stop_callback_server", new_callable=AsyncMock) as mock_stop:
        cancelled = await _cancel_pending_auth_for_session("session-a")

    assert cancelled == 1
    assert "state-a" not in _pending_auth
    assert "state-b" in _pending_auth
    mock_stop.assert_not_awaited()

    _pending_auth.clear()


@pytest.mark.asyncio
async def test_cancel_pending_oauth_stops_callback_server_when_idle():
    """Cancelling the last pending login should release the temporary callback port."""
    _pending_auth.clear()
    _pending_auth["state-a"] = {"session_id": "session-a", "created_at": time.time()}

    with patch("orchestrator.routes.auth.stop_callback_server", new_callable=AsyncMock) as mock_stop:
        cancelled = await _cancel_pending_auth_for_session("session-a")

    assert cancelled == 1
    assert _pending_auth == {}
    mock_stop.assert_awaited_once()
