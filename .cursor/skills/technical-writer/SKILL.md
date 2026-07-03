---
name: technical-writer
description: Technical writing skill for creating, editing, translating, reviewing, and maintaining engineering documentation in the Voice Support Bot repository. Use this skill whenever the user asks to write or update docs, architecture notes, integration contracts, README sections, operational guides, technical specifications, diagrams, ADRs, API/BSS notes, or wants documentation wording improved. Use it even when the user writes in French: repository documentation must be written in English, while conversation with the user can remain in French.
---

# Technical Writer

Use this skill when writing or reviewing technical documentation for the Voice
Support Bot repository.

The goal is to produce clear, maintainable English documentation that matches
the current architecture and preserves decisions already made with the user.

## Core Rules

### Write Repository Docs In English

All files under `docs/` must be written in English.

The user may discuss requirements in French. Keep the conversation in the user's
language if useful, but write the document content itself in English.

If editing an existing French document, do not silently mix languages. Either:

- translate the touched section fully to English; or
- tell the user that a larger translation pass is needed if the document is
  mostly French and the request is broad.

### Ground The Doc In Existing Sources

Before writing, read the nearest source-of-truth documents for the topic:

| Topic | Read First |
|-------|------------|
| Architecture / boundaries / ADRs | `docs/architecture/architecture.md`, `docs/architecture/infra-v1.md`, `CLAUDE.md`, `AGENTS.md` |
| Product scope / backlog | `docs/product/v1-scope.md`, `product-backlog/`, and use `product-business` if product requirements are being shaped |
| Galaxion / BSS | `docs/integrations/galaxion/` |
| Knowledge base | `docs/knowledge-base/` |
| Development commands / troubleshooting | `docs/engineering/development-guide.md` |
| Operational follow-ups | `docs/operations/backlog.md` |

Do not invent missing facts to make a document feel complete. Put unknowns in an
explicit "Open Questions", "Missing Inputs", or "To Validate" section.

### Preserve Decisions Already Made

Generalize corrections the user has already made:

- Voice target V1 starts with **Gradium + Pipecat** through
  `voice-agent/agent/bot.py`.
- Web target V1 uses Pipecat WebRTC (`http://localhost:7860`).
- Twilio Media Streams are served through the Pipecat bot in the V1 target.
- `bridge_server.py` is a legacy POC / fallback / comparison path, not the V1
  target.
- Billing V1 uses `billing-api`, not `billing-service`.
- Invoice details are not assumed to be structured unless proven by payloads.
- The invoice PDF must be extracted into deterministic JSON before comparison.
- The LLM must never calculate invoice amounts or infer billing causes directly
  from the PDF.
- Amounts in extraction/comparison contracts should use integer cents when they
  are internal calculation inputs.

### Keep The Audience Clear

Choose the level of detail by audience:

| Audience | Style |
|----------|-------|
| Product / business | Explain outcomes, boundaries, decisions, risks, and open questions. Avoid implementation details unless already baselined. |
| Architecture / engineering | Explain components, dependencies, contracts, flow, trade-offs, and failure modes. |
| Developers | Include precise commands, paths, config keys, expected behavior, and troubleshooting. |
| Operations / delivery | Include readiness, dependencies, risks, owners, and validation steps. |

If a document mixes audiences, split sections clearly.

## Reuse Other Skills

Use specialized skills when the documentation task touches their domain:

- Use `software-architect` for architectural decisions, module boundaries,
  ports/adapters, deployment topology, ADRs, or diagrams explaining system
  structure.
- Use `product-business` for product scope, epics, user stories, acceptance
  criteria, business rules, stakeholder questions, and open-question logs.
- Use `diagram-drawer` when creating, editing, or reviewing Mermaid or Draw.io
  diagrams.
- Use `mermaid-diagrams` for raw Mermaid syntax details when `diagram-drawer`
  needs deeper syntax support.
- Use `drawio-diagrams` when the user asks for editable diagrams, `.drawio`
  files, image export, or diagrams that will be maintained visually.
- Use `java-backend-developer`, `react-frontend-developer`, or
  `test-guidelines` when docs must reflect code/test conventions in those
  areas.

Do not replace these skills. This skill coordinates the documentation layer and
pulls in the domain skill needed for the content.

## Documentation Workflow

1. Identify the document type: README, architecture, ADR, integration contract,
   missing-input list, backlog, runbook, API guide, or technical specification.
2. Read the relevant source-of-truth files.
3. Check whether the change should update an index file such as `docs/README.md`.
4. Write in English with concise headings and stable terminology.
5. Link to related documents instead of duplicating long sections.
6. Mark assumptions and unknowns explicitly.
7. Keep diffs focused: avoid translating or refactoring unrelated sections
   unless the user asked for a full cleanup.
8. After editing Markdown, run a lightweight validation such as `git diff --check`
   and read lints for touched files.

## Standard Sections

Use these section patterns when helpful.

### Integration / Contract Document

```markdown
# [System] [Contract / Integration Plan]

## Objective
## Scope
## Source Systems
## Target Flow
## Contract
## Error Cases
## Missing Inputs
## Open Questions
## Next Steps
```

### Missing Inputs Document

```markdown
# Missing [Domain] Inputs

## Objective
## Priority 1 - [Blocking Inputs]
## Priority 2 - [Validation Inputs]
## Priority 3 - [Operational Inputs]
## What Can Move Forward Without These Inputs
## Related Open Questions
```

### ADR Section

```markdown
### ADR-[number]: [Decision Title]

**Context**:
**Decision**:
**Status**:
**Rationale**:
**Implications**:
```

## Wording Guidelines

- Prefer "target V1", "legacy/fallback", "to validate", "missing input", and
  "source of truth" consistently.
- Avoid overclaiming: use "current working contract", "draft", or "to validate"
  when inputs are still missing.
- Prefer concrete examples over abstract statements when defining contracts.
- Use field names exactly as documented in source systems and JSON examples.
- Keep JSON field names stable and snake_case unless the surrounding contract
  already uses another convention.

## Validation Checklist

Before finishing:

- [ ] The edited documentation is in English.
- [ ] The content matches `CLAUDE.md` and `AGENTS.md`.
- [ ] Target V1 vs legacy/fallback flows are not confused.
- [ ] Missing facts are documented as missing inputs or open questions.
- [ ] Related index or overview docs are updated when a new document is added.
- [ ] Diagram changes, if any, were handled through `diagram-drawer`.
- [ ] `git diff --check` passes.
- [ ] Lints for touched files have no new errors.
