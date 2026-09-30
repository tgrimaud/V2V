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
import com.voicesupport.billing.infrastructure.adapter.out.pdf.FixtureInvoicePdfExtractorAdapter;
import org.junit.jupiter.api.Test;

import java.time.LocalDate;
import java.util.Currency;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FixtureBillRunDocumentAdapterTest {

    private static final Currency EUR = Currency.getInstance("EUR");
    private static final AccountId ACCOUNT = AccountId.of("99224964");
    private static final InvoiceId INVOICE = InvoiceId.of("113444");

    private final Map<AccountId, List<Invoice>> fixtures = Map.of(ACCOUNT, List.of(invoice()));
    private final FixtureBillRunDocumentAdapter adapter = new FixtureBillRunDocumentAdapter(fixtures);

    @Test
    void listDocuments_mapsInvoicesToSummaries() {
        // WHEN the account's documents are listed
        List<InvoiceSummary> summaries = adapter.listDocuments(ACCOUNT);

        // THEN one summary maps with the invoice id, period and TTC total
        assertEquals(1, summaries.size());
        assertEquals("113444", summaries.get(0).id().value());
        assertEquals(5000L, summaries.get(0).totalTaxIncluded().minorUnits());
    }

    @Test
    void listDocuments_unknownAccount_isEmpty() {
        // GIVEN / WHEN / THEN an unknown account lists no documents (fail-closed, BR-002-1)
        assertTrue(adapter.listDocuments(AccountId.of("00000000")).isEmpty());
    }

    @Test
    void download_returnsNonEmptyPdfWhoseReferenceIsThePeriodId() {
        // WHEN a known invoice is downloaded
        Optional<PdfSource> pdf = adapter.download(ACCOUNT, INVOICE);

        // THEN a non-empty PDF is produced and its reference is the invoice period id (the key the
        // fixture extractor indexes on)
        assertTrue(pdf.isPresent());
        assertEquals("202602", pdf.get().reference());
        assertFalse(pdf.get().isEmpty());
    }

    @Test
    void download_unknownInvoiceOrAccount_isEmpty() {
        // GIVEN / WHEN / THEN a missing invoice or a foreign account yields no document
        assertTrue(adapter.download(ACCOUNT, InvoiceId.of("999999")).isEmpty());
        assertTrue(adapter.download(AccountId.of("00000000"), INVOICE).isEmpty());
    }

    @Test
    void download_thenFixtureExtractor_regeneratesTheInvoice() {
        // GIVEN the fixture extractor built from the same invoices (proves the reference contract lines
        // up between the two fixture adapters end to end)
        FixtureInvoicePdfExtractorAdapter fixtureExtractor = new FixtureInvoicePdfExtractorAdapter(fixtures);
        PdfSource pdf = adapter.download(ACCOUNT, INVOICE).orElseThrow();

        // WHEN the downloaded document is extracted
        ExtractionResult result = fixtureExtractor.extract(pdf);

        // THEN the same invoice is regenerated (SUCCESS)
        assertTrue(result.hasInvoice());
        assertEquals(INVOICE, result.invoice().id());
        assertEquals(ACCOUNT, result.invoice().accountId());
    }

    private static Invoice invoice() {
        Money amount = Money.ofMinorUnits(5000L, EUR);
        LineAmounts totals = new LineAmounts(amount, amount, Money.zero(EUR));
        return new Invoice(INVOICE, ACCOUNT, InvoiceLevel.BILLING_ACCOUNT,
                new BillingPeriod("202602", LocalDate.of(2026, 2, 15)), totals, List.of());
    }
}
