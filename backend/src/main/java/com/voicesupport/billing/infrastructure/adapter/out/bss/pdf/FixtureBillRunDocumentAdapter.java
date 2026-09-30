package com.voicesupport.billing.infrastructure.adapter.out.bss.pdf;

import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceSummary;
import com.voicesupport.billing.domain.model.valueobject.PdfSource;
import com.voicesupport.billing.domain.port.out.BillRunDocumentPort;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

// Fixture BillRunDocumentPort standing in for Galaxion bill-run-documents until real read-only access
// is validated (OQ-003). Backed by the same in-memory invoice fixtures as the mock BSS, so switching
// VOICE_SUPPORT_BILLING_BSS_SOURCE to `pdf` exercises the whole download -> InvoicePdfExtractorPort ->
// Invoice path against the customer-eir-* / eir B2C samples. The synthetic PdfSource carries the
// invoice period id as its reference (what FixtureInvoicePdfExtractorAdapter indexes on) and non-empty
// bytes so it is not treated as an empty document. The real REST adapter registers later behind the
// same port (deferred: the /bill-run-documents/search response lacks period/amount — missing-inputs).
public class FixtureBillRunDocumentAdapter implements BillRunDocumentPort {

    private final Map<AccountId, List<Invoice>> invoicesByAccount;

    public FixtureBillRunDocumentAdapter(Map<AccountId, List<Invoice>> invoicesByAccount) {
        this.invoicesByAccount = Map.copyOf(Objects.requireNonNull(invoicesByAccount, "invoicesByAccount"));
    }

    @Override
    public List<InvoiceSummary> listDocuments(AccountId account) {
        Objects.requireNonNull(account, "account must not be null");
        return invoicesOf(account).stream().map(FixtureBillRunDocumentAdapter::toSummary).toList();
    }

    @Override
    public Optional<PdfSource> download(AccountId account, InvoiceId invoiceId) {
        Objects.requireNonNull(account, "account must not be null");
        Objects.requireNonNull(invoiceId, "invoiceId must not be null");
        return invoicesOf(account).stream()
                .filter(invoice -> invoice.id().equals(invoiceId))
                .findFirst()
                .map(FixtureBillRunDocumentAdapter::toPdfSource);
    }

    private List<Invoice> invoicesOf(AccountId account) {
        return invoicesByAccount.getOrDefault(account, List.of());
    }

    private static InvoiceSummary toSummary(Invoice invoice) {
        return new InvoiceSummary(invoice.id(), invoice.period(), invoice.totals().taxIncluded());
    }

    private static PdfSource toPdfSource(Invoice invoice) {
        String reference = invoice.period().id();
        return new PdfSource(reference, reference.getBytes(StandardCharsets.UTF_8));
    }
}
