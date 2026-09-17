package com.voicesupport.billing.domain.port.out;

import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceSummary;

import java.util.List;
import java.util.Optional;

// Read-only access to the billing source of truth (BSS), typed to the billing domain (ADR-0004): the
// domain never talks to billing-api / the BSS directly. V1 needs to list the invoices available for
// an account (to choose two to compare) and to fetch one invoice's full line tree. Every call is
// scoped by AccountId so a customer can only ever reach their own data (BR-002-1). No mutation.
// Implementations: a mock + fixtures (TASK-BE-040) now, the real billing-api adapter (TASK-BE-047)
// once access is confirmed (OQ-003).
public interface BssBillingPort {

    List<InvoiceSummary> listInvoices(AccountId account);

    Optional<Invoice> fetchInvoice(AccountId account, InvoiceId invoiceId);
}
