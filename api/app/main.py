from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.config import settings
from app.database import init_db
from app.routes import health, auth, db_status, inference

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[Startup] Initializing Kapita Distributed ML Service...")
    init_db()
    yield
    logger.info("[Shutdown] Shutting down service...")

app = FastAPI(
    title="Kapita Distributed ML & SSO API Service",
    description="""
## Tugas Proyek Terintegrasi:
- **Distributed Database**: PostgreSQL Primary (Write) & Standby Read-Replica (Read)
- **Single Sign-On (SSO)**: OAuth2 / OIDC token authentication with Keycloak
- **Inference Engine**: ML Model inference serving (Iris Flower Classification)
- **Containerization**: Multi-stage Dockerfile & Docker Compose
    """,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(health.router)
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(db_status.router, prefix=settings.API_V1_PREFIX)
app.include_router(inference.router, prefix=settings.API_V1_PREFIX)

@app.get("/")
def root():
    return {
        "service": settings.APP_NAME,
        "status": "online",
        "documentation": "/docs",
        "health": "/health",
        "endpoints": {
            "health": "GET /health",
            "db_status": f"GET {settings.API_V1_PREFIX}/db/status",
            "auth_token": f"POST {settings.API_V1_PREFIX}/auth/token",
            "user_me": f"GET {settings.API_V1_PREFIX}/auth/me",
            "predict_write": f"POST {settings.API_V1_PREFIX}/predict",
            "history_read": f"GET {settings.API_V1_PREFIX}/predictions"
        }
    }

