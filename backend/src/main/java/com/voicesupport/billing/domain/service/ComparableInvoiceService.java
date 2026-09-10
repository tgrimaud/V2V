package com.voicesupport.billing.domain.service;

import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceSummary;
import com.voicesupport.billing.domain.port.in.RetrieveComparableInvoicesUseCase;
import com.voicesupport.billing.domain.port.out.BssBillingPort;

import java.util.Comparator;
import java.util.List;
import java.util.Objects;

// Lists an account's invoices ordered most-recent-first (by invoice date) so the two latest are the
// head of the list — the pair the comparison engine (TASK-BE-042) will diff. Pure domain: wired to a
// BssBillingPort implementation (mock now, real adapter later) via @Bean in TASK-BE-040.
public class ComparableInvoiceService implements RetrieveComparableInvoicesUseCase {

    private static final Comparator<InvoiceSummary> MOST_RECENT_FIRST =
            Comparator.comparing((InvoiceSummary summary) -> summary.period().invoiceDate()).reversed();

    private final BssBillingPort bssBillingPort;

    public ComparableInvoiceService(BssBillingPort bssBillingPort) {
        this.bssBillingPort = Objects.requireNonNull(bssBillingPort, "bssBillingPort must not be null");
    }

    @Override
    public List<InvoiceSummary> availableInvoices(AccountId account) {
        Objects.requireNonNull(account, "account must not be null");
        return bssBillingPort.listInvoices(account).stream()
                .sorted(MOST_RECENT_FIRST)
                .toList();
    }
}
