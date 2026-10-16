"""HTTP adapter of the authentication contract described in docs/auth.md.

Errors of these routes use the ``{"error": "<code>"}`` body. The body is parsed
inside the handlers so the format does not leak into other routers.
"""

import math
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from smeshariki_ai.auth import (
    AuthService,
    AuthUnavailableError,
    Credentials,
    InvalidCredentialsError,
    IssuedTokens,
    LoginTakenError,
    UnauthorizedError,
    User,
)

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
ACCESS_COOKIE_PATH = "/"
REFRESH_COOKIE_PATH = "/api/v1/auth"


class AuthHTTPError(Exception):
    def __init__(self, status_code: int, code: str) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code


def _invalid_fields() -> AuthHTTPError:
    return AuthHTTPError(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_fields")


def _unauthorized() -> AuthHTTPError:
    return AuthHTTPError(status.HTTP_401_UNAUTHORIZED, "unauthorized")


def _unavailable() -> AuthHTTPError:
    return AuthHTTPError(status.HTTP_503_SERVICE_UNAVAILABLE, "unavailable")


def install_auth(
    app: FastAPI,
    auth_service: AuthService,
    *,
    cookie_secure: bool,
) -> None:
    app.state.auth_service = auth_service
    app.add_exception_handler(AuthHTTPError, _handle_auth_error)  # type: ignore[arg-type]
    app.include_router(_create_router(auth_service, cookie_secure=cookie_secure))


async def current_user(
    request: Request,
    access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
) -> User:
    """FastAPI dependency that resolves the authenticated user or fails closed."""

    auth_service: AuthService = request.app.state.auth_service
    if not access_token:
        raise _unauthorized()
    try:
        return await auth_service.authenticate(access_token)
    except UnauthorizedError as error:
        raise _unauthorized() from error
    except AuthUnavailableError as error:
        raise _unavailable() from error


def _create_router(auth_service: AuthService, *, cookie_secure: bool) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    def set_tokens(response: Response, tokens: IssuedTokens) -> None:
        now = datetime.now(UTC)
        for name, value, expires_at, path in (
            (
                ACCESS_COOKIE,
                tokens.access_token,
                tokens.access_expires_at,
                ACCESS_COOKIE_PATH,
            ),
            (
                REFRESH_COOKIE,
                tokens.refresh_token,
                tokens.refresh_expires_at,
                REFRESH_COOKIE_PATH,
            ),
        ):
            response.set_cookie(
                name,
                value,
                max_age=max(0, math.ceil((expires_at - now).total_seconds())),
                path=path,
                secure=cookie_secure,
                httponly=True,
                samesite="lax",
            )

    def clear_tokens(response: Response) -> None:
        for name, path in (
            (ACCESS_COOKIE, ACCESS_COOKIE_PATH),
            (REFRESH_COOKIE, REFRESH_COOKIE_PATH),
        ):
            response.delete_cookie(
                name, path=path, secure=cookie_secure, httponly=True, samesite="lax"
            )

    @router.post("/users", status_code=status.HTTP_201_CREATED)
    async def register(request: Request) -> JSONResponse:
        credentials = await _read_credentials(request)
        try:
            user = await auth_service.register(credentials.login, credentials.password)
        except LoginTakenError as error:
            raise AuthHTTPError(status.HTTP_409_CONFLICT, "login_taken") from error
        except AuthUnavailableError as error:
            raise _unavailable() from error
        return JSONResponse(_user_body(user), status_code=status.HTTP_201_CREATED)

    @router.post("/auth/login")
    async def login(request: Request) -> JSONResponse:
        credentials = await _read_credentials(request)
        try:
            result = await auth_service.login(credentials.login, credentials.password)
        except InvalidCredentialsError as error:
            raise AuthHTTPError(
                status.HTTP_401_UNAUTHORIZED, "invalid_credentials"
            ) from error
        except AuthUnavailableError as error:
            raise _unavailable() from error
        response = JSONResponse(_user_body(result.user))
        set_tokens(response, result.tokens)
        return response

    @router.post("/auth/refresh")
    async def refresh(
        refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
    ) -> JSONResponse:
        try:
            if not refresh_token:
                raise UnauthorizedError
            result = await auth_service.refresh(refresh_token)
        except UnauthorizedError:
            response = JSONResponse(
                {"error": "unauthorized"}, status_code=status.HTTP_401_UNAUTHORIZED
            )
            clear_tokens(response)
            return response
        except AuthUnavailableError as error:
            raise _unavailable() from error
        response = JSONResponse(_user_body(result.user))
        set_tokens(response, result.tokens)
        return response

    @router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
    async def logout(
        access_token: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
        refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
    ) -> Response:
        try:
            await auth_service.logout(access_token, refresh_token)
        except AuthUnavailableError as error:
            raise _unavailable() from error
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        clear_tokens(response)
        return response

    @router.get("/users/me")
    async def me(request: Request) -> JSONResponse:
        user = await current_user(request, request.cookies.get(ACCESS_COOKIE))
        return JSONResponse(_user_body(user))

    return router


async def _read_credentials(request: Request) -> Credentials:
    try:
        return Credentials.model_validate_json(await request.body())
    except ValidationError as error:
        raise _invalid_fields() from error


def _user_body(user: User) -> dict[str, str]:
    return {"id": str(user.id), "login": user.login, "role": user.role.value}


async def _handle_auth_error(_: Request, error: AuthHTTPError) -> JSONResponse:
    return JSONResponse({"error": error.code}, status_code=error.status_code)
