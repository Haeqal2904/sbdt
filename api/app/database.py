from sqlalchemy import create_engine, Column, Integer, String, Float, JSON, DateTime, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.sql import func
from typing import Generator
import logging

from app.config import settings

logger = logging.getLogger(__name__)

# Primary Engine for Write Operations
primary_engine = create_engine(
    settings.primary_db_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=False
)

# Replica Engine for Read Operations
replica_engine = create_engine(
    settings.replica_db_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=False
)

PrimarySessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=primary_engine)
ReplicaSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=replica_engine)

Base = declarative_base()

class PredictionRecord(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, index=True)
    username = Column(String(100), nullable=True)
    model_name = Column(String(100), nullable=False, default="iris_classifier")
    model_version = Column(String(50), nullable=False, default="v1.0.0")
    features = Column(JSON, nullable=False)
    prediction = Column(String(100), nullable=False)
    confidence = Column(Float, nullable=False)
    probabilities = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

def init_db():
    """Initializes schema on the primary database."""
    try:
        Base.metadata.create_all(bind=primary_engine)
        logger.info("[Database] Primary database schema verified/created.")
    except Exception as e:
        logger.warning(f"[Database] Could not auto-create schema on primary: {e}")

def get_primary_db() -> Generator[Session, None, None]:
    """Dependency for Write operations (Primary DB node)."""
    db = PrimarySessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_replica_db() -> Generator[Session, None, None]:
    """Dependency for Read operations (Replica DB node)."""
    db = ReplicaSessionLocal()
    try:
        yield db
    finally:
        db.close()

def check_node_recovery(engine) -> dict:
    """Checks whether the node is in standby recovery mode (Replica = True, Primary = False)."""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT pg_is_in_recovery()")).scalar()
        server_version = conn.execute(text("SHOW server_version")).scalar()
        return {
            "is_in_recovery": bool(result),
            "role": "Replica (Standby)" if result else "Primary (Write)",
            "server_version": server_version,
            "status": "connected"
        }

