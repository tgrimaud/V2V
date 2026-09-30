package com.voicesupport.billing.infrastructure.adapter.out.bss.pdf;

import com.voicesupport.billing.domain.model.ExtractionResult;
import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.BillingPeriod;
import com.voicesupport.billing.domain.model.valueobject.InvoiceId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceLevel;
import com.voicesupport.billing.domain.model.valueobject.InvoiceSummary;
import com.voicesupport.billing.domain.model.valueobject.LineAmounts;
import com.voicesupport.billing.domain.model.valueobject.Money;
import com.voicesupport.billing.domain.model.valueobject.PdfSource;
import com.voicesupport.billing.domain.port.out.BillRunDocumentPort;
import com.voicesupport.billing.domain.port.out.InvoicePdfExtractorPort;
import com.voicesupport.shared.observability.BackendTelemetry;
import com.voicesupport.shared.observability.Slices;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.util.Currency;
import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PdfBssBillingAdapterTest {

    private static final Currency EUR = Currency.getInstance("EUR");
    private static final AccountId ACCOUNT = AccountId.of("99224964");
    private static final InvoiceId INVOICE = InvoiceId.of("113444");

    private final SimpleMeterRegistry registry = new SimpleMeterRegistry();
    private final BackendTelemetry telemetry = new BackendTelemetry(registry);
    private final FakeDocuments documents = new FakeDocuments();
    private final FakeExtractor extractor = new FakeExtractor();
    private final PdfBssBillingAdapter adapter = new PdfBssBillingAdapter(documents, extractor, telemetry);

    @Test
    void fetchInvoice_downloadsThenExtracts_regeneratingTheDomainInvoice() {
        // GIVEN a downloadable document that the extractor parses into the requested account's invoice
        Invoice parsed = invoice(ACCOUNT);
        documents.pdf = Optional.of(new PdfSource("202602", "pdf-bytes".getBytes(StandardCharsets.UTF_8)));
        extractor.next = ExtractionResult.success(parsed);

        // WHEN the invoice is fetched
        Optional<Invoice> result = adapter.fetchInvoice(ACCOUNT, INVOICE);

        // THEN the extracted invoice is returned, the download was account-scoped, the extractor saw the
        // downloaded bytes, and the BSS network hop is timed as its own slice (provider=pdf)
        assertSame(parsed, result.orElseThrow());
        assertEquals(ACCOUNT, documents.lastAccount);
        assertEquals(INVOICE, documents.lastInvoice);
        assertEquals("202602", extractor.lastSource.reference());
        assertBssSlice("success", "n/a");
    }

    @Test
    void fetchInvoice_partialExtraction_failsClosedPerBr003() {
        // GIVEN a partial extraction (some lines missing): BR-003 / ADR-0005 forbid treating it as
        // complete, so the PDF adapter fails closed (escalation) rather than exposing a skewed invoice
        documents.pdf = Optional.of(new PdfSource("202602", "x".getBytes(StandardCharsets.UTF_8)));
        extractor.next = ExtractionResult.partial(invoice(ACCOUNT), List.of("some lines could not be read"));

        // WHEN / THEN no invoice is returned and the slice records the extraction_partial reason
        assertTrue(adapter.fetchInvoice(ACCOUNT, INVOICE).isEmpty());
        assertBssSlice("error", "extraction_partial");
    }

    @Test
    void fetchInvoice_emptyDownload_failsClosedWithoutExtracting() {
        // GIVEN no document to download
        documents.pdf = Optional.empty();

        // WHEN the invoice is fetched
        Optional<Invoice> result = adapter.fetchInvoice(ACCOUNT, INVOICE);

        // THEN it fails closed to empty, never calls the extractor, and records document_unavailable
        assertTrue(result.isEmpty());
        assertFalse(extractor.called);
        assertBssSlice("error", "document_unavailable");
    }

    @Test
    void fetchInvoice_failedExtraction_failsClosed() {
        // GIVEN a downloadable document the extractor cannot parse
        documents.pdf = Optional.of(new PdfSource("202602", "corrupt".getBytes(StandardCharsets.UTF_8)));
        extractor.next = ExtractionResult.failed("unreadable document");

        // WHEN / THEN a FAILED extraction degrades to empty (safe escalation, never a 500)
        assertTrue(adapter.fetchInvoice(ACCOUNT, INVOICE).isEmpty());
        assertBssSlice("error", "extraction_failed");
    }

    @Test
    void fetchInvoice_ownershipMismatch_failsClosed() {
        // GIVEN the extracted invoice belongs to another account (BR-002-1 defense in depth)
        documents.pdf = Optional.of(new PdfSource("202602", "pdf".getBytes(StandardCharsets.UTF_8)));
        extractor.next = ExtractionResult.success(invoice(AccountId.of("someone-else")));

        // WHEN / THEN it is dropped rather than exposing another account's invoice
        assertTrue(adapter.fetchInvoice(ACCOUNT, INVOICE).isEmpty());
        assertBssSlice("error", "ownership_mismatch");
    }

    @Test
    void listInvoices_delegatesToTheDocumentPortAndTimesTheSlice() {
        // GIVEN the document port lists two documents for the account
        documents.summaries = List.of(summary(INVOICE), summary(InvoiceId.of("113443")));

        // WHEN the account's invoices are listed
        List<InvoiceSummary> summaries = adapter.listInvoices(ACCOUNT);

        // THEN the port result is returned, account-scoped, and the slice is recorded
        assertEquals(2, summaries.size());
        assertEquals(ACCOUNT, documents.lastAccount);
        assertBssSlice("success", "n/a");
    }

    private void assertBssSlice(String outcome, String reason) {
        assertTrue(registry.find("voice_support.slice")
                        .tag("slice", Slices.BSS).tag("provider", "pdf")
                        .tag("outcome", outcome).tag("reason", reason)
                        .timer().count() >= 1,
                "BSS slice must be recorded with provider=pdf outcome=" + outcome + " reason=" + reason);
    }

    private static Invoice invoice(AccountId owner) {
        Money amount = Money.ofMinorUnits(5000L, EUR);
        LineAmounts totals = new LineAmounts(amount, amount, Money.zero(EUR));
        return new Invoice(INVOICE, owner, InvoiceLevel.BILLING_ACCOUNT,
                new BillingPeriod("202602", LocalDate.of(2026, 2, 15)), totals, List.of());
    }

    private static InvoiceSummary summary(InvoiceId id) {
        return new InvoiceSummary(id, new BillingPeriod(id.value(), LocalDate.of(2026, 2, 15)),
                Money.ofMinorUnits(5000L, EUR));
    }

    private static final class FakeDocuments implements BillRunDocumentPort {
        private List<InvoiceSummary> summaries = List.of();
        private Optional<PdfSource> pdf = Optional.empty();
        private AccountId lastAccount;
        private InvoiceId lastInvoice;

        @Override
        public List<InvoiceSummary> listDocuments(AccountId account) {
            this.lastAccount = account;
            return summaries;
        }

        @Override
        public Optional<PdfSource> download(AccountId account, InvoiceId invoiceId) {
            this.lastAccount = account;
            this.lastInvoice = invoiceId;
            return pdf;
        }
    }

    private static final class FakeExtractor implements InvoicePdfExtractorPort {
        private ExtractionResult next = ExtractionResult.failed("none");
        private PdfSource lastSource;
        private boolean called;

        @Override
        public ExtractionResult extract(PdfSource source) {
            this.called = true;
            this.lastSource = source;
            return next;
        }
    }
}
