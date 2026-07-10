# Sprint - STT Validation

## Sprint Objective

Validate the first speech-to-text capability before broader Voice2Voice delivery.

The sprint proves that the system can accept controlled audio, produce a usable
transcript, measure the STT slice independently, and provide QA evidence for
go/no-go decisions.

## Status

**Status:** In review — STT-scope tickets delivered; US-036 (STT scope) pending merge. Residual: TASK-STT-008 live quality/latency run pending real Gradium credentials.
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
| TASK-STT-008 | Connect the Gradium STT provider (fresh implementation) | Technical task | High | Replaces the fixture provider so quality/latency reflect the real STT engine (emerged mid-sprint from RF-003 once Gradium was selected) |

## Ticket Status

| Ticket | Sprint status | Evidence |
|---|---|---|
| US-003 | Done | `docs/architecture/channel-identity-boundary.md`; user validation 2026-07-09 |
| US-019 | Done (STT scope) | STT half delivered & merged: `TASK-WEB-001` (live web mic → Gradium → transcript), QA GO in `docs/qa/web-voice-qa-report.md`. Voice response `TASK-WEB-002` (TTS) and `TASK-WEB-003` (backend bridge) are **deferred out of this STT sprint** per user decision; US-019 as a full Voice2Voice story stays In progress in the backlog. |
| US-036 | Done (STT sprint scope) | `docs/observability/voice-journey-timing.md`; `PipelineTimingReport` reports all six canonical slices with p50/p95/p99 for the instrumented slices (`channel_ingress`, `stt`) and explicit `"measured": false` gaps for the four downstream slices. **STT-sprint scope is complete** (the reporting capability + the STT-path slices are measured); the full 6-slice measurement stays open and is gated by out-of-sprint follow-ups: `end_of_turn`→TASK-STT-009, `backend_first_token`→TASK-WEB-003, `tts_first_audio`/`channel_egress`→TASK-WEB-002. CLI `pipeline_timing_cli`; 6 unit tests + Behave `features/pipeline_timing.feature`. |
| TASK-STT-001 | Done | `voice-agent/stt_validation/`; developer tests; user validation 2026-07-09 |
| TASK-STT-002 | Done | `docs/qa/stt-transcription-quality.md`; quality harness + fixture manifest; 17 tests |
| TASK-STT-003 | Done | `docs/observability/stt-validation-telemetry.md`; spans + LatencyReport + sanitization; 7 tests |
| TASK-STT-004 | Done | `docs/qa/stt-qa-report.md`; Behave `features/stt_validation.feature` (5 scenarios); go/no-go recommendation |
| TASK-STT-008 | In progress | `voice-agent/stt_validation/gradium_provider.py` + `provider_factory.py`; 11 provider tests, live smoke test 2026-07-09 (auth OK, `audio/pcm` content-type fix). Live quality/latency run pending real `GRADIUM_API_KEY` + fixtures; RF-003 stays open until real numbers recorded. |

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
| TASK-WEB-002 / TASK-WEB-003 | Voice response (TTS) and backend/LLM bridge for US-019 are Voice2Voice, not STT validation; deferred out of this sprint per user decision (2026-07-10) |
| US-027 | Full Genesys voice routing is optional and should not block first STT validation |
| Billing comparison stories | STT can be validated with controlled utterances before invoice reasoning is implemented |
| Genesys handoff stories | Handoff is downstream from transcript capture and not needed to prove STT |

## Follow-ups (Out Of Sprint, deliberately scheduled)

These tickets were surfaced by this sprint's delivery or adversarial review but are
**not** part of the STT validation objective. They are candidates for the next
sprint. The last three each close one of US-036's `"measured": false` slices, so
US-036 only becomes globally Done once they are delivered.

| Ticket | Reason it is out of this sprint | Relation to US-036 |
|---|---|---|
| TASK-STT-005 | Bare-identifier redaction hardening (RF-001); STT already sanitizes path-bearing tokens | — |
| TASK-STT-006 | Dedicated `UNAVAILABLE` outcome (RF-004); "no invented transcript" already holds | — |
| TASK-STT-007 | Expand fixtures for statistically meaningful p95/p99 (RF-005) | Sharpens STT-slice percentiles, not a new slice |
| TASK-STT-009 | End-of-turn / VAD detection is a voice-runtime feature, not STT validation | Closes the `end_of_turn` slice |
| TASK-WEB-003 | Backend/LLM bridge is Voice2Voice, not STT | Closes the `backend_first_token` slice |
| TASK-WEB-002 | Voice response (TTS) is Voice2Voice, not STT | Closes `tts_first_audio` + `channel_egress` |

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
| TASK-STT-008 | `task/TASK-STT-008-gradium-stt-provider` |

## Delivery Order

1. US-003 - confirm the channel/runtime/backend responsibility boundary.
2. TASK-STT-001 - create the minimal STT validation scaffold.
3. TASK-STT-003 - add OpenTelemetry evidence for the STT path.
4. TASK-STT-002 - run fixture-based transcription quality validation.
5. TASK-STT-008 - connect the real Gradium STT engine behind the provider protocol.
6. US-019 - connect the validation path to the web voice journey scope.
7. US-036 - verify the voice timing slice evidence is reportable.
8. TASK-STT-004 - produce QA report, Gherkin scenarios and go/no-go decision.

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

- ~~Which STT provider is the first validation target?~~ **Resolved: Gradium**
  (DEC-005, ADR-0002). Connected via a fresh implementation in TASK-STT-008.
- Which languages and accents must be present in the first fixture set?
- What transcript quality threshold is acceptable for the pilot?
- How many fixture samples are required before p95/p99 are meaningful?
