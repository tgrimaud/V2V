package com.voicesupport.billing.domain.model.valueobject;

// A request to explain a customer's bill (TASK-BE-045): the channel and the customer reference that
// scope identity resolution (BR-002-1), the raw transcript the intent guard inspects, an optional
// invoice id (reserved for future targeted selection — V1 compares the two most recent invoices), and
// the resolved answer-language code so the deterministic explanation is composed in the right
// language. The reference is potentially personal data and must never be logged in clear.
public record BillingExplanationQuery(String channel, String transcript, String reference,
        String invoiceId, String languageCode) {

    private static final String DEFAULT_CHANNEL = "api";

    public BillingExplanationQuery {
        channel = channel == null || channel.isBlank() ? DEFAULT_CHANNEL : channel.strip();
        transcript = transcript == null ? "" : transcript;
    }

    public static BillingExplanationQuery of(
            String channel, String transcript, String reference, String invoiceId, String languageCode) {
        return new BillingExplanationQuery(channel, transcript, reference, invoiceId, languageCode);
    }

    public boolean hasReference() {
        return reference != null && !reference.isBlank();
    }
}
