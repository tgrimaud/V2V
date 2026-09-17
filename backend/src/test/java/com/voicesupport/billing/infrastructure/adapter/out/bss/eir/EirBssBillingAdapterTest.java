package com.voicesupport.billing.infrastructure.adapter.out.bss.eir;

import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.InvoiceItem;
import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceSummary;
import com.voicesupport.billing.domain.model.valueobject.LineCategory;
import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.BillingEnquiryClient.BillAmount;
import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.BillingEnquiryClient.GalaxionUser;
import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.BillingEnquiryClient.InvoiceResponse;
import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.BillingServiceClient.InvoiceHistory;
import com.voicesupport.shared.observability.BackendTelemetry;
import com.voicesupport.shared.observability.Slices;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.time.LocalDate;
import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class EirBssBillingAdapterTest {

    private static final GalaxionUser USER = new GalaxionUser("SYSTEM", "SYSTEM");

    private final SimpleMeterRegistry registry = new SimpleMeterRegistry();
    private final BackendTelemetry telemetry = new BackendTelemetry(registry);

    private EirBssBillingAdapter adapterWith(BillingEnquiryClient enquiry, BillingServiceClient service) {
        return new EirBssBillingAdapter(enquiry, service, java.util.Currency.getInstance("EUR"), USER, telemetry);
    }

    @Test
    void listInvoices_mapsEntriesAndSkipsUnusableOnes() {
        // GIVEN billing-service returns two usable invoices, one with a null number and one with no date
        FakeServiceClient service = new FakeServiceClient(List.of(
                new InvoiceHistory(113444L, 5000L, "2026-02-15", "2026-03-01"),
                new InvoiceHistory(113443L, 4500L, "2026-01-15", "2026-02-01"),
                new InvoiceHistory(null, 100L, "2026-01-15", null),
                new InvoiceHistory(999L, 100L, null, null)));
        EirBssBillingAdapter adapter = adapterWith(new FakeEnquiryClient(), service);

        // WHEN the account's invoices are listed
        List<InvoiceSummary> summaries = adapter.listInvoices(AccountId.of("12312"));

        // THEN only the two usable invoices map, and the account + user reach the client
        assertEquals(2, summaries.size());
        assertEquals("113444", summaries.get(0).id().value());
        assertEquals(5000L, summaries.get(0).totalTaxIncluded().minorUnits());
        assertEquals(LocalDate.of(2026, 2, 15), summaries.get(0).period().invoiceDate());
        assertEquals("12312", service.lastAccountId);
        assertEquals(USER, service.lastUser);
        // AND the BSS network hop is timed as its own slice (provider=eir) so QA can report p50/p95/p99
        assertTrue(registry.find("voice_support.slice").tag("slice", Slices.BSS).tag("provider", "eir")
                .timer().count() >= 1, "BSS slice must be recorded");
    }

    @Test
    void fetchInvoice_mapsRealAccount5Breakdown_vatStaysInsideTheTotal() {
        // GIVEN the real account-5 invoice: invoiceAmount == recurringAmount, vat is INSIDE the total
        // (TTC), not additive (confirmed against the live Eir dev services 2026-09-15)
        FakeEnquiryClient enquiry = new FakeEnquiryClient();
        enquiry.next = Optional.of(new InvoiceResponse(5L, 2608020000000067L, "202608",
                new BillAmount(3999L, 3999L, 0L, 0L, 748L), "2026-09-01T00:00:00"));
        EirBssBillingAdapter adapter = adapterWith(enquiry, new FakeServiceClient(List.of()));

        // WHEN the invoice is fetched
        Invoice invoice = adapter.fetchInvoice(AccountId.of("5"), InvoiceId.of("2608020000000067")).orElseThrow();

        // THEN totals are TTC=invoiceAmount with the VAT split, and there is NO separate tax line
        assertEquals(2608020000000067L, enquiry.lastInvoiceId);
        assertEquals(3999L, invoice.totals().taxIncluded().minorUnits());
        assertEquals(748L, invoice.totals().tax().minorUnits());
        assertEquals(3251L, invoice.totals().taxExcluded().minorUnits());
        List<InvoiceItem> lines = invoice.lines();
        assertEquals(1, lines.size(), "only the recurring TTC line (usage/one-off are zero, vat is not a line)");
        assertEquals(LineCategory.SUBSCRIPTION, lines.get(0).category());
        assertEquals(3999L, lines.get(0).amounts().taxIncluded().minorUnits());
        assertTrue(lines.stream().noneMatch(l -> l.category() == LineCategory.TAX), "VAT is inside the total, never a line");
    }

    @Test
    void fetchInvoice_multiCategoryLinesReconcileToTheTtcTotal() {
        // GIVEN a TTC breakdown with recurring + usage (VAT inside the total, not additive)
        FakeEnquiryClient enquiry = new FakeEnquiryClient();
        enquiry.next = Optional.of(new InvoiceResponse(5L, 113444L, "2026-02",
                new BillAmount(4200L, 3000L, 0L, 1200L, 785L), "2026-02-15T00:00:00Z"));
        EirBssBillingAdapter adapter = adapterWith(enquiry, new FakeServiceClient(List.of()));

        // WHEN the invoice is fetched
        Invoice invoice = adapter.fetchInvoice(AccountId.of("5"), InvoiceId.of("113444")).orElseThrow();

        // THEN the category (TTC) lines reconcile exactly to invoiceAmount
        List<InvoiceItem> lines = invoice.lines();
        assertEquals(2, lines.size());
        long lineSum = lines.stream().mapToLong(l -> l.amounts().taxIncluded().minorUnits()).sum();
        assertEquals(4200L, lineSum, "TTC category lines must reconcile to the invoice total");
        assertEquals(4200L, invoice.totals().taxIncluded().minorUnits());
        assertEquals(785L, invoice.totals().tax().minorUnits());
    }

    @Test
    void fetchInvoice_returnsEmptyForNonNumericInvoiceIdWithoutCallingEnquiry() {
        // GIVEN a non-numeric invoice id (Eir invoice ids are int64)
        FakeEnquiryClient enquiry = new FakeEnquiryClient();
        EirBssBillingAdapter adapter = adapterWith(enquiry, new FakeServiceClient(List.of()));

        // WHEN fetching with a non-numeric id
        Optional<Invoice> result = adapter.fetchInvoice(AccountId.of("12312"), InvoiceId.of("eir-XYZ"));

        // THEN it fails closed to empty and never calls the enquiry service
        assertTrue(result.isEmpty());
        assertFalse(enquiry.called);
    }

    @Test
    void fetchInvoice_failsClosedWhenInvoiceBelongsToAnotherAccount() {
        // GIVEN the enquiry returns an invoice owned by a different account (BR-002-1)
        FakeEnquiryClient enquiry = new FakeEnquiryClient();
        enquiry.next = Optional.of(new InvoiceResponse(99999L, 113444L, "2026-02",
                new BillAmount(5000L, 3000L, 0L, 1200L, 800L), "2026-02-15T00:00:00Z"));
        EirBssBillingAdapter adapter = adapterWith(enquiry, new FakeServiceClient(List.of()));

        // WHEN the invoice is fetched for account 12312
        Optional<Invoice> result = adapter.fetchInvoice(AccountId.of("12312"), InvoiceId.of("113444"));

        // THEN it is dropped rather than exposing another account's invoice
        assertTrue(result.isEmpty());
    }

    @Test
    void fetchInvoice_returnsEmptyWhenEnquiryHasNoInvoice() {
        // GIVEN the enquiry service reports no invoice
        EirBssBillingAdapter adapter = adapterWith(new FakeEnquiryClient(), new FakeServiceClient(List.of()));

        // WHEN fetching
        Optional<Invoice> result = adapter.fetchInvoice(AccountId.of("12312"), InvoiceId.of("113444"));

        // THEN the result is empty
        assertTrue(result.isEmpty());
    }

    private static final class FakeEnquiryClient implements BillingEnquiryClient {
        private Optional<InvoiceResponse> next = Optional.empty();
        private long lastInvoiceId;
        private boolean called;

        @Override
        public Optional<InvoiceResponse> fetchInvoice(long invoiceId, GalaxionUser user) {
            this.called = true;
            this.lastInvoiceId = invoiceId;
            return next;
        }
    }

    private static final class FakeServiceClient implements BillingServiceClient {
        private final List<InvoiceHistory> invoices;
        private String lastAccountId;
        private GalaxionUser lastUser;

        private FakeServiceClient(List<InvoiceHistory> invoices) {
            this.invoices = invoices;
        }

        @Override
        public List<InvoiceHistory> listAccountInvoices(String accountId, GalaxionUser user) {
            this.lastAccountId = accountId;
            this.lastUser = user;
            return invoices;
        }
    }
}
