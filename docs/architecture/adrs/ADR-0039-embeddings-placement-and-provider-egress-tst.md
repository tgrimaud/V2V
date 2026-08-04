# ADR-0039 - Embeddings placement (Ollama CPU sidecar) and provider egress on eir-ai4cc-tst

- **Status:** Accepted (2026-08-04) - addendum to ADR-0006 (chat/embeddings split) and ADR-0038 §6 (open item)
- **Deciders:** Product owner (Thomas Grimaud), architecture
- **Related:** ADR-0006, ADR-0038, ADR-0030 (CSV connector), ADR-0032 (retrieval/vector store)
- **Sprint:** Sprint 11 (remote deployment) / TASK-INFRA-003

## Context

The backend needs an embedding model (`nomic-embed-text`, **768 dim**) for two
things: the one-shot/periodic KB sync, and a **per-turn query embedding on the
retrieval hot path** (every user turn embeds the query before vector search). The
provided tst inventory has **no Ollama/GPU host**
([`deployment-eir-ai4cc-tst.md`](../../operations/deployment-eir-ai4cc-tst.md)),
and ADR-0038 §6 deferred the placement decision to this ticket.

Two candidates:

- **(a) Ollama `nomic-embed-text` on CPU, co-located** with the backend. 768 dim,
  no storage change, no cloud egress for embeddings.
- **(b) Switch to Mistral embeddings.** 1024 dim → **recreate `vector_store`** +
  full re-sync, and adds cloud egress on the retrieval hot path.

The internet **egress policy** of the tst tenant is an external input (Mistral
chat, Gradium STT/TTS and registry pulls all need controlled egress).

## Decision

### 1. Embeddings run on Ollama, CPU, as a co-located sidecar per backend VM

Each backend VM (`vla-t03/t04`, 4 vCPU / 8 GB) runs an **`ollama` sidecar** in the
backend docker-compose stack (`deploy/compose/backend/docker-compose.yml`),
reachable only over the compose network (`OLLAMA_BASE_URL=http://ollama:11434`,
`expose: 11434`, never published). The `nomic-embed-text` model is **pulled at
deploy time** by Ansible (`docker compose exec ollama ollama pull …`) into a named
volume (`ollama-models`).

Rationale:

- **No storage migration:** stays 768 dim → no `vector_store` DROP, no full re-sync
  (the CLAUDE.md dimension caveat is avoided).
- **No cloud egress for RAG:** embeddings never leave the VM; the KB and query text
  are not sent to a third party.
- **No SPOF / no cross-VM hop on the hot path:** each backend embeds locally, so
  query-embedding latency has no network dependency and one bad VM does not take
  embeddings down for the other.

### 2. Reject Mistral embeddings for the pilot

Option (b) is rejected for V1: the 1024-dim switch forces a `vector_store`
recreation + full re-sync, adds a cloud round-trip to **every** retrieval, and
couples the retrieval hot path to Mistral egress/availability. Revisit only if a
retrieval-quality benchmark (ADR-0032) shows a gain that justifies the cost.

### 3. Resource split on the 8 GB backend VM

Backend and sidecar co-exist on the 8 GB VM: **backend 5 GB / 3.0 CPU**, **ollama
2 GB / 1.0 CPU** (`nomic-embed-text` is a small CPU model). Env-tunable
(`BACKEND_MEMORY/CPUS`, `OLLAMA_MEMORY/CPUS`).

### 4. Provider egress required by the pilot

Embedding **inference** needs no egress (local sidecar); there is no per-query
cloud round-trip. The outbound the pilot needs:

| From tier | Destination | Port | When | Purpose |
|-----------|-------------|------|------|---------|
| Backend (`.105/.106`) | `api.mistral.ai` | 443 | runtime | Chat LLM (Mistral) |
| Voice bridge (`.103/.104`) | Gradium API | 443 | runtime | STT/TTS |
| Backend + voice VMs | container registry (`ghcr.io` or internal) | 443 | deploy | image pulls |
| Backend (`.105/.106`) | `registry.ollama.ai` (+ CDN) | 443 | deploy | one-time `nomic-embed-text` model pull |

Egress may be **direct or via the tenant proxy**; the confirmed allowlist (and
proxy host, if any) is the required platform input, tracked in the deployment doc.

**If Ollama-registry egress is not allowed**, pre-seed the model instead of pulling
it: either bake `nomic-embed-text` into a custom Ollama image, or have Ansible copy
a pre-downloaded model blob into the `ollama-models` volume. Either removes the
deploy-time `registry.ollama.ai` dependency; runtime embedding stays fully local
in all cases.

## Consequences

- The backend stack now runs **two containers** (backend + ollama); deploy pulls
  the model (~275 MB) once into `ollama-models` (needs one-time `registry.ollama.ai`
  egress, or pre-seed the volume/image if that egress is denied), then the first
  `POST /api/knowledge/sync` populates pgvector.
- No vector dimension change; retrieval works with no dimension mismatch (the AC).
- ADR-0038 §6 is resolved; the pilot backend is functional without a GPU host and
  without embedding egress.
- Slightly higher per-VM footprint (2 GB for ollama), absorbed by resizing the
  backend limit from 6 GB to 5 GB.

## Alternatives considered

- **Central Ollama on the DB VM `.102`.** More RAM headroom, one instance, but it
  crosses the platform-managed podman boundary on `.102` and adds a **cross-VM hop
  on the query hot path** plus a shared SPOF. Rejected in favour of per-backend
  sidecars.
- **Mistral embeddings (1024 dim).** Rejected — see §2.
- **Dedicated GPU embeddings host.** Not provisioned and not a pilot prerequisite
  (out of scope, `infra-v1.md` long-term target).

## Related Documents

- ADR-0006, ADR-0038, ADR-0032
- `docs/operations/deployment-eir-ai4cc-tst.md`
- `deploy/compose/backend/docker-compose.yml`, `deploy/ansible/`
