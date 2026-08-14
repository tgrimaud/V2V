# ADR-0041: Postgres schema management with Liquibase (versioned bootstrap)

## Status

Accepted (2026-08-14, TASK-INFRA-009). Supersedes the implicit schema-init part of
[ADR-0038](ADR-0038-pilot-deployment-architecture-eir-ai4cc-tst.md) (Hibernate `ddl-auto: update`
+ Spring AI `initialize-schema: true` + ad-hoc superuser SQL at deploy).

## Context

The backend had **no database migration tool**. Two runtime mechanisms created the schema
implicitly on first start:

- **Spring AI `initialize-schema: true`** created `vector_store` (768-dim, HNSW cosine) and — as a
  side effect — ran `CREATE EXTENSION IF NOT EXISTS vector` / `hstore` / `"uuid-ossp"`.
- **Hibernate `ddl-auto: update`** created the `kb_source_state` JPA ledger.

This worked in local dev because the pgvector container's app user (`voicesupport`) is a
**superuser**, so `CREATE EXTENSION` succeeded. It does **not** transfer to the pilot: on the
`eir-ai4cc-tst` Patroni cluster the application role is **unprivileged**, so the Spring AI
`CREATE EXTENSION` path would fail. The first-deploy runbook therefore carried a **manual,
untracked superuser SQL block** (`CREATE DATABASE` / `ROLE` / `EXTENSION` / `GRANT`) at Step 4.

The team wants the Postgres bootstrap **versioned and reproducible via Liquibase YAML shipped in
the backend project**, replacing both the implicit `ddl-auto`/`initialize-schema` behavior and the
ad-hoc SQL.

### The privilege / chicken-and-egg constraint

Liquibase connects **into** a database, **as a login role**. Three operations therefore can never
be performed by the Liquibase that the backend runs at startup as the app user, and must happen
**before** it:

| Operation | Why it cannot be app-startup Liquibase |
|---|---|
| `CREATE DATABASE voicesupport` | Liquibase cannot create the database it is connected to (and `CREATE DATABASE` cannot run inside a transaction). |
| `CREATE ROLE voicesupport LOGIN` | The app connects **as** this role → it must already exist. |
| `CREATE EXTENSION vector` / `uuid-ossp` | Superuser-only (`vector` is not a *trusted* extension); the pilot app role is not a superuser. |

Everything else — `vector_store`, `kb_source_state`, indexes — is ordinary schema DDL that the app
user can own.

## Decision

Split the bootstrap into three phases; keep both Liquibase changelogs **in the backend project**.

1. **App schema — Liquibase at startup, as the app user.**
   `spring.liquibase` runs `classpath:/db/changelog/db.changelog-master.yaml`, which creates:
   - `public.vector_store` reproducing **Spring AI 1.0.0's exact DDL** (verified from
     `spring-ai-pgvector-store-1.0.0.jar`):
     `id uuid DEFAULT uuid_generate_v4() PRIMARY KEY, content text, metadata json,
     embedding vector(768)` + index `spring_ai_vector_index` `USING hnsw (embedding
     vector_cosine_ops)`. Byte-for-byte parity is mandatory — the retrieval/insert path is bound to
     that schema (metadata is `json`, **not** `jsonb`; the `uuid` default is inert because Spring AI
     always supplies the id, but is kept identical to the historical schema).
   - `public.kb_source_state` matching the JPA entity (composite PK `source_type, source_id`).
   Both changesets are guarded by `preConditions … not tableExists` with `onFail: MARK_RAN`, so on a
   **legacy dev DB** (already created by Spring AI) they are recorded as run without re-creating.
   Hibernate is switched to **`ddl-auto: none`** and Spring AI to **`initialize-schema: false`** so
   Liquibase is the single source of truth and no implicit `CREATE EXTENSION` is attempted at
   startup by an unprivileged role.

2. **Privileged bootstrap — a superuser Liquibase changelog, run once at deploy Step 4.**
   `db/changelog/bootstrap/db.changelog-bootstrap.yaml` runs `CREATE EXTENSION IF NOT EXISTS vector`
   + `uuid-ossp` and a defensive `GRANT ALL ON SCHEMA public TO ${app_db_user}`. It is executed by a
   **one-shot `podman run liquibase/liquibase`** container on the data VM toward the Patroni
   **primary**, with **superuser** credentials, and its **own tracking tables**
   (`databasechangelog_bootstrap` / `databasechangeloglock_bootstrap`) so the superuser run never
   collides with the app user's default `databasechangelog`.

