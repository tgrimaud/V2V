# Knowledge Base — Content Author's Guide

> Audience: support, billing and commercial teams who **add and edit the bot's
> knowledge** — no programming required.
> For the internals, see [`knowledge-base-technical.md`](./knowledge-base-technical.md).

This guide explains how the virtual assistant gets its answers, how to write and
update that knowledge, and how to publish your changes.

---

## 1. How the bot uses your content (in one minute)

The assistant does **not** invent answers. It reads from a **Knowledge Base
(KB)** — a set of FAQ documents you maintain. When a customer asks a question,
the bot:

1. Finds the passages in your documents that best match the question.
2. Uses **only those passages** to write its answer.

So the quality of the bot's answers depends directly on the quality of your KB.
If something is missing, unclear, or outdated in the documents, the bot will be
too.

> If the bot can't find a confident match, it says it doesn't have the
> information and offers to transfer to a human advisor — it will **not** guess.

For billing questions, the KB explains tariff, offer, and business rules. It
does **not** replace invoice PDF extraction, BSS evidence, or deterministic
billing comparison for amounts, deltas, discounts, and usage.

---

## 2. Where the content lives

All knowledge is stored as **Markdown files** (`.md`) in the
**`knowledge-base/`** folder of the project:

```
knowledge-base/
├── telecom-faq.md      → technical support
├── billing-faq.md      → billing & subscriptions
└── commercial-faq.md   → sales & offers
```

You enrich the KB by **editing these files** or **adding new `.md` files** in
this folder. Markdown is a simple text format — you can edit it in any text
editor.

---

## 3. Anatomy of a knowledge file

Each file has two parts: a small **header** (called "front-matter") and the
**body**.

```markdown
---
domain: billing
language: fr
---

# Billing and Subscriptions

## Invoices

### How do I view my invoice?

1. Log in to your customer area.
2. Go to "My invoices".
3. Download your last 12 invoices as PDF.

### Why is my invoice higher than usual?

The most common causes are ...
```

### 3.1 The header (front-matter)

The block between the two `---` lines configures the file:

| Field | Required? | What it does |
|-------|-----------|--------------|
| `domain` | **Yes (recommended)** | Routes the content to the right specialist (see §4). If omitted, the content is treated as `general`. |
| `title` | Optional | A human-friendly title. If omitted, the first `#` heading is used. |
| `language` | Optional | Informational. The system currently tags all Markdown content with the global default language (`fr`). |

> Keep the `---` lines exactly as shown, at the very top of the file.

### 3.2 The body

Plain Markdown. **Headings are important**: the text under each `##`/`###`
heading is what the bot retrieves and may cite as its source. Structure your
content with clear headings so each answer is easy to locate.

---

## 4. Domains (very important)

Every piece of content belongs to a **domain**. The bot has one specialist
"agent" per domain, and it searches the matching domain for each question.

| `domain:` value | Use it for |
|-----------------|------------|
| `support` | Technical issues: box, Wi-Fi, connection, TV, outages |
| `billing` | Invoices, payments, direct debit, subscriptions, refunds |
| `commercial` | Offers, pricing, signing up, upgrades, promotions |
| `general` | Content useful to **all** agents (company info, opening hours…) |

Rules of thumb:
- Put each file's content in **one** domain that matches its topic.
- Use `general` only for cross-cutting info you want every agent to see.
- If you're unsure, `general` is a safe default but less precise.

---

## 5. Writing content the bot can use well

Good KB writing is a bit different from writing a web page. Follow these
principles:

**Do**
- **One question per heading.** Use `###` for each FAQ question, with the answer
  right below it.
- **Be self-contained.** Each section should make sense on its own — the bot may
  retrieve it without the surrounding text.
- **Be concise and concrete.** Short steps, numbered lists, exact names of menus
  and pages.
- **Use the customer's words.** Include phrasings customers actually use
  ("my bill is too high", "change my RIB") so matching works.
- **Keep facts current.** Prices, phone numbers, deadlines — update them as they
  change.

**Avoid**
- One giant wall of text with no headings (hard to retrieve precisely).
- Burying several different topics under a single heading.
- Vague answers ("contact us for more info") with no actual content.
- Internal jargon or codes the customer would never type.

> **Length tip:** content is automatically split into ~500-character pieces.
> Well-structured short sections survive this split best. Very long paragraphs
> may be cut mid-thought.

---

## 6. Common tasks

### 6.1 Add a new question to an existing topic

1. Open the relevant file (e.g. `billing-faq.md`).
2. Add a new `###` heading with the question and its answer, under the right
   `##` section.
3. Save, then **publish** (see §7).

### 6.2 Update an existing answer

1. Edit the text in place.
2. Save, then **publish**. The bot replaces the old version automatically — you
   don't need to delete anything.

### 6.3 Create a brand-new file

1. Create a new file in `knowledge-base/`, e.g. `tv-faq.md`.
2. Add the front-matter header with the right `domain`.
3. Write your content with `#`/`##`/`###` headings.
4. Save, then **publish**.

### 6.4 Remove content

- Delete the section, or delete the whole `.md` file.
- On the next publish, the bot automatically removes that content from its
  memory (no leftover answers).

> Renaming a file is treated as "remove the old + add the new" — that's fine,
> just re-publish.

---

## 7. Publishing your changes

Editing a file does **not** instantly update the bot. The KB is refreshed by a
**synchronization** step that reads the files and updates the bot's memory.

You have two options:

### Option A — wait for the automatic refresh
A sync runs **automatically every hour**. Your saved changes go live at the next
run, no action needed.

### Option B — publish now (manual sync)
To apply changes immediately, trigger a sync. Ask a developer/operator to run, or
run yourself if you have access:

```bash
curl -X POST http://localhost:8081/api/knowledge/sync
```

The response tells you exactly what happened:

```json
{ "processed": 3, "ingested": 1, "skipped": 2, "deleted": 0 }
```

| Field | Meaning |
|-------|---------|
| `processed` | How many documents were examined |
| `ingested` | How many were **new or changed** and got (re)indexed |
| `skipped` | How many were **unchanged** (nothing to do) |
| `deleted` | How many were removed because the file no longer exists |

If you edited one file, expect `ingested: 1` and the rest `skipped`. Running sync
again right away should show `ingested: 0` — that's normal and means everything
is up to date.

---

## 8. Verify it worked

After publishing, ask the assistant the question you just added/updated. You
should get an answer based on your new content. If not, see troubleshooting
below.

---

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| New file isn't picked up | Not a `.md` file, or not in `knowledge-base/` | Check the extension and location |
| Change didn't go live | Sync hasn't run yet | Wait for the hourly sync or trigger it manually (§7) |
| Answer is routed to the wrong specialist | Wrong `domain:` in the header | Set the correct `domain` and re-publish |
| Bot says it has no information | No close match in the KB | Add a section that uses the customer's wording; keep it focused |
| `sync` shows `ingested: 0` after an edit | The file content didn't actually change (or wasn't saved) | Re-save the file and re-run sync |
| Header looks broken / ignored | The `---` lines are missing or not at the very top | Restore the front-matter exactly as in §3 |

---

## 10. Quick checklist before publishing

- [ ] File is in `knowledge-base/` and ends with `.md`
- [ ] Front-matter has the correct `domain`
- [ ] Each FAQ entry is under its own clear heading
- [ ] Answers are concise, current, and self-contained
- [ ] Saved the file
- [ ] Triggered a sync (or you're OK waiting for the hourly one)
- [ ] Tested the question against the bot
