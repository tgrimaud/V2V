# Branch Divergence Reconciliation — Sprint 12 vs `feat/restart-from-scratch`

- **Date:** 2026-08-28
- **Mode:** READ-ONLY investigation (no tracked-file edits, no commit/push, no merge/branch mutation). This report is the only new file and is intentionally **uncommitted**.
- **Repo:** `voice-support-bot` (separate git repo; default branch `main`).
- **Branches compared:**
  - `feat/sprint-12-external-voice-websocket` @ `e66f7bb` (`v0.6.0-20-ge66f7bb`)
  - `feat/restart-from-scratch` (mainline) @ `b947395` (`v0.7.0-2-gb947395`)
- **Merge-base:** `6ebd394` = the **v0.6.0 release / Sprint-12 closure commit** ("docs: close Sprint 12 (external voice WebSocket) + release v0.6.0", 2026-08-25 16:51).

> Correction to the briefing facts: the annotated tag object `f8f2d72` **is** `v0.6.0`; the commit it points at is `6ebd394`. The closure *merge* into restart was `0a10da4` (16:47); the release/doc commit `6ebd394` (16:51) is its child and is where the tag sits. The two branches therefore **diverged exactly at v0.6.0** — Sprint-12 work was layered on top of the closed/released commit, and restart advanced independently from the same point. There is **no v0.7.0 "track only"**: `v0.7.0` is a real tag at `1eb1326` (2026-08-26), on restart.

---

## 1. Full divergence

### 1a. Commits ONLY on Sprint-12 (`restart..sprint-12`) — 20 commits

Content commits (14) + integration merges (6). `git cherry` confirms **all 14 content commits are unique** (`+`) — none is patch-equivalent to anything already on restart.

| Commit | Ticket / theme | Nature |
|---|---|---|
| `05d1f6e` | **TASK-OPS-006** — pin GitHub Actions to commit SHAs + add `dependabot.yml` | CI supply-chain (CI-only) |
| `d32d72c` | merge TASK-OPS-006 | merge |
| `7256dfc` | **TASK-INFRA-011** — probe container `State.Health.Status` instead of host loopback | deploy code (Ansible) |
| `15ca575` | docs: capture INFRA-011 in CLAUDE/AGENTS knowledge | docs |
| `aa5f1ba` | merge TASK-INFRA-011 | merge |
| `ecf8b15` | **TASK-BE-034/035** — bilingual KB corpus decision **ADR-0048** + retrieval language-filter target ticket | ADR + docs |
| `6e02103` | TASK-BE-035/ADR-0048 — cancel rebrand (Eir brand intentional) | docs |
| `6e9e445` | merge TASK-BE-034 | merge |
| `876619c` | **TASK-OPS-009** — deploy triggers/verifies KB sync + FR corpus default | deploy code (Ansible) |
| `9589b3e` | TASK-OPS-009 — KB bilingual pilot load + verification evidence | docs |
| `84884b2` | TASK-OPS-009 — adversarial review 96/100 + Eir-brand correction | docs |
| `024f8ef` | merge TASK-OPS-009 | merge |
| `94e119e` | **TASK-BE-020** — warm the reactive LLM **streaming** path (connect-time) | backend code |
| `c180223` | merge TASK-BE-020 | merge |
| `89c4c68` | **TASK-STT-014** — partial-quiet early STT finalization + async reconcile | voice-agent code *(later reverted)* |
| `5418b61` | merge TASK-STT-014 | merge |
| `cfbf1a9` | docs(qa): live A/B latency evidence for BE-020 + STT-014 | docs |
| `f0472b5` | **revert TASK-STT-014** — remove measured-harmful partial-quiet code | code revert (net-zero with `89c4c68`) |
| `1eb05cd` | docs: close **adversarial-review doc gate (2026-08-28)** — 4 review files | docs |
| `e66f7bb` | docs(sprint-12): reflect OPS-006 + INFRA-011 merged; log 2026-08-28 session | docs (sprint-branch bookkeeping) |

### 1b. Commits ONLY on restart (`sprint-12..restart`) — 17 commits

