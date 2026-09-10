package com.voicesupport.billing.infrastructure.adapter.out.bss;

import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceSummary;
import com.voicesupport.billing.domain.port.out.BssBillingPort;
import com.voicesupport.billing.infrastructure.fixtures.BssBillingFixtures;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

@DisplayName("InMemoryBssBillingAdapter (fixture-backed BSS, fail-closed)")
class InMemoryBssBillingAdapterTest {

    private final BssBillingPort adapter = new InMemoryBssBillingAdapter(BssBillingFixtures.all());

    @Test
    void list_invoices_returns_summaries_for_a_known_account() {
        // GIVEN a known account with two comparable invoices (discount-expiry journey)
        AccountId account = AccountId.of("eir-002");

        // WHEN its invoices are listed
        List<InvoiceSummary> summaries = adapter.listInvoices(account);

        // THEN both invoices are returned as summaries
        assertThat(summaries).hasSize(2);
        assertThat(summaries).allSatisfy(summary ->
                assertThat(summary.totalTaxIncluded().currency().getCurrencyCode()).isEqualTo("EUR"));
    }

    @Test
    void list_invoices_returns_empty_for_an_unknown_account() {
        // GIVEN an account that does not exist in the BSS
        AccountId unknown = AccountId.of("eir-999");

        // WHEN its invoices are listed
        List<InvoiceSummary> summaries = adapter.listInvoices(unknown);

        // THEN nothing is returned (fail-closed, not an error)
        assertThat(summaries).isEmpty();
    }

    @Test
    void fetch_invoice_returns_the_invoice_when_it_belongs_to_the_account() {
        // GIVEN a known account and one of its invoice ids
        AccountId account = AccountId.of("eir-003");

        // WHEN that invoice is fetched
        Optional<Invoice> invoice = adapter.fetchInvoice(account, InvoiceId.of("eir-003-2026-02"));

        // THEN the invoice is returned with its billed lines
        assertThat(invoice).isPresent();
        assertThat(invoice.get().lines()).isNotEmpty();
    }

    @Test
    void fetch_invoice_is_empty_when_the_invoice_belongs_to_another_account() {
        // GIVEN account eir-003 and an invoice id that belongs to eir-002
        AccountId account = AccountId.of("eir-003");

        // WHEN the foreign invoice is fetched under eir-003
        Optional<Invoice> invoice = adapter.fetchInvoice(account, InvoiceId.of("eir-002-2026-02"));

        // THEN nothing is returned (a customer cannot reach another account's invoice)
        assertThat(invoice).isEmpty();
    }
}
