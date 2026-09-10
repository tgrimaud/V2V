package com.voicesupport.billing.domain.service;

import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.BillingPeriod;
import com.voicesupport.billing.domain.model.valueobject.InvoiceId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceSummary;
import com.voicesupport.billing.domain.model.valueobject.Money;
import com.voicesupport.billing.domain.port.out.BssBillingPort;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Currency;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DisplayName("ComparableInvoiceService (list account invoices)")
class ComparableInvoiceServiceTest {

    private static final Currency EUR = Currency.getInstance("EUR");
    private static final AccountId ACCOUNT = AccountId.of("acc-1");

    @Test
    void available_invoices_returns_summaries_most_recent_first() {
        // GIVEN a port returning three invoices in a non-chronological order
        InvoiceSummary january = summary("inv-01", LocalDate.of(2026, 1, 15));
        InvoiceSummary march = summary("inv-03", LocalDate.of(2026, 3, 15));
        InvoiceSummary february = summary("inv-02", LocalDate.of(2026, 2, 15));
        FakeBssBillingPort port = new FakeBssBillingPort();
        port.setInvoices(List.of(january, march, february));
        ComparableInvoiceService service = new ComparableInvoiceService(port);

        // WHEN the available invoices are listed
        List<InvoiceSummary> result = service.availableInvoices(ACCOUNT);

        // THEN they are ordered most-recent-first, so the latest pair is the head
        assertThat(result).containsExactly(march, february, january);
    }

    @Test
    void available_invoices_breaks_a_same_date_tie_by_invoice_id() {
        // GIVEN two invoices issued on the same date, given out of id order
        LocalDate sameDate = LocalDate.of(2026, 2, 15);
        InvoiceSummary b = summary("inv-b", sameDate);
        InvoiceSummary a = summary("inv-a", sameDate);
        FakeBssBillingPort port = new FakeBssBillingPort();
        port.setInvoices(List.of(b, a));
        ComparableInvoiceService service = new ComparableInvoiceService(port);

        // WHEN the available invoices are listed
        List<InvoiceSummary> result = service.availableInvoices(ACCOUNT);

        // THEN the ordering is deterministic (tie broken by invoice id ascending)
        assertThat(result).containsExactly(a, b);
    }

    @Test
    void available_invoices_scopes_the_query_to_the_requested_account() {
        // GIVEN a port that records the account it was queried with
        FakeBssBillingPort port = new FakeBssBillingPort();
        ComparableInvoiceService service = new ComparableInvoiceService(port);

        // WHEN invoices are listed for a specific account
        service.availableInvoices(ACCOUNT);

        // THEN the port received that exact account (fail-closed scoping, BR-002-1)
        assertThat(port.lastQueriedAccount()).isEqualTo(ACCOUNT);
    }

    @Test
    void available_invoices_returns_empty_when_the_account_has_none() {
        // GIVEN a port with no invoices for the account
        ComparableInvoiceService service = new ComparableInvoiceService(new FakeBssBillingPort());

        // WHEN the available invoices are listed
        List<InvoiceSummary> result = service.availableInvoices(ACCOUNT);

        // THEN the result is empty (not null)
        assertThat(result).isEmpty();
    }

    @Test
    void available_invoices_throws_when_account_is_null() {
        // GIVEN the service
        ComparableInvoiceService service = new ComparableInvoiceService(new FakeBssBillingPort());

        // WHEN / THEN a null account is rejected
        assertThatThrownBy(() -> service.availableInvoices(null))
                .isInstanceOf(NullPointerException.class);
    }

    @Test
    void construction_throws_when_the_port_is_null() {
        // GIVEN / WHEN / THEN the service cannot be built without a port
        assertThatThrownBy(() -> new ComparableInvoiceService(null))
                .isInstanceOf(NullPointerException.class);
    }

    private static InvoiceSummary summary(String id, LocalDate invoiceDate) {
        return new InvoiceSummary(InvoiceId.of(id), new BillingPeriod(id, invoiceDate),
                Money.ofMinorUnits(4200L, EUR));
    }

    private static final class FakeBssBillingPort implements BssBillingPort {

        private List<InvoiceSummary> invoices = new ArrayList<>();
        private AccountId lastQueriedAccount;

        void setInvoices(List<InvoiceSummary> invoices) {
            this.invoices = new ArrayList<>(invoices);
        }

        AccountId lastQueriedAccount() {
            return lastQueriedAccount;
        }

        @Override
        public List<InvoiceSummary> listInvoices(AccountId account) {
            this.lastQueriedAccount = account;
            return List.copyOf(invoices);
        }

        @Override
        public Optional<Invoice> fetchInvoice(AccountId account, InvoiceId invoiceId) {
            return Optional.empty();
        }
    }
}
