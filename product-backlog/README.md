# Voice Support Bot - Product Backlog

This folder is the local product backlog for Voice Support Bot. It keeps the
V1 epics, user stories, product decisions and open questions in Markdown before
any future Jira migration.

## V1 Product Baseline

The canonical V1 is an operator invoice explanation assistant for end users.
It is available by phone and web voice chat, reads billing evidence from the BSS,
compares two invoices or billing periods, identifies the business causes of price
deltas, and produces a clear, reliable, traceable spoken explanation.

The broad telecom support assistant remains the reusable product foundation.
The V1 value focus is billing/BSS invoice explanation, as defined by
`docs/product/v1-scope.md` and ADR-0017. Voice latency and escalation behavior
are governed by ADR-0018 and ADR-0019.

## Backlog Layers

| Layer | File | Role |
|---|---|---|
| Product scope | `docs/product/v1-scope.md` | Canonical V1 value slice and success criteria |
| Product epics and stories | `product-backlog/` | Business-level backlog, acceptance criteria and open questions |
| Technical / operations backlog | `docs/operations/backlog.md` | Engineering work, pilot gates and post-MVP roadmap |
| BSS contract planning | `docs/integrations/galaxion/` | Evidence sources, mock fixtures and missing external inputs |

## Product / Business Principles

- Stay at the level of problem, value, business rules and observable acceptance.
- Do not describe APIs, schemas, tables, frameworks or implementation details in
  product stories unless an ADR has made them product-visible contracts.
- Do not invent missing facts; record them as open questions or blockers.
- Keep acceptance criteria observable by a customer, advisor, auditor, product
  owner, billing expert or security stakeholder.
- Link business rules to acceptance scenarios and to the ADRs that govern them.

## V1 Classification

| Classification | Meaning |
|---|---|
| `V1 core` | Directly delivers the invoice explanation value proposition |
| `V1 enabler` | Required to deliver V1 safely or coherently |
| `V1 pilot gate` | Required to validate the pilot before production-grade claims |
| `Post-MVP` | Valuable later, not required for the first V1 slice |
| `Replaced / done` | Already delivered or superseded by accepted decisions |

## Structure

```text
backlog-index.md
epics/v1-epics.md
stories/v1-user-stories.md
decisions/v1-decisions.md
open-questions/v1-open-questions.md
```

## States

- `Draft`: still needs product review.
- `Ready for review`: ready for Product / Architecture / Security review.
- `Ready for delivery split`: business scope is stable enough to split into
  technical tasks.
- `Blocked`: external decision or input required.
- `Done`: delivered or replaced by a stronger artifact such as an ADR.

Every story must reference its parent epic and include product-language
acceptance criteria.
