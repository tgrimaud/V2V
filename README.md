# Voice Support Bot

This branch is a **from-scratch restart branch** for the Voice Support Bot V1.

The previous implementation remains preserved on `main` as a backup/reference.
The restart began by removing the old stack and rebuilding from the validated
product and architecture baseline. Through **Sprint 9** the restart has rebuilt a
runnable two-service stack (Python voice runtime + Java conversation backend).

> **Restart history vs current state.** The branch *started* by deleting the old
> `backend/`, `frontend/`, `agent/bot.py`, `bridge_server.py` and Docker Compose.
> Since then the backend, the RAG answer engine, streaming/WebRTC/barge-in and a
> minimal `docker-compose.yml` (Postgres + Ollama) have been **rebuilt** from
> scratch. The only piece **not** rebuilt is the standalone React `frontend/`; the
> web client is now the static page served by the voice runtime (`web_voice/`).

## Current Repository State On This Branch

This branch keeps the product/architecture baseline:

- product scope and backlog;
- architecture decisions and target documentation;
- BSS/Galaxion integration notes;
- knowledge-base content;
- shared agent guidance.

Rebuilt and runnable on this branch today:

- `voice-agent/` — Python voice runtime (STT/TTS/answer loop, streaming, WebRTC);
- `backend/` — Java Spring Boot conversation backend (RAG, guardrails, memory);
- `docker-compose.yml` — Postgres (`pgvector`, port 5433) + Ollama for embeddings.

Not present on this branch:

- the standalone React `frontend/` (superseded by the `web_voice/` static client);
- the legacy `agent/bot.py` and `bridge_server.py` (preserved on `main`).

## What Actually Runs On This Branch Today

A full **web Voice2Voice loop** rebuilt from scratch, delivered through **Sprint 9**
across two services:

**Python voice runtime (`voice-agent/`, default port `8090`):**

- `stt_validation/` — STT (voice-in): fixture + real **Gradium** providers (batch
  REST **and** streaming WebSocket), WER quality scoring, telemetry, per-slice
  timing (US-036).
- `tts_synthesis/` — TTS (voice-out): fixture + real **Gradium** providers, batch
  and **streaming** synthesis.
- `conversation_backend/` — neutral answer seam (`BackendAnswerPort`) with a
  deterministic **stub** (offline) and an **HTTP** adapter (`VOICE_BACKEND_URL`)
  that calls the Java backend, plus the safe **degraded-mode** fallback.
- `voice_pipeline/` + `web_voice/` — HTTP server + batch loop (`POST /api/voice/turn`)
  **and** the streaming **WebRTC** loop (`POST /api/voice/webrtc/offer`) with
  energy-based end-of-turn detection and native **barge-in** interruption.
- `voice_common/` — neutral shared telemetry, sanitization, per-slice timing.

**Java conversation backend (`backend/`, default port `8080`):**

- Hexagonal Spring Boot app: **RAG** retrieval over **pgvector** (Ollama
  `nomic-embed-text`, 768-dim) with domain + audience filters, input/output
  **guardrails** (incl. the DEC-002 no-fabricated-amount invariant), three-band
  retrieval **confidence** policy, conversation **memory**, and per-slice
  correlation-id observability.
- **Chat LLM = Mistral** (`mistral-small-latest`, default; Ollama alternative);
  **embeddings = Ollama** — the two are distinct models.
- Endpoints: `POST /api/conversation/converse`, `/converse-stream`, `/answer`,
  `/retrieve`; `POST /api/knowledge/ingest`, `/sync`; OpenAPI/Swagger UI.

Delivered capability = **audio in → transcript → RAG-grounded answer → spoken
answer out**, streaming or batch, with a single correlation id and per-slice
latency evidence end to end.
**Not yet built** (target only): customer identity, read-only BSS access,
invoice PDF extraction + deterministic comparison, escalation contract + Genesys
handoff, and phone (Twilio) Voice2Voice — see Sprints 10–11.
See `voice-agent/README.md` to run the full stack and
`product-backlog/backlog-index.md` for sprint status.

## V1 Product Outcome

The V1 outcome remains an operator invoice explanation assistant for end users.
It must:

- identify the customer with enough confidence;
- retrieve read-only billing evidence from the BSS or validated fixtures;
- compare two invoices or billing periods deterministically;
- explain the delta with evidence before LLM wording;
- support Voice2Voice by phone and web voice;
- hand off to Genesys with advisor context when the customer asks for a human or
  when the bot cannot answer safely;
- measure latency by pipeline slice before making any production SLO claim.

## Key Documents

| Purpose | File |
|---|---|
| Canonical V1 scope | `docs/product/v1-scope.md` |
| Backlog index | `product-backlog/backlog-index.md` |
| Epics | `product-backlog/epics/v1-epics.md` |
| User stories | `product-backlog/stories/v1-user-stories.md` |
| Product decisions | `product-backlog/decisions/v1-decisions.md` |
| Open questions | `product-backlog/open-questions/v1-open-questions.md` |
| Architecture spine | `docs/architecture/architecture.md` |
| ADRs | `docs/architecture/adrs/` |
| Galaxion/BSS integration | `docs/integrations/galaxion/` |

## Restart Delivery Sequence

The recommended build order is:

1. Reconfirm the product and architecture baseline.
2. Establish customer identity and billing evidence access.
3. Validate BSS/PDF fixtures and extraction status.
4. Build deterministic invoice comparison.
5. Build evidence-backed explanation.
6. Add Voice2Voice journeys.
7. Add Genesys advisor handoff.
8. Add web synthesis and evidence views.
9. Add trust, security and audit controls.
10. Add observability, latency measurement and pilot readiness reporting.

## Git Note

`voice-support-bot` is a separate Git repository nested inside the broader
`BMad` workspace. Work for this project must be committed in this repository,
not in the parent workspace.
