"""HTTP login/session helpers. No analysis/pipeline logic."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response as StarletteResponse

from hap_auth import (
    COOKIE_NAME,
    GENERIC_LOGIN_ERROR,
    SessionPrincipal,
    auth_enabled,
    auth_is_configured,
    auth_username,
    cookie_samesite_literal,
    cookie_secure,
    credentials_match,
    issue_session_token,
    log_login_failure,
    log_login_success,
    log_logout,
    parse_session_token,
    session_ttl_seconds,
    validate_auth_configuration,
)
from hap_auth.state import revoked_jtis, throttle

PUBLIC_EXACT = frozenset({"/health", "/healthz", "/auth/login", "/auth/logout", "/auth/me"})


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=1024)


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client:
        return request.client.host
    return "unknown"


def apply_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=session_ttl_seconds(),
        httponly=True,
        secure=cookie_secure(),
        samesite=cookie_samesite_literal(),
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/")


def principal_from_request(request: Request) -> SessionPrincipal | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    return parse_session_token(token, revoked_jtis)


class AuthGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[StarletteResponse]],
    ) -> StarletteResponse:
        if request.method == "OPTIONS":
            return await call_next(request)
        path = request.url.path
        if path in PUBLIC_EXACT:
            return await call_next(request)
        if not auth_enabled():
            return await call_next(request)
        try:
            validate_auth_configuration()
        except AuthConfigError:
            return JSONResponse({"detail": "Authentication is not configured."}, status_code=503)
        principal = principal_from_request(request)
        if principal is None:
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        request.state.principal = principal
        return await call_next(request)


def register_auth_routes(app: FastAPI) -> None:
    @app.post("/auth/login")
    def login(body: LoginBody, request: Request, response: Response) -> dict[str, bool | str]:
        try:
            validate_auth_configuration()
        except AuthConfigError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if not auth_enabled():
            return {"ok": True, "auth_required": False}

        key = client_key(request)
        if throttle.is_blocked(key):
            log_login_failure()
            raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")

        if not credentials_match(body.username, body.password):
            throttle.register_failure(key)
            log_login_failure()
            raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)

        throttle.register_success(key)
        token = issue_session_token(auth_username())
        apply_session_cookie(response, token)
        log_login_success()
        return {"ok": True, "auth_required": True}

    @app.post("/auth/logout")
    def logout(request: Request, response: Response) -> dict[str, bool]:
        principal = principal_from_request(request)
        if principal is not None:
            revoked_jtis.add(principal.jti)
        clear_session_cookie(response)
        log_logout()
        return {"ok": True}

    @app.get("/auth/me")
    def me(request: Request) -> dict[str, bool | str | None]:
        if not auth_enabled():
            return {
                "authenticated": True,
                "auth_required": False,
                "username": None,
            }
        principal = principal_from_request(request)
        return {
            "authenticated": principal is not None,
            "auth_required": True,
            "username": principal.username if principal else None,
        }


def auth_health_fields() -> dict[str, bool]:
    return {
        "auth_required": auth_enabled(),
        "auth_configured": auth_is_configured() if auth_enabled() else True,
    }
