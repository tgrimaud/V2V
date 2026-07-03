---
name: presentation-maker
description: Create high-level technical and strategy presentations using the local template at ~/Downloads/Presentation.odp. Use this skill whenever the user asks to create, draft, refine, or export a PPT/PPTX/ODP presentation, slide deck, executive technical deck, strategy deck, architecture direction deck, roadmap presentation, or stakeholder presentation. Use it especially when technical content must be turned into a clear high-level narrative for direction, strategy, alignment, or decision-making.
---

# Presentation Maker

Use this skill to create stakeholder-friendly presentations from technical
content, using `~/Downloads/Presentation.odp` as the visual template.

The goal is not to dump documentation into slides. The goal is to explain a
technical direction, strategy, decision, or roadmap at the right altitude for the
audience.

## Template Source

The default template is:

```text
~/Downloads/Presentation.odp
```

Before creating a deck:

1. Verify the template exists.
2. Inspect the template if needed by treating the ODP as a ZIP archive.
3. Preserve the template visual identity: slide size, background, typography,
   spacing, and visual rhythm.
4. Create a new deck from a copy of the template. Do not modify the template
   file in `Downloads`.

If `soffice` or LibreOffice is available, use it for conversion/export. If it is
not available, produce the editable `.odp` and tell the user that PPTX/PDF export
requires LibreOffice or manual export from an office suite.

If direct ODP editing produces slides whose XML contains text but the office
application renders them as blank, stop patching placeholders. Generate a PPTX
with standard PowerPoint text shapes instead, reusing visual assets from the ODP
template when possible. A visible presentation is more valuable than an ODP file
that technically contains text but cannot be read by the user.

## Output Defaults

Ask for an output path when the user has not specified one. If the user wants a
fast draft and does not care where it goes, use a clear local folder such as:

```text
outputs/presentations/<deck-slug>/
```

Recommended artifacts:

- `<deck-slug>.odp` as the editable source deck.
- `<deck-slug>.pptx` when export tooling is available.
- `<deck-slug>.pdf` when the user asks for a shareable review format.
- `<deck-slug>-storyboard.md` when the deck is non-trivial.

## Presentation Language

Match the audience and user request:

- Use French when the presentation is for French-speaking business stakeholders.
- Use English when the user asks for English or the deck is meant for repository
  documentation, international teams, or technical governance.
- Do not mix languages inside the same deck unless there is a deliberate reason.

## Workflow

1. Clarify the deck purpose if it is ambiguous:
   - audience;
   - decision or alignment goal;
   - target duration;
   - desired language;
   - output format: ODP, PPTX, PDF, or storyboard first.
2. Read the source material: docs, code, architecture notes, backlog, meeting
   notes, or user-provided content.
3. Write a storyboard before generating slides unless the deck is tiny.
4. Turn technical detail into a high-level narrative.
5. Build the deck using `Presentation.odp` as the visual template.
6. Validate readability, flow, and export status.

## High-Level Technical Story Structure

Use this structure as the default for strategy or direction decks:

1. **Title / Purpose**: what decision or alignment the deck supports.
2. **Context**: current situation and why it matters now.
3. **Problem / Friction**: the pain, risk, or opportunity.
4. **Direction**: the proposed technical/product direction.
5. **Target Picture**: architecture, operating model, or future-state view.
6. **Plan / Roadmap**: phases, sequencing, and key milestones.
7. **Trade-offs / Risks**: what must be decided or monitored.
8. **Next Steps**: concrete actions, owners, or validation points.

Do not force every deck into all eight sections. Compress when the audience needs
a shorter narrative.

## Slide Writing Rules

- One main idea per slide.
- Prefer slide titles that state the conclusion, not the topic.
- Use short bullets. Avoid paragraphs unless the slide is intentionally a quote
  or executive summary.
- Keep code, endpoints, JSON, and implementation details out of high-level decks
  unless they support a decision.
- Translate technical mechanisms into business impact: speed, risk, cost,
  governance, scalability, maintainability, customer experience.
- Use diagrams sparingly and only when they clarify a decision or direction.
- End with a decision, request, or next action.

## Technical Content Transformation

When turning technical content into presentation material:

| Source Content | Presentation Treatment |
|----------------|------------------------|
| Architecture document | Show target state, boundaries, key flows, and decisions. |
| API/integration contract | Explain dependency, ownership, risk, and validation plan. |
| Backlog or epics | Show roadmap, increments, value, and dependencies. |
| Incident or limitation | Show impact, root direction, mitigation, and next steps. |
| Detailed implementation | Summarize why it matters and what choice it enables. |

## Diagram Use

Use `diagram-drawer` for diagrams before placing them in slides.

Presentation diagrams should be simpler than documentation diagrams:

- 5 to 9 visible boxes is usually enough.
- Prefer one story flow over complete system inventory.
- Put labels on the real interaction edge.
- Distinguish target vs legacy paths visually.
- Avoid diagrams that require the presenter to apologize for complexity.

## Working With `Presentation.odp`

The template may not contain text placeholders. Treat it as a visual source:

- reuse its slide backgrounds and layout patterns;
- prefer native large-content layouts from the template over adding custom text
  boxes;
- keep generous margins;
- avoid dense grids that fight the template;
- do not fill every available placeholder just because it exists;
- preserve the number and order of template slides only when it helps the story.

For this template, readability is more important than slide count:

- use one idea per slide;
- use two short bullets by default;
- avoid long sentences inside small decorative frames;
- repeat a simple readable layout when the template has many small placeholders;
- validate the deck by checking the number of text blocks and the length of each
  visible paragraph.

If editing ODP internals directly:

- ODP is a ZIP archive.
- Main slide content lives in `content.xml`.
- Images and media live under `media/` or similar folders.
- Preserve `mimetype`, `META-INF/manifest.xml`, and existing media references.
- Validate the resulting archive by opening it or by checking XML well-formedness.

Prefer safer tooling when available:

```bash
soffice --headless --convert-to pptx --outdir <outdir> <deck.odp>
soffice --headless --convert-to pdf --outdir <outdir> <deck.odp>
```

## Quality Checklist

Before finishing:

- [ ] The deck has a clear audience and purpose.
- [ ] The first three slides make the context and direction understandable.
- [ ] The level of detail is appropriate for strategy/alignment.
- [ ] The content fits the chosen slide layouts without overfilling frames.
- [ ] The template file in `Downloads` was not modified.
- [ ] The generated deck is saved as a new artifact.
- [ ] The visible deck format has been validated when direct ODP rendering is
      uncertain.
- [ ] Diagrams, if any, were handled through `diagram-drawer`.
- [ ] Export limitations are stated if PPTX/PDF export could not be performed.
- [ ] The final response includes generated file paths and any manual follow-up.

## Common Deck Patterns

### Direction Deck

Use for "where are we going and why":

- Current situation.
- Strategic direction.
- Target architecture or operating model.
- Phased plan.
- Decisions needed.

### Executive Technical Brief

Use for leaders who need the essence:

- The decision in one sentence.
- Why now.
- Business impact.
- Key risks.
- Proposed next step.

### Architecture Alignment Deck

Use for engineering/product alignment:

- Current constraints.
- Target architecture.
- Migration or implementation phases.
- Trade-offs.
- Validation plan.

### Roadmap Deck

Use for delivery planning:

- Vision.
- Milestones.
- Dependencies.
- Risks.
- Near-term actions.