The **v0.7.0 single-port aiohttp voice runtime** track (WS-primary) + WEB-039 re-measure.

| Commit | Ticket / theme |
|---|---|
| `333bdc3` | **ADR-0046** — WebSocket is the primary V1 live voice transport (supersedes ADR-0033) |
| `c982e79` | **TASK-WEB-037** — WebSocket-primary live voice transport (edge + client) |
| `8e84126` | WEB-037/ADR-0047 — revert HAProxy `voice_ws` edge route (avoid LB touch) |
| `150ce3a` | deploy(voice) — ADR-0047 compose comments |
| `9800c5a` | **ADR-0047 + TASK-WEB-038** — unify voice runtime on a single async HTTP+WS server (one port) |
| `fd3a116`,`f049eb5`,`6cb7a40`,`1b8bec6`,`329c746`,`a1ffdfb` | **TASK-WEB-038** slices 1–3 (aiohttp single-port + adversarial fixes + tests) |
| `7b0d160`,`2fb38a8` | docs: WS live-latency evidence, aiohttp one-port spike + generalized learnings |
| `25d5eaa` | merge WEB-037 + WEB-038 |
| `1eb1326` | docs: mark WEB-037/038 merged **(v0.7.0)** + deployed  ← **`v0.7.0` tag** |
| `b3f7135` | docs: log v0.7.0 release + `eir-ai4cc-tst` deploy of single-port runtime |
| `b947395` | **qa(TASK-WEB-039)** — edge 101 confirmed + v0.7.0 ADR-0029 re-measure through HAProxy ← restart HEAD |

### 1c. Divergence picture

Both branches share identical history through **`6ebd394` = v0.6.0** (2026-08-25). From that single point:
- restart moved forward through the WS-primary/one-port track and **tagged/released v0.7.0** (`1eb1326`, 2026-08-26), now at `b947395`.
- sprint-12 (a **closed/released** branch) kept accumulating this week's tickets (BE-020, STT-014+revert, OPS-006, INFRA-011, OPS-009, BE-034/ADR-0048, the 2026-08-28 doc gate), now at `e66f7bb`.

`feat/sprint-13-genesys-audio-connector` was cut correctly **from restart HEAD** (merge-base = `b947395`, 3 ahead / 0 behind) and does **not** contain the sprint-12 tail either.

---

## 2. Is our session work already on mainline (restart)? — per-item verdict

| Session item | Verdict on restart | Evidence |
|---|---|---|
| **TASK-BE-020** (streaming warm-up in `WarmUpService`) | **ABSENT** | restart `WarmUpService.java` is the base TASK-BE-017 **sync-only** version (`generator.generate` only; no `StreamingAnswerGeneratorPort`, no `warmStream`, `WarmUpResult` has no `streamWarmed`). The streaming warm-up (`SLICE_STREAM`, `streamingGenerator`) exists **only** on sprint-12 (`94e119e`). |
| **TASK-BE-033** (`scripts/llm_benchmark/` benchmark) | **PARTIAL** | The **decision** (ADR-0045) is **present on restart** (`docs/architecture/adrs/ADR-0045-…md`). The **harness code** is on **neither** branch — it lives on the unmerged `task/TASK-BE-033-llm-provider-benchmark` branch (`aa9cffe`, `5bb566f`: `scripts/llm_benchmark/README.md`, `run_local_candidate.sh`, fixtures). The local `scripts/llm_benchmark/reports/` is **untracked** working-tree output. |
| **STT-014 revert** (partial-quiet code absent) | **PRESENT (equivalent) — as a no-op** | restart **never had** the partial-quiet code (`git grep` finds only doc/ticket references, no `partial-quiet`/early-finalization runtime code). Sprint-12 added it (`89c4c68`) then reverted it (`f0472b5`), so both branches end with the **same absent runtime state**. Difference: sprint-12 additionally carries the QA doc `docs/qa/task-stt-014-finalize-tail-qa.md` (ABSENT on restart). |
| **2026-08-28 doc gate** (4 adversarial-review docs) | **ABSENT** | `docs/qa/adversarial-review-2026-08-28-{backend,deploy-observability,docs-architecture,voice-runtime}.md` exist only on sprint-12. |
| **TASK-OPS-006** (.github SHA pins + dependabot) | **ABSENT** | restart has **no** `.github/dependabot.yml` and **0** SHA-pinned `uses:` in workflows; sprint-12 has `dependabot.yml` + 9 SHA-pinned `uses:` (`images.yml` 5, `tests.yml` 4). |
| **TASK-INFRA-011** (container `Health.Status` probe) | **ABSENT** | restart `roles/compose_tier/tasks/health.yml` still uses the **loopback HTTP `uri`** probe; `group_vars/voice.yml` still `health_url: http://127.0.0.1:8090/` with **no** `health_container_name`; restart CLAUDE.md line 234 still calls the fix a "**follow-up, ticketed TASK-INFRA-011**". The actual implementation (health.yml container-verdict poll, `health_container_name: "voice-support-bridge"`, `qa-validate-ansible.sh` checks) exists **only** on sprint-12. **NOT already on restart** (contrary to the working hypothesis). |

