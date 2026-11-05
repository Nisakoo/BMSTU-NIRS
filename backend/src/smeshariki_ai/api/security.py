"""Cross-site request protections of the HTTP API (see docs/auth.md)."""

import logging

from fastapi import Request, status
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from smeshariki_ai.observability import log_event

logger = logging.getLogger(__name__)

_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_CROSS_SITE_VALUES = frozenset({"cross-site", "same-site"})
_JSON_MEDIA_TYPE = "application/json"


class ForbiddenOriginMiddleware:
    """Reject unsafe ``/api`` requests that a browser marks as cross-site.

    Only ``Sec-Fetch-Site`` is used: reverse proxies such as the Vite dev proxy
    rewrite ``Host``, so comparing ``Origin`` with it would break legitimate
    traffic. Requests without the header (non-browser clients) pass.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] in _UNSAFE_METHODS
            and (scope["path"] == "/api" or scope["path"].startswith("/api/"))
            and _fetch_site(scope) in _CROSS_SITE_VALUES
        ):
            log_event(
                logger,
                logging.WARNING,
                "http.request.forbidden_origin",
                method=scope["method"],
                outcome="rejected",
            )
            response = JSONResponse(
                {"error": "forbidden_origin"}, status_code=status.HTTP_403_FORBIDDEN
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def has_json_body(request: Request) -> bool:
    """Return whether the request declares an ``application/json`` body.

    A rejection is logged without the header value.
    """

    media_type = request.headers.get("content-type", "").split(";", 1)[0]
    if media_type.strip().lower() == _JSON_MEDIA_TYPE:
        return True
    log_event(
        logger,
        logging.INFO,
        "http.request.unsupported_media_type",
        method=request.method,
        outcome="rejected",
    )
    return False


def _fetch_site(scope: Scope) -> str:
    for name, value in scope["headers"]:
        if name == b"sec-fetch-site":
            return value.decode("latin-1").strip().lower()
    return ""
