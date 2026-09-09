package com.voicesupport.billing.domain.model;

import com.voicesupport.billing.domain.model.valueobject.Evidence;
import com.voicesupport.billing.domain.model.valueobject.LineAmounts;
import com.voicesupport.billing.domain.model.valueobject.LineCategory;

import java.util.Objects;

// A single billed line — the leaf of the BSS hierarchy (invoice_item). Carries the raw BSS
// classifiers (type / code / vatType, kept for audit and future catalogue mapping), the V1
// category the comparison engine reasons on, the amounts, and the evidence backing it. type / code
// / vatType may be null for a synthetic or partially-extracted line.
public record InvoiceItem(String id, String type, String code, String vatType,
        LineCategory category, LineAmounts amounts, Evidence evidence) {

    public InvoiceItem {
        Objects.requireNonNull(id, "item id must not be null");
        Objects.requireNonNull(category, "category must not be null");
        Objects.requireNonNull(amounts, "amounts must not be null");
        Objects.requireNonNull(evidence, "evidence must not be null");
    }
}
