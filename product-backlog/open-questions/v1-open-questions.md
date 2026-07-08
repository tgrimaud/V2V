# V1 Open Questions

## OQ-001 - Customer Identification By Phone And Web Voice Channel

**Status:** Open  
**Owner:** Product / BSS / Security  
**Impacts:** EPIC-001, EPIC-004, EPIC-005, EPIC-008

### Question

How is the customer identity established on each V1 channel?

### Why It Matters

The bot must explain invoices only for a customer identified with enough
confidence. The identification level determines BSS access, what can be spoken or
displayed, and when escalation is required.

### Needed Decision

- Identity source for the phone journey.
- Identity source for the web voice journey.
- Minimum confidence level for invoice access.
- Product behavior when identity is incomplete or conflicting.

---

## OQ-002 - Minimum Proof Threshold For Answering Without Escalation

**Status:** Open  
**Owner:** Product / Billing SME / Legal  
**Impacts:** EPIC-003, EPIC-006, EPIC-008

### Question

What evidence level is required for the bot to confirm a cause of invoice delta
without escalating to a human advisor?

### Why It Matters

An unproven answer may mislead the customer. A threshold that is too strict may
also create unnecessary escalations.

### Needed Decision

- Causes the bot may confirm alone.
- Causes the bot may present as probable.
- Causes that require escalation.
- Expected wording when certainty is insufficient.

---

## OQ-003 - BSS Data Availability And Granularity

**Status:** Open  
**Owner:** BSS owner  
**Impacts:** EPIC-001, EPIC-002, EPIC-003, EPIC-010

### Question

Which BSS data is available in read-only mode to explain invoice deltas?

### Why It Matters

The comparison engine and customer-visible evidence depend directly on available
granularity: invoice lines, usage, discounts, prorations, options, taxes, billing
events and offer changes.

### Needed Decision

- Data accessible in V1.
- Available history depth.
- Expected freshness.
- Access and confidentiality limits.
- Whether any structured invoice-line endpoint can replace PDF extraction later.

---

## OQ-004 - Invoice PDF Extraction Reliability And Fixture Coverage

**Status:** Open  
**Owner:** Product / BSS / QA  
**Impacts:** EPIC-002, EPIC-003, EPIC-010

### Question

Which real invoice PDFs and extraction quality thresholds are required to validate
the V1 explanation behavior?

### Why It Matters

ADR-0005 makes invoice PDF extraction the V1 evidence path until a validated
structured line endpoint exists. Product behavior depends on whether extraction
is `parseable`, `partial` or `unusable`.

### Needed Decision

- Minimum anonymized PDF samples for pilot validation.
- Required fixture journeys: nominal, discount expiry, overage, proration,
  insufficient data, partial/unusable extraction.
- Acceptance threshold for treating extracted lines as confirmed evidence.
- Expected customer wording for partial or unusable extraction.

---

## OQ-005 - Pilot Latency Acceptance Context

**Status:** Open  
**Owner:** Product / Architecture / Operations  
**Impacts:** EPIC-004, EPIC-005, EPIC-009

### Question

Under which measured conditions is the V1 voice journey accepted for the pilot?

### Why It Matters

ADR-0018 defines `time_to_first_audio` p95 below 800 ms as a pilot criterion in a
pre-warmed, co-located environment, not a production SLO. The backlog must avoid
turning an aspirational target into an unmeasured contractual promise.

### Needed Decision

- Measurement environment and sample size.
- Which journeys count toward the pilot metric.
- How long-running BSS evidence analysis is handled with a quick spoken
  acknowledgement.
- What latency or evidence failures require degraded mode or escalation.
