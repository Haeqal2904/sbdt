from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime

# ML Inference Schemas
class IrisFeatures(BaseModel):
    sepal_length: float = Field(..., ge=0.0, le=20.0, description="Sepal length in cm", example=5.1)
    sepal_width: float = Field(..., ge=0.0, le=20.0, description="Sepal width in cm", example=3.5)
    petal_length: float = Field(..., ge=0.0, le=20.0, description="Petal length in cm", example=1.4)
    petal_width: float = Field(..., ge=0.0, le=20.0, description="Petal width in cm", example=0.2)

class PredictionResponse(BaseModel):
    id: int
    user_id: str
    username: Optional[str]
    model_name: str
    model_version: str
    input_features: Dict[str, float]
    predicted_class: str
    confidence: float
    probabilities: Optional[Dict[str, float]]
    created_at: datetime
    db_node_written: str = "postgres-primary (Write)"
    auth_verification: Optional[Dict[str, Any]] = None
    db_routing_proof: Optional[Dict[str, Any]] = None

class PredictionHistoryItem(BaseModel):
    id: int
    user_id: str
    username: Optional[str]
    model_name: str
    model_version: str
    features: Dict[str, Any]
    prediction: str
    confidence: float
    probabilities: Optional[Dict[str, float]]
    created_at: datetime

    class Config:
        from_attributes = True

class PredictionHistoryListResponse(BaseModel):
    total: int
    db_node_read: str = "postgres-replica (Read)"
    auth_verification: Optional[Dict[str, Any]] = None
    db_routing_proof: Optional[Dict[str, Any]] = None
    items: List[PredictionHistoryItem]

# Auth & SSO Schemas
class TokenRequest(BaseModel):
    username: str = Field(..., example="student")
    password: str = Field(..., example="student123")
    client_id: Optional[str] = None
    client_secret: Optional[str] = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    refresh_token: Optional[str] = None
    scope: Optional[str] = None

class UserInfo(BaseModel):
    user_id: str
    username: Optional[str] = None
    email: Optional[str] = None
    roles: List[str] = []
    jwks_kid: Optional[str] = None
    verified_by_jwks: bool = True

# Database & System Status Schemas
class NodeStatus(BaseModel):
    host: str
    port: int
    status: str
    role: str
    is_in_recovery: bool
    server_version: Optional[str] = None

class ReplicationStream(BaseModel):
    client_addr: Optional[str] = None
    state: Optional[str] = None
    sync_state: Optional[str] = None
    sync_priority: Optional[int] = None

class DatabaseStatusResponse(BaseModel):
    primary_node: NodeStatus
    replica_node: NodeStatus
    replication_streams: List[ReplicationStream]
    replication_healthy: bool

