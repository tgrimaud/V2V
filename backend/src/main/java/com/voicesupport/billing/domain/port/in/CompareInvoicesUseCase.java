package com.voicesupport.billing.domain.port.in;

import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.InvoiceComparison;

// Inbound use case (US-010..013, ADR-0003, DEC-002): deterministically compare two invoices and
// return the line deltas, the business causes and the unexplained residual. Amounts and causes are
// computed here by code — the LLM only phrases this grounded result, it never computes anything.
public interface CompareInvoicesUseCase {

    InvoiceComparison compare(Invoice previous, Invoice current);
}
