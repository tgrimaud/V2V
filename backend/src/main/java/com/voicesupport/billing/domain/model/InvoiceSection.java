package com.voicesupport.billing.domain.model;

import com.voicesupport.billing.domain.model.valueobject.LineAmounts;

import java.util.List;
import java.util.Objects;

// A section of the invoice (BSS invoice_section). Holds its rolled-up amounts, whether it is shown
// in the detailed breakdown, and the ordered groups it contains. The groups list is defensively
// copied so the aggregate is immutable.
public record InvoiceSection(String id, String name, int displayOrder, boolean inDetails,
        LineAmounts amounts, List<InvoiceGroup> groups) {

    public InvoiceSection {
        Objects.requireNonNull(id, "section id must not be null");
        Objects.requireNonNull(name, "section name must not be null");
        Objects.requireNonNull(amounts, "amounts must not be null");
        groups = List.copyOf(Objects.requireNonNull(groups, "groups must not be null"));
    }
}
