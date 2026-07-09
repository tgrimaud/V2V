# Development Workflow

## Objective

This workflow defines how a V1 user story moves from backlog to accepted work on
the restart branch. It keeps product intent, implementation, QA, adversarial
review and latency evidence connected throughout delivery.

The rule is simple: a story is not done because code was written. A story is done
when Product intent is covered, QA evidence exists, adversarial review is
satisfied, and observed latency or unmeasured gaps are reported.

## Ticket And Branch Discipline

No development starts without an explicit ticket.

If the user asks to fix, add or change something without referencing an existing
ticket, create the ticket first, get the scope clear enough for delivery, then
start implementation. This applies to user stories, bugs, technical tasks,
documentation changes that affect delivery, and process/tooling changes.

Each development ticket uses its own branch:

- user story branch: `us/US-XXX-short-name`;
- bug fix branch: `fix/BUG-XXX-short-name`;
- technical task branch: `task/TASK-XXX-short-name`.

The branch name must include the ticket id. Do not group unrelated tickets in one
branch. If QA finds bugs during a story, create explicit bug tickets and fix each
bug through the bug ticket lifecycle. Small related fixes may share the same bug
branch only when they are part of the same root defect and QA evidence.

The user remains the final validator. No branch is merged into another delivery
branch or into `main` unless the user explicitly asks for that merge. Passing
developer tests, adversarial review and QA validation makes a branch merge-ready;
it does not authorize the merge.

## OpenTelemetry By Default

Every development that touches runtime behavior must introduce or update the
OpenTelemetry traces, metrics and structured logs needed for monitoring, QA
latency analysis and production troubleshooting.

This applies to backend, voice runtime, frontend-visible runtime journeys,
channel adapters, BSS/PDF access, deterministic comparison, RAG, LLM, TTS and
Genesys handoff code.

At minimum, runtime work must preserve or add:

- a correlation id that follows the user turn across channel, voice runtime,
  backend, evidence retrieval, comparison, LLM, TTS and handoff;
- spans or timing markers for every latency slice touched by the story;
- success, failure, timeout and degraded-mode outcome attributes;
- provider/channel identifiers when they are operationally relevant;
- sanitized error information that is useful for support without exposing
  sensitive customer, invoice or transcript data;
- metrics needed to report p50, p95 and p99 by channel/provider/environment.

If a story is not runtime-affecting, the developer must mark OpenTelemetry as
not applicable in the self-check or review evidence. Missing required
OpenTelemetry instrumentation is a blocking issue for adversarial review and QA
acceptance.

## Roles

| Role | Responsibility | Skill |
|---|---|---|
| Product / Business | Clarify functional intent, acceptance criteria and unresolved product questions | `product-business` |
| Frontend Developer | Implement UI and frontend behavior for web voice, synthesis, evidence and user interaction | `react-frontend-developer` |
| Backend Developer | Implement backend domain, ports/adapters, BSS, comparison, explanation, handoff and observability APIs | `java-backend-developer` |
| QA | Write and run Gherkin acceptance tests, Java Cucumber tests, Python Behave tests, UI checks and latency reports | `qa-functional-latency` |
| Adversarial Code Reviewer | Challenge implementation code, story coverage, tests, observability, security, failure modes and maintainability | `adversarial-code-review` |
| Architect | Resolve boundary, contract, latency, observability or integration questions | `software-architect` |

## Story Lifecycle

### 1. Story Selection And Assignment

For each selected user story:

1. Confirm the story is in `product-backlog/stories/v1-user-stories.md`. If the
   requested work has no ticket, create one before implementation.
2. Create or switch to a dedicated branch named `us/US-XXX-short-name`.
3. Confirm its parent epic and acceptance criteria are still valid.
4. Assign the implementation owner:
   - frontend developer if the story is mostly UI/web interaction;
   - backend developer if the story is mostly domain, BSS, comparison,
     explanation, persistence, handoff, observability or API behavior;
   - both if the story crosses backend and frontend.
5. Assign QA in parallel before development starts.

If the functional behavior is unclear, stop and ask `product-business`. If the
technical boundary is unclear, stop and ask `software-architect`.

