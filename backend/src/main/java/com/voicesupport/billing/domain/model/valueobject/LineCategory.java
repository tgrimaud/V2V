package com.voicesupport.billing.domain.model.valueobject;

// V1 line categories that feed the comparison engine's business-cause attribution. Mirrors the
// invoice-extraction-json.md category set; the mapping from the raw BSS classifiers
// (invoice_item.type / code / vatType) to these categories is pending the Galaxion catalogue
// (OQ-003 / INFRA-017). OTHER is the safe default for an unclassified monetary line.
public enum LineCategory {
    SUBSCRIPTION,
    DISCOUNT,
    USAGE,
    OVERAGE,
    OPTION,
    PRORATA,
    ONE_OFF,
    ADJUSTMENT,
    TAX,
    PAYMENT,
    OTHER
}
