# Sprint - STT Validation

## Sprint Objective

Validate the first speech-to-text capability before broader Voice2Voice delivery.

The sprint proves that the system can accept controlled audio, produce a usable
transcript, measure the STT slice independently, and provide QA evidence for
go/no-go decisions.

## Status

**Status:** Draft  
**Created:** 2026-07-09  
**Final validator:** User  
**Merge rule:** no branch is merged unless the user explicitly asks.

## Included Tickets

| Ticket | Title | Type | Priority | Sprint role |
|---|---|---|---|---|
| US-003 | Confirm the channel and identity boundary | User story | High | Boundary prerequisite for channel/runtime/backend responsibilities |
| US-019 | Ask from a web voice chat | User story | High | First practical voice channel for STT validation |
| US-036 | Measure key voice journey timings by pipeline slice | User story | High | Required latency and observability gate |
| TASK-STT-001 | Create the voice runtime STT validation scaffold | Technical task | High | Enables repeatable audio fixture processing |
| TASK-STT-002 | Validate STT transcription quality with audio fixtures | Technical task | High | Establishes transcript-quality evidence |
| TASK-STT-003 | Add OpenTelemetry instrumentation for STT validation | Technical task | High | Makes STT latency/outcome observable |
| TASK-STT-004 | Produce the STT QA report and Gherkin scenarios | Technical task | High | Defines QA evidence and readiness report |

## Optional Stretch Ticket

| Ticket | Title | Condition |
|---|---|---|
| US-021 | Interrupt the bot during a spoken answer | Include only if STT validation must also prove user-speech detection during assistant playback |

US-021 is not part of the core STT sprint. It should move to a barge-in or full
Voice2Voice sprint unless the user explicitly decides that interruption detection
is required for this first STT validation.

## Out Of Sprint

| Ticket | Reason |
|---|---|
| US-018 | Phone Voice2Voice adds telephony complexity; validate web voice STT first |
| US-020 | Quick spoken acknowledgement depends more on backend/TTS orchestration than STT |
| US-027 | Full Genesys voice routing is optional and should not block first STT validation |
| Billing comparison stories | STT can be validated with controlled utterances before invoice reasoning is implemented |
| Genesys handoff stories | Handoff is downstream from transcript capture and not needed to prove STT |

## Branch Plan

Each ticket must be implemented on its own branch:

| Ticket | Branch |
|---|---|
| US-003 | `us/US-003-channel-identity-boundary` |
| US-019 | `us/US-019-web-voice-chat` |
| US-036 | `us/US-036-voice-timing-slices` |
| TASK-STT-001 | `task/TASK-STT-001-stt-validation-scaffold` |
| TASK-STT-002 | `task/TASK-STT-002-stt-quality-fixtures` |
| TASK-STT-003 | `task/TASK-STT-003-stt-opentelemetry` |
| TASK-STT-004 | `task/TASK-STT-004-stt-qa-report` |

## Delivery Order

1. US-003 - confirm the channel/runtime/backend responsibility boundary.
2. TASK-STT-001 - create the minimal STT validation scaffold.
3. TASK-STT-003 - add OpenTelemetry evidence for the STT path.
4. TASK-STT-002 - run fixture-based transcription quality validation.
5. US-019 - connect the validation path to the web voice journey scope.
6. US-036 - verify the voice timing slice evidence is reportable.
7. TASK-STT-004 - produce QA report, Gherkin scenarios and go/no-go decision.

## Sprint Acceptance Criteria

```gherkin
Scenario: STT validation sprint is complete
  Given the STT validation sprint tickets are delivered
  When the sprint evidence is reviewed
  Then controlled audio fixtures can produce transcript outcomes
  And STT latency can be isolated from other voice pipeline slices
  And OpenTelemetry evidence includes correlation id, provider, duration, outcome
  And QA has a report with p50, p95 and p99 where sample size allows it
  And all blocking STT defects are captured as bug tickets
```

```gherkin
Scenario: STT readiness decision is possible
  Given QA has completed the STT validation run
  When the user reviews the sprint output
  Then the user can decide whether STT is ready for the next Voice2Voice sprint
  Or identify the blocking defects that must be fixed first
```

## QA Expectations

QA starts in parallel with development and must prepare:

- Gherkin scenarios for short, long, noisy, silent and accented audio where
  fixtures are available;
- expected transcript or transcript-quality criteria per fixture;
- latency report format for STT duration and outcome;
- explicit bug tickets for failed or unstable fixture categories;
- go/no-go recommendation for broader Voice2Voice work.

## Open Questions

- Which STT provider is the first validation target?
- Which languages and accents must be present in the first fixture set?
- What transcript quality threshold is acceptable for the pilot?
- How many fixture samples are required before p95/p99 are meaningful?
