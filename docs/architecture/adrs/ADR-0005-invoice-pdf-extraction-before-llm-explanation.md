# ADR-0005: Invoice PDFs Are Extracted Before LLM Explanation

## Status

Accepted

## Context

The identified Galaxion billing path provides invoice documents through
`billing-api`, but no validated endpoint has been identified yet for structured
invoice lines.

The V1 billing assistant still needs line-level evidence to compare invoices and
explain deltas.

## Decision

Invoice PDF documents must be extracted into deterministic structured JSON before
comparison and before any LLM-generated explanation.

The `InvoicePdfExtractor` contract must produce normalized invoice data suitable
for reconciliation and comparison. The LLM may cite or explain the extracted
evidence, but it must not parse the PDF as the primary calculation mechanism.

## Consequences

- PDF extraction quality becomes a critical part of billing correctness.
- Extraction contracts must use stable numeric formats, including integer cents
  for internal calculation inputs.
- Extraction failures must be explicit and may trigger escalation.
- If a structured BSS endpoint is validated later, it can replace or complement
  PDF extraction behind the same domain port.

## Alternatives Considered

- **Let the LLM read invoice PDFs directly**: rejected because billing amounts
  and line-level evidence must be deterministic and auditable.
- **Wait for a structured invoice-line endpoint**: rejected because V1 can move
  forward with a controlled extraction contract while keeping the port
  replaceable.

## Related Documents

- `docs/integrations/galaxion/bss-integration-plan.md`
- `docs/integrations/galaxion/invoice-extraction-json.md`
