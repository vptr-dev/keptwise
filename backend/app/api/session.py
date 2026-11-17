"""Session token check: only the app's own window may use the API.

The backend listens on 127.0.0.1, so other computers can't reach it. But
other programs on this PC could. To keep them out:

1. The launcher makes a random token at every start.
2. The window first opens /session/start?token=<token>. That page stores
   the token in a cookie and sends the window on to the home page.
3. Every /api request must then carry that cookie (or, for tools and
   tests, an X-Session-Token header).
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse

SESSION_COOKIE = "sk_session"
TOKEN_HEADER = "X-Session-Token"

router = APIRouter()


def _is_valid(request: Request, candidate: str | None) -> bool:
    """True if candidate matches this run's token (timing-safe compare)."""
    expected: str = request.app.state.session_token
    return candidate is not None and secrets.compare_digest(
        candidate.encode(), expected.encode()
    )


def require_session(request: Request) -> None:
    """FastAPI dependency: reject the request unless it has the token."""
    candidate = request.cookies.get(SESSION_COOKIE) or request.headers.get(
        TOKEN_HEADER
    )
    if not _is_valid(request, candidate):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or wrong session token.",
        )


@router.get("/session/start", include_in_schema=False)
def start_session(request: Request, token: str = "") -> RedirectResponse:
    """Swap the launcher's one-time link for a cookie, then go home.

    Redirecting also removes the token from the address bar.
    """
    if not _is_valid(request, token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Wrong session token."
        )
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,  # page scripts can't read it
        samesite="strict",  # other websites can't make the browser send it
        path="/",
    )
    return response
