# Bug Ticket

## Header

- **Bug ID:** BUG-028
- **Title:** `EirB2cInvoiceLayoutParser` emits `code=null` → the deterministic comparison collapses same-category lines and leaves a spurious residual
- **Status:** ✅ Merged into `feat/restart-from-scratch` (2026-10-05, `--no-ff` `a5f1948`; shipped in `v0.9.4`) — parser emits a stable, invoice-unique slug `code`; `InvoiceComparisonService.index()` hardened to never drop a colliding line; `EirB2cBillingComparisonE2eTest` now asserts residual €0.00 / OPTION_CHANGE €16.98. Backend **710** + ArchUnit green. **Adversarial review 94/100 (Pass, 2026-10-05)** — no blocking finding; residual (accepted): line code is label-derived (stable for V1 eir labels). Full review: `docs/qa/BUG-028-adversarial-review.md`.
- **Severity:** Medium
- **Priority:** P2
- **Detected by:** TASK-BE-066 `EirB2cBillingComparisonE2eTest` (real-PDF end-to-end comparison)
- **Detected date:** 2026-10-05
- **Related ticket:** TASK-BE-065 (eir B2C layout parser), TASK-BE-042 (`InvoiceComparisonService`), TASK-BE-066 (real-PDF runtime path)
- **Related epic:** EPIC-004 (billing explanation)
- **Branch:** surfaced on `task/TASK-BE-066-runtime-real-eir-b2c-pdf-source`
- **Owner:** Backend developer

## Problem Statement

`EirB2cInvoiceLayoutParser` builds each line as
`new InvoiceItem("line-" + (++lineCounter), null, null, null, category, …)` — the sequential value
goes into the **`id`** slot and **`code` is left `null`** (so is `type`).

`InvoiceComparisonService` matches lines across the two invoices by `label(item)`, which uses
`item.code()` first and, when it is null/blank, **falls back to `item.category().name()`**. With
`code=null` the matching key becomes the **category name**, and `index()` keeps only the **first**
line per key (`putIfAbsent`). Any invoice with **two or more lines in the same category** therefore
loses all but one of them in the diff. The dropped amount is not attributed to a cause, so it stays
in the **unexplained residual** even though it is a perfectly ordinary, fully-known line.

This never showed with the fixture/synthetic path because `EirB2cSampleFixtures` (and the other
fixtures) assign **unique** synthetic codes. Parsing the **real** PDFs (TASK-BE-066) exposes it.

## Steps To Reproduce

1. `bss.source=pdf`, `billrun.source=sample`, `pdf.source=eir-b2c` (or run `EirB2cBillingComparisonE2eTest`).
2. Account `99224964`, compare September vs August (the real sample PDFs).
3. September has two `OPTION` lines: `15GB Bundle` (€14.99) and `eir Mobile Security` (€1.99).

## Expected

- Total delta +€55.47 fully attributed: PRORATION €8.50 + OPTION_CHANGE €16.98 (14.99 + 1.99) +
  ONE_OFF €29.99, **residual €0.00**.

## Actual

- Total delta +€55.47 (correct, from the real parsed totals), but OPTION_CHANGE = **€14.99** only
  (the €1.99 `eir Mobile Security` line is collapsed into `15GB Bundle` by category name and dropped),
  leaving an **unexplained residual of €1.99**. Evidence (parsed September lines, all `code=null`):
  `SUBSCRIPTION 2999 / DISCOUNT -1000 / PRORATA 850 / OPTION 1499 / OPTION 199 / ONE_OFF 2999`.

## Impact

- A fully-known, benign line is reported as unexplained. With the confidence gate
  (`max-residual-ratio`, TASK-BE-043) a large enough collapsed line could tip a comparison into a
  caveat or an unnecessary escalation, or produce a misleading explanation that omits a real charge.
- Affects every account with ≥ 2 lines of the same category in a bill run (common: multiple options).

## Proposed Fix (to agree)

- Give parsed lines a **stable, unique `code`** so the comparison matches like-for-like **and**
  distinguishes sibling lines. The code must be (a) unique within an invoice and (b) stable for the
  same product across months, while keeping a recurring line distinct from its prorata variant
  (fixtures encode this as `15gb-bundle` vs `15gb-bundle-prorata`). Candidate: a normalized slug of
  the label with date/period ranges stripped, suffixed by the category (e.g. `15gb-bundle#OPTION`
  vs `15gb-bundle#PRORATA`). Needs care so cross-month matching still works.
- Alternatively/additionally, harden `InvoiceComparisonService.index()` so it does **not** silently
  drop lines that share a fallback key (e.g. include a positional discriminator when `code` is null),
  though a stable code is the better fix.
- Add a regression test with two same-category lines; flip `EirB2cBillingComparisonE2eTest` to assert
  residual 0 / OPTION_CHANGE €16.98.

## Workaround

- None needed for the default runtime (fixture path uses unique codes). The real-PDF path
  (`billrun.source=sample` + `pdf.source=eir-b2c`) carries the €1.99 residual until fixed.
