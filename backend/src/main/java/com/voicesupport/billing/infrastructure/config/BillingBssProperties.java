package com.voicesupport.billing.infrastructure.config;

// Resolved configuration for the BSS billing source. Groups the `eir` adapter settings so the
// BillingConfig bean stays small. Values default to the mock source; the Eir base URLs, currency,
// authorization headers and timeouts are only used when source=eir (TASK-BE-047).
public record BillingBssProperties(
        String source,
        String enquiryBaseUrl,
        String serviceBaseUrl,
        String currency,
        String userType,
        String userIdentifier,
        long connectMs,
        long readMs) {
}
