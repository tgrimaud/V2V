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

    // End-to-end on the REAL parsed PDFs: the +€55.47 increase is fully attributed to the real line
    // changes with zero residual. This exercises BUG-028's fix — EirB2cInvoiceLayoutParser now emits a
    // stable, invoice-unique slug code per line, so the comparison keeps the two SEPTEMBER OPTION lines
    // ("15GB Bundle" €14.99 and "eir Mobile Security" €1.99) distinct instead of collapsing them by
    // category name (previously dropping the €1.99 into an unexplained residual).
    @Test
    void payMoreThisMonth_account99224964_isFullyExplainedFromTheRealParsedPdfs() {
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
        assertEquals(1698L, impactByCause.get(BillingCauseType.OPTION_CHANGE),
                "15GB Bundle €14.99 + eir Mobile Security €1.99 (both kept — BUG-028 fixed)");

        // AND nothing is left unexplained: the identified causes account for the whole delta (BR-003).
        assertEquals(0, result.unexplainedAmount().minorUnits(), "nothing unexplained");
        long explained = impactByCause.values().stream().mapToLong(Long::longValue).sum();
        assertEquals(5547L, explained, "identified causes sum to the total delta");
    }
}
