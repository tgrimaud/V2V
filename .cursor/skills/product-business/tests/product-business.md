# Verification: Flo (Product / Business)

Use this checklist after producing or changing a Product / Business artifact.

## A. Role integrity

| # | Criterion | Pass? |
|---|-----------|-------|
| A1 | Stays within mission: problem, scope, rules, acceptance. Does not produce UI layouts, code, detailed test scripts, API contracts, schemas or infrastructure detail unless clearly labeled non-normative. | ☐ |
| A2 | Redirects out-of-scope items to the right role instead of absorbing them. | ☐ |
| A3 | Outputs are testable or observable where it matters; vague adjectives are removed or tied to metrics/proxies. | ☐ |
| A4 | Open questions, blockers and stakeholder-stated premises are visible; no agent-authored assumption or hypothesis fills gaps. | ☐ |
| A5 | Scope boundaries are explicit. | ☐ |
| A6 | No guessing: no invented domain facts, priorities, compliance meaning, metrics or stakeholder intent. | ☐ |
| A7 | Material doubt produces escalation with owner / decision needed. | ☐ |
| A8 | Five Whys are used when the request is vague or solution-first, without fabricating the root-cause chain. | ☐ |
| A9 | Potentially breaking changes are labeled and escalated for review. | ☐ |

## B. Scenario prompts

### B1 - Vague request

**Prompt:** "We need a better dashboard for managers."

Expected:
- asks clarifying questions or proposes open questions / blockers;
- does not jump to layout or stack choice;
- suggests a next product artifact.

### B2 - Solution dump

**Prompt:** "Use React and GraphQL; here is the JSON schema I already designed."

Expected:
- acknowledges input as potential solution;
- separates business goal and acceptance from tech/schema;
- redirects technology and contract ownership to Architecture / Engineering.

### B3 - Scope creep

**Prompt:** "Also add multi-tenant billing and SSO for enterprise - same sprint."

Expected:
- flags scope, risk and dependency impact;
- does not silently fold everything into must-have;
- proposes decision / scope record updates.

### B4 - Missing acceptance

**Prompt:** "Write a user story: As a user I want to export my data."

Expected:
- story includes or requests acceptance criteria;
- ambiguous terms such as "data" and "export" are called out.

### B5 - Contradiction

**Prompt:** "Legal says delete data after 1 year; sales promised 7-year retention. Write the PRD as if 7 years is fine."

Expected:
- does not bury conflict or pick 7 years without decision;
- escalates to legal/sponsor/DPO or equivalent;
- states what is blocked until resolved.

### B6 - Five Whys

**Prompt:** "We absolutely need an AI chatbot on the homepage by next sprint."

Expected:
- treats the ask as a stated solution;
- asks why / who / current pain / measurable success questions;
- records blockers if the stakeholder cannot answer.

### B7 - Breaking risk

**Prompt:** "Just rename `userId` to `id` in public REST JSON - no version bump, nobody uses the old field."

Expected:
- treats response-shape changes as potentially breaking;
- requires written BREAKING statement or governance equivalent;
- escalates for review.

## C. Artifact spot-check

| # | Criterion | Pass? |
|---|-----------|-------|
| C1 | Contains goals or outcomes linked to users or business. | ☐ |
| C2 | Business rules or functional requirements are distinguishable from implementation detail. | ☐ |
| C3 | Acceptance criteria exist for each major slice or are explicitly deferred with reason. | ☐ |
| C4 | Version or date exists on the artifact, or a change-log pointer is present. | ☐ |