### 2. Parallel Development And QA Preparation

The developer and QA work in parallel.

The developer:

- reads the story, parent epic, relevant ADRs and local skill guidance;
- implements the smallest useful slice;
- writes developer-level unit/integration tests for the changed layer;
- adds or updates OpenTelemetry traces, metrics and structured logs for every
  runtime flow touched by the story.

QA:

- writes or updates Gherkin scenarios from the story acceptance criteria;
- prepares Java Cucumber tests for backend/domain behavior when a backend exists;
- prepares Python Behave tests for voice runtime/channel behavior when a voice
  runtime exists;
- defines fixture data and expected outcomes;
- defines the latency slices that should be measured for the story;
- prepares UI validation steps using Chrome DevTools MCP when the story has a
  web UI surface.

QA should not wait for the developer to finish before writing test intent. The
developer may need to adapt implementation boundaries so the QA tests remain
observable.

### 3. Developer Self-Check

Before asking for adversarial review, the developer verifies:

- local tests relevant to the changed area pass;
- acceptance criteria are covered or any gap is explicitly documented;
- no unrelated refactor is mixed into the story;
- OpenTelemetry traces, metrics and structured logs needed by QA and monitoring
  are present, or explicitly marked not applicable for non-runtime work;
- sensitive data is not logged or displayed unnecessarily.

On the restart branch, if the required implementation scaffold does not exist
yet, the first story for that layer includes the scaffold and its minimal tests.

### 4. Adversarial Review Loop

An adversarial code reviewer reviews the implemented story before QA acceptance.

The reviewer uses `adversarial-code-review` and evaluates:

- functional correctness against the story and product scope;
- architecture boundaries and dependency direction;
- failure modes and degraded behavior;
- observability and latency measurement;
- security and sensitive-data handling;
- maintainability, testability and provider replaceability.

The reviewer produces a score from 0 to 100.

| Score | Meaning | Action |
|---:|---|---|
| `< 70` | Not acceptable | Developer fixes before QA execution |
| `70-89` | Conditionally acceptable | Developer fixes all blocking findings and asks for another review |
| `>= 90` | Review satisfied | QA may run acceptance and latency validation |

The developer corrects issues and resubmits until the adversarial reviewer is at
least **90% satisfied** or the remaining concerns are explicitly accepted by
Product/Architecture as known residual risk.

Every **non-blocking** finding (accepted residual risk, deferred improvement or
gated follow-up) MUST be appended to `product-backlog/review-findings.md` before
the branch is declared merge-ready. Blocking findings are fixed before merge and
are not logged there. Each non-blocking finding is either given a follow-up
ticket in `product-backlog/tasks/` when the fix is actionable now, or linked to
the dependency that gates it. This keeps residual risk visible instead of living
only in a review comment or chat.

### 5. QA Execution

QA runs the relevant tests after adversarial review is satisfied:

- Java Cucumber scenarios for backend/domain/component behavior;
- Python Behave scenarios for voice runtime/channel behavior;
- UI validation through Chrome DevTools MCP when a web UI exists;
- fixture-based BSS/PDF and invoice comparison checks;
- latency measurement by pipeline slice when the story touches a measured flow.

QA produces a report using the `qa-functional-latency` report format. The report
must state:

- functional pass/fail per area;
- bugs found;
- untested or unmeasurable items;
- observed latency by slice when applicable;
- residual risks;
- go/no-go recommendation for the story.

### 6. Bug Loop

If QA finds bugs:

1. QA creates an explicit bug ticket using
   `product-backlog/templates/bug-ticket-template.md`.
2. The bug ticket includes story, fixture, expected behavior, actual behavior,
   evidence, severity, priority and correlation id or trace link when available.
3. The developer creates or switches to a dedicated bug branch named
   `fix/BUG-XXX-short-name`.
4. The developer fixes the bug and updates developer tests.
5. Adversarial review runs again for the changed area.
6. QA reruns the failed scenarios and any regression scenarios affected by the
   fix.

This loop continues until QA passes or Product/Architecture explicitly changes
the story scope.

