---
name: adversarial-code-review
description: Adversarial code review skill for reviewing implementation changes before QA acceptance. Use whenever a user story implementation, bug fix, frontend/backend change, test scaffold, observability change, Genesys handoff code, BSS integration, voice runtime, or latency-related code needs a strict review. This skill scores code from 0 to 100 and should block progression to QA until the review is at least 90% satisfied or residual risk is explicitly accepted.
---

# Adversarial Code Review

Use this skill to perform a strict, constructive code review before QA acceptance.
The goal is to catch functional gaps, architectural drift, hidden coupling,
missing tests, weak observability, security issues and maintainability risks
early enough for the developer to fix them.

This is not a polite approval review. It is a delivery gate.

## Review Goal

For each implemented user story, decide whether the change is ready for QA
execution.

The reviewer must:

- compare code behavior against the user story and acceptance criteria;
- verify that implementation respects architecture boundaries;
- verify that tests exist at the right level;
- verify that QA can observe the behavior under test;
- verify that runtime changes emit the required OpenTelemetry traces, metrics and
  structured logs;
- identify bugs, risks and missing evidence;
- assign a numeric satisfaction score from 0 to 100.

## Gate Rule

| Score | Meaning | Workflow action |
|---:|---|---|
| `0-69` | Not acceptable | Developer must fix before QA runs |
| `70-89` | Conditionally acceptable | Developer must fix blocking findings and resubmit |
| `90-100` | Review satisfied | QA may run acceptance and latency validation |

The story may move past review below 90 only if Product or Architecture
explicitly accepts the residual risk and records it in the story or QA report.

## Read First

Before reviewing:

1. Read the target user story from `product-backlog/stories/v1-user-stories.md`.
2. Read the parent epic from `product-backlog/epics/v1-epics.md`.
3. Read relevant ADRs under `docs/architecture/adrs/`.
4. Read `docs/operations/development-workflow.md`.
5. Read relevant implementation skill guidance:
   - `java-backend-developer` for Java backend code;
   - `react-frontend-developer` for frontend code;
   - `qa-functional-latency` for testability and latency reporting;
   - `software-architect` for boundary or integration questions.

If the expected behavior is unclear, stop and ask `product-business`. If the
technical boundary is unclear, stop and ask `software-architect`.

## Review Dimensions

### 1. Functional Alignment

Check whether the implementation satisfies the story, not just the developer's
interpretation.

Look for:

- missing acceptance criteria;
- unsupported happy-path assumptions;
- weak handling of missing/partial evidence;
- incorrect escalation behavior;
- answer wording that overstates certainty;
- UI behavior that does not match the product-visible outcome.

### 2. Architecture And Boundaries

Check whether responsibilities stay in the right layer.

For Voice Support Bot:

- backend owns billing reasoning, RAG, guardrails, escalation policy, handoff
  content and conversation memory;
- voice runtime owns real-time media, STT/TTS integration, turn detection and
  barge-in;
- frontend owns presentation and user interaction;
- Genesys owns contact-center operations, not conversation intelligence;
- BSS access is read-only and goes through typed business boundaries;
- providers are behind replaceable adapters.

### 3. Test Evidence

Check whether the developer provided enough tests for the changed layer.

Expected examples:

- domain unit tests for comparison, evidence rules, proof thresholds and money;
- adapter tests or fakes for BSS, PDF extraction, LLM, Genesys and providers;
- Java Cucumber scenarios for backend acceptance behavior when implemented;
- Python Behave scenarios for voice runtime behavior when implemented;
- frontend tests for customer-visible UI behavior;
- regression tests for bugs fixed during QA loops.

Missing tests are blocking when the code changes product behavior, money,
identity, escalation, security, latency or provider failure handling.

### 4. Observability And Latency

If the story touches runtime behavior, check that QA and Operations can observe
it through OpenTelemetry traces, metrics and structured logs. This is mandatory
even when the story is not primarily about observability.

Expected evidence:

- correlation id continuity;
- OpenTelemetry spans or timing markers for the relevant slice;
- metrics that allow p50, p95 and p99 reporting by channel, provider and
  environment when enough samples exist;
- structured logs with correlation id, story-relevant outcome, component,
  channel/provider and sanitized error context;
- clear success/failure outcome events;
- no sensitive data in logs;
- ability to report p50, p95 and p99 from collected samples;
- explicit marking of unmeasurable slices when scaffolding is not ready yet.

Relevant slices include channel ingress, end-of-turn, STT, backend first action,
BSS/PDF evidence, comparison, RAG, LLM, TTS, channel egress and Genesys handoff.

Missing required OpenTelemetry instrumentation is a blocking finding for runtime
changes and should normally keep the score below 90.

### 5. Failure Modes And Degraded Behavior

Challenge how the implementation behaves when dependencies fail or are slow.

Review:

- missing identity;
- missing, inconsistent, partial or unusable billing evidence;
- BSS/PDF extraction failure;
- LLM slow or unavailable;
- STT/TTS failure;
- Genesys handoff failure;
- duplicate or retried channel messages;
- timeouts and fallback wording.

### 6. Security And Privacy

Check especially:

- sensitive billing data exposure;
- logs containing personal or invoice data;
- advisor context over-sharing;
- identity confidence bypass;
- BSS write operations in V1;
- unsafe test fixtures or committed secrets.

### 7. Maintainability

Flag:

- oversized classes/methods;
- unclear names;
- duplicated business rules;
- brittle sleeps/time assumptions;
- hidden provider coupling;
- unreviewable diffs mixing unrelated concerns.

## Output Format

Always return this structure:

```markdown
## Verdict

Proceed / Fix required / Stop and redesign.

## Satisfaction Score

Score: NN/100
QA gate: Pass / Blocked

## Blocking Findings

| Severity | Finding | Evidence | Required fix |
|---|---|---|---|

## Non-Blocking Findings

| Severity | Finding | Evidence | Recommendation |
|---|---|---|---|

## Story Coverage

| Acceptance criterion | Covered? | Evidence |
|---|---|---|

## Test Evidence

- Developer tests:
- Missing tests:
- QA scenarios to run:

## Observability And Latency

- Relevant slices:
- OpenTelemetry traces:
- Metrics:
- Structured logs:
- Missing:
- Risk:

## Security And Privacy

- Sensitive data risk:
- Identity/access risk:
- Logging risk:

## Required Developer Actions

1. ...

## Residual Risk If Accepted

- ...
```

Lead with blocking findings. Do not bury serious issues in a summary.

## Scoring Guidance

Start from 100 and subtract:

- `-30` to `-50` for a likely functional bug in a core flow;
- `-20` to `-40` for missing handling of insufficient evidence, identity or
  escalation;
- `-20` to `-40` for architecture boundary violations;
- `-15` to `-30` for missing tests on critical behavior;
- `-15` to `-30` for unobservable latency in a measured story;
- `-20` to `-40` for missing required OpenTelemetry traces, metrics or
  structured logs in runtime behavior;
- `-20` to `-50` for security or privacy risk;
- `-5` to `-15` for maintainability issues that slow future delivery.

Scores above 90 require:

- story acceptance criteria covered;
- no blocking bug;
- relevant developer tests present;
- QA can observe the behavior;
- required OpenTelemetry traces, metrics and structured logs are present for
  runtime changes;
- no unaccepted security, privacy or architecture risk.

## Done Criteria For Review

The adversarial review is complete when:

- a score is assigned;
- QA gate status is explicit;
- blocking findings have required fixes;
- missing tests or missing observability are named;
- residual risks are explicit;
- developer has a clear list of next actions.
