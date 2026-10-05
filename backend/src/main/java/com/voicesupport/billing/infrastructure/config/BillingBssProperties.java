package com.voicesupport.billing.infrastructure.config;

// Resolved configuration for the BSS billing source. Groups the `eir` adapter settings so the
// BillingConfig bean stays small. Values default to the mock source; the Eir base URLs, currency,
// authorization headers and timeouts are only used when source=eir (TASK-BE-047). `billRunBaseUrl`
// and `billRunSource` are only used when source=pdf: `billRunSource` selects the document source
// (`fixture` default = synthetic shortcut; `sample` = the real eir B2C sample PDFs shipped on the
// classpath, TASK-BE-066); when `billRunBaseUrl` is set the real Galaxion bill-run-documents adapter
// is wired instead (TASK-BE-063).
public record BillingBssProperties(
        String source,
        String enquiryBaseUrl,
        String serviceBaseUrl,
        String currency,
        String userType,
        String userIdentifier,
        long connectMs,
        long readMs,
        String billRunBaseUrl,
        String billRunSource) {
}
