package com.voicesupport.billing.infrastructure.fixtures;

import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.InvoiceItem;
import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.LineCategory;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

@DisplayName("BssBillingFixtures (six V1 journeys)")
class BssBillingFixturesTest {

    private final Map<AccountId, List<Invoice>> fixtures = BssBillingFixtures.all();

    @Test
    void exposes_the_six_customer_journeys() {
        // GIVEN the fixture set
        // WHEN the accounts are listed
        // THEN the six eir journeys are present
        assertThat(fixtures.keySet()).containsExactlyInAnyOrder(
                AccountId.of("eir-001"), AccountId.of("eir-002"), AccountId.of("eir-003"),
                AccountId.of("eir-004"), AccountId.of("eir-005"), AccountId.of("eir-006"));
    }

    @Test
    void comparable_journeys_have_two_invoices_but_insufficient_data_has_one() {
        // GIVEN the fixture set
        // WHEN the invoice counts are inspected
        // THEN comparable accounts expose a pair, and the insufficient-data account exposes a single one
        assertThat(fixtures.get(AccountId.of("eir-001"))).hasSize(2);
        assertThat(fixtures.get(AccountId.of("eir-005"))).hasSize(1);
    }

    @Test
    void discount_expiry_previous_invoice_carries_a_discount_line() {
        // GIVEN the discount-expiry journey (eir-002), previous invoice (period 2026-01)
        Invoice previous = fixtures.get(AccountId.of("eir-002")).stream()
                .filter(invoice -> invoice.period().id().endsWith("2026-01"))
                .findFirst().orElseThrow();

        // WHEN its lines are read
        List<InvoiceItem> lines = previous.lines();

        // THEN a discount line is present (the delta cause once the discount expires)
        assertThat(lines).anySatisfy(line -> assertThat(line.category()).isEqualTo(LineCategory.DISCOUNT));
    }

    @Test
    void unusable_journey_has_invoices_without_billed_lines() {
        // GIVEN the unusable journey (eir-006)
        List<Invoice> invoices = fixtures.get(AccountId.of("eir-006"));

        // WHEN the billed lines are read
        // THEN the invoices exist but carry no lines (structurally unusable for a comparison)
        assertThat(invoices).isNotEmpty();
        assertThat(invoices).allSatisfy(invoice -> assertThat(invoice.lines()).isEmpty());
    }
}
