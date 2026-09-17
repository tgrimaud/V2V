package com.voicesupport.billing.domain.model;

import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.BillingPeriod;
import com.voicesupport.billing.domain.model.valueobject.InvoiceId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceLevel;
import com.voicesupport.billing.domain.model.valueobject.LineAmounts;
import com.voicesupport.billing.domain.model.valueobject.Money;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.time.LocalDate;
import java.util.Currency;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DisplayName("ExtractionResult (invariants)")
class ExtractionResultTest {

    private static final Currency EUR = Currency.getInstance("EUR");

    @Test
    void a_failed_result_carries_a_reason_and_no_invoice() {
        // GIVEN / WHEN a failed extraction
        ExtractionResult result = ExtractionResult.failed("unreadable document");

        // THEN it has the FAILED status, no invoice, and the reason as an issue
        assertThat(result.status()).isEqualTo(ExtractionStatus.FAILED);
        assertThat(result.hasInvoice()).isFalse();
        assertThat(result.issues()).containsExactly("unreadable document");
    }

    @Test
    void a_success_result_requires_an_invoice() {
        // GIVEN a SUCCESS status with no invoice -> WHEN/THEN rejected
        assertThatThrownBy(() -> new ExtractionResult(ExtractionStatus.SUCCESS, null, List.of()))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void a_failed_result_must_not_carry_an_invoice() {
        // GIVEN a FAILED status with an invoice -> WHEN/THEN rejected
        assertThatThrownBy(() -> new ExtractionResult(ExtractionStatus.FAILED, anInvoice(), List.of()))
                .isInstanceOf(IllegalArgumentException.class);
    }

    private static Invoice anInvoice() {
        LineAmounts zero = new LineAmounts(cents(0L), cents(0L), cents(0L));
        InvoiceGroup group = new InvoiceGroup("g", "Charges", null, 0, zero, List.of());
        InvoiceSection section = new InvoiceSection("s", "Invoice", 0, true, zero, List.of(group));
        return new Invoice(InvoiceId.of("inv-1"), AccountId.of("eir-x"), InvoiceLevel.BILLING_ACCOUNT,
                new BillingPeriod("inv-1", LocalDate.of(2026, 2, 15)), zero, List.of(section));
    }

    private static Money cents(long value) {
        return Money.ofMinorUnits(value, EUR);
    }
}
