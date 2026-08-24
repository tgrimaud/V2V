# Infrastructure V1 - Machine/VM Target

> **Branch note:** this is a **target** pilot topology (Java backend, Pipecat,
> Postgres, Redis, etc.). `feat/restart-from-scratch` now carries the full web
> Voice2Voice loop (Pipecat + WebRTC, Gradium STT/TTS, the Java conversation/RAG
> backend) plus the Sprint 11 deployment packaging (Docker images, docker-compose
> per tier, HAProxy/Keepalived, GitHub Actions CI, Ansible deploy). It is
> **packaged and deployable** but not yet live on tst (gated by network-access
> open inputs). The old custom WebSocket bridge was removed on this branch
> (preserved on `main`).

> **Concrete realization (2026-08-03):** the first remote environment,
> **eir-ai4cc-tst**, realizes this generic target on **bare Rocky EL9 VMs with
> HAProxy/Keepalived** (not Kubernetes). See
> [`../operations/deployment-eir-ai4cc-tst.md`](../operations/deployment-eir-ai4cc-tst.md)
> for the environment inventory and
> [`adrs/ADR-0038-pilot-deployment-architecture-eir-ai4cc-tst.md`](adrs/ADR-0038-pilot-deployment-architecture-eir-ai4cc-tst.md)
> for the deployment decision (Docker + docker-compose, Redis-backed shared
> memory, GitHub Actions + Ansible release), and the
> [`first-deploy runbook`](../operations/first-deploy-runbook.md) for the
> zero-to-running bring-up. Kubernetes stays the longer-term evolution, not the
> pilot deployment.

## Objective

This document describes a V1 infrastructure target for running the Voice Support
Bot at a telecom operator, for example Eir in Ireland.

The target is a realistic operator pilot: limited traffic, but properly deployed
services, minimal high availability, protected customer data, and the ability to
evolve toward a production platform.

## V1 Assumptions

- EU cloud region, ideally Ireland (`eu-west-1` or equivalent).
- STT/TTS/LLM AI consumed through managed providers at launch.
- BSS accessible in read-only mode through a private link, VPN, or dedicated endpoint.
- Frontend served by CDN or object storage, with no dedicated VM.
- Kubernetes is recommended for the operator V1, but the sizing below remains
  readable as a "VM equivalent".
- The initial target covers a pilot with a few dozen simultaneous calls, not a
  full-load national deployment.

## Minimal Pilot Environment

This option is suitable for an operator demonstration or controlled pilot.

| Role | Count | Indicative size | Notes |
|------|--------|-------------------|-----------|
| Load balancer / ingress | 1 managed service | N/A | TLS, HTTPS/WSS routing, health checks |
| Backend Java | 2 VMs or pods | 2-4 vCPU, 4-8 GB RAM | Conversation API, RAG, business orchestration |
| Pipecat voice agent | 2 VMs or pods | 2-4 vCPU, 4-8 GB RAM | WebRTC/Twilio audio, STT/TTS, voice orchestration |
| PostgreSQL + pgvector | 1 managed instance | 4 vCPU, 16 GB RAM, SSD | KB, embeddings, technical state |
| Redis | 1 managed instance | 2 vCPU, 4-8 GB RAM | Sessions, shared conversation state, cache |
| Observability | Managed or 1 VM | 2-4 vCPU, 8 GB RAM | Logs, traces, dashboards |
| Bastion / admin VPN | 1 small VM | 1-2 vCPU, 1-4 GB RAM | Controlled admin access, optional if managed SSO/VPN is available |

This target represents approximately 6 to 8 equivalent VMs if everything is
self-managed, or 4 application VMs if the database, Redis, and observability are
managed.

## Recommended Operator V1 Target

This option is the recommended target for an operator-ready V1.

| Pool / Service | Count | Indicative size | Usage |
|----------------|--------|-------------------|-------|
| General Kubernetes worker pool | 3 VMs | 4-8 vCPU, 16-32 GB RAM | Backend Java, KB jobs, small services |
| Voice Kubernetes worker pool | 2-3 VMs | 4-8 vCPU, 16 GB RAM | Pipecat voice agents, WebRTC/Twilio audio, telephony |
| PostgreSQL + pgvector HA | 2 managed instances | 4-8 vCPU, 16-32 GB RAM, SSD | KB data, vector store, persistent state |
| Redis HA | 2 managed instances | 2-4 vCPU, 8-16 GB RAM | Sessions, cache, low-latency shared state |
| Observability | Managed service or 2 VMs | 4-8 vCPU, 16-32 GB RAM | OpenTelemetry, logs, metrics, alerting |
| Bastion / admin VPN | 1 small VM | 1-2 vCPU, 1-4 GB RAM | Restricted access to the private network |

This target represents approximately 8 to 12 equivalent VMs depending on the
level of managed services selected.

## Workload Distribution

### Backend Java