**Additional sprint-12-only work not in the briefing list** (also ABSENT on restart, real code):
- **TASK-OPS-009** — deploy KB-sync trigger + FR corpus default (`kb_sync.yml`, `kb_assets.yml`, `backend.env.j2`, `group_vars/backend.yml`, `.env.example`).
- **TASK-BE-034/035 / ADR-0048** — bilingual KB corpus + retrieval language-scope ADR.

---

## 3. Redundancy / conflict if we forward-port Sprint-12's unique commits onto restart

Files changed since v0.6.0 on **both** branches (⇒ conflict candidates); everything else applies cleanly.

**CONFLICT-prone (touched on both sides):**
- `product-backlog/backlog-index.md` — both branches rewrote many ticket rows.
- `done-tasks.md` — both appended dated entries.
- `CLAUDE.md`, `AGENTS.md` — both appended "issues/learnings" rows.
- `docs/architecture/adrs/README.md` — restart added ADR-0046/0047; sprint-12 added ADR-0048.
- `deploy/ansible/group_vars/voice.yml` — restart edited voice env vars; sprint-12 added `health_container_name` (INFRA-011).
- `deploy/ansible/qa-validate-ansible.sh` — both added validation checks.
- `product-backlog/tasks/deployment-tasks.md` — restart deploy edits vs OPS-006/INFRA-011/OPS-009 edits.

**Applies CLEANLY (new/isolated files, no restart overlap):**
- BE-020: `backend/.../WarmUpService.java`, `WarmUpResult.java`, `WarmUpController.java`, `WarmUpResponse.java`, `ConversationConfig.java`, `WarmUpServiceTest.java`, `WarmUpControllerTest.java`.
- OPS-006: `.github/dependabot.yml`, `.github/qa-validate-workflows.sh`, `.github/workflows/images.yml`, `tests.yml` (restart touched no `.github`).
- INFRA-011: `roles/compose_tier/tasks/health.yml` (clean); **partial conflict** on `group_vars/voice.yml` + `qa-validate-ansible.sh`.
- OPS-009: `kb_sync.yml`, `kb_assets.yml`, `roles/.../main.yml`, `templates/backend.env.j2`, `deploy/compose/backend/.env.example`, `group_vars/backend.yml`.
- ADR-0048 file + the 4 `adversarial-review-2026-08-28-*.md` + `task-be-020-first-sentence-latency-report.md` + `task-ops-009-*` + `task-stt-014-finalize-tail-qa.md` (all new files).

**NO-OPS / should be DROPPED (redundant):**
- `89c4c68` (STT-014 add) **+** `f0472b5` (STT-014 revert) — net-zero; restart never had the code. Forward-porting the pair is pointless. Keep only the STT-014 **QA doc** if the finding is wanted on restart.
- The 6 **merge commits** — cherry-pick the content commits instead of the merges.
- `e66f7bb` — sprint-branch bookkeeping ("log 2026-08-28 session onto the closed sprint"); do not carry to restart.

