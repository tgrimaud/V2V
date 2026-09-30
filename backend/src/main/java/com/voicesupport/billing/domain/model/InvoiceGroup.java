package com.voicesupport.billing.domain.model;

import com.voicesupport.billing.domain.model.valueobject.DateRange;
import com.voicesupport.billing.domain.model.valueobject.LineAmounts;

import java.util.List;
import java.util.Objects;

// A group of billed lines within a section (BSS invoice_group). Holds its own rolled-up amounts and
// the ordered items it contains. `period` is the block's applicable window (nullable), e.g. the
// "Subscription and options for the period from X to Y" header (ADR-0054). The items list is
// defensively copied so the aggregate is immutable.
public record InvoiceGroup(String id, String name, String description, int displayOrder,
        LineAmounts amounts, List<InvoiceItem> items, DateRange period) {

    public InvoiceGroup {
        Objects.requireNonNull(id, "group id must not be null");
        Objects.requireNonNull(name, "group name must not be null");
        Objects.requireNonNull(amounts, "amounts must not be null");
        items = List.copyOf(Objects.requireNonNull(items, "items must not be null"));
    }

    // Backward-compatible shorthand for a group with no explicit period.
    public InvoiceGroup(String id, String name, String description, int displayOrder,
            LineAmounts amounts, List<InvoiceItem> items) {
        this(id, name, description, displayOrder, amounts, items, null);
    }
}
