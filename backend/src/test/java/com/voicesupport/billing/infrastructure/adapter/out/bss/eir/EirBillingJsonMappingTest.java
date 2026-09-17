package com.voicesupport.billing.infrastructure.adapter.out.bss.eir;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.BillingEnquiryClient.InvoiceResponse;
import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.BillingServiceClient.InvoiceHistory;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

// Guards that the Eir DTOs deserialize their camelCase wire fields even though the backend's global
// Jackson strategy is SNAKE_CASE: the @JsonProperty pins must win. This mapper mirrors the app's
// SNAKE_CASE configuration, so a regression (dropping a @JsonProperty) would fail here.
class EirBillingJsonMappingTest {

    private final ObjectMapper mapper = new ObjectMapper()
            .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);

    @Test
    void invoiceResponse_deserializesCamelCaseUnderSnakeCaseStrategy() throws Exception {
        // GIVEN a billing-enquiry-service invoice payload (camelCase, as the Eir API emits it)
        String json = """
                {"accountId":12312,"invoiceId":113444,"billPeriod":"2026-02",
                 "billAmount":{"invoiceAmount":5000,"recurringAmount":3000,"oneOffAmount":0,
                 "usageAmount":1200,"vatAmount":800},"effectiveDate":"2026-02-15T00:00:00Z"}""";

        // WHEN deserialized with the SNAKE_CASE mapper
        InvoiceResponse dto = mapper.readValue(json, InvoiceResponse.class);

        // THEN every pinned field is populated
        assertEquals(113444L, dto.invoiceId());
        assertEquals(12312L, dto.accountId());
        assertEquals("2026-02", dto.billPeriod());
        assertEquals("2026-02-15T00:00:00Z", dto.effectiveDate());
        assertEquals(5000L, dto.billAmount().invoiceAmount());
        assertEquals(1200L, dto.billAmount().usageAmount());
        assertEquals(800L, dto.billAmount().vatAmount());
    }

    @Test
    void invoiceHistory_deserializesCamelCaseUnderSnakeCaseStrategy() throws Exception {
        // GIVEN a billing-service invoice-history entry
        String json = "{\"invoiceNumber\":113444,\"amount\":5000,\"invoiceDate\":\"2026-02-15\",\"dueDate\":\"2026-03-01\"}";

        // WHEN deserialized with the SNAKE_CASE mapper
        InvoiceHistory dto = mapper.readValue(json, InvoiceHistory.class);

        // THEN the pinned fields are populated
        assertEquals(113444L, dto.invoiceNumber());
        assertEquals(5000L, dto.amount());
        assertEquals("2026-02-15", dto.invoiceDate());
        assertEquals("2026-03-01", dto.dueDate());
    }
}
