package com.voicesupport.billing.domain.port.in;

import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceSummary;

import java.util.List;

// Inbound use case (US-005): list the invoices available for an account, ordered most-recent-first so
// the caller can offer / pick the two latest to compare. Returns lightweight summaries; the full
// invoice tree is fetched separately through BssBillingPort when a comparison is run.
public interface RetrieveComparableInvoicesUseCase {

    List<InvoiceSummary> availableInvoices(AccountId account);
}
