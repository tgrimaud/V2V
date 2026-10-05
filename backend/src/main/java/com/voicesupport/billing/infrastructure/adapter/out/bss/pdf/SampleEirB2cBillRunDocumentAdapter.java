package com.voicesupport.billing.infrastructure.adapter.out.bss.pdf;

import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceSummary;
import com.voicesupport.billing.domain.model.valueobject.PdfSource;
import com.voicesupport.billing.domain.port.out.BillRunDocumentPort;
import com.voicesupport.billing.infrastructure.fixtures.EirB2cSampleFixtures;

import java.io.IOException;
import java.io.InputStream;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

// Real-PDF document source for the eir B2C samples (TASK-BE-066, ADR-0005): unlike the synthetic
// FixtureBillRunDocumentAdapter (whose download() returns the period id as bytes and relies on the
// fixture extractor to shortcut back to the transcribed Invoice), this adapter serves the ACTUAL
// anonymized sample PDF bytes shipped on the classpath (src/main/resources/billing/eir-b2c). Paired
// with pdf.source=eir-b2c it exercises the whole runtime path end to end: download real bytes ->
// PDFBox text -> EirB2cInvoiceLayoutParser -> domain Invoice -> comparison. The LLM never reads the
// PDF (DEC-002). The catalog (which invoices exist + their period/total for listDocuments) is taken
// from EirB2cSampleFixtures as the search-metadata stand-in (the real bill-run-documents /search is
// deferred, OQ-003); the compared invoices themselves come from parsing the real bytes, not the
// fixtures. The sample PDF file name embeds the bill-run date as the invoice id's leading YYMMDD
// (e.g. 2608129...-> 20260812), so the file is resolved deterministically from the account + id.
public class SampleEirB2cBillRunDocumentAdapter implements BillRunDocumentPort {

    private static final String RESOURCE_BASE = "/billing/eir-b2c/";
    private static final String FILE_SUFFIX = "_B2C.pdf";
    private static final String FILE_INFIX = "_EIR_MOBILE_TEST_";

    private final Map<AccountId, List<InvoiceSummary>> catalog;

    public SampleEirB2cBillRunDocumentAdapter() {
        this(EirB2cSampleFixtures.all());
    }

    SampleEirB2cBillRunDocumentAdapter(Map<AccountId, List<Invoice>> sampleInvoices) {
        this.catalog = buildCatalog(sampleInvoices);
    }

    @Override
    public List<InvoiceSummary> listDocuments(AccountId account) {
        Objects.requireNonNull(account, "account must not be null");
        return catalog.getOrDefault(account, List.of());
    }

    @Override
    public Optional<PdfSource> download(AccountId account, InvoiceId invoiceId) {
        Objects.requireNonNull(account, "account must not be null");
        Objects.requireNonNull(invoiceId, "invoiceId must not be null");
        if (!knownInvoice(account, invoiceId)) {
            return Optional.empty();
        }
        byte[] bytes = readResource(resourceName(account, invoiceId));
        if (bytes == null || bytes.length == 0) {
            return Optional.empty();
        }
        return Optional.of(new PdfSource(invoiceId.value(), bytes));
    }

    private boolean knownInvoice(AccountId account, InvoiceId invoiceId) {
        return catalog.getOrDefault(account, List.of()).stream()
                .anyMatch(summary -> summary.id().equals(invoiceId));
    }

    // <account>_EIR_MOBILE_TEST_20<YYMMDD>_B2C.pdf, where YYMMDD is the invoice id's bill-run date
    // prefix (eir bill numbers start with the 6-digit yy-mm-dd of the bill run, e.g. 2608129...).
    private static String resourceName(AccountId account, InvoiceId invoiceId) {
        String id = invoiceId.value();
        String dateTag = "20" + id.substring(0, 6);
        return account.value() + FILE_INFIX + dateTag + FILE_SUFFIX;
    }

    private static byte[] readResource(String fileName) {
        try (InputStream in = SampleEirB2cBillRunDocumentAdapter.class
                .getResourceAsStream(RESOURCE_BASE + fileName)) {
            return in == null ? null : in.readAllBytes();
        } catch (IOException e) {
            return null;
        }
    }

    private static Map<AccountId, List<InvoiceSummary>> buildCatalog(
            Map<AccountId, List<Invoice>> sampleInvoices) {
        Map<AccountId, List<InvoiceSummary>> byAccount = new LinkedHashMap<>();
        sampleInvoices.forEach((account, invoices) ->
                byAccount.put(account, invoices.stream().map(SampleEirB2cBillRunDocumentAdapter::toSummary).toList()));
        return Map.copyOf(byAccount);
    }

    private static InvoiceSummary toSummary(Invoice invoice) {
        return new InvoiceSummary(invoice.id(), invoice.period(), invoice.totals().taxIncluded());
    }
}
