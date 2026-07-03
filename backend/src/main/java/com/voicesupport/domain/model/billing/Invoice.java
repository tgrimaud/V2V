package com.voicesupport.domain.model.billing;

import java.util.List;
import java.util.Objects;

public record Invoice(
        String invoiceNumber,
        String accountId,
        InvoiceExtractionStatus extractionStatus,
        Money totalTaxIncluded,
        List<InvoiceLine> lines
) {

    public Invoice {
        requireText(invoiceNumber, "invoice number required");
        requireText(accountId, "account id required");
        Objects.requireNonNull(extractionStatus, "extraction status required");
        Objects.requireNonNull(totalTaxIncluded, "invoice total required");
        lines = List.copyOf(Objects.requireNonNull(lines, "invoice lines required"));
    }

    public boolean comparisonForbidden() {
        return extractionStatus == InvoiceExtractionStatus.UNUSABLE;
    }

    public boolean requiresCaution() {
        return extractionStatus == InvoiceExtractionStatus.PARTIAL;
    }

    private static void requireText(String value, String message) {
        Objects.requireNonNull(value, message);
        if (value.isBlank()) {
            throw new IllegalArgumentException(message);
        }
    }
}
