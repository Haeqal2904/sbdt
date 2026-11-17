from fastapi import APIRouter
from sqlalchemy import text
import httpx
import logging

from app.database import primary_engine, replica_engine
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health & Diagnostics"])

@router.get("/health")
async def health_check():
    """
    Comprehensive health check for API, Distributed Databases, and Keycloak SSO.
    """
    services = {
        "api": "healthy",
        "database_primary": "unknown",
        "database_replica": "unknown",
        "keycloak_sso": "unknown"
    }

    # Check Primary DB (Write Node)
    try:
        with primary_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            services["database_primary"] = "healthy"
    except Exception as e:
        logger.error(f"[Health] Primary DB check failed: {e}")
        services["database_primary"] = f"unhealthy: {str(e)}"

    # Check Replica DB (Read Node)
    try:
        with replica_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            services["database_replica"] = "healthy"
    except Exception as e:
        logger.error(f"[Health] Replica DB check failed: {e}")
        services["database_replica"] = f"unhealthy: {str(e)}"

    # Check Keycloak SSO
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.KEYCLOAK_INTERNAL_URL}/health/ready")
            if resp.status_code in [200, 204]:
                services["keycloak_sso"] = "healthy"
            else:
                # Keycloak dev mode may not expose /health/ready, check realm endpoint
                r2 = await client.get(f"{settings.KEYCLOAK_INTERNAL_URL}/realms/{settings.KEYCLOAK_REALM}")
                if r2.status_code == 200:
                    services["keycloak_sso"] = "healthy"
                else:
                    services["keycloak_sso"] = f"degraded (status: {r2.status_code})"
    except Exception as e:
        services["keycloak_sso"] = f"unreachable: {str(e)}"

    overall_status = (
        "healthy"
        if services["database_primary"] == "healthy"
        and services["database_replica"] == "healthy"
        and services["keycloak_sso"] == "healthy"
        else "degraded"
    )

    return {
        "status": overall_status,
        "services": services,
        "config": {
            "primary_host": settings.DB_PRIMARY_HOST,
            "replica_host": settings.DB_REPLICA_HOST,
            "keycloak_realm": settings.KEYCLOAK_REALM
        }
    }

