package com.voicesupport.billing.infrastructure.pdf;

import com.voicesupport.billing.domain.model.BillingCause;
import com.voicesupport.billing.domain.model.BillingCauseType;
import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.InvoiceComparison;
import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceSummary;
import com.voicesupport.billing.domain.port.in.CompareInvoicesUseCase;
import com.voicesupport.billing.domain.port.in.RetrieveComparableInvoicesUseCase;
import com.voicesupport.billing.domain.port.out.BssBillingPort;
import com.voicesupport.billing.domain.service.ComparableInvoiceService;
import com.voicesupport.billing.domain.service.InvoiceComparisonService;
import com.voicesupport.billing.infrastructure.adapter.out.bss.pdf.PdfBssBillingAdapter;
import com.voicesupport.billing.infrastructure.adapter.out.bss.pdf.SampleEirB2cBillRunDocumentAdapter;
import com.voicesupport.billing.infrastructure.adapter.out.pdf.PdfBoxInvoiceExtractorAdapter;
import com.voicesupport.shared.observability.BackendTelemetry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertEquals;

// TASK-BE-066 — the user's question "why do I pay more this month?" for account 99224964, answered
// end to end from the REAL eir B2C PDFs with no LLM and no database: the sample PDF bytes are served
// by SampleEirB2cBillRunDocumentAdapter, parsed by the eir B2C PDFBox layout parser through the
// PdfBssBillingAdapter, listed most-recent-first by ComparableInvoiceService, then diffed by the
// deterministic InvoiceComparisonService. This proves the explanation is driven by the real parsed
// invoice amounts (the LLM only phrases this grounded, pre-computed result — DEC-002).
class EirB2cBillingComparisonE2eTest {

    private final BssBillingPort bss = new PdfBssBillingAdapter(
            new SampleEirB2cBillRunDocumentAdapter(),
            new PdfBoxInvoiceExtractorAdapter(new EirB2cInvoiceLayoutParser()),
            new BackendTelemetry(new SimpleMeterRegistry()));
    private final RetrieveComparableInvoicesUseCase comparables = new ComparableInvoiceService(bss);
    private final CompareInvoicesUseCase comparison = new InvoiceComparisonService();

    // Characterization of the current end-to-end behaviour. The real parsed invoices drive the
    // comparison (real totals + delta + the business causes), BUT a known residual of €1.99 is left
    // unexplained: BUG-028 — EirB2cInvoiceLayoutParser emits InvoiceItem with code=null, so the
    // comparison (which matches lines by code, falling back to the category name) collapses the two
    // SEPTEMBER OPTION lines ("15GB Bundle" €14.99 and "eir Mobile Security" €1.99) into one and drops
    // the €1.99 from the diff. Fixtures hid this (unique synthetic codes); real parsed data exposes it.
    // When BUG-028 is fixed, flip unexplained to 0 and OPTION_CHANGE to 1698 (1499 + 199).
    @Test
    void payMoreThisMonth_account99224964_isDrivenByTheRealParsedPdfs_withKnownResidual() {
        // GIVEN the account's invoices listed most-recent-first (September first, then August)
        AccountId account = AccountId.of("99224964");
        List<InvoiceSummary> available = comparables.availableInvoices(account);
        assertEquals(2, available.size());
        InvoiceId september = available.get(0).id();
        InvoiceId august = available.get(1).id();
        assertEquals("2609129000000008", september.value(), "most recent = September");
        assertEquals("2608129000000039", august.value(), "previous = August");

        // WHEN both invoices are fetched from the REAL PDFs (download bytes -> PDFBox -> parse) and compared
        Invoice sep = bss.fetchInvoice(account, september).orElseThrow();
        Invoice aug = bss.fetchInvoice(account, august).orElseThrow();
        assertEquals(1999, aug.totals().taxIncluded().minorUnits(), "August total TTC (€19.99) from the real PDF");
        assertEquals(7546, sep.totals().taxIncluded().minorUnits(), "September total TTC (€75.46) from the real PDF");
        InvoiceComparison result = comparison.compare(aug, sep);

        // THEN the +€55.47 increase comes from the real parsed amounts and is attributed to the real causes
        assertEquals(5547, result.totalDelta().minorUnits(), "total delta +€55.47 from the real invoices");
        Map<BillingCauseType, Long> impactByCause = result.causes().stream()
                .collect(Collectors.toMap(BillingCause::type, cause -> cause.impact().minorUnits()));
        assertEquals(2999L, impactByCause.get(BillingCauseType.ONE_OFF_FEE), "1GB USA/Canada roaming bundle");
        assertEquals(850L, impactByCause.get(BillingCauseType.PRORATION), "15GB bundle prorata");
        assertEquals(1499L, impactByCause.get(BillingCauseType.OPTION_CHANGE), "15GB Bundle (mobile security dropped — BUG-028)");

        // AND a known €1.99 residual remains until BUG-028 (parser line codes) is fixed — target 0.
        assertEquals(199, result.unexplainedAmount().minorUnits(), "KNOWN residual pending BUG-028 (target 0)");
    }
}
