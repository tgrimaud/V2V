# Architecture & class diagrams (draw.io)

Editable [draw.io](https://app.diagrams.net) (`.drawio`) versions of every
architecture and class diagram of the project. Open them at
[app.diagrams.net](https://app.diagrams.net) or with the Draw.io Integration
extension in VS Code / Cursor.

> **Branch note:** these diagrams depict the **target** V1 architecture. The
> general solution view (`target-v1-solution.drawio`) was refreshed on 2026-09-30
> (TASK-DOC-009) to reflect the decisions taken since 2026-08-07 — the single
> async mono-port voice runtime (ADR-0047), the answer engine on `:8080`
> (`/converse` + `/converse-stream` SSE), the default LLM provider OpenAI `gpt-5`
> (ADR-0051), the bilingual fr/en KB on Postgres + pgvector (ADR-0048, Liquibase
> ADR-0041), the customer-identity resolution (ADR-0050/0055), the by-reference
> Genesys escalation, and the OpenTelemetry + structured JSON logs observability
> (TASK-OBS-002). The **older** component/class diagrams below still show
> target-only or legacy elements — notably the removed custom WebSocket bridge
> (`bridge_server.py`/`agent/bot.py`) and legacy `/api/conversation/ask*` routes —
> so they do **not** all match the code runnable on `feat/restart-from-scratch`
> (full web Voice2Voice loop: Pipecat + WebRTC under `voice-agent/web_voice`,
> backend `POST /converse` + `POST /converse-stream`, Sprint 11+ deployment
> packaging). For the runnable contract see
> [`../voice-runtime-http-contract.md`](../voice-runtime-http-contract.md) and
> `product-backlog/backlog-index.md`.

| File | Type | Source diagram |
|------|------|----------------|
| [`target-v1-solution.drawio`](./target-v1-solution.drawio) ([PNG](./target-v1-solution.png)) | General target solution | Full target V1 solution view (kept up to date — TASK-DOC-009) |
| [`target-v1-solution-simplified.drawio`](./target-v1-solution-simplified.drawio) ([PNG](./target-v1-solution-simplified.png)) | Simplified target solution | High-level left-to-right flow of the target V1 solution (stakeholder view) |
| [`application-components.drawio`](./application-components.drawio) | Application components | High-level application and external-service view |
| [`architecture-overview.drawio`](./architecture-overview.drawio) | Component / deployment | `docs/architecture/architecture.md` § Architecture Diagram |
| [`hexagonal-architecture.drawio`](./hexagonal-architecture.drawio) | Class / ports & adapters | `docs/architecture/architecture.md` (target ports & adapters) |
| [`voice-streaming-sequence.drawio`](./voice-streaming-sequence.drawio) | Sequence | `docs/architecture/architecture.md` § Voice Mode (SSE streaming) |

The two `target-v1-solution*` diagrams are exported to PNG alongside the `.drawio`
sources (`target-v1-solution.png`, `target-v1-solution-simplified.png`) so they can
be viewed without opening draw.io. Re-export after any edit with the draw.io
desktop CLI: `/Applications/draw.io.app/Contents/MacOS/draw.io --export --format png
--scale 1.5 --border 10 --output <name>.png <name>.drawio`.

Knowledge base diagrams live in `docs/knowledge-base/diagrams/`.

The Mermaid versions embedded in `README.md` and `docs/architecture/architecture.md` remain
the source of truth for inline reading; these `.drawio` files mirror them for
editing and export (PNG/SVG/PDF).
