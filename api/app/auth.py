from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
import httpx
import logging
from typing import Dict, Any, List
import time

from app.config import settings
from app.schemas import UserInfo

logger = logging.getLogger(__name__)

security_scheme = HTTPBearer(auto_error=True)

# In-memory cache for Keycloak public keys (JWKS)
_jwks_cache: Dict[str, Any] = {}
_jwks_last_fetched: float = 0
JWKS_CACHE_TTL = 300  # 5 minutes

async def fetch_keycloak_jwks(force_refresh: bool = False) -> Dict[str, Any]:
    """Fetches the JSON Web Key Set (JWKS) from Keycloak."""
    global _jwks_cache, _jwks_last_fetched
    current_time = time.time()

    if not force_refresh and _jwks_cache and (current_time - _jwks_last_fetched < JWKS_CACHE_TTL):
        return _jwks_cache

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(settings.keycloak_jwks_url)
            if resp.status_code == 200:
                _jwks_cache = resp.json()
                _jwks_last_fetched = current_time
                logger.info(f"[Auth] Successfully fetched and cached Keycloak JWKS from {settings.keycloak_jwks_url}")
                return _jwks_cache
            else:
                logger.warning(f"[Auth] Keycloak JWKS returned status {resp.status_code}")
    except Exception as e:
        logger.warning(f"[Auth] Failed to reach Keycloak JWKS endpoint ({settings.keycloak_jwks_url}): {e}")

    return _jwks_cache

def _find_rsa_key(jwks: Dict[str, Any], kid: str) -> Dict[str, Any]:
    if jwks and "keys" in jwks:
        for key in jwks["keys"]:
            if key.get("kid") == kid:
                return {
                    "kty": key.get("kty"),
                    "kid": key.get("kid"),
                    "use": key.get("use"),
                    "n": key.get("n"),
                    "e": key.get("e"),
                }
    return {}

async def verify_jwt_token(token: str) -> Dict[str, Any]:
    """
    Verifies and decodes the Keycloak JWT Bearer Token strictly via JWKS RS256 public key.
    """
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid JWT header format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    kid = unverified_header.get("kid")
    if not kid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token header missing key ID ('kid')",
            headers={"WWW-Authenticate": "Bearer"},
        )

    jwks = await fetch_keycloak_jwks()
    rsa_key = _find_rsa_key(jwks, kid)

    # Refresh JWKS once if key ID is not found (handles key rotation or Keycloak restart)
    if not rsa_key:
        jwks = await fetch_keycloak_jwks(force_refresh=True)
        rsa_key = _find_rsa_key(jwks, kid)

    if not rsa_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Public key for kid '{kid}' not found in Keycloak JWKS",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=["RS256"],
            options={
                "verify_aud": False,
                "verify_exp": True,
            },
        )
        payload["_verified_kid"] = kid
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please refresh or login again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token signature verification failed via JWKS: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security_scheme)) -> UserInfo:
    """Dependency that extracts and validates the authenticated user from Keycloak JWT token."""
    token = credentials.credentials
    payload = await verify_jwt_token(token)

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token does not contain a subject (sub) claim",
            headers={"WWW-Authenticate": "Bearer"},
        )

    username = payload.get("preferred_username") or payload.get("email") or "unknown_user"
    email = payload.get("email")

    realm_access = payload.get("realm_access", {})
    roles: List[str] = realm_access.get("roles", [])

    return UserInfo(
        user_id=user_id,
        username=username,
        email=email,
        roles=roles,
        jwks_kid=payload.get("_verified_kid"),
        verified_by_jwks=True
    )

def require_role(role_name: str):
    """Factory dependency to enforce role-based access control (RBAC)."""
    async def role_checker(user: UserInfo = Depends(get_current_user)) -> UserInfo:
        if role_name not in user.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Requires role '{role_name}'"
            )
        return user
    return role_checker
