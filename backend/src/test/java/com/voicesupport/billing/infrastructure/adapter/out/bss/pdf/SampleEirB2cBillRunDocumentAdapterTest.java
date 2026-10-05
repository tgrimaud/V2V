package com.voicesupport.billing.infrastructure.adapter.out.bss.pdf;

import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceSummary;
import com.voicesupport.billing.domain.model.valueobject.PdfSource;
import com.voicesupport.billing.infrastructure.adapter.out.pdf.PdfBoxInvoiceExtractorAdapter;
import com.voicesupport.billing.infrastructure.fixtures.EirB2cSampleFixtures;
import com.voicesupport.billing.infrastructure.pdf.EirB2cInvoiceLayoutParser;
import com.voicesupport.shared.observability.BackendTelemetry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

// TASK-BE-066: the sample document source must serve the ACTUAL eir B2C PDF bytes shipped on the
// classpath (not a synthetic shortcut), so the whole runtime path download -> PDFBox -> eir B2C
// layout parser -> domain Invoice is exercisable without the real Galaxion tenant (OQ-003). We prove
// (a) the adapter contract (catalog listing, real %PDF bytes, fail-closed on unknown ids) and (b) the
// full PdfBssBillingAdapter chain regenerates the transcribed invoices for all three sample accounts.
class SampleEirB2cBillRunDocumentAdapterTest {

    private final SampleEirB2cBillRunDocumentAdapter adapter = new SampleEirB2cBillRunDocumentAdapter();

    @Test
    void listDocuments_returnsTheTwoSampleInvoicesPerAccount() {
        // GIVEN the first sample account (one mobile line, August + September bill runs)
        AccountId account = AccountId.of("99224964");

        // WHEN its documents are listed
        List<InvoiceSummary> documents = adapter.listDocuments(account);

        // THEN both transcribed invoices are advertised with their ids
        assertEquals(2, documents.size());
        assertEquals(List.of("2608129000000039", "2609129000000008"),
                documents.stream().map(summary -> summary.id().value()).toList());
    }

    @Test
    void download_servesTheRealPdfBytesForAKnownInvoice() {
        // GIVEN a known account + invoice id
        AccountId account = AccountId.of("99224964");
        InvoiceId invoiceId = InvoiceId.of("2608129000000039");

        // WHEN the document is downloaded
        Optional<PdfSource> pdf = adapter.download(account, invoiceId);

        // THEN the real PDF bytes are returned (a genuine %PDF document, not a synthetic stand-in)
        assertTrue(pdf.isPresent());
        assertFalse(pdf.get().isEmpty());
        assertEquals(invoiceId.value(), pdf.get().reference());
        byte[] content = pdf.get().content();
        assertTrue(content.length > 1000, "a real PDF is far larger than a reference stub");
        assertEquals("%PDF", new String(content, 0, 4, StandardCharsets.US_ASCII), "PDF magic header");
    }

    @Test
    void download_isFailClosedForUnknownAccountOrInvoice() {
        // GIVEN an unknown account and an unknown invoice id on a known account
        assertTrue(adapter.download(AccountId.of("00000000"), InvoiceId.of("2608129000000039")).isEmpty());
        assertTrue(adapter.download(AccountId.of("99224964"), InvoiceId.of("9999999999999999")).isEmpty());
    }

    @Test
    void fullRuntimeChain_regeneratesEverySampleInvoiceFromTheRealPdf() {
        // GIVEN the PDF-backed BSS wired exactly like the runtime: sample documents + eir B2C extractor
        PdfBssBillingAdapter bss = new PdfBssBillingAdapter(
                adapter,
                new PdfBoxInvoiceExtractorAdapter(new EirB2cInvoiceLayoutParser()),
                new BackendTelemetry(new SimpleMeterRegistry()));
        Map<AccountId, List<Invoice>> fixtures = EirB2cSampleFixtures.all();

        for (Map.Entry<AccountId, List<Invoice>> entry : fixtures.entrySet()) {
            AccountId account = entry.getKey();
            // WHEN each advertised invoice is fetched (download real bytes -> parse)
            for (Invoice expected : entry.getValue()) {
                Optional<Invoice> fetched = bss.fetchInvoice(account, expected.id());

                // THEN the real PDF is parsed back into the transcribed invoice identity + total
                assertTrue(fetched.isPresent(), "fetch " + expected.id().value());
                assertEquals(expected.id().value(), fetched.get().id().value());
                assertEquals(expected.accountId().value(), fetched.get().accountId().value());
                assertEquals(expected.totals().taxIncluded().minorUnits(),
                        fetched.get().totals().taxIncluded().minorUnits(), "TTC " + expected.id().value());
            }
        }
    }
}
