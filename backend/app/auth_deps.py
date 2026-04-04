"""Optional Google OAuth gate for selected routes."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request


def require_google_user_if_enabled(request: Request) -> dict | None:
    from app.main import load_settings

    settings = load_settings()
    if not settings.google_oauth_enabled():
        return None
    user = request.session.get("user")
    if not isinstance(user, dict) or not user.get("sub"):
        raise HTTPException(
            status_code=401,
            detail="Sign in with Google is required to generate videos.",
        )
    return user


GoogleUserDep = Annotated[dict | None, Depends(require_google_user_if_enabled)]
