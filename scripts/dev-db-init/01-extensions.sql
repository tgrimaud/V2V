-- Local-dev only (TASK-INFRA-009, ADR-0041). The pgvector container runs this once on first
-- init (empty volume) via /docker-entrypoint-initdb.d/. It replaces the extension creation Spring
-- AI's initialize-schema used to do (now disabled): the Liquibase app changelog creates
-- vector_store, which needs `vector` (embedding type) and `uuid-ossp` (uuid_generate_v4 default).
-- On the pilot the same extensions are created by the superuser bootstrap changelog at Step 4.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
