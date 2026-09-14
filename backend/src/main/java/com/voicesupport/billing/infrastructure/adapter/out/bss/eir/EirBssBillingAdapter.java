package com.voicesupport.billing.infrastructure.adapter.out.bss.eir;

import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.InvoiceGroup;
import com.voicesupport.billing.domain.model.InvoiceItem;
import com.voicesupport.billing.domain.model.InvoiceSection;
import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.BillingPeriod;
import com.voicesupport.billing.domain.model.valueobject.Evidence;
import com.voicesupport.billing.domain.model.valueobject.InvoiceId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceLevel;
import com.voicesupport.billing.domain.model.valueobject.InvoiceSummary;
import com.voicesupport.billing.domain.model.valueobject.LineAmounts;
import com.voicesupport.billing.domain.model.valueobject.LineCategory;
import com.voicesupport.billing.domain.model.valueobject.Money;
import com.voicesupport.billing.domain.port.out.BssBillingPort;
import com.voicesupport.shared.observability.BackendTelemetry;
import com.voicesupport.shared.observability.Slices;
import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.BillingEnquiryClient.BillAmount;
import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.BillingEnquiryClient.GalaxionUser;
import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.BillingEnquiryClient.InvoiceResponse;
import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.BillingServiceClient.InvoiceHistory;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Currency;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

// Real read-only BssBillingPort over the two Eir services (TASK-BE-047): the account invoice list
// comes from billing-service, one invoice's structured amount breakdown from billing-enquiry-service.
// Each service sits behind its own client so they stay independently swappable; this adapter only
// maps their DTOs onto the billing domain (no Eir type crosses this boundary). Amounts are integer
// minor units in the configured currency; the enquiry breakdown is category-level, so the invoice
// tree is a single synthetic group (finer lines need the CSV detail-report / PDF — a follow-up).
public class EirBssBillingAdapter implements BssBillingPort {

    private static final String PROVIDER = "eir";

    private final BillingEnquiryClient enquiryClient;
    private final BillingServiceClient serviceClient;
    private final Currency currency;
    private final GalaxionUser user;
    private final BackendTelemetry telemetry;

    public EirBssBillingAdapter(BillingEnquiryClient enquiryClient, BillingServiceClient serviceClient,
            Currency currency, GalaxionUser user, BackendTelemetry telemetry) {
        this.enquiryClient = Objects.requireNonNull(enquiryClient, "enquiryClient must not be null");
        this.serviceClient = Objects.requireNonNull(serviceClient, "serviceClient must not be null");
        this.currency = Objects.requireNonNull(currency, "currency must not be null");
        this.user = Objects.requireNonNull(user, "user must not be null");
        this.telemetry = Objects.requireNonNull(telemetry, "telemetry must not be null");
    }

    @Override
    public List<InvoiceSummary> listInvoices(AccountId account) {
        Objects.requireNonNull(account, "account must not be null");
        return telemetry.time(Slices.BSS, PROVIDER, () -> mapSummaries(account));
    }

    private List<InvoiceSummary> mapSummaries(AccountId account) {
        List<InvoiceSummary> summaries = new ArrayList<>();
        for (InvoiceHistory dto : serviceClient.listAccountInvoices(account.value(), user)) {
            InvoiceSummary summary = toSummary(dto);
            if (summary != null) {
                summaries.add(summary);
            }
        }
        return List.copyOf(summaries);
    }

    @Override
    public Optional<Invoice> fetchInvoice(AccountId account, InvoiceId invoiceId) {
        Objects.requireNonNull(account, "account must not be null");
        Objects.requireNonNull(invoiceId, "invoiceId must not be null");
        Long numericId = parseLong(invoiceId.value());
        if (numericId == null) {
            return Optional.empty();
        }
        return telemetry.time(Slices.BSS, PROVIDER,
                () -> enquiryClient.fetchInvoice(numericId, user)
                        .map(dto -> toInvoice(account, invoiceId, dto))
                        .filter(Objects::nonNull));
    }

    private InvoiceSummary toSummary(InvoiceHistory dto) {
        if (dto == null || dto.invoiceNumber() == null) {
            return null;
        }
        LocalDate date = parseDate(dto.invoiceDate());
        if (date == null) {
            return null;
        }
        InvoiceId id = InvoiceId.of(String.valueOf(dto.invoiceNumber()));
        return new InvoiceSummary(id, new BillingPeriod(id.value(), date), money(dto.amount()));
    }

    private Invoice toInvoice(AccountId account, InvoiceId id, InvoiceResponse dto) {
        LocalDate date = parseDate(dto.effectiveDate());
        if (date == null) {
            return null;
        }
        BillAmount amounts = dto.billAmount();
        String periodId = dto.billPeriod() == null || dto.billPeriod().isBlank() ? id.value() : dto.billPeriod();
        List<InvoiceItem> items = items(amounts);
        LineAmounts totals = totals(amounts);
        InvoiceGroup group = new InvoiceGroup(id.value() + "-g", "Charges", null, 0, totals, items);
        InvoiceSection section = new InvoiceSection(id.value() + "-s", "Invoice", 0, true, totals, List.of(group));
        return new Invoice(id, account, InvoiceLevel.BILLING_ACCOUNT,
                new BillingPeriod(periodId, date), totals, List.of(section));
    }

    private List<InvoiceItem> items(BillAmount amounts) {
        if (amounts == null) {
            return List.of();
        }
        List<InvoiceItem> items = new ArrayList<>();
        addItem(items, "recurring", LineCategory.SUBSCRIPTION, orZero(amounts.recurringAmount()));
        addItem(items, "usage", LineCategory.OVERAGE, orZero(amounts.usageAmount()));
        addItem(items, "one-off", LineCategory.ONE_OFF, orZero(amounts.oneOffAmount()));
        addItem(items, "vat", LineCategory.TAX, orZero(amounts.vatAmount()));
        return List.copyOf(items);
    }

    private void addItem(List<InvoiceItem> items, String id, LineCategory category, long minorUnits) {
        if (minorUnits == 0L) {
            return;
        }
        LineAmounts amounts = category == LineCategory.TAX
                ? new LineAmounts(money(minorUnits), Money.zero(currency), money(minorUnits))
                : new LineAmounts(money(minorUnits), money(minorUnits), Money.zero(currency));
        items.add(new InvoiceItem(id, null, null, null, category, amounts,
                new Evidence("eir-billing-enquiry", null, category + " " + minorUnits)));
    }

    private LineAmounts totals(BillAmount amounts) {
        long total = amounts == null ? 0L : orZero(amounts.invoiceAmount());
        long tax = amounts == null ? 0L : orZero(amounts.vatAmount());
        return new LineAmounts(money(total), money(total - tax), money(tax));
    }

    private Money money(Long minorUnits) {
        return Money.ofMinorUnits(orZero(minorUnits), currency);
    }

    private static long orZero(Long value) {
        return value == null ? 0L : value;
    }

    private static LocalDate parseDate(String raw) {
        if (raw == null || raw.strip().length() < 10) {
            return null;
        }
        try {
            return LocalDate.parse(raw.strip().substring(0, 10));
        } catch (RuntimeException invalid) {
            return null;
        }
    }

    private static Long parseLong(String raw) {
        try {
            return Long.valueOf(raw.strip());
        } catch (RuntimeException invalid) {
            return null;
        }
    }
}