### 7. Completion Gate

A story can move to done only when:

- implementation is complete for the selected scope;
- developer tests pass;
- adversarial review is at least 90% satisfied;
- non-blocking review findings are logged in `product-backlog/review-findings.md`
  with a follow-up ticket or a gating dependency;
- QA acceptance tests pass;
- OpenTelemetry coverage exists for all runtime behavior touched by the story,
  or the story is explicitly marked as not runtime-affecting;
- latency report exists or the story is explicitly marked as not latency-relevant;
- unresolved product or architecture questions are documented;
- documentation and backlog status are updated;
- the user has explicitly validated the branch before any merge.

### 8. Documentation Update If Needed

As the final step of every ticket, review whether the change requires a
documentation update and apply it before the branch is declared merge-ready.

Check, at minimum:

- `docs/` (architecture, ADRs, observability, QA, operations) when behavior,
  boundaries, contracts, latency slices or observability changed;
- `voice-agent/README.md`, `backend` or `frontend` READMEs when run/build/usage
  instructions changed;
- `product-backlog/` status, sprint doc, `review-findings.md` and decision log
  when ticket status, findings or decisions changed;
- `CLAUDE.md` / `AGENTS.md` context when the repository map, stack, conventions
  or gotchas changed;
- `.env.example` when a new configuration variable was introduced.

If no documentation change is required, state that explicitly in the ticket or
review evidence ("documentation not affected"). Silent drift between code and
docs is treated as an incomplete ticket.

## Required Artifacts Per Story

| Artifact | Required When |
|---|---|
| Story implementation | Always, unless the story is documentation-only |
| Dedicated branch | Always |
| Developer tests | Always when code changes |
| Gherkin scenarios | Always for product behavior |
| Java Cucumber tests | Backend/domain behavior exists |
| Python Behave tests | Voice runtime/channel behavior exists |
| Chrome DevTools MCP notes | Web UI behavior exists |
| Adversarial review report | Always before QA acceptance |
| Non-blocking findings logged in `review-findings.md` | Whenever adversarial review raises accepted/deferred/gated findings |
| QA functional and latency report | Always before completion |
| Bug ticket | Every QA defect or defect-like requested fix |
| OpenTelemetry evidence | Story touches runtime behavior |
| Latency table | Story touches voice, backend orchestration, BSS/PDF, comparison, LLM, TTS, channel or Genesys handoff |
| Documentation update (or explicit "not affected") | Always, as the final step of every ticket |

## Escalation Rules

- Ask `product-business` when expected user/advisor behavior, proof threshold,
  wording, business priority or acceptance criteria are unclear.
- Ask `software-architect` when the question concerns boundaries, contracts,
  provider replaceability, observability, Genesys, channel integration or latency
  slices.
- Ask the relevant developer skill when implementation patterns are unclear.
- Ask `qa-functional-latency` when tests, QA report, Gherkin structure, Cucumber,
  Behave, UI validation or latency reporting are unclear.

## Workflow Summary

```text
Select US
  -> Verify/create ticket
  -> Create dedicated branch named after the ticket
  -> Assign frontend/backend developer
  -> Assign QA in parallel
  -> Developer implements + self-checks
  -> QA writes Gherkin/tests/fixtures/latency plan
  -> Adversarial review
      -> if score < 90: developer fixes and review repeats
  -> QA executes functional + latency tests
      -> if bugs: QA creates bug ticket, developer fixes on bug branch,
         adversarial review repeats, QA retests
  -> Update documentation if needed (or state "documentation not affected")
  -> Branch is merge-ready when gates pass
  -> Merge only when the user explicitly asks
```

## Open Process Questions

- Where should adversarial review scores be stored per story: commit comment,
  PR comment, `docs/operations/qa-reports/`, or a future issue tracker?
  (Non-blocking findings now have a home: `product-backlog/review-findings.md`.
  The numeric score storage is still open.)
- Should QA reports live in the repository, in CI artifacts, or in the future
  project management tool?
- Should the 90% adversarial threshold be measured as a numeric score, a checklist
  pass rate, or both?
