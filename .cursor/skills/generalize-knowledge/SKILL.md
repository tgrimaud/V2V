# Generalize Knowledge

Capture learnings from the current conversation and persist them into
**this repository's** shared knowledge files (`CLAUDE.md`, `AGENTS.md`,
`done-tasks.md`).

Use after completing significant work — features, bug fixes, API integrations,
or when the user asks to save what was learned.

## Scope — write to THIS repository only

This skill belongs to the **`voice-support-bot`** repository. When it runs while
working on Voice Support Bot, it must write to the files at the **root of this
repository** (`voice-support-bot/`), **never** to the workspace-root `BMad/`
files:

| Target | Correct path | Do NOT use |
|--------|--------------|------------|
| Context | `voice-support-bot/CLAUDE.md` | `BMad/claude.md` |
| Agent pitfalls | `voice-support-bot/AGENTS.md` | `BMad/agents.md` |
| Done log | `voice-support-bot/done-tasks.md` | `BMad/done-tasks.md` |

If the paths above are addressed relative to the open workspace, resolve them
against the `voice-support-bot/` directory, not the `BMad` workspace root. The
`BMad/` knowledge files govern `cursor-usage-dashboard/` and must stay untouched
by Voice Support Bot work.

## When to run

Trigger when the user says `/generalize-knowledge`, "save what we learned",
"update the knowledge files", or similar. Also appropriate to suggest after
finishing a multi-step feature, fixing a non-trivial bug, or discovering
important API/architecture details that future sessions would benefit from.

## Workflow

### Step 1 — Scan the conversation for learnings

Review the current conversation and identify:

1. **Bugs encountered and their root causes / fixes** — anything that cost
   debugging time and could trip up a future session.
2. **API or architecture discoveries** — field names, endpoint behaviors,
   data structures, or gotchas that differ from what you'd naively expect
   (Gradium STT/TTS, Mistral/Ollama, pgvector, BSS/Galaxion, Pipecat, Genesys…).
3. **New patterns or conventions** — decisions that set precedent for how
   similar work should be done going forward.
4. **Common mistakes** — things that went wrong because of incorrect
   assumptions (wrong param names, wrong field paths, off-by-one errors, etc.).
5. **Completed work** — user stories, tasks, sprints, or bug tickets finished
   in this session.

### Step 2 — Update `voice-support-bot/CLAUDE.md`

This file gives future AI assistants fast context about the project. Append to
the **existing sections** — never remove or rewrite content that's already there.

| Section | What to add |
|---------|-------------|
| **Issues historically hit (and fixes)** | New rows for each bug. Keep format: `\| Issue \| Resolution \|`. Be concise — one line per issue. |
| **API gotchas** | New bullet points for endpoint or field-name surprises. |
| **Architecture** sections | Only if a structural change was made (new module, new pattern, new port/adapter). |
| **Product scope V1** | Only if a product/architecture decision was recorded. |

Do NOT duplicate entries already present. Read the current content first and
skip anything that's already captured.

### Step 3 — Update `voice-support-bot/AGENTS.md`

Append to the **Common mistakes to avoid** section with new bullets for
pitfalls discovered in this session. Same rule: read first, skip duplicates.

Only add entries that represent mistakes a future AI agent would plausibly
make — not one-off typos or environment issues.

### Step 4 — Update `voice-support-bot/done-tasks.md`

Add a new dated section at the **bottom** of the file. Follow the existing
format (paths are relative to the `voice-support-bot/` repository root, e.g.
`voice-agent/...`, `backend/...`, `docs/...` — no `voice-support-bot/` prefix):

```markdown
## YYYY-MM-DD — Short title

**Summary:**

- Bullet points describing what was accomplished
- Include bug fixes, features, and notable discoveries
- Reference changed files only if it adds useful context

### Files changed
- `voice-agent/path/to/file.py` — brief description of change
```

### Step 5 — Summarize to the user

After updating all three files, tell the user:
- How many new entries were added to each file
- A one-line summary of the key learnings captured

## Important constraints

- **Right repository** — always write to `voice-support-bot/{CLAUDE.md,AGENTS.md,done-tasks.md}`,
  never the workspace-root `BMad/` files.
- **Read before writing** — always read each file's current content before
  editing to avoid duplicates or format mismatches.
- **Append only** — never remove, rewrite, or reorganize existing content.
  Only add new entries.
- **No code changes** — this skill only updates documentation files.
- **Be concise** — table rows and bullets should be one or two lines max.
  Future agents need to scan quickly, not read essays.
- **Use today's date** for the done-tasks.md entry header.