- Minimum 2 replicas.
- CPU sized for RAG, BSS calls, and SSE streaming.
- Stateless as much as possible.
- Conversation state shared in Redis or persisted in the database as needed.

### Pipecat Voice Agent

- Separate pool from the backend to scale according to simultaneous calls.
- Minimum 2 replicas.
- Sensitive to network latency toward STT/TTS and the backend.
- Must be co-located in the same region as the backend.
- Plan session draining before restarts to avoid cutting off active calls.
- The custom WebSocket bridge remains a legacy/fallback path and should not size
  the V1 target unless it is explicitly kept for comparison.

### PostgreSQL + pgvector

- Prefer a managed HA service.
- Stores embeddings, KB synchronization state, and technical data.
- SSD storage required.
- Automated backups and tested restore.

### Redis

- Prefer a managed HA service.
- Used for shared conversation state, sessions, and short-lived caches.
- Required as soon as multiple backend or Pipecat voice-agent instances run in parallel.

### Frontend

- No dedicated VM recommended.
- Serve through object storage + CDN or a static hosting service.
- WAF, TLS, CSP, and cache control at the edge.

## Self-Hosted AI Option

The V1 can start with managed AI. If the operator imposes a strong sovereignty
or data residency constraint, add a GPU pool.

| AI role | Count | Indicative size | Notes |
|---------|--------|-------------------|-----------|
| LLM inference | 1-2 GPU VMs | NVIDIA L4/A10 minimum depending on model | vLLM or equivalent runtime |
| Embeddings | 1 CPU VM or lightweight GPU VM | 4-8 vCPU, 16 GB RAM | Can be separated from the LLM |
| Self-hosted STT/TTS | 1-2 GPU VMs | L4/A10 minimum | Size after audio benchmarking |

This option should be treated as an architecture evolution, not as a pilot
prerequisite, unless required by contract.

## Recommended Network Zones

- Public subnet: load balancer, public ingress, optional bastion.
- Private application subnet: backend Java, Pipecat voice agents, jobs.
- Private data subnet: Postgres, Redis, internal storage.
- Controlled internet egress: managed STT/TTS/LLM, updates, observability.
- Private BSS link: VPN, peering, private endpoint, or dedicated interconnect.

Genesys Cloud CX, WhatsApp, or equivalent omnichannel providers are optional
future edge integrations. They should enter through dedicated channel adapters or
contact-center connectors and must not own RAG, billing reasoning, guardrails, or
memory. Production activation is gated by ADR-0010 channel contracts, ADR-0018
SLO measurement, and ADR-0019 escalation handoff readiness.

## Sizing by Voice Load

The values below are starting points to validate through load testing.

| Simultaneous calls | Backend Java | Pipecat voice agent | Data |
|-------------------|--------------|--------------|---------|
| 5-10 | 2 replicas, 2 vCPU each | 2 replicas, 2 vCPU each | Postgres 4 vCPU, Redis 2 vCPU |
| 20-50 | 3-4 replicas, 2-4 vCPU each | 3-5 replicas, 4 vCPU each | Postgres 4-8 vCPU, Redis 2-4 vCPU |
| 50-100 | 5+ replicas, 4 vCPU each | 6+ replicas, 4-8 vCPU each | Postgres 8+ vCPU, Redis HA 4 vCPU |

The Pipecat voice-agent pool must be scaled based on active calls and audio latency. The
backend must be scaled based on conversation count, BSS latency, and LLM
generation time.

## Minimal Observability

Per
[`ADR-0010`](adrs/ADR-0010-industrialization-requires-contracts-slos-and-observability.md)
and
[`ADR-0018`](adrs/ADR-0018-voice-latency-targets-and-slo-measurement.md),
production voice SLOs are not accepted until observability covers every channel
and pipeline step. The pilot validation target is `time_to_first_audio` p95
below 800 ms in a pre-warmed, co-located environment (the stub-era number,
**revised for the real backend by
[`ADR-0029`](adrs/ADR-0029-pilot-latency-criterion-real-backend-and-market-baseline.md)**
to mouth-to-ear p95 ≤ 1.5 s / `time_to_first_audio` p95 ≤ 1.2 s).

Each conversation must make it possible to measure:

- voice channel and transport;
- time to first STT transcription;
- backend request time;
- BSS retrieval time;
- vector search time;
- time to first LLM token;
- time to first TTS audio;
- channel output time;
- time to first audio;
- escalation count and reasons;
- STT/TTS/LLM provider errors;
- BSS errors or insufficient data.

## Startup Recommendation

For an operator pilot, start with:

- 3 general Kubernetes VMs;
- 2 dedicated Pipecat voice-agent Kubernetes VMs;
- managed HA PostgreSQL + pgvector;
- managed HA Redis;
- frontend on CDN;
- managed observability;
- managed AI, with a documented evolution path toward a GPU pool.

This target avoids oversizing the pilot while preparing the critical points of
operator production: scalability, high availability, separation of roles,
network security, and observability.
