# Architecture & class diagrams (draw.io)

Editable [draw.io](https://app.diagrams.net) (`.drawio`) versions of every
architecture and class diagram of the project. Open them at
[app.diagrams.net](https://app.diagrams.net) or with the Draw.io Integration
extension in VS Code / Cursor.

| File | Type | Source diagram |
|------|------|----------------|
| [`architecture-overview.drawio`](./architecture-overview.drawio) | Component / deployment | `docs/architecture.md` § Diagramme d'architecture |
| [`hexagonal-architecture.drawio`](./hexagonal-architecture.drawio) | Class / ports & adapters | `README.md` § Diagramme de dépendances (Hexagonal) |
| [`voice-streaming-sequence.drawio`](./voice-streaming-sequence.drawio) | Sequence | `docs/architecture.md` § Mode vocal (SSE streaming) |
| [`knowledge-base.drawio`](./knowledge-base.drawio) | Component (KB) | `docs/architecture.md` § Base de connaissance multi-sources |

The Mermaid versions embedded in `README.md` and `docs/architecture.md` remain
the source of truth for inline reading; these `.drawio` files mirror them for
editing and export (PNG/SVG/PDF).
