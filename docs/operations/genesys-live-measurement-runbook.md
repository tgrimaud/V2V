# Genesys Audio Connector — Live Cloud-Leg Measurement Runbook (TASK-WEB-025)

## Objective

Give the Genesys team a precise, ordered, copy-pasteable procedure to complete the
**cloud-leg latency measurement** that the synthetic Sprint 13 spike could **not** produce.
The synthetic spike (`docs/qa/task-web-025-genesys-audio-connector-spike-report.md`) proved
the transport/transcode/observability shape and re-scored the ADR-0029 mouth-to-ear budget
to a **FAIL floor** driven by the in-house base latency — but the Genesys **cloud legs**
(ingress, Architect Call-Audio-Connector fork, cloud egress), the **negotiated codec**, the
**15-minute cap** behaviour and the **native barge-in / end-of-turn events** are all
`measured=false` because they need a **live Genesys org**.

This runbook turns the spike report's seven "Manual Genesys-Architect Steps" into an
actionable procedure, then feeds the measured numbers back into the harness to produce a
**live ADR-0029 re-score** and a **GO / NO-GO** verdict.

> **Decouple posture (DEC-015).** Per **DEC-015**, the Genesys connector **build already
> proceeds** independently of this measurement — the ADR-0029 gate is a **separate latency
> workstream** (owned by TASK-BE-033 / TASK-STT-014 / TASK-BE-020). This runbook does **not**
> gate the build. What it governs is (a) any **SLO claim** on the Genesys path and (b) the
> **ADR-0049 `Proposed` → `Accepted`** flip, both of which stay blocked until a re-scored
> **GO** lands **and** the OQ-006 PII-audio residency sign-off is obtained.

## Audience & Prerequisites

**Audience:** the Genesys administrator/architect (Architect flow + Audio Connector
integration), plus one runtime/ops engineer (endpoint exposure + harness re-score).

**Prerequisites before starting:**

| # | Prerequisite | Source / owner |
|---|---|---|
| P1 | A pilot Genesys org with **Architect** access and permission to add an **Audio Connector** integration (available now per **DEC-014**). | Genesys admin |
| P2 | The current **in-house mouth-to-ear p95** to use as the harness base (last measured **~2760 ms**, TASK-WEB-039 — refresh it if TASK-BE-033/STT-014/BE-020 have since landed). | Runtime/ops |
| P3 | A reachable, TLS-terminated **`wss://` endpoint that speaks the AudioHook control/PCM framing** (see Step 1). | Runtime/ops |
| P4 | A **billing advisor queue** (or any pilot test queue) to receive the degraded-path transfer and the session-end handoff. | Genesys admin |
| P5 | **Synthetic / non-PII audio** only for every test call (DEC-014). Do **not** place real customer calls — the PII-audio residency/egress sign-off is a separate OQ-006 item. | Both |
| P6 | The repo checked out with the voice-agent venv ready (`cd voice-agent && python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt`). | Runtime/ops |

## Procedure Overview (maps to the spike report's 7 manual steps)

| Runbook step | Spike-report manual step | Produces |
|---|---|---|
| **Step 1** — Expose the `wss` endpoint | Step 1 | A reachable, authenticated AudioHook endpoint |
| **Step 2** — Build the Architect flow | Steps 2, 5, 6 | Inbound flow + Call Audio Connector fork + degraded branch + `handoff_id` variable |
| **Step 3** — Place 3 concurrent test calls | Steps 3 (calls), 4 (cap) | Live session traffic at the concurrency target |
| **Step 4** — Capture per-leg data | Steps 3 (capture), 4, 6 | Cloud-leg times, codec, cap behaviour, native events, variable limits |
| **Step 5** — Feed the numbers back | Step 7 | Live ADR-0029 re-score JSON |
| **Step 6** — GO / NO-GO + ADR-0049 flip | (report Recommendation) | The verdict and the Accepted-flip decision |

---

## Step 0 — Pre-flight self-test WITHOUT Genesys (TASK-WEB-047, recommended first)

