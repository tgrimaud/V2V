package com.voicesupport.billing.infrastructure.pdf;

import com.voicesupport.billing.domain.model.BillingCause;
import com.voicesupport.billing.domain.model.BillingCauseType;
import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.InvoiceComparison;
import com.voicesupport.billing.domain.model.valueobject.AccountId;
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

    // 99224964 (single mobile line) — the +€55.47 increase is FULLY explained, zero residual. Exercises
    // BUG-028's fix: the two September OPTION lines ("15GB Bundle" €14.99 and "eir Mobile Security" €1.99)
    // stay distinct (stable slug codes) instead of collapsing by category name (which dropped the €1.99).
    @Test
    void account99224964_singleMobileLine_isFullyExplained() {
        InvoiceComparison result = compareSeptemberVsAugust("99224964", "2609129000000008", "2608129000000039",
                1999, 7546);

        assertEquals(5547, result.totalDelta().minorUnits(), "total delta +€55.47 from the real invoices");
        Map<BillingCauseType, Long> impact = impacts(result);
        assertEquals(2999L, impact.get(BillingCauseType.ONE_OFF_FEE), "1GB USA/Canada roaming bundle");
        assertEquals(850L, impact.get(BillingCauseType.PRORATION), "15GB bundle prorata");
        assertEquals(1698L, impact.get(BillingCauseType.OPTION_CHANGE),
                "15GB Bundle €14.99 + eir Mobile Security €1.99 (both kept — BUG-028 fixed)");
        assertEquals(0, result.unexplainedAmount().minorUnits(), "nothing unexplained");
        assertEquals(5547L, impact.values().stream().mapToLong(Long::longValue).sum(),
                "identified causes sum to the whole delta (BR-003)");
    }

    // 99226126 (fibre → fibre + new eir TV) — a strong BUG-028 regression case: three DISCOUNT lines
    // (one fibre + two new TV, incl. a prorata) that ALL share the DISCOUNT category. Before the fix they
    // collapsed to a single DISCOUNT key; now each is kept, so DISCOUNT_EXPIRY sums the two real TV
    // discounts. The new eir TV base line is a SUBSCRIPTION, which maps to UNEXPLAINED by current design,
    // so it surfaces as a (traceable) residual — see TASK-BE-067.
    @Test
    void account99226126_newTvService_keepsEveryDiscountLine_baseIsResidual() {
        InvoiceComparison result = compareSeptemberVsAugust("99226126", "2609129000000009", "2608129000000040",
                13998, 7347);

        assertEquals(-6651, result.totalDelta().minorUnits(), "net change −€66.51 (install fee gone, TV added)");
        Map<BillingCauseType, Long> impact = impacts(result);
        assertEquals(-9999L, impact.get(BillingCauseType.ONE_OFF_FEE), "fibre installation fee no longer billed");
        assertEquals(1133L, impact.get(BillingCauseType.PRORATION), "eir TV prorata");
        assertEquals(-783L, impact.get(BillingCauseType.DISCOUNT_EXPIRY),
                "BOTH new TV discounts kept: −€2.83 prorata + −€5.00 (BUG-028: not collapsed)");
        assertEquals(999L, impact.get(BillingCauseType.OPTION_CHANGE), "eir TV Extra pack");
        assertEquals(1999, result.unexplainedAmount().minorUnits(),
                "new eir TV base subscription €19.99 → SUBSCRIPTION maps to UNEXPLAINED (TASK-BE-067)");
    }

    // 99226337 (fibre + TV → fibre + TV + new mobile 5G) — the richest invoice: multiple DISCOUNT lines
    // across three sections, prorata lines appearing AND disappearing. BUG-028 proof: the three real
    // discount deltas are all kept (DISCOUNT_EXPIRY = +€0.64 − €5.66 − €10.00). The new eir Mobile 5G base
    // line is a SUBSCRIPTION → the €64.99 residual.
    @Test
    void account99226337_newMobile5gService_keepsEveryDiscountAndProrata_baseIsResidual() {
        InvoiceComparison result = compareSeptemberVsAugust("99226337", "2609129000000011", "2608129000000042",
                14689, 18112);

        assertEquals(3423, result.totalDelta().minorUnits(), "net change +€34.23");
        Map<BillingCauseType, Long> impact = impacts(result);
        assertEquals(-4999L, impact.get(BillingCauseType.ONE_OFF_FEE), "broadband activation fee no longer billed");
        assertEquals(3425L, impact.get(BillingCauseType.PRORATION),
                "mobile 5G prorata +€36.83 minus the Aug TV prorata −€2.58 that rolled off");
        assertEquals(-1502L, impact.get(BillingCauseType.DISCOUNT_EXPIRY),
                "three discount deltas kept: +€0.64 − €5.66 − €10.00 (BUG-028: not collapsed)");
        assertEquals(6499, result.unexplainedAmount().minorUnits(),
                "new eir Mobile Connect Plus 5G base €64.99 → SUBSCRIPTION maps to UNEXPLAINED (TASK-BE-067)");
    }

    private InvoiceComparison compareSeptemberVsAugust(String accountId, String septemberId, String augustId,
            long augustTotalCents, long septemberTotalCents) {
        AccountId account = AccountId.of(accountId);
        List<InvoiceSummary> available = comparables.availableInvoices(account);
        assertEquals(2, available.size(), "two bill runs for " + accountId);
        assertEquals(septemberId, available.get(0).id().value(), "most recent = September for " + accountId);
        assertEquals(augustId, available.get(1).id().value(), "previous = August for " + accountId);
        Invoice september = bss.fetchInvoice(account, available.get(0).id()).orElseThrow();
        Invoice august = bss.fetchInvoice(account, available.get(1).id()).orElseThrow();
        assertEquals(augustTotalCents, august.totals().taxIncluded().minorUnits(), "August total " + accountId);
        assertEquals(septemberTotalCents, september.totals().taxIncluded().minorUnits(),
                "September total " + accountId);
        return comparison.compare(august, september);
    }

    private static Map<BillingCauseType, Long> impacts(InvoiceComparison result) {
        return result.causes().stream()
                .collect(Collectors.toMap(BillingCause::type, cause -> cause.impact().minorUnits()));
    }
}