3. **Irreducible psql pre-step (superuser).**
   Only `CREATE DATABASE voicesupport`, `CREATE ROLE voicesupport LOGIN PASSWORD …`, and
   `ALTER DATABASE voicesupport OWNER TO voicesupport`. Making the app user the **database owner**
   gives it `CREATE` on `public` on PG15+ (the DB owner is a member of `pg_database_owner`, which
   owns `public`), so the app-startup Liquibase can create its tables and tracking table without
   extra grants.

**Secret boundary (chosen).** The app-user password (`vault_db_password`) is set only in the psql
`CREATE ROLE` and stays **out of every Liquibase changelog and property file**. The bootstrap and
app changelogs contain no secrets.

**Local dev.** The pgvector container creates `vector` + `uuid-ossp` via an init script
(`scripts/dev-db-init/01-extensions.sql` mounted at `/docker-entrypoint-initdb.d/`), replacing the
extension creation Spring AI used to perform. Existing dev volumes are unaffected (the guarded
changesets MARK_RAN).

## Consequences

- The schema is **versioned, tracked and reproducible**; the first-deploy runbook Step 4 loses its
  free-form SQL and becomes a 3-line psql pre-step + one deterministic Liquibase run.
- The pilot no longer depends on the app role being a superuser: extension creation is isolated to
  the superuser bootstrap phase.
- Deploy order is enforced by dependency: extensions (Step 4b) exist before the app changelog
  (Step 6) references `vector(768)` / `uuid_generate_v4()`.
- New dependency `liquibase-core` (Spring Boot BOM-managed) — a version bump now triggers the
  `code-guidelines` regression rule (`mvn test`). `mvn test` stays offline: no `@SpringBootTest`
  boots the context, so Liquibase never contacts a database during the unit suite.
- **Risk:** a divergence between the Liquibase `vector_store` DDL and Spring AI's expected schema
  would break RAG. Mitigated by copying the DDL verbatim from the shipped jar and a schema-parity
  test; re-verify on any Spring AI upgrade.
- **Trade-off:** `ddl-auto: none` (not `validate`) avoids brittle JDBC type-matching between
  Hibernate's `Instant`/`String` mappings and the hand-written DDL; drift detection is deferred to
  a future `validate` hardening once the exact type map is pinned.
- The one-shot bootstrap needs a **superuser DSN** to the primary at Step 4 (same superuser access
  the previous manual SQL already required); documented as a deploy input.

## Alternatives Considered

- **Keep `ddl-auto: update` + `initialize-schema: true` (status quo).** Rejected: not versioned,
  and the implicit `CREATE EXTENSION` fails for the unprivileged pilot role.
- **Everything in Liquibase incl. `CREATE DATABASE`/`ROLE`.** Rejected: Liquibase cannot create the
  DB it connects to nor the login role it uses; and it would force the app-user secret into a
  Liquibase parameter file.
- **Minimal — Liquibase owns only the tables; privileged bootstrap stays psql SQL.** Rejected: the
  explicit ask was to manage the bootstrap (extension/grants) through Liquibase, not free-form SQL.
- **Flyway instead of Liquibase.** Not chosen: Liquibase's YAML changelogs, `preConditions`
  (`tableExists`/`MARK_RAN` for legacy-DB idempotency) and per-run tracking-table override fit the
  two-role split cleanly; the sibling dashboard project already standardizes on Liquibase.
- **Quadlet / init-container for the bootstrap.** Deferred: a one-shot `podman run liquibase` is a
  smaller, auditable Step-4 action consistent with the podman runtime (ADR-0038 addendum).

## Related Documents

- [ADR-0038 — Pilot deployment architecture (eir-ai4cc-tst)](ADR-0038-pilot-deployment-architecture-eir-ai4cc-tst.md)
- [ADR-0039 — Embeddings placement and provider egress (tst)](ADR-0039-embeddings-placement-and-provider-egress-tst.md)
- [First-deploy runbook — Step 4](../../operations/first-deploy-runbook.md)
- [Deployment reference — eir-ai4cc-tst](../../operations/deployment-eir-ai4cc-tst.md)
- Ticket: `product-backlog/tasks/deployment-tasks.md` → TASK-INFRA-009
