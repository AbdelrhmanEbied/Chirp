#!/bin/bash
set -euo pipefail

DATABASES="chirp_auth chirp_user chirp_post chirp_graph chirp_timeline chirp_search chirp_notification chirp_messaging chirp_media chirp_moderation"

for db in $DATABASES; do
  echo "creating database ${db}"
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    SELECT 'CREATE DATABASE ${db}'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${db}')\gexec
EOSQL
done
