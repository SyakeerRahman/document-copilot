from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    email: str


class InvalidToken(Exception):
    pass


class AuthUnavailable(Exception):
    pass


async def verify_access_token(http: httpx.AsyncClient, token: str) -> CurrentUser:
    # Asking Supabase Auth is slower than verifying the JWT locally, but it also catches
    # revoked sessions and avoids hand-rolled signature checks. Swap here if volume demands it.
    try:
        response = await http.get(
            f"{settings.supabase_url}/auth/v1/user",
            headers={"apikey": settings.supabase_anon_key, "Authorization": f"Bearer {token}"},
        )
    except httpx.HTTPError as exc:
        raise AuthUnavailable("Supabase Auth is unreachable") from exc

    if response.status_code in (400, 401, 403):
        raise InvalidToken
    if response.status_code != 200:
        raise AuthUnavailable(f"Supabase Auth returned {response.status_code}")

    body = response.json()
    return CurrentUser(id=UUID(body["id"]), email=body.get("email") or "")


_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid access token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        return await verify_access_token(request.app.state.http, credentials.credentials)
    except InvalidToken:
        raise unauthorized from None
    except AuthUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Authentication service unavailable"
        ) from exc


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
