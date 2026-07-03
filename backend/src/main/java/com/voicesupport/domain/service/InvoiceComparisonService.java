package com.voicesupport.domain.service;

import com.voicesupport.domain.model.billing.Invoice;
import com.voicesupport.domain.model.billing.InvoiceComparison;
import com.voicesupport.domain.model.billing.InvoiceComparisonDecision;
import com.voicesupport.domain.model.billing.InvoiceLine;
import com.voicesupport.domain.model.billing.LineDelta;
import com.voicesupport.domain.model.billing.Money;
import com.voicesupport.domain.port.in.CompareInvoicesUseCase;

import java.util.List;
import java.util.Map;
import java.util.TreeSet;
import java.util.function.Function;
import java.util.stream.Collectors;

public class InvoiceComparisonService implements CompareInvoicesUseCase {

    @Override
    public InvoiceComparison compare(Invoice previous, Invoice current) {
        InvoiceComparisonDecision decision = decision(previous, current);
        Money totalDelta = totalDelta(previous, current, decision);
        List<LineDelta> deltas = decision == InvoiceComparisonDecision.FORBIDDEN
                ? List.of()
                : lineDeltas(previous, current);
        return new InvoiceComparison(previous.invoiceNumber(), current.invoiceNumber(), decision, totalDelta, deltas);
    }

    private Money totalDelta(Invoice previous, Invoice current, InvoiceComparisonDecision decision) {
        if (decision == InvoiceComparisonDecision.FORBIDDEN) {
            return Money.zero(current.totalTaxIncluded().currency());
        }
        return current.totalTaxIncluded().minus(previous.totalTaxIncluded());
    }

    private InvoiceComparisonDecision decision(Invoice previous, Invoice current) {
        if (previous.comparisonForbidden() || current.comparisonForbidden()) {
            return InvoiceComparisonDecision.FORBIDDEN;
        }
        if (previous.requiresCaution() || current.requiresCaution()) {
            return InvoiceComparisonDecision.CAUTIOUS_COMPARISON;
        }
        return InvoiceComparisonDecision.FULL_COMPARISON;
    }

    private List<LineDelta> lineDeltas(Invoice previous, Invoice current) {
        LineIndexes indexes = new LineIndexes(
                indexByComparisonKey(previous.lines()),
                indexByComparisonKey(current.lines()),
                current.totalTaxIncluded().currency());
        return indexes.allKeys().stream()
                .map(key -> lineDelta(key, indexes))
                .filter(delta -> !delta.delta().isZero())
                .toList();
    }

    private Map<String, InvoiceLine> indexByComparisonKey(List<InvoiceLine> lines) {
        return lines.stream().collect(Collectors.toMap(InvoiceLine::comparisonKey, Function.identity()));
    }

    private LineDelta lineDelta(String key, LineIndexes indexes) {
        InvoiceLine previous = indexes.previousLines().get(key);
        InvoiceLine current = indexes.currentLines().get(key);
        Money previousAmount = amountOrZero(previous, indexes.currency());
        Money currentAmount = amountOrZero(current, indexes.currency());
        InvoiceLine reference = current != null ? current : previous;
        return new LineDelta(reference.label(), reference.category(), previousAmount,
                currentAmount, currentAmount.minus(previousAmount));
    }

    private Money amountOrZero(InvoiceLine line, String currency) {
        return line == null ? Money.zero(currency) : line.amount();
    }

    private record LineIndexes(Map<String, InvoiceLine> previousLines,
                               Map<String, InvoiceLine> currentLines,
                               String currency) {

        TreeSet<String> allKeys() {
            TreeSet<String> keys = new TreeSet<>(previousLines.keySet());
            keys.addAll(currentLines.keySet());
            return keys;
        }
    }
}
