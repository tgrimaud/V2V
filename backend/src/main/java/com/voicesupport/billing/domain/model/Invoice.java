package com.voicesupport.billing.domain.model;

import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.BillingPeriod;
import com.voicesupport.billing.domain.model.valueobject.InvoiceId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceLevel;
import com.voicesupport.billing.domain.model.valueobject.LineAmounts;

import java.util.List;
import java.util.Objects;

// The invoice aggregate root, mirroring the BSS hierarchy invoice -> section -> group -> item with
// rolled-up amounts at each level (bss-billing-data-model.md). The sections list is defensively
// copied so the aggregate is immutable; lines() flattens the tree to the billed leaves the
// comparison engine diffs (TASK-BE-042).
public record Invoice(InvoiceId id, AccountId accountId, InvoiceLevel level, BillingPeriod period,
        LineAmounts totals, List<InvoiceSection> sections) {

    public Invoice {
        Objects.requireNonNull(id, "invoice id must not be null");
        Objects.requireNonNull(accountId, "accountId must not be null");
        Objects.requireNonNull(level, "level must not be null");
        Objects.requireNonNull(period, "period must not be null");
        Objects.requireNonNull(totals, "totals must not be null");
        sections = List.copyOf(Objects.requireNonNull(sections, "sections must not be null"));
    }

    public List<InvoiceItem> lines() {
        return sections.stream()
                .flatMap(section -> section.groups().stream())
                .flatMap(group -> group.items().stream())
                .toList();
    }
}
