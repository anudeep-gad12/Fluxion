"""Grok OAuth routes backed by the official Grok CLI."""

from fastapi import APIRouter

from orchestrator.services.grok_auth import (
    cancel_grok_login,
    get_grok_auth_status,
    logout_grok,
    start_grok_login,
)

router = APIRouter(prefix="/api/auth/grok", tags=["auth"])


@router.get("/status")
async def grok_status():
    """Return Grok OAuth status from local Grok CLI credentials."""
    return await get_grok_auth_status()


@router.post("/login")
async def grok_login():
    """Start the official Grok CLI browser OAuth flow."""
    return await start_grok_login()


@router.post("/cancel")
async def grok_cancel_login():
    """Cancel an in-flight Grok CLI OAuth login process."""
    return await cancel_grok_login()


@router.post("/logout")
async def grok_logout():
    """Clear cached Grok CLI credentials through the official CLI."""
    return await logout_grok()
