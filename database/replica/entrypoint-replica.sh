#!/bin/sh
set -e

echo "[PostgreSQL Replica] Initializing Standby Replica Node..."

# Wait until postgres-primary is ready to accept connections
echo "[PostgreSQL Replica] Waiting for postgres-primary to be healthy and accessible..."
until pg_isready -h postgres-primary -p 5432 -U app_user; do
  echo "[PostgreSQL Replica] Waiting for primary database..."
  sleep 2
done

# If PGDATA does not have PG_VERSION, perform initial streaming basebackup
if [ ! -s "$PGDATA/PG_VERSION" ]; then
  echo "[PostgreSQL Replica] Empty PGDATA detected. Performing initial pg_basebackup from primary..."
  rm -rf "${PGDATA:?}"/*

  PGPASSWORD=replica_password pg_basebackup \
    -h postgres-primary \
    -p 5432 \
    -U replicator \
    -D "$PGDATA" \
    -Fp \
    -Xs \
    -R \
    -P

  echo "[PostgreSQL Replica] Base backup completed."
  chown -R postgres:postgres "$PGDATA"
  chmod 700 "$PGDATA"
else
  echo "[PostgreSQL Replica] PGDATA already initialized. Skipping base backup."
fi

echo "[PostgreSQL Replica] Starting PostgreSQL Standby Engine..."
exec docker-entrypoint.sh postgres

