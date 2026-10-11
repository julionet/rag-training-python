#!/bin/sh
# Roda só na primeira subida do banco (volume novo), como superusuário do contêiner.
# Reaproveita sql/setup_admin.sql: cria rag_user, rag_training_db e a extensão vector.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v rag_password="$POSTGRES_PASSWORD" -f /sql/setup_admin.sql
