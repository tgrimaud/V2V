package com.voicesupport.billing.infrastructure.adapter.out.bss;

import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceSummary;
import com.voicesupport.billing.domain.port.out.BssBillingPort;

import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

// In-memory BssBillingPort backed by static fixtures (TASK-BE-040) — the API-compatible stand-in for
// the real billing-api adapter (TASK-BE-047) so the domain and QA journeys run before live access.
// Fail-closed on identity (BR-002-1): an unknown account yields no invoices, and fetchInvoice only
// returns an invoice that belongs to the requested account.
public class InMemoryBssBillingAdapter implements BssBillingPort {

    private final Map<AccountId, List<Invoice>> invoicesByAccount;

    public InMemoryBssBillingAdapter(Map<AccountId, List<Invoice>> invoicesByAccount) {
        this.invoicesByAccount = Map.copyOf(Objects.requireNonNull(invoicesByAccount, "invoicesByAccount"));
    }

    @Override
    public List<InvoiceSummary> listInvoices(AccountId account) {
        Objects.requireNonNull(account, "account must not be null");
        return invoicesOf(account).stream().map(InMemoryBssBillingAdapter::toSummary).toList();
    }

    @Override
    public Optional<Invoice> fetchInvoice(AccountId account, InvoiceId invoiceId) {
        Objects.requireNonNull(account, "account must not be null");
        Objects.requireNonNull(invoiceId, "invoiceId must not be null");
        return invoicesOf(account).stream().filter(invoice -> invoice.id().equals(invoiceId)).findFirst();
    }

    private List<Invoice> invoicesOf(AccountId account) {
        return invoicesByAccount.getOrDefault(account, List.of());
    }

    private static InvoiceSummary toSummary(Invoice invoice) {
        return new InvoiceSummary(invoice.id(), invoice.period(), invoice.totals().taxIncluded());
    }
}
