package com.voicesupport.billing.domain.service;

import com.voicesupport.billing.domain.model.BillingCause;
import com.voicesupport.billing.domain.model.BillingCauseType;
import com.voicesupport.billing.domain.model.ChangeKind;
import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.InvoiceComparison;
import com.voicesupport.billing.domain.model.InvoiceItem;
import com.voicesupport.billing.domain.model.LineDelta;
import com.voicesupport.billing.domain.model.valueobject.LineCategory;
import com.voicesupport.billing.domain.model.valueobject.Money;
import com.voicesupport.billing.domain.port.in.CompareInvoicesUseCase;

import java.util.ArrayList;
import java.util.Currency;
import java.util.EnumMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

// Deterministic invoice comparison (ADR-0003, DEC-002): matches lines by code across the two
// invoices, computes each line's signed contribution on the tax-included (TTC) basis, attributes it
// to a business cause from its category, and exposes the residual the line deltas do not account for
// (BR-003 — never hidden). No LLM, no guessing: the engine only does exact arithmetic.
public class InvoiceComparisonService implements CompareInvoicesUseCase {

    private static final Map<LineCategory, BillingCauseType> CAUSE_BY_CATEGORY = causeByCategory();

    @Override
    public InvoiceComparison compare(Invoice previous, Invoice current) {
        Objects.requireNonNull(previous, "previous invoice must not be null");
        Objects.requireNonNull(current, "current invoice must not be null");
        Money totalDelta = current.totals().taxIncluded().minus(previous.totals().taxIncluded());
        Currency currency = totalDelta.currency();
        List<CategorizedDelta> categorized = lineDeltas(previous, current);
        List<LineDelta> deltas = categorized.stream().map(CategorizedDelta::delta).toList();
        List<BillingCause> causes = causes(categorized, currency);
        Money unexplained = totalDelta.minus(sum(deltas, currency));
        return new InvoiceComparison(previous, current, totalDelta, deltas, causes, unexplained);
    }

    private List<CategorizedDelta> lineDeltas(Invoice previous, Invoice current) {
        Map<String, InvoiceItem> previousLines = index(previous.lines());
        Map<String, InvoiceItem> currentLines = index(current.lines());
        List<CategorizedDelta> result = new ArrayList<>();
        for (String key : union(previousLines, currentLines)) {
            CategorizedDelta delta = delta(previousLines.get(key), currentLines.get(key));
            if (delta != null) {
                result.add(delta);
            }
        }
        return result;
    }

    private CategorizedDelta delta(InvoiceItem previous, InvoiceItem current) {
        InvoiceItem present = current != null ? current : previous;
        Currency currency = present.amounts().taxIncluded().currency();
        Money previousAmount = previous != null ? previous.amounts().taxIncluded() : Money.zero(currency);
        Money currentAmount = current != null ? current.amounts().taxIncluded() : Money.zero(currency);
        Money contribution = currentAmount.minus(previousAmount);
        if (contribution.isZero()) {
            return null;
        }
        LineDelta lineDelta = new LineDelta(label(present), kind(previous, current),
                previousAmount, currentAmount, contribution);
        return new CategorizedDelta(lineDelta, cause(present.category()));
    }

    private List<BillingCause> causes(List<CategorizedDelta> categorized, Currency currency) {
        Map<BillingCauseType, List<LineDelta>> byCause = new EnumMap<>(BillingCauseType.class);
        for (CategorizedDelta item : categorized) {
            byCause.computeIfAbsent(item.cause(), key -> new ArrayList<>()).add(item.delta());
        }
        List<BillingCause> result = new ArrayList<>();
        for (BillingCauseType type : BillingCauseType.values()) {
            List<LineDelta> deltas = byCause.get(type);
            if (deltas != null) {
                result.add(new BillingCause(type, sum(deltas, currency), deltas));
            }
        }
        return result;
    }

    private static Map<String, InvoiceItem> index(List<InvoiceItem> lines) {
        Map<String, InvoiceItem> byKey = new LinkedHashMap<>();
        for (InvoiceItem line : lines) {
            byKey.putIfAbsent(label(line), line);
        }
        return byKey;
    }

    private static Set<String> union(Map<String, InvoiceItem> previous, Map<String, InvoiceItem> current) {
        Set<String> keys = new LinkedHashSet<>(previous.keySet());
        keys.addAll(current.keySet());
        return keys;
    }

    private static Money sum(List<LineDelta> deltas, Currency currency) {
        return deltas.stream().map(LineDelta::contribution).reduce(Money.zero(currency), Money::plus);
    }

    private static ChangeKind kind(InvoiceItem previous, InvoiceItem current) {
        if (previous == null) {
            return ChangeKind.APPEARED;
        }
        if (current == null) {
            return ChangeKind.DISAPPEARED;
        }
        return ChangeKind.CHANGED;
    }

    private static String label(InvoiceItem item) {
        if (item.code() != null && !item.code().isBlank()) {
            return item.code();
        }
        return item.type() != null ? item.type() : item.category().name();
    }

    private static BillingCauseType cause(LineCategory category) {
        return CAUSE_BY_CATEGORY.getOrDefault(category, BillingCauseType.UNEXPLAINED);
    }

    private static Map<LineCategory, BillingCauseType> causeByCategory() {
        Map<LineCategory, BillingCauseType> map = new EnumMap<>(LineCategory.class);
        map.put(LineCategory.DISCOUNT, BillingCauseType.DISCOUNT_EXPIRY);
        map.put(LineCategory.USAGE, BillingCauseType.USAGE_OVERAGE);
        map.put(LineCategory.OVERAGE, BillingCauseType.USAGE_OVERAGE);
        map.put(LineCategory.OPTION, BillingCauseType.OPTION_CHANGE);
        map.put(LineCategory.PRORATA, BillingCauseType.PRORATION);
        map.put(LineCategory.TAX, BillingCauseType.TAX);
        map.put(LineCategory.ONE_OFF, BillingCauseType.ONE_OFF_FEE);
        map.put(LineCategory.ADJUSTMENT, BillingCauseType.ADJUSTMENT);
        return map;
    }

    private record CategorizedDelta(LineDelta delta, BillingCauseType cause) {
    }
}
