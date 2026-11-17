#!/bin/bash
set -e

echo "[PostgreSQL Primary Init] Setting up replication user and pg_hba.conf..."

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'replicator') THEN
            CREATE ROLE replicator WITH REPLICATION LOGIN PASSWORD 'replica_password';
            RAISE NOTICE 'Replication user created.';
        END IF;
    END
    \$\$;
EOSQL

# Append replication permission to pg_hba.conf
echo "host replication replicator 0.0.0.0/0 scram-sha-256" >> "$PGDATA/pg_hba.conf"

# Reload configuration
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -c "SELECT pg_reload_conf();"

echo "[PostgreSQL Primary Init] Replication configuration completed."

