# Voice Support Bot Documentation

> **Branch state (`feat/restart-from-scratch`, through Sprint 11):** the runnable
> code on this branch is a **two-service** web Voice2Voice stack: the Python voice
> runtime under `voice-agent/` (batch `POST /api/voice/turn` **and** streaming
> WebRTC with barge-in) and the Java conversation backend under `backend/` (RAG
> over pgvector, guardrails, memory; `POST /converse` + `POST /converse-stream`).
> Sprint 11 added the **deployment packaging**: Docker images for both services,
> `deploy/compose/` stacks per tier (Postgres, Ollama sidecar, Redis), HAProxy/
> Keepalived VIP config, GitHub Actions CI, and an Ansible deploy — packaged and
> deployable, not yet live on tst (gated by network-access open inputs). **Still
> target-only:** billing/BSS, invoice comparison, escalation/Genesys handoff,
> telephony, and the standalone React frontend. Sections in these docs that
> describe those parts are design intent. For what actually runs, start at
> `voice-agent/README.md` and `product-backlog/backlog-index.md`.

## Structure

| Folder | Audience | Contents |
|--------|----------|----------|
| [`product/`](product/) | Product / delivery | Broad functional specification and V1 billing/BSS scope |
| [`architecture/`](architecture/) | Architecture / engineering | System architecture, ADRs, infra target and architecture diagrams |
| [`integrations/`](integrations/) | Architecture / backend / BSS | External system integration plans and contracts |
| [`knowledge-base/`](knowledge-base/) | Content contributors / engineering | RAG knowledge base authoring and technical docs |
| [`engineering/`](engineering/) | Developers | Development guide and implementation conventions |
| [`operations/`](operations/) | Delivery / ops | Deployment runbooks, release process, backup/restore, operational backlog |
| [`qa/`](qa/) | QA / delivery | Functional + latency QA reports and pilot-readiness evidence per story |
| [`observability/`](observability/) | Ops / SRE | OpenTelemetry/latency-slice observability notes for the pilot |

## Main Entry Points

- Product hierarchy: [`product/cahier-des-charges-fonctionnel.md`](product/cahier-des-charges-fonctionnel.md)
  describes the broad support assistant target, while
  [`product/v1-scope.md`](product/v1-scope.md) defines the billing/BSS invoice
  explanation V1 value slice.
- Product backlog: [`../product-backlog/`](../product-backlog/) contains the V1
  epics, user stories, product decisions and open questions.
- Architecture: [`architecture/architecture.md`](architecture/architecture.md)
- Channel and identity boundary: [`architecture/channel-identity-boundary.md`](architecture/channel-identity-boundary.md)
- Voice runtime HTTP API contract: [`architecture/voice-runtime-http-contract.md`](architecture/voice-runtime-http-contract.md)
- Architecture decisions: [`architecture/adrs/`](architecture/adrs/)
- Documentation coherence review: [`architecture/documentation-coherence-review-2026-07-08.md`](architecture/documentation-coherence-review-2026-07-08.md)
- Infrastructure V1: [`architecture/infra-v1.md`](architecture/infra-v1.md)
- Pilot deployment (eir-ai4cc-tst) environment: [`operations/deployment-eir-ai4cc-tst.md`](operations/deployment-eir-ai4cc-tst.md)
- First-deploy runbook (zero-to-running pilot): [`operations/first-deploy-runbook.md`](operations/first-deploy-runbook.md)
- Pilot voice access + WebRTC entry point/status: [`operations/pilot-voice-access.md`](operations/pilot-voice-access.md)
- Galaxion BSS integration: [`integrations/galaxion/bss-integration-plan.md`](integrations/galaxion/bss-integration-plan.md)
- Missing Galaxion inputs: [`integrations/galaxion/missing-inputs.md`](integrations/galaxion/missing-inputs.md)
- Invoice PDF extraction JSON: [`integrations/galaxion/invoice-extraction-json.md`](integrations/galaxion/invoice-extraction-json.md)
- Knowledge base guide: [`knowledge-base/knowledge-base-guide.md`](knowledge-base/knowledge-base-guide.md)
- Development guide: [`engineering/development-guide.md`](engineering/development-guide.md)
- Development workflow: [`operations/development-workflow.md`](operations/development-workflow.md)
- Release process (repeatable deploy/rollback, authored in Sprint 11): [`operations/release-process.md`](operations/release-process.md)
- Backup / restore runbook (RPO/RTO, TASK-OPS-008): [`operations/backup-restore.md`](operations/backup-restore.md)
- Pilot request flow (eir-ai4cc-tst): [`operations/flow-requests-eir-ai4cc-tst.md`](operations/flow-requests-eir-ai4cc-tst.md)
- QA reports index: [`qa/`](qa/)
- Observability notes: [`observability/`](observability/)
- Operational backlog: [`operations/backlog.md`](operations/backlog.md)
