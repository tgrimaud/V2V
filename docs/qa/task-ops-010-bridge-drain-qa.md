# QA runbook — TASK-OPS-010 bridge active-session `/drain` (pilot)

> **Scope:** validate the graceful bridge session-drain (BUG-018 fix #3) on the pilot voice
> tier (`vla-ai4cc-t01/t02.prod.lan`). Covers the runtime endpoint, the Ansible deploy wiring,
> the fail-safe degrade path, and the observability evidence. Ticket:
> `product-backlog/tasks/deployment-tasks.md` (TASK-OPS-010). Contract:
> `docs/architecture/voice-runtime-http-contract.md#post-drain`. Drain layering:
> `docs/operations/release-process.md#voice-session-draining`.

## Pilot execution log

**2026-09-29 — baseline run on `vla-ai4cc-t01.prod.lan` (non-destructive S0/S1/S5):**

| Step | Expected | Observed | Verdict |
|---|---|---|---|
| S0 token present | boolean | `VOICE_DRAIN_TOKEN present: False`, `VOICE_DRAIN_TIMEOUT_MS: None` | token not set on the running container |
| S1 `POST /drain` on the deployed image | 503 (token unset) or route | **`HTTP 405 Method Not Allowed`** | **route not mounted** |
| S5 health | `healthy` | `healthy` | ✅ |

Running image: **`ghcr.io/tgrimaud/voice-support-voice:0.9.3`** — predates TASK-OPS-010 (committed
2026-09-29, not merged / not built / not deployed). The `405` (not `503`) is the exact
*not-mounted* contract: the static catch-all is GET-only, so an absent `POST /drain` returns 405
(matches `tests/test_web_voice_app.py::DrainEndpointTest::test_not_mounted_without_controller`).

**Conclusion:** S2/S3/S4/S6 (real drain, drained Gradium/Genesys call, deploy integration,
fail-safe degrade) are **blocked until an OPS-010 image is built + `vault_voice_drain_token` is
set + the tier is redeployed**. Re-run this runbook from S0 after that deploy.

## What is already proven (do not re-run on the pilot)

- **Automated regression (green):** `voice-agent` unit suite **703** + `behave` **15/43/194**.
  Relevant: `tests/test_drain.py` (controller state, bounded wait with injected clock, config),
  `tests/test_web_voice_app.py::DrainEndpointTest` (token gate 503/403, drained, timeout,
  not-mounted), `tests/test_websocket_app.py` (refuse-while-draining → WS 1013 + counter
  registration), `tests/test_voice_openapi.py` (route drift guard).
- **Local live smoke (real aiohttp server + real WS session, 2026-09-29):**
  | Check | Result |
  |---|---|
  | `POST /drain`, server token set, missing/wrong `X-Drain-Token` | `403 forbidden` |
  | `POST /drain`, correct token, 0 active calls | `200 {"status":"drained","remaining":0}` |
  | New WS connect **while draining** | closed with **WS 1013** |
  | `POST /drain` **during an active WS call** (`?timeout_ms=1500`) | `200 {"status":"timeout","active_at_start":1,"remaining":1,"elapsed_ms":≈1501}` |
  | `POST /drain` **after the call hung up** | `200 {"status":"drained","remaining":0}` |

The pilot QA below validates only what the local smoke cannot: the **container-namespace exec
path**, a **real Gradium/Genesys call**, the **deploy integration** (drain.yml bridge drain +
grace fallback), and the **fail-safe degrade**.

## Preconditions

- The genesys-capable voice image is deployed (`VOICE_GENESYS=on`) and the container
  `voice-support-bridge` is `healthy` on the target node.
- **To exercise the exact drain**, `vault_voice_drain_token` must be set in
  `deploy/ansible/group_vars/all/vault.yml` and the voice tier redeployed so the container env
  carries `VOICE_DRAIN_TOKEN`. If it is **unset**, only the fail-safe/degrade scenarios (S6)
  apply — that is itself a valid pilot posture.
- **SSH to the target node first**, then run every `docker exec` / `docker inspect` command
  below **on the node** (avoids triple-nested quoting):
  `ssh -i ~/.ssh/id_itsf grimaud@vla-ai4cc-t01.prod.lan` (raw IPs are unreachable; use the FQDN).
  The Ansible commands (S4) run from `deploy/ansible/` on the **control host** with
  `--vault-password-file .vault_pass`.
- **Never print or hand-write `.env` / vault secrets.** The token is verified only as a
  boolean (present/absent) below; the deploy renders `.env` (root, `0600`, `no_log`).
- **Loopback quirk (TASK-INFRA-011):** `curl http://127.0.0.1:8090/drain` from the host returns
  `000`. Always probe `/drain` **inside the container namespace** (`docker exec … python`),
  exactly as the deploy does.

## Scenarios (Gherkin ↔ acceptance criteria)

### S0 — Token is rendered into the container (secret-safe check)

```gherkin
Scenario: The drain token reaches the container without being printed
  Given the voice tier was deployed with vault_voice_drain_token set
  When I inspect the container env as a boolean
  Then VOICE_DRAIN_TOKEN is present (True) and its value is never printed
```

```bash
# on the node
sudo docker exec -i voice-support-bridge python - <<'PY'
import os
print("VOICE_DRAIN_TOKEN present:", bool(os.environ.get("VOICE_DRAIN_TOKEN")))
print("VOICE_DRAIN_TIMEOUT_MS:", os.environ.get("VOICE_DRAIN_TIMEOUT_MS"))
PY
```
**Expect:** `VOICE_DRAIN_TOKEN present: True` and a timeout value (e.g. `90000`). If `False`,
the token is not in the vault → only S6 applies.

### S1 — Token gate (fail-closed)

```gherkin
Scenario: /drain rejects unauthenticated callers
  Given the bridge is serving on :8090
  When /drain is called with a missing or wrong token
  Then it is refused (403 when a token is configured, 503 when it is not)
    And no session is affected
```

Probe with **no** token header inside the container (the real token is never referenced, so it
cannot leak):
```bash
# on the node — missing token => 403 (token set) OR 503 (token unset)
sudo docker exec -i voice-support-bridge python - <<'PY'
import urllib.request, urllib.error
req = urllib.request.Request("http://localhost:8090/drain", method="POST")
try:
    print("HTTP", urllib.request.urlopen(req, timeout=5).status)
except urllib.error.HTTPError as e:
    print("HTTP", e.code, e.read().decode())
PY
```
**Expect:** `HTTP 403 {"error":"forbidden"}` (token set) or
`HTTP 503 {"error":"drain_not_configured"}` (token unset). *(The deploy's own drain step in S4 is
the authoritative caller with the correct token.)*

### S2 — Exact drain with no active calls

```gherkin
Scenario: A drain on an idle bridge returns drained immediately
  Given no active calls on the bridge
  When the deploy drains it
  Then it reports status=drained and remaining=0
```

Use the **same style the deploy runs** — the token is read from the container env, so it never
appears on the argv:
```bash
# on the node
sudo docker exec -i voice-support-bridge python - <<'PY'
import os, urllib.request
req = urllib.request.Request(
    "http://localhost:8090/drain?timeout_ms=5000", method="POST",
    headers={"X-Drain-Token": os.environ.get("VOICE_DRAIN_TOKEN", "")})
print(urllib.request.urlopen(req, timeout=10).read().decode())
PY
```
**Expect:** `{"status":"drained","drained":true,"active_at_start":0,"remaining":0,...}`.
> Note: a drain is **one-way** — after this the bridge refuses new calls until it is recreated.
> Run S2 only when you intend to recreate, or immediately recreate afterwards.

### S3 — Exact drain during a REAL active call (the core AC)

```gherkin
Scenario: A redeploy during an active call drains rather than hard-cuts
  Given an active voice call on the bridge (browser WS or Genesys)
  When the bridge is drained
  Then it stops accepting new sessions (WS 1013)
    And the drain waits for the in-flight call up to the bounded timeout
    And the call is not hard-cut mid-turn before recreate
```

1. Start a **real call**: open the pilot web UI (`ws.html`) via the LB and hold a live turn, OR
   place a Genesys AudioHook call.
2. While the call is up, run the S2 drain command with a short budget
   (`?timeout_ms=8000`). **Expect** `{"status":"timeout","active_at_start":>=1,"remaining":>=1}`
   if you do not hang up within the budget, or `{"status":"drained","remaining":0}` if the call
   ends first.
3. From a second browser, try to start a NEW call during the drain → **expect it is refused**
   (WS closes with 1013; the UI shows "try again"). If both bridges are up, the VIP peer serves
   the new call — confirm the retry lands on the peer.
4. Hang up the original call, drain again → **expect** `status=drained`, `remaining=0`.

### S4 — Deploy integration (drain.yml bridge drain + grace fallback)

```gherkin
Scenario: The voice deploy drains before recreate and skips the grace window on a clean drain
  Given the voice tier is redeployed at a new image tag
  When the play reaches the "Drain the voice bridge before recreate" block
  Then the "exact wait, POST /drain" task runs inside the container
    And "Report the bridge drain outcome" shows status=drained (idle) 
    And the "Grace window ... (fallback)" task is SKIPPED on a confirmed drain
```

```bash
cd deploy/ansible
# dry-run first (no changes): confirm the drain tasks are planned on the voice tier
ansible-playbook deploy.yml --vault-password-file .vault_pass \
  -e image_tag=<new_tag> --limit vla-ai4cc-t01.prod.lan --check --diff 2>&1 | \
  sed -n '/Drain the voice bridge/,/Re-enable the voice bridge/p'
# then the real rolling deploy (serial:1)
ansible-playbook deploy.yml --vault-password-file .vault_pass \
  -e image_tag=<new_tag> --limit 'vla-ai4cc-t01.prod.lan,vla-ai4cc-t02.prod.lan'
```
**Expect in the play output:** the `Drain in-flight calls on the bridge (exact wait, POST /drain
— TASK-OPS-010)` task runs and is `changed`; `Report the bridge drain outcome` prints the JSON;
on an idle node `Grace window for in-flight calls to wind down (fallback)` is **skipped**; the
node then recreates and the container-health gate turns `healthy`.

### S5 — Health-gate interaction (TASK-INFRA-011)

```gherkin
Scenario: The drain does not compound the health-gate loopback false-negative
  Given the bridge recreates after the drain
  Then readiness is verified via the container health verdict, not host loopback
```

```bash
# on the node
sudo docker inspect --format '{{.State.Health.Status}}' voice-support-bridge
```
**Expect:** `healthy`. Confirms the deploy uses `health_container_name` (immune to loopback),
consistent with the drain probe path.

### S6 — Fail-safe degrade (token unset OR drain fails)

```gherkin
Scenario: Drain is fail-safe
  Given the bridge drain cannot complete (token unset, endpoint error, or timeout)
  Then the deploy degrades to the grace-window behaviour without aborting the whole play
```

- **Token unset:** remove/leave `vault_voice_drain_token` empty and deploy. **Expect:** the exact
  drain task is **skipped** (`when: voice_drain_token | length > 0`), the `Grace window …
  (fallback)` task **runs**, and the play does **not** abort.
- **Timeout with a stuck call:** hold a call past `voice_drain_timeout_seconds` (90 s).
  **Expect:** `status=timeout`, the grace window runs, the play continues (the container recreate
  closes the residual socket; the browser watchdog TASK-WEB-046 surfaces the terminal signal
  client-side). The step is `failed_when: false`, so a `502`/exec error never aborts the roll.

## Observability check

```gherkin
Scenario: A drain that could not fully drain is observable
  When a drain runs
  Then voice.drain.requested / voice.drain.completed events and the
       voice.drain.remaining_sessions metric are emitted with the outcome
```

Inspect the container logs (telemetry dumps to stderr; OTLP export is additive when
`OTEL_EXPORTER_OTLP_ENDPOINT` is set):
```bash
# on the node
sudo docker logs --since 10m voice-support-bridge 2>&1 | grep -o 'voice.drain.[a-z_]*' | sort | uniq -c
```
**Expect:** `voice.drain.requested` and `voice.drain.completed` present; the completed event and
the `voice.drain.remaining_sessions` metric carry `outcome` = `drained`/`timeout`. No secret is
logged (the token is never in the body or the events).

## Latency note

The drain runs **only at deploy/failover time**, not on the mouth-to-ear turn path — it is **out
of scope for the ADR-0029 latency slices**. No p50/p95/p99 to report; the only timing of interest
is `elapsed_ms` in the `/drain` response (how long the bounded wait took), already surfaced.

## Recommendation template

```markdown
## Recommendation
- Go / No-go for TASK-OPS-010:
- Evidence: S0–S6 results (attach the /drain JSON + the deploy output snippet + health verdict)
- Residual risks: WebRTC sessions not counted (dev-only, ADR-0042); on-timeout socket teardown
  relies on container recreate + browser watchdog (TASK-WEB-046)
- Required before Go: <none / list>
```