Before involving the Genesys org, validate the endpoint from a **local environment** with the
headless AudioHook client `voice-agent/scripts/genesys_local_client.py`. Everything the
endpoint owns at the transport boundary is Genesys-independent — the **connection-auth
handshake** (X-API-KEY + IETF HTTP Message Signatures HMAC-SHA256, TASK-INFRA-012), the
**`open`/`opened`/`close` control channel** (ADR-0043), the **PCMU/L16 ↔ PCM16/16 kHz codec**,
the **session lifecycle**, the **concurrency ceiling / WS 1013 backpressure** and the **15-min
cap** — so it can be driven without a live org. This de-risks Steps 1–2 (auth, TLS, path,
reachability) before scheduling the Genesys team.

The client signs the handshake **byte-for-byte** as the server's `GenesysConnectionAuthenticator`
rebuilds it, so a successful turn proves the deployed auth + framing are correct.

### 0a. Local bridge (both sides under your control)

```bash
cd voice-agent
export GENESYS_AUDIOHOOK_API_KEY=local-dev-key
export GENESYS_AUDIOHOOK_SECRET=$(python3 -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())")
set -a; . ../.env; set +a   # GRADIUM_* / MISTRAL_* for a real spoken answer
./.venv/bin/python -m web_voice.server --genesys on --backend http \
    --stt-mode streaming --tts-mode streaming &

# drive one turn with a real PCM16/16 kHz mono WAV (say -o q.wav --data-format=LEI16@16000 …)
# credentials are read from the env (same vars as the server) — never pass the secret on argv (`ps`).
./.venv/bin/python scripts/genesys_local_client.py \
    --url ws://127.0.0.1:8090/genesys/audiohook \
    --audio fixtures/long/billing-question.wav --codec L16 --out /tmp/genesys-answer.wav
```

The client prints the control frames (`opened` … `closed`), the bot-audio byte count, the
time-to-first-bot-audio, and saves the answer WAV. Without `--audio` it streams synthetic
non-PII noise (DEC-014) — enough to validate auth + handshake + lifecycle, but it will not
trigger a spoken answer (below the STT onset threshold).

### 0b. Deployed endpoint (self-signed TLS edge)

```bash
# export the vault-rendered secret into the env first (do NOT put it on argv):
export GENESYS_AUDIOHOOK_API_KEY=...  GENESYS_AUDIOHOOK_SECRET=...   # base64 secret
./.venv/bin/python scripts/genesys_local_client.py \
    --url wss://vip-ai4cc-voice-t01.prod.lan/genesys/audiohook --insecure \
    --authority vip-ai4cc-voice-t01.prod.lan \
    --audio speech.wav --codec L16 --out /tmp/genesys-answer.wav
```

