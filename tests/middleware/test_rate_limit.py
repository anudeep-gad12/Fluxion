"""Tests for rate limiting middleware."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import Request
from fastapi.testclient import TestClient

from orchestrator.middleware.rate_limit import (
    InMemoryRateLimiter,
    get_client_ip,
    RateLimitMiddleware,
)


class TestInMemoryRateLimiter:
    """Tests for InMemoryRateLimiter."""

    def test_first_request_allowed(self):
        """First request should always be allowed."""
        limiter = InMemoryRateLimiter()
        allowed, remaining, reset = limiter.check_rate_limit(
            ip="192.168.1.1",
            endpoint_key="agent",
            max_requests=10,
            window_seconds=3600,
        )
        assert allowed is True
        assert remaining == 9
        assert reset == 3600

    def test_requests_within_limit(self):
        """Requests within limit should be allowed."""
        limiter = InMemoryRateLimiter()
        for i in range(5):
            allowed, remaining, _ = limiter.check_rate_limit(
                ip="192.168.1.1",
                endpoint_key="agent",
                max_requests=10,
                window_seconds=3600,
            )
            assert allowed is True
            assert remaining == 10 - (i + 1)

    def test_requests_exceed_limit(self):
        """Requests exceeding limit should be blocked."""
        limiter = InMemoryRateLimiter()
        # Make 10 requests (max)
        for _ in range(10):
            limiter.check_rate_limit(
                ip="192.168.1.1",
                endpoint_key="agent",
                max_requests=10,
                window_seconds=3600,
            )
        # 11th request should be blocked
        allowed, remaining, _ = limiter.check_rate_limit(
            ip="192.168.1.1",
            endpoint_key="agent",
            max_requests=10,
            window_seconds=3600,
        )
        assert allowed is False
        assert remaining == 0

    def test_different_ips_separate_limits(self):
        """Different IPs should have separate rate limits."""
        limiter = InMemoryRateLimiter()
        # Exhaust limit for IP1
        for _ in range(10):
            limiter.check_rate_limit(
                ip="192.168.1.1",
                endpoint_key="agent",
                max_requests=10,
                window_seconds=3600,
            )
        # IP1 should be blocked
        allowed1, _, _ = limiter.check_rate_limit(
            ip="192.168.1.1",
            endpoint_key="agent",
            max_requests=10,
            window_seconds=3600,
        )
        # IP2 should still be allowed
        allowed2, _, _ = limiter.check_rate_limit(
            ip="192.168.1.2",
            endpoint_key="agent",
            max_requests=10,
            window_seconds=3600,
        )
        assert allowed1 is False
        assert allowed2 is True

    def test_different_endpoints_separate_limits(self):
        """Different endpoint types should have separate limits."""
        limiter = InMemoryRateLimiter()
        # Exhaust limit for agent
        for _ in range(10):
            limiter.check_rate_limit(
                ip="192.168.1.1",
                endpoint_key="agent",
                max_requests=10,
                window_seconds=3600,
            )
        # Agent should be blocked
        allowed_agent, _, _ = limiter.check_rate_limit(
            ip="192.168.1.1",
            endpoint_key="agent",
            max_requests=10,
            window_seconds=3600,
        )
        # Chat should still be allowed
        allowed_chat, _, _ = limiter.check_rate_limit(
            ip="192.168.1.1",
            endpoint_key="chat",
            max_requests=30,
            window_seconds=3600,
        )
        assert allowed_agent is False
        assert allowed_chat is True


class TestGetClientIP:
    """Tests for get_client_ip function."""

    def test_direct_connection(self):
        """Should use client.host for direct connections."""
        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.1"

        ip = get_client_ip(request)
        assert ip == "192.168.1.1"

    def test_x_forwarded_for_single(self):
        """Should use X-Forwarded-For when present."""
        request = MagicMock(spec=Request)
        request.headers = {"X-Forwarded-For": "10.0.0.1"}
        request.client = MagicMock()
        request.client.host = "192.168.1.1"

        ip = get_client_ip(request)
        assert ip == "10.0.0.1"

    def test_x_forwarded_for_chain(self):
        """Should use first IP in X-Forwarded-For chain."""
        request = MagicMock(spec=Request)
        request.headers = {"X-Forwarded-For": "10.0.0.1, 10.0.0.2, 10.0.0.3"}
        request.client = MagicMock()
        request.client.host = "192.168.1.1"

        ip = get_client_ip(request)
        assert ip == "10.0.0.1"

    def test_x_real_ip(self):
        """Should use X-Real-IP when X-Forwarded-For not present."""
        request = MagicMock(spec=Request)
        request.headers = {"X-Real-IP": "10.0.0.1"}
        request.client = MagicMock()
        request.client.host = "192.168.1.1"

        ip = get_client_ip(request)
        assert ip == "10.0.0.1"

    def test_no_client(self):
        """Should return 'unknown' when no client info available."""
        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = None

        ip = get_client_ip(request)
        assert ip == "unknown"
