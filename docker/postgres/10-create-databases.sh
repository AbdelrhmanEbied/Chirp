#!/bin/bash
# Creates one database per service inside a single PostgreSQL container.
#
# Each service still owns its data exclusively: separate database, separate
# credentials-free connection string, separate migration history, no
# cross-database joins or foreign keys. What they share is one server process,
# which keeps local development runnable on a laptop instead of demanding
# nine PostgreSQL containers.
#
# In production each of these becomes its own RDS instance. The only thing
# that changes is the DATABASE_URL handed to each service.
set -euo pipefail

DATABASES="chirp_auth chirp_user chirp_post chirp_graph chirp_timeline chirp_search chirp_notification chirp_messaging chirp_media chirp_moderation"

for db in $DATABASES; do
  echo "creating database ${db}"
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    SELECT 'CREATE DATABASE ${db}'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${db}')\gexec
EOSQL
done
