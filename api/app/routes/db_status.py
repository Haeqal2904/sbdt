from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text
import logging

from app.database import primary_engine, replica_engine, check_node_recovery
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/db", tags=["Distributed Database Status"])

@router.get("/status")
def get_database_status():
    """
    Examines distributed PostgreSQL topology:
    - Primary Node: Write operations (pg_is_in_recovery = false)
    - Replica Node: Read operations (pg_is_in_recovery = true)
    - Replication Streams: Active connections in pg_stat_replication
    """
    status_report = {
        "primary_node": None,
        "replica_node": None,
        "replication_streams": [],
        "replication_healthy": False
    }

    # Inspect Primary
    try:
        primary_info = check_node_recovery(primary_engine)
        primary_info["host"] = settings.DB_PRIMARY_HOST
        primary_info["port"] = settings.DB_PRIMARY_PORT
        status_report["primary_node"] = primary_info

        # Check replication streams on primary
        with primary_engine.connect() as conn:
            streams = conn.execute(text(
                "SELECT client_addr, state, sync_state, sync_priority FROM pg_stat_replication"
            )).fetchall()
            for row in streams:
                status_report["replication_streams"].append({
                    "client_addr": str(row[0]),
                    "state": row[1],
                    "sync_state": row[2],
                    "sync_priority": row[3]
                })

            if len(status_report["replication_streams"]) > 0:
                status_report["replication_healthy"] = True
    except Exception as e:
        logger.error(f"[DB Status] Failed checking primary: {e}")
        status_report["primary_node"] = {"status": "error", "error": str(e)}

    # Inspect Replica
    try:
        replica_info = check_node_recovery(replica_engine)
        replica_info["host"] = settings.DB_REPLICA_HOST
        replica_info["port"] = settings.DB_REPLICA_PORT
        status_report["replica_node"] = replica_info
    except Exception as e:
        logger.error(f"[DB Status] Failed checking replica: {e}")
        status_report["replica_node"] = {"status": "error", "error": str(e)}

    return status_report

