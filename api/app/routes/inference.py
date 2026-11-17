from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
import logging

from app.config import settings
from app.schemas import (
    IrisFeatures,
    PredictionResponse,
    PredictionHistoryListResponse,
    PredictionHistoryItem,
    UserInfo
)
from app.auth import get_current_user
from app.database import get_primary_db, get_replica_db, PredictionRecord
from app.ml_model import inference_engine

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Machine Learning Inference"])


def _get_db_routing_metadata(db: Session, operation: str, configured_host: str) -> dict:
    row = db.execute(text("SELECT inet_server_addr()::text, pg_is_in_recovery()")).first()
    server_ip = row[0] if row else None
    is_in_recovery = bool(row[1]) if row else None
    return {
        "operation": operation,
        "configured_host": configured_host,
        "server_ip": server_ip,
        "is_in_recovery": is_in_recovery,
        "node_role": "Standby Read-Replica" if is_in_recovery else "Primary Write Node"
    }


def _get_auth_metadata(current_user: UserInfo) -> dict:
    return {
        "verified_by_jwks": current_user.verified_by_jwks,
        "jwks_kid": current_user.jwks_kid,
        "jwks_url": settings.keycloak_jwks_url,
        "algorithm": "RS256"
    }


@router.post("/predict", response_model=PredictionResponse, status_code=status.HTTP_201_CREATED)
def predict_and_store(
    features: IrisFeatures,
    current_user: UserInfo = Depends(get_current_user),
    db: Session = Depends(get_primary_db)
):
    """
    ML Inference Endpoint:
    1. Authenticates request via Keycloak SSO Bearer Token (JWKS RS256 verification).
    2. Runs inference using loaded ML model (Iris Flower classification).
    3. Persists inference input, output, and user metadata to Primary Database (Write Routing).
    """
    predicted_class, confidence, probabilities = inference_engine.predict(features)
    input_dict = features.model_dump()

    record = PredictionRecord(
        user_id=current_user.user_id,
        username=current_user.username,
        model_name="iris_classifier",
        model_version=inference_engine.model_version,
        features=input_dict,
        prediction=predicted_class,
        confidence=confidence,
        probabilities=probabilities
    )

    try:
        db.add(record)
        db.commit()
        db.refresh(record)
        routing_proof = _get_db_routing_metadata(db, "WRITE", settings.DB_PRIMARY_HOST)
    except Exception as e:
        db.rollback()
        logger.error(f"[Predict Route] Failed saving to Primary DB: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database write operation failed: {str(e)}"
        )

    return PredictionResponse(
        id=record.id,
        user_id=record.user_id,
        username=record.username,
        model_name=record.model_name,
        model_version=record.model_version,
        input_features=record.features,
        predicted_class=record.prediction,
        confidence=record.confidence,
        probabilities=record.probabilities,
        created_at=record.created_at,
        db_node_written="postgres-primary (Write)",
        auth_verification=_get_auth_metadata(current_user),
        db_routing_proof=routing_proof
    )


@router.get("/predictions", response_model=PredictionHistoryListResponse)
def get_prediction_history(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: UserInfo = Depends(get_current_user),
    db: Session = Depends(get_replica_db)
):
    """
    Reads prediction history exclusively from the Standby Read-Replica Node (Read Routing).
    Demonstrates Read/Write separation and replication transparency.
    """
    try:
        routing_proof = _get_db_routing_metadata(db, "READ", settings.DB_REPLICA_HOST)
        query = db.query(PredictionRecord).order_by(PredictionRecord.id.desc())
        total = query.count()
        records = query.offset(offset).limit(limit).all()

        items = [
            PredictionHistoryItem(
                id=r.id,
                user_id=r.user_id,
                username=r.username,
                model_name=r.model_name,
                model_version=r.model_version,
                features=r.features,
                prediction=r.prediction,
                confidence=r.confidence,
                probabilities=r.probabilities,
                created_at=r.created_at
            )
            for r in records
        ]

        return PredictionHistoryListResponse(
            total=total,
            db_node_read="postgres-replica (Read)",
            auth_verification=_get_auth_metadata(current_user),
            db_routing_proof=routing_proof,
            items=items
        )
    except Exception as e:
        logger.error(f"[History Route] Failed reading from Replica DB: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database read operation failed: {str(e)}"
        )


@router.get("/predictions/{prediction_id}", response_model=PredictionHistoryItem)
def get_prediction_by_id(
    prediction_id: int,
    current_user: UserInfo = Depends(get_current_user),
    db: Session = Depends(get_replica_db)
):
    """
    Reads a single prediction record by ID from the Standby Read-Replica Node.
    """
    record = db.query(PredictionRecord).filter(PredictionRecord.id == prediction_id).first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prediction with ID {prediction_id} not found on replica"
        )
    return PredictionHistoryItem.model_validate(record)
