# QA Functional And Latency Report — TASK-INFRA-003 (Embeddings placement + provider egress)

## Executive Summary

- **Overall readiness:** GO for merge-ready. The decision is recorded in **ADR-0039**
  (Ollama `nomic-embed-text` CPU sidecar co-located per backend VM; Mistral embeddings
  rejected for the pilot) and wired end-to-end: the backend compose stack gained an
  internal `ollama` sidecar, the Ansible deploy pulls the model, and the docs
  (ADR-0038 §6, ADR-0006, ADR index, deployment doc, runbook) are consistent.
- **Deterministic validation:** backend `docker compose config` OK (sidecar 1.0 CPU/2 g,
  backend resized 5 g/3.0, `OLLAMA_BASE_URL=http://ollama:11434`, dim unchanged);
  Ansible QA **33/33** (key parity holds with the 3 new keys, template renders);
  compose QA **22/22**; embedding dimension stays **768** (no `vector_store` change).
- **Main blockers:** none.
- **Residual risks:**
  1. **Deploy-time egress** to `registry.ollama.ai` for the one-time model pull — added
     to the egress table with a pre-seed alternative (bake image / copy blob) if denied.
  2. **Provider egress allowlist** (Mistral, Gradium, registries) remains a platform
     input; embedding *inference* needs none (local).
  3. **Live "backend syncs + retrieves on tst"** (the AC) runs on the tst backend VMs;
     deferred like the other Sprint 11 tickets.

## Scope Tested

- **Epic / task:** EPIC-012 / TASK-INFRA-003 (decision/spike + wiring).
- **Environment:** local; `docker compose config` (backend stack) + `ansible-core 2.21`
  template render + the compose/ansible QA scripts. No tst host contacted.

## Acceptance Scenario (Gherkin)

```gherkin
Scenario: Embeddings reachable on tst
  Given the chosen embeddings option deployed/configured
  When the backend performs a KB sync and a retrieval
  Then embeddings are produced and vector search returns results with no dimension mismatch
```

## Coverage

| Acceptance element | Covered? | Evidence |
|---|---|---|
| Embeddings option chosen + documented | Yes | ADR-0039 (option a, with rationale + rejected alternatives); ADR-0038 §6 resolved; deployment doc updated. |
| Deployed/configured | Structurally yes; live deferred | `ollama` sidecar in `deploy/compose/backend/docker-compose.yml` (internal, model volume, healthcheck, `depends_on` healthy); Ansible pulls the model (`ollama_model.yml`, backend-gated); `OLLAMA_BASE_URL=http://ollama:11434`. `docker compose config` validates the wiring. |
| No dimension mismatch | Yes | Stays `nomic-embed-text` (768 dim); no `vector_store` recreation, no re-sync; Mistral 1024-dim path explicitly rejected. |
| Egress confirmed | Documented; platform input | ADR-0039 egress table (Mistral, Gradium, registry, one-time Ollama model) + deployment open input #2. |

## Deterministic Checks

| Check | Result |
|-------|--------|
| `docker compose config` (backend stack, with ollama sidecar) | PASS |
| Ansible `qa-validate-ansible.sh` (template render + `.env` key parity incl. 3 new keys) | 33/33 PASS |
| Compose `qa-validate.sh` (backend/voice/redis stacks) | 22/22 PASS |
| Ansible `--syntax-check` (new `ollama_model.yml` include) | PASS |
| Embedding dimension unchanged (768) | PASS |
| `git diff --check` (docs whitespace) | clean |

## Observability And Latency

- **Runtime-affecting?** No new application code; this is a deploy-topology decision
  plus compose/Ansible wiring. Query-embedding latency is already observable through
  the backend's retrieval slice metrics (ADR-0028); no new instrumentation required.
- Moving embeddings on-VM removes a would-be network hop, keeping the per-turn
  query-embedding off the WAN.

## Security And Privacy

- Embeddings (KB + query text) never leave the VM — no third party sees them.
- The `ollama` sidecar is internal-only (`expose`, not published); no new attack surface.
- No secrets involved in this layer.

## Adversarial Review

- **Score:** 92/100 (Pass, ≥90 gate).
- **Blocking finding fixed:** the egress analysis omitted the **deploy-time
  `registry.ollama.ai`** model pull, which slightly contradicted the "no cloud egress"
  framing. Added it to the egress table + open input with a pre-seed alternative, and
  scoped the no-egress claim to runtime inference.
- **Accepted residual risk:** deploy-time model egress (or pre-seed); provider egress
  allowlist is a platform input; live tst sync/retrieval deferred.

## Verdict

**GO — merge-ready.** Decision recorded (ADR-0039) and wired; deterministic checks
green; dimension preserved (no mismatch); egress fully enumerated including the
deploy-time model pull. Merge on the user's explicit request; live KB-sync + retrieval
proof runs on the tst backend VMs.
