"""Google OAuth 2 (OpenID Connect) for browser sign-in."""

import logging
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.config import Settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


def _settings_for_auth() -> Settings:
    from app.main import load_settings

    return load_settings()


def _authorize_query(settings: Settings, state: str) -> str:
    q = {
        "client_id": settings.google_oauth_client_id.strip(),
        "redirect_uri": settings.google_oauth_redirect_uri.strip(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(q)}"


@router.get("/auth/google/login")
async def google_login(request: Request) -> RedirectResponse:
    settings = _settings_for_auth()
    if not settings.google_oauth_enabled():
        raise HTTPException(status_code=404, detail="Google sign-in is not configured.")
    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state
    return RedirectResponse(url=_authorize_query(settings, state), status_code=302)


@router.get("/auth/google/callback")
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    settings = _settings_for_auth()
    if not settings.google_oauth_enabled():
        raise HTTPException(status_code=404, detail="Google sign-in is not configured.")

    if error:
        logger.warning("Google OAuth error param: %s", error)
        return RedirectResponse(url="/?auth_error=1", status_code=302)

    if not code or not state:
        return RedirectResponse(url="/?auth_error=1", status_code=302)

    saved = request.session.pop("oauth_state", None)
    if not saved or saved != state:
        logger.warning("Google OAuth state mismatch")
        return RedirectResponse(url="/?auth_error=1", status_code=302)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            token_res = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.google_oauth_client_id.strip(),
                    "client_secret": settings.google_oauth_client_secret.strip(),
                    "redirect_uri": settings.google_oauth_redirect_uri.strip(),
                    "grant_type": "authorization_code",
                },
            )
            if token_res.status_code != 200:
                logger.warning(
                    "Google token exchange failed: %s %s",
                    token_res.status_code,
                    token_res.text[:200],
                )
                return RedirectResponse(url="/?auth_error=1", status_code=302)
            tokens: dict[str, Any] = token_res.json()
            access = tokens.get("access_token")
            if not access or not isinstance(access, str):
                return RedirectResponse(url="/?auth_error=1", status_code=302)

            ui = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access}"},
            )
            if ui.status_code != 200:
                logger.warning(
                    "Google userinfo failed: %s %s",
                    ui.status_code,
                    ui.text[:200],
                )
                return RedirectResponse(url="/?auth_error=1", status_code=302)
            profile: dict[str, Any] = ui.json()
    except httpx.HTTPError:
        logger.exception("Google OAuth HTTP error")
        return RedirectResponse(url="/?auth_error=1", status_code=302)

    sub = profile.get("sub")
    if not sub:
        return RedirectResponse(url="/?auth_error=1", status_code=302)

    request.session["user"] = {
        "sub": str(sub),
        "email": (profile.get("email") or "") if isinstance(profile.get("email"), str) else "",
        "name": (profile.get("name") or "") if isinstance(profile.get("name"), str) else "",
        "picture": (profile.get("picture") or "")
        if isinstance(profile.get("picture"), str)
        else "",
    }
    return RedirectResponse(url="/", status_code=302)


@router.get("/auth/logout")
async def logout(request: Request) -> RedirectResponse:
    settings = _settings_for_auth()
    if not settings.google_oauth_enabled():
        return RedirectResponse(url="/", status_code=302)
    request.session.clear()
    return RedirectResponse(url="/", status_code=302)
