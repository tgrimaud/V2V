package com.voicesupport.domain.service;

import com.voicesupport.domain.model.billing.Evidence;
import com.voicesupport.domain.model.billing.Invoice;
import com.voicesupport.domain.model.billing.InvoiceComparison;
import com.voicesupport.domain.model.billing.InvoiceComparisonDecision;
import com.voicesupport.domain.model.billing.InvoiceExtractionStatus;
import com.voicesupport.domain.model.billing.InvoiceLine;
import com.voicesupport.domain.model.billing.InvoiceLineCategory;
import com.voicesupport.domain.model.billing.Money;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class InvoiceComparisonServiceTest {

    private final InvoiceComparisonService service = new InvoiceComparisonService();

    @Test
    void compare_returns_full_comparison_when_both_invoices_are_parseable() {
        // GIVEN
        Invoice previous = invoice("INV-MAY", InvoiceExtractionStatus.PARSEABLE, 5000, line("plan", 5000));
        Invoice current = invoice("INV-JUN", InvoiceExtractionStatus.PARSEABLE, 6000, line("plan", 6000));

        // WHEN
        InvoiceComparison comparison = service.compare(previous, current);

        // THEN
        assertEquals(InvoiceComparisonDecision.FULL_COMPARISON, comparison.decision());
        assertEquals(1000, comparison.totalDelta().cents());
        assertEquals(1, comparison.lineDeltas().size());
        assertEquals(1000, comparison.lineDeltas().getFirst().delta().cents());
    }

    @Test
    void compare_returns_cautious_comparison_when_one_invoice_is_partial() {
        // GIVEN
        Invoice previous = invoice("INV-MAY", InvoiceExtractionStatus.PARSEABLE, 5000, line("plan", 5000));
        Invoice current = invoice("INV-JUN", InvoiceExtractionStatus.PARTIAL, 6000, line("plan", 6000));

        // WHEN
        InvoiceComparison comparison = service.compare(previous, current);

        // THEN
        assertEquals(InvoiceComparisonDecision.CAUTIOUS_COMPARISON, comparison.decision());
        assertEquals(1000, comparison.totalDelta().cents());
    }

    @Test
    void compare_forbids_comparison_when_one_invoice_is_unusable() {
        // GIVEN
        Invoice previous = invoice("INV-MAY", InvoiceExtractionStatus.UNUSABLE, 5000, line("plan", 5000));
        Invoice current = invoice("INV-JUN", InvoiceExtractionStatus.PARSEABLE, 6000, line("plan", 6000));

        // WHEN
        InvoiceComparison comparison = service.compare(previous, current);

        // THEN
        assertEquals(InvoiceComparisonDecision.FORBIDDEN, comparison.decision());
        assertFalse(comparison.allowed());
        assertEquals(0, comparison.lineDeltas().size());
        assertTrue(comparison.totalDelta().isZero());
    }

    @Test
    void compare_detects_appeared_and_disappeared_lines() {
        // GIVEN
        Invoice previous = invoice("INV-MAY", InvoiceExtractionStatus.PARSEABLE, 4000, line("discount", -1000));
        Invoice current = invoice("INV-JUN", InvoiceExtractionStatus.PARSEABLE, 6500, line("overage", 1500));

        // WHEN
        InvoiceComparison comparison = service.compare(previous, current);

        // THEN
        assertEquals(2, comparison.lineDeltas().size());
        assertEquals(1000, comparison.lineDeltas().getFirst().delta().cents());
        assertEquals(1500, comparison.lineDeltas().getLast().delta().cents());
    }

    @Test
    void invoice_line_requires_evidence() {
        // WHEN / THEN
        assertThrows(IllegalArgumentException.class, () -> new InvoiceLine(
                "line-1", "Plan", InvoiceLineCategory.SUBSCRIPTION, Money.ofCents(5000, "EUR"), List.of()));
    }

    @Test
    void compare_rejects_different_invoice_currencies() {
        // GIVEN
        Invoice previous = invoice("INV-MAY", InvoiceExtractionStatus.PARSEABLE, 5000, line("plan", 5000));
        Invoice current = new Invoice("INV-JUN", "account-1", InvoiceExtractionStatus.PARSEABLE,
                Money.ofCents(6000, "GBP"), List.of(line("plan", 6000)));

        // WHEN / THEN
        assertThrows(IllegalArgumentException.class, () -> service.compare(previous, current));
    }

    private Invoice invoice(String number, InvoiceExtractionStatus status, long total, InvoiceLine... lines) {
        return new Invoice(number, "account-1", status, Money.ofCents(total, "EUR"), List.of(lines));
    }

    private InvoiceLine line(String label, long cents) {
        return new InvoiceLine("line-" + label, label, category(label), Money.ofCents(cents, "EUR"), evidence(label));
    }

    private InvoiceLineCategory category(String label) {
        return switch (label) {
            case "discount" -> InvoiceLineCategory.DISCOUNT;
            case "overage" -> InvoiceLineCategory.OVERAGE;
            default -> InvoiceLineCategory.SUBSCRIPTION;
        };
    }

    private List<Evidence> evidence(String label) {
        return List.of(new Evidence("pdf", "page-1", label));
    }
}