**Caveats for the deployed target (TASK-INFRA-012, TO CONFIRM):** the real shared secret is
vault-rendered (you need that exact base64 `GENESYS_AUDIOHOOK_SECRET` to sign), and behind the
HAProxy edge the signed `@request-target`/`@authority` may be rewritten — use `--authority`
(matching the server's `GENESYS_AUDIOHOOK_AUTHORITY`) and, if the path is rewritten,
`--request-target`.

### 0c. What Step 0 CANNOT cover

The cloud legs (ingress / Architect fork / egress), the org-negotiated codec, the native
barge-in/EOT events and the Architect degraded branch still need the live org — they remain
`measured=false` and are exactly what Steps 1–6 below produce.

---

## Step 1 — Expose an AudioHook-speaking `wss` endpoint (reachable + secure)

Genesys **initiates** the connection **from the Genesys cloud to our endpoint**, so the
endpoint must be reachable **inbound** over **`wss://` (WebSocket over TLS, TCP `:443`)** from
the Genesys org's egress IP ranges. This mirrors the pilot's documented Genesys flow
(`docs/operations/flow-requests-eir-ai4cc-tst.md` §3: inbound TCP `:443` wss from Genesys to
the voice VIP).

### 1a. The endpoint is already deployed

The AudioHook transport adapter (TASK-WEB-041) is **shipped and deployed** on the pilot
bridges: `GET /genesys/audiohook` on the ADR-0047 single async server (`:8090`), enabled with
`VOICE_GENESYS=on` (`v0.8.0`; Step 0b self-test PASSED 2026-08-31). It terminates the AudioHook
`wss` handshake, verifies connection auth (see below), and speaks the AudioHook control
vocabulary + audio (**wire = 8 kHz L16 preferred, or PCMU**; the adapter resamples to the
internal PCM16/16 kHz boundary). There is **no listener to stand up** — the per-leg spans and
deterministic `traceparent` are emitted by the shipped adapter. Use
`voice-agent/scripts/genesys_local_client.py` (TASK-WEB-047) to drive it locally or against the
deployed endpoint without a live org.

> **Auth (implemented + self-tested).** Connection auth is the `X-API-KEY` header + IETF HTTP
> Message Signature (HMAC-SHA256) over the AudioHook covered components, verified **before** the
> WS upgrade and fail-closed (TASK-INFRA-012; Step 0b self-test PASSED). Only the **live tenant's**
> exact signing values (header casing, `expires`/`created`/`nonce`) remain TO CONFIRM against the
> org — record the confirmed scheme in the capture template.

### 1b. Expose it through the pilot edge (Option A)

The pilot terminates TLS at HAProxy on the voice VIP and routes to the bridge `:8090`
(ADR-0047). Reuse that path — **no new port**, the AudioHook endpoint is a route on the same
routed `:8090`:

- **Endpoint URL to give Genesys:** `wss://vip-ai4cc-voice-t01.prod.lan/genesys/audiohook`
  (served by the ADR-0047 server; the HAProxy edge passes the path through unchanged — TASK-INFRA-016).
- **Firewall:** allow **inbound TCP `:443`** from the Genesys org egress ranges to the voice
  VIP (`10.195.59.39` / `vip-ai4cc-voice-t01`) — same request shape as
  `flow-requests-eir-ai4cc-tst.md` §3.
- **TLS (open blocker):** the HAProxy edge currently serves a **private-CA** cert for the
  internal `.prod.lan` name on a **private** IP (`10.195.59.39`). Genesys Cloud (public SaaS)
  can neither reach the private IP over the internet nor trust a private CA by default. Resolve
  the network path (interconnect/VPN + internal-CA trust) **or** expose a public FQDN +
  publicly-trusted cert before the live-org test (see `genesys-admin-connection-request.md`
  §4/§8b, items 1 & 3).

### 1c. Verify reachability before touching Architect

From a host on the Genesys side of the firewall (or a stand-in), confirm the `wss` upgrade
returns `101 Switching Protocols` (not the `200` UI page):

```bash
curl -sv --http1.1 -H "Connection: Upgrade" -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: $(openssl rand -base64 16)" \
  https://vip-ai4cc-voice-t01.prod.lan/<audiohook-path> 2>&1 | grep -i '< HTTP'
```

Record the endpoint URL + the confirmed auth scheme in the capture template (Step 4).

---

## Step 2 — Build the Genesys Architect inbound flow

Build a **minimal inbound call flow** in Architect. It has three responsibilities: fork the
call audio to our endpoint, provide a **degraded branch** to a human queue, and carry the
**by-reference handoff** identifier (DEC-013).

### 2a. Inbound flow + Call Audio Connector fork (report step 2)

1. Create/point an **inbound call flow** at a pilot test DID.
2. Configure the **Audio Connector integration** to target the Step 1 endpoint
   (`wss://…/<audiohook-path>` + the confirmed auth). **Record which of the premium
   ≤5-integrations slot it consumes** (R6, DEC-014 concurrency envelope).
3. Add a **Call Audio Connector** action that **forks (and pauses) the flow** to stream the
   call audio bidirectionally to the endpoint. This is the media plane leg the spike could not
   exercise.

### 2b. Degraded-path branch → billing advisor queue (report step 5, R3)

1. On the Call Audio Connector action, add a **failure / timeout branch**: if the endpoint is
   **unavailable or does not respond**, the flow must **fail safe** and **transfer to the
   billing advisor queue** (P4) — never dead air.
2. This is the "endpoint-down → advisor queue" degraded mode (ADR-0049 §5, TASK-WEB-044). You
   will trigger it deliberately in Step 4d.

### 2c. Handoff variable — `handoff_id` + minimal routing metadata (report step 6, DEC-013)

1. Define an **Architect variable / participant attribute** that carries **only** the opaque
   **`handoff_id`** plus the **minimal routing metadata** the pilot trust model permits
   (e.g. a routing skill/language hint). **No inline escalation context and no PII** — the
   full audited `EscalationHandoff` stays backend-owned and is fetched by reference
   (DEC-013 / ADR-0019 / TASK-BE-036).
2. On **session end**, the flow resumes and **routes to the billing advisor queue** carrying
   that variable.
3. **Record the Architect variable/attribute size + type limits** you observe (R5) so
   TASK-BE-036 can size the minimal routing metadata against them.

---

## Step 3 — Place 3 concurrent synthetic / non-PII test calls

The pilot concurrency **target is 3** concurrent Genesys sessions (DEC-014), sized against the
Genesys **premium ≤5-integrations / 1-vCPU-class** envelope (R6).

1. Prepare a **synthetic / non-PII** audio clip that exercises a realistic billing turn
   (a spoken billing question then silence). Reuse a spike fixture or generate one; **never use
   real customer audio** (P5).
2. Place **3 calls at once** to the pilot DID (three softphones, a dialer, or three
   scripted SIP callers), so **3 Audio Connector sessions** are live simultaneously.
3. Keep the calls up for at least one full request/response turn each so the cloud legs and the
   bot answer round trip complete. For the cap test (Step 4c) hold **one** call much longer.
4. Note the **wall-clock start** of the concurrent batch — you will compare the runtime's
   per-session CPU/latency behaviour against the spike's ~2.96× serialization finding.

---

## Step 4 — Capture per cloud leg, codec, cap, and native events

Capture everything under the **Genesys `conversationId`** so it can be stitched to the runtime
and backend spans (the endpoint derives a deterministic `traceparent` from the conversationId —
`voice_common.trace_context`). Use the capture template at the end of this doc.

### 4a. Cloud legs — ingress, fork, egress (report step 3, R1)

For each test call, from **Genesys Analytics / conversation detail** and the endpoint's per-leg
spans, record (ms):

- **`genesys_ingress`** — call answered → Call Audio Connector fork begins.
- **`architect_fork`** — fork begins → first audio frame arrives at our `wss` endpoint.
- **`genesys_egress`** — our last outbound audio frame → caller hears it (cloud egress).

These are the three legs the synthetic harness reports `measured=false`. Report **p50 and p95**
across the calls (aim for enough turns to make p95 meaningful — the synthetic runs used 50).

### 4b. Negotiated codec (report step 3, codec recommendation)

Record the **codec actually negotiated** on the pilot org (**PCMU** µ-law vs **L16**). The
spike recommends **L16 end to end** (resample only; PCMU adds ~5× transport overhead and forces
companding). If the org negotiates PCMU, confirm whether L16 can be forced, and flag the
native-codec requirement for the transcode (R6).

### 4c. 15-minute cap (report step 4, R2)

Hold **one** synthetic call **past ~15 minutes** (or inspect the org's Audio Connector session
policy) and record whether the session is **capped/terminated** and how. Compare against the
**worst-case billing journey** (auth + slow BSS + PDF + hold). Record the decision input:
**fits as-is**, or needs **checkpoint/resume** or **call-back** (TASK-WEB-041/044).

### 4d. Degraded mode (report step 5, R3)

Make the endpoint **unavailable or time out mid-call** (stop the listener, or block it) and
observe Architect: confirm it **fails safe to the billing advisor queue** (Step 2b) and that
the flow resumes cleanly at session end. Record the observed behaviour and the caller
experience (no dead air).

### 4e. Native barge-in / end-of-turn events (report step 3, R4)

During a turn, confirm the **Genesys native events** fire and are received by the endpoint:
`barge-in`, `playback-started` / `playback-completed`, `BotTurnResponse`. These own barge-in /
end-of-turn **on the Genesys path**; the in-house energy/amplitude detectors are disabled there
(ADR-0049 §4, TASK-WEB-042). Record which events were observed.

### 4f. Handoff variable limits (report step 6, R5)

From Step 2c, record the **variable/attribute size + type limits** and confirm the
`handoff_id` + minimal routing metadata fits well within them.

---

## Step 5 — Feed the numbers back into the harness (live re-score)

Re-score ADR-0029 with the **measured** Genesys cloud legs folded in, using the real harness
(`voice-agent/spikes/genesys_audiohook/harness.py`).

> **Flag name:** the base flag is **`--base-mouth-to-ear-ms`** (there is no `--base`
> shorthand). It sets the in-house mouth-to-ear p95 that the Genesys transport/transcode
> overhead stacks on top of.

### 5a. Baseline re-score (in-house p95 only)

```bash
cd voice-agent
./.venv/bin/python spikes/genesys_audiohook/harness.py \
  --base-mouth-to-ear-ms <in-house_p95_ms> \
  --turns 50
```

Use the **current** in-house mouth-to-ear p95 for `<in-house_p95_ms>` (P2 — refresh it if
TASK-BE-033/STT-014/BE-020 have since improved the base; the last known value is ~2760 ms).

### 5b. Full re-score including the measured Genesys cloud legs

The harness models the **transport/transcode** overhead itself; to include the **cloud legs**
in the mouth-to-ear total (report step 7), **add the measured `genesys_ingress + architect_fork
+ genesys_egress` p95 to the base value** you pass in:

```bash
cd voice-agent
# base_with_cloud = in_house_p95 + (genesys_ingress_p95 + architect_fork_p95 + genesys_egress_p95)
./.venv/bin/python spikes/genesys_audiohook/harness.py \
  --base-mouth-to-ear-ms <base_with_cloud_ms> \
  --turns 50 \
  > ../docs/qa/task-web-025-genesys-live-latency.json
```

The output JSON contains, per codec, the `adr_0029_rescore` block (the measured floor p95 and
the pass/fail vs the 1500 ms gate) plus the per-leg report and the concurrency probe. Commit the
JSON next to the synthetic artifact (`docs/qa/task-web-025-genesys-synthetic-latency.json`).

> Also re-run the **concurrency probe** on a **1-vCPU-class runtime** with the **native codec**
> once available, to confirm the target-3 sessions fit the premium ≤5 / 1-vCPU envelope (R6);
> the pure-Python transcode serialized at ~2.96× in the synthetic run.

---

## Step 6 — GO / NO-GO criteria and the ADR-0049 flip

Apply these criteria to the live re-score (Step 5b) and the captures (Step 4):

**GO (SLO-claimable + Accepted-flip eligible) — all must hold:**

1. **Latency:** the re-scored mouth-to-ear **p95 ≤ 1500 ms** (ADR-0029), with the measured
   Genesys cloud legs included.
2. **Codec:** **L16** confirmed workable end to end (or PCMU confirmed within budget with a
   native codec).
3. **15-min cap:** the worst-case billing journey **fits**, or a checkpoint/resume / call-back
   mitigation is defined (R2).
4. **Degraded mode:** endpoint-down **fails safe to the advisor queue**, verified (R3).
5. **Native events:** barge-in / end-of-turn native events **confirmed** on the Genesys path
   (R4).
6. **Concurrency:** **target 3** sessions fit the premium **≤5-integrations / 1-vCPU** envelope
   with the native codec (R6).
7. **Handoff:** `handoff_id` + minimal routing metadata **fits** the Architect variable limits
   (R5).

**On GO + OQ-006 PII-audio residency/egress sign-off:** flip **ADR-0049 `Proposed` →
`Accepted`** (update its Status + the spike-outcome hook), record the resolved OQ-006 items, and
only then may an SLO be claimed on the Genesys path.

**NO-GO (latency still over budget):** the re-scored **p95 > 1500 ms**. Per **DEC-015** this
does **not** stop the Genesys build — it keeps the ADR-0029 gate as a **separate latency
workstream** (TASK-BE-033 model choice / OpenAI key + TASK-STT-014 + TASK-BE-020) and keeps
**ADR-0049 at `Proposed`** with **no SLO claim** on the Genesys path. Re-run this runbook's
Step 5 once the base-latency levers land. If a non-latency criterion (2–7) fails, raise the
specific mitigation ticket (e.g. TASK-WEB-041 for codec/cap, TASK-WEB-044 for degraded mode).

---

## Data Capture Template

Fill one row per test call (and summarise p50/p95 across calls for the cloud legs):

| Field | Value | Source | Report ref |
|---|---|---|---|
| Genesys `conversationId` | | Genesys Analytics | R1 |
| Endpoint URL + auth scheme | | Step 1 | Step 1 |
| Integrations slot consumed (of ≤5) | | Architect integration | R6 |
| `genesys_ingress` p50 / p95 (ms) | | Analytics + endpoint spans | R1 |
| `architect_fork` p50 / p95 (ms) | | Analytics + endpoint spans | R1 |
| `genesys_egress` p50 / p95 (ms) | | Analytics + endpoint spans | R1 |
| In-house base p95 (ms) | | TASK-WEB-039 / re-measure | R1 / P2 |
| Negotiated codec (PCMU / L16) | | Audio Connector session | Codec |
| 15-min cap behaviour | | Long call / org policy | R2 |
| Degraded mode (endpoint-down → queue?) | | Step 4d | R3 |
| Native events observed | | Endpoint spans | R4 |
| Architect variable size/type limits | | Architect | R5 |
| Concurrency (3 sessions) wall/CPU | | Runtime + harness probe | R6 |
| Re-scored mouth-to-ear p95 (ms) | | `harness.py` (Step 5b) | R1 |
| GO / NO-GO | | Step 6 | — |

## Open Items / To Confirm

- **AudioHook auth handshake** — the exact API-key/signature scheme Genesys sends, confirmed
  against the current Genesys AudioHook protocol docs (Step 1a).
- **Audio Connector endpoint path** on the ADR-0047 server (`<audiohook-path>`) — confirmed with
  the runtime engineer once the measurement listener / TASK-WEB-041 adapter is in place.
- **PII-audio residency / egress sign-off** — a **parallel OQ-006 item owned by Security /
  Compliance** (DEC-014); required for the Accepted flip but **not** for this synthetic-audio
  measurement.

## Related Documents

- Spike go/no-go report + the 7 manual steps: [`../qa/task-web-025-genesys-audio-connector-spike-report.md`](../qa/task-web-025-genesys-audio-connector-spike-report.md)
- Synthetic latency artifact: [`../qa/task-web-025-genesys-synthetic-latency.json`](../qa/task-web-025-genesys-synthetic-latency.json)
- Harness + prototype: `voice-agent/spikes/genesys_audiohook/` (`harness.py`, `README.md`)
- Local AudioHook self-test client (Step 0, no live Genesys): `voice-agent/scripts/genesys_local_client.py` (TASK-WEB-047)
- Delivery-shape ADR (stays Proposed): [`../architecture/adrs/ADR-0049-genesys-audio-connector-sprint-13-delivery-shape.md`](../architecture/adrs/ADR-0049-genesys-audio-connector-sprint-13-delivery-shape.md)
- Latency gate: [`../architecture/adrs/ADR-0029-pilot-latency-criterion-real-backend-and-market-baseline.md`](../architecture/adrs/ADR-0029-pilot-latency-criterion-real-backend-and-market-baseline.md)
- Media plane + 3-plane split: [`../architecture/adrs/ADR-0040-genesys-audio-connector-v2v-media-plane.md`](../architecture/adrs/ADR-0040-genesys-audio-connector-v2v-media-plane.md)
- Single async server (endpoint host): [`../architecture/adrs/ADR-0047-single-async-http-websocket-server-one-port.md`](../architecture/adrs/ADR-0047-single-async-http-websocket-server-one-port.md)
- Pilot voice access + edge topology: [`pilot-voice-access.md`](pilot-voice-access.md)
- Genesys inbound flow request (wss/443): [`flow-requests-eir-ai4cc-tst.md`](flow-requests-eir-ai4cc-tst.md)
- Decisions: `../../product-backlog/decisions/v1-decisions.md` — **DEC-012/013/014/015**
- Sprint: `../../product-backlog/sprints/sprint-13-genesys-audio-connector.md`
