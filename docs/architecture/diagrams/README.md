# Architecture & class diagrams (draw.io)

Editable [draw.io](https://app.diagrams.net) (`.drawio`) versions of every
architecture and class diagram of the project. Open them at
[app.diagrams.net](https://app.diagrams.net) or with the Draw.io Integration
extension in VS Code / Cursor.

> **Branch note:** these diagrams depict the **target** V1 architecture (Java
> backend, Pipecat agent, React, bridge). They do **not** represent the code
> runnable on `feat/restart-from-scratch`, where only the Python STT-validation
> slice exists. `target-v1-solution.drawio` is explicitly the target solution.

| File | Type | Source diagram |
|------|------|----------------|
| [`application-components.drawio`](./application-components.drawio) | Application components | High-level application and external-service view |
| [`architecture-overview.drawio`](./architecture-overview.drawio) | Component / deployment | `docs/architecture/architecture.md` § Architecture Diagram |
| [`hexagonal-architecture.drawio`](./hexagonal-architecture.drawio) | Class / ports & adapters | `docs/architecture/architecture.md` (target ports & adapters) |
| [`voice-streaming-sequence.drawio`](./voice-streaming-sequence.drawio) | Sequence | `docs/architecture/architecture.md` § Voice Mode (SSE streaming) |

Knowledge base diagrams live in `docs/knowledge-base/diagrams/`.

The Mermaid versions embedded in `README.md` and `docs/architecture/architecture.md` remain
the source of truth for inline reading; these `.drawio` files mirror them for
editing and export (PNG/SVG/PDF).
