from fastapi import APIRouter, HTTPException, Depends, status
import httpx
import logging

from app.config import settings
from app.schemas import TokenRequest, TokenResponse, UserInfo
from app.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["SSO / Authentication"])

@router.post("/token", response_model=TokenResponse)
async def obtain_token(request: TokenRequest):
    """
    Helper proxy to obtain OAuth2/OIDC JWT access token from Keycloak
    using Resource Owner Password Credentials Grant.
    """
    client_id = request.client_id or settings.KEYCLOAK_CLIENT_ID
    client_secret = request.client_secret or settings.KEYCLOAK_CLIENT_SECRET

    token_url = settings.keycloak_token_url
    payload = {
        "grant_type": "password",
        "client_id": client_id,
        "client_secret": client_secret,
        "username": request.username,
        "password": request.password,
        "scope": "openid profile email"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(token_url, data=payload)
            if resp.status_code == 200:
                data = resp.json()
                return TokenResponse(
                    access_token=data["access_token"],
                    token_type=data.get("token_type", "Bearer"),
                    expires_in=data.get("expires_in", 300),
                    refresh_token=data.get("refresh_token"),
                    scope=data.get("scope")
                )
            else:
                logger.error(f"[Auth Route] Keycloak error {resp.status_code}: {resp.text}")
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"Keycloak authentication failed: {resp.text}"
                )
    except httpx.RequestError as e:
        logger.error(f"[Auth Route] Failed to connect to Keycloak at {token_url}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not reach Keycloak SSO service at {token_url}"
        )

@router.get("/me", response_model=UserInfo)
async def get_user_profile(current_user: UserInfo = Depends(get_current_user)):
    """
    Returns information about the currently authenticated SSO user.
    Requires valid Bearer token.
    """
    return current_user

