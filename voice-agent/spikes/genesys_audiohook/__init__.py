"""THROWAWAY spike (TASK-WEB-025) — Genesys Audio Connector feasibility.

Investigation-only prototype + synthetic-audio latency harness for the Sprint 13
Genesys go/no-go gate (ADR-0049, refines ADR-0040). This package is deliberately
isolated under ``spikes/`` and is **never imported by the production runtime**: it
does not wire into ``web_voice`` / the ADR-0047 async server, and it touches **no
backend business code** (the ADR-0001 boundary invariant holds). Delete after the
gate decision lands.

What it measures on SYNTHETIC / non-PII audio only (DEC-014, synthetic-first):
- the AudioHook ``wss`` transport framing legs (inbound/outbound), and
- the codec transcode budget (PCMU/µ-law ↔ PCM16, L16-8 kHz ↔ PCM16-16 kHz),
reusing the real ``voice_common`` telemetry / pipeline-timing / trace-context so a
Genesys ``conversationId`` maps to one OpenTelemetry trace.

What it CANNOT measure without the live Genesys org (marked ``measured=false`` in the
report, per the US-036 rule): the Genesys cloud legs — ingress, Architect
Call-Audio-Connector fork, and cloud egress. Those need a human to run the Architect
flow (see ``README.md`` / the go/no-go report under ``docs/qa/``).
"""

SPIKE_TICKET = "TASK-WEB-025"
THROWAWAY = True