---

## 4. Doc / state truth

| Artifact | restart (`b947395`) | sprint-12 (`e66f7bb`) | Canonical? |
|---|---|---|---|
| `backlog-index.md` SPRINT-12 registry row | `✅ Done (closed 2026-08-25, → restart `--no-ff` 0a10da4, released **v0.6.0**)` (line ~220) | present, but branch also flips per-ticket rows (INFRA-011/OPS-006/BE-020/STT-014/OPS-009) to merged/implemented | **restart** holds the correct closed/v0.6.0 registry line |
| `sprints/sprint-12-…md` `## Status` header (line 23) | `✅ Done (closed 2026-08-25) … released v0.6.0` | same | both say Done |
| `sprints/sprint-12-…md` **roadmap row** (line 53 restart / 61 sprint-12) | `🚧 In progress (started 2026-08-24)` | `🚧 In progress (started 2026-08-24)` | **both WRONG** — pre-existing bug baked into the v0.6.0 closure commit |
| `sprints/sprint-12-…md` narrative (line ~38) | `The sprint is **not yet closed**: at closure this file … must be flipped to ✅ Done` | same, plus post-closure ticket rows | **both WRONG** |
| `done-tasks.md` | v0.7.0 track entries | Sprint-12-tail entries | divergent (union needed) |

**Self-contradictions on the sprint-12 branch that need fixing:**
1. Header (line 23) says **"✅ Done (closed 2026-08-25) … v0.6.0"** while the roadmap row (line 61) says **"🚧 In progress"** and the narrative (line 38) says **"the sprint is not yet closed"**. *(Note: this specific trio is also present on restart — it is a defect in the v0.6.0 closure commit, not introduced by the post-closure work.)*
2. Post-closure per-ticket rows appended to a **closed** sprint file/backlog: `TASK-INFRA-011 ✅ Merged into sprint-12 (2026-08-28)`, `TASK-OPS-006 ✅ Merged (2026-08-28)`, `TASK-BE-020 🟢 Implemented + merged into sprint 12`, `TASK-STT-014 ❌ Rejected … reverted from sprint-12`, `TASK-OPS-009 …` — these imply the closed/released sprint reopened.
3. `e66f7bb` literally logs a "2026-08-28 cleanup+merge session" onto the closed sprint branch.

---

## 5. Releases

- **`v0.6.0`** → commit **`6ebd394`** (annotated tag object `f8f2d72`) = merge-base = Sprint-12 closure/release. Sprint-12 = `v0.6.0-20`; this is the branches' divergence point.
- **`v0.7.0`** → commit **`1eb1326`** (2026-08-26, annotated) — "single-port aiohttp voice runtime (WS-primary, ADR-0046/0047)". It **exists as a real tag** on restart. restart HEAD `b947395` = `v0.7.0-2` (WEB-039 re-measure). All tags: `V0.1, v0.2, v0.3, v0.4.0, v0.5.0, v0.5.1, v0.5.2, v0.6.0, v0.7.0`.

---

## Recommended reconciliation plan (concrete, minimal-risk)

Guiding principle: **do NOT merge the closed/released `sprint-12` branch into restart wholesale** (it would drag the reopened-sprint doc contradictions, the STT-014 add/revert churn, and heavy ledger conflicts). Instead **cherry-pick the valuable unique tickets** onto a fresh branch cut from restart, ticket by ticket, cleanest first.

### A. Forward-port (cherry-pick) — in this order
1. **Cut a fresh branch from restart HEAD** (`b947395`). Because the sprint-12 tail is cross-cutting (CI, deploy, backend, KB) and **not Genesys-themed**, do **not** fold it into `feat/sprint-13`. Use a dedicated `feat/sprint-14-…` (or `chore/forward-port-sprint12-tail`) branch off restart. *(User decision — see Ambiguities.)*
2. **TASK-BE-020** — cherry-pick `94e119e`. Isolated backend files → clean. Re-run `mvn test`.
3. **TASK-OPS-006** — cherry-pick `05d1f6e`. `.github/*` new → clean. Re-run `qa-validate-workflows.sh` + `actionlint`.
4. **TASK-INFRA-011** — cherry-pick `7256dfc` (+ knowledge `15ca575`). `health.yml` clean; resolve small conflicts on `group_vars/voice.yml` (add `health_container_name` beside restart's voice vars) and `qa-validate-ansible.sh` (union of checks).
5. **TASK-OPS-009** — cherry-pick `876619c` (+ evidence `9589b3e`, `84884b2`). New deploy files clean; resolve `deployment-tasks.md`/`backend.yml` overlaps.
6. **TASK-BE-034/035 / ADR-0048** — cherry-pick `ecf8b15` (+ `6e02103`). ADR file clean; resolve `adrs/README.md` (keep restart's ADR-0046/0047 rows **and** add ADR-0048).
7. **2026-08-28 doc gate** — cherry-pick `1eb05cd` (4 new review files, clean).
8. **QA evidence** — cherry-pick `cfbf1a9` (BE-020/STT-014 A/B report) if wanted; and optionally the standalone **STT-014 QA doc** file.
9. Resolve the **shared-ledger conflicts** once, taking the **union**: `backlog-index.md`, `done-tasks.md`, `CLAUDE.md`, `AGENTS.md`.

### B. Drop (redundant / do not forward-port)
- STT-014 code pair `89c4c68` + `f0472b5` (net-zero; restart never had it) — keep only the QA finding/doc.
- All 6 merge commits (`024f8ef`, `6e9e445`, `c180223`, `5418b61`, `d32d72c`, `aa5f1ba`) — use the content commits.
- `e66f7bb` (closed-sprint bookkeeping).

### C. TASK-BE-033 (benchmark harness)
- Decision (ADR-0045) is already on restart. To land the **harness** in mainline, rebase/merge `task/TASK-BE-033-llm-provider-benchmark` onto the forward-port branch (or keep it as a spike branch). Decide what to do with the untracked `scripts/llm_benchmark/reports/` (commit to the BE-033 branch, keep local, or discard). *(User decision.)*

### D. Closed `feat/sprint-12-external-voice-websocket` branch
- It is **released at v0.6.0 = its divergence point**; treat it as **frozen**. After the forward-port lands and is validated, **retire** it (keep local/remote for audit until then, then delete). Do not continue adding tickets to it.
- Today's **OPS-006 / INFRA-011 merges** live only on this closed branch ⇒ they **must be re-landed on restart** via step A.3/A.4 (INFRA-011 is **not** yet on restart).

### E. Fix the sprint-12 file self-contradiction (on restart, canonical)
- Flip the roadmap row (restart line ~53) and the narrative (line ~38) from `🚧 In progress` / "not yet closed" to **`✅ Done (closed 2026-08-25, released v0.6.0)`**, matching the header (line 23) and the backlog-index registry row (line ~220). This is a small doc edit on restart — **not** a sprint-12 cherry-pick — and also cleans the same defect that exists on both branches.
- Re-home the post-closure ticket-status rows into the forward-port target sprint/backlog, so they don't imply the closed sprint reopened.

### F. Next sprint branching
- **Branch the next sprint from `feat/restart-from-scratch`** (post-v0.7.0). `feat/sprint-13-genesys-audio-connector` already does this correctly (cut at `b947395`). Keep the two-level model: sprint branch off restart, ticket branches off the sprint branch.

### Ambiguities needing a user decision
1. **Home for the sprint-12 tail** — dedicated `feat/sprint-14-…` vs `chore/forward-port-…` branch (recommended) vs folding into `feat/sprint-13` (not recommended — off-theme).
2. **TASK-BE-033 harness** — land in mainline now (merge the task branch) or leave as a spike; and the fate of untracked `scripts/llm_benchmark/reports/`.
3. **STT-014 QA doc** — keep the finding on restart (recommended) even though the code was rejected.
4. **Cherry-pick vs `git rebase --onto`** — for a long clean-picked chain some may prefer `rebase --onto restart 6ebd394 <sprint-12-subset>`; either works, cherry-pick per ticket gives finer control over the drops in §B.
