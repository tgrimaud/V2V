package com.voicesupport.billing.infrastructure.config;

import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.port.out.BillRunDocumentPort;
import com.voicesupport.billing.domain.port.out.BssBillingPort;
import com.voicesupport.billing.domain.port.out.CustomerDirectoryPort;
import com.voicesupport.billing.domain.port.out.InvoicePdfExtractorPort;
import com.voicesupport.billing.infrastructure.adapter.out.bss.InMemoryBssBillingAdapter;
import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.BillingEnquiryClient;
import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.BillingEnquiryClient.GalaxionUser;
import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.BillingServiceClient;
import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.EirBssBillingAdapter;
import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.RestBillingEnquiryAdapter;
import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.RestBillingServiceAdapter;
import com.voicesupport.billing.infrastructure.adapter.out.bss.pdf.FixtureBillRunDocumentAdapter;
import com.voicesupport.billing.infrastructure.adapter.out.bss.pdf.GalaxionBillRunDocumentAdapter;
import com.voicesupport.billing.infrastructure.adapter.out.bss.pdf.PdfBssBillingAdapter;
import com.voicesupport.billing.infrastructure.adapter.out.bss.pdf.RestBillRunDocumentAdapter;
import com.voicesupport.billing.infrastructure.adapter.out.bss.pdf.SampleEirB2cBillRunDocumentAdapter;
import com.voicesupport.billing.infrastructure.adapter.out.identity.InMemoryCustomerDirectoryAdapter;
import com.voicesupport.billing.infrastructure.adapter.out.pdf.FixtureInvoicePdfExtractorAdapter;
import com.voicesupport.billing.infrastructure.adapter.out.pdf.PdfBoxInvoiceExtractorAdapter;
import com.voicesupport.billing.infrastructure.fixtures.BssBillingFixtures;
import com.voicesupport.billing.infrastructure.fixtures.EirB2cSampleFixtures;
import com.voicesupport.billing.infrastructure.pdf.EirB2cInvoiceLayoutParser;
import com.voicesupport.shared.observability.BackendTelemetry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

import java.util.Currency;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

// Out-adapter selection for the billing BSS (ADR-0004/0005): resolves the BssBillingPort source
// (mock | eir | pdf), the invoice PDF extractor, the bill-run document source and the customer
// directory from configuration. Extracted from BillingConfig (which keeps the domain use-case
// wiring) to stay within the 200-line budget; bean definitions and behaviour are unchanged.
@Configuration
public class BillingAdapterConfig {

    private static final Logger log = LoggerFactory.getLogger(BillingAdapterConfig.class);

    @Bean
    public BssBillingPort bssBillingPort(BillingBssProperties properties, BackendTelemetry telemetry,
            InvoicePdfExtractorPort invoicePdfExtractorPort) {
        if ("eir".equalsIgnoreCase(properties.source())) {
            log.info("[BILLING-BSS] source=eir — enquiry={} service={} currency={} user-type={}",
                    properties.enquiryBaseUrl(), properties.serviceBaseUrl(),
                    properties.currency(), properties.userType());
            return eirAdapter(properties, telemetry);
        }
        if ("pdf".equalsIgnoreCase(properties.source())) {
            return new PdfBssBillingAdapter(
                    billRunDocumentPort(properties), invoicePdfExtractorPort, telemetry);
        }
        if (!"mock".equalsIgnoreCase(properties.source())) {
            log.warn("[BILLING-BSS] source={} unknown — using mock fixtures", properties.source());
        }
        log.info("[BILLING-BSS] source=mock — in-memory fixtures (synthetic eir-00X + real eir B2C samples)");
        return new InMemoryBssBillingAdapter(mockInvoices());
    }

    // Mock invoice set = the six synthetic V1 journeys (eir-00X, TASK-BE-040) merged with the realistic
    // eir B2C samples transcribed from anonymized PDFs (99224964/99226126/99226337, TASK-BE-059). Keys
    // never overlap, so the two sets compose into one lookup for the in-memory BSS + PDF fallback.
    static Map<AccountId, List<Invoice>> mockInvoices() {
        Map<AccountId, List<Invoice>> merged = new LinkedHashMap<>(BssBillingFixtures.all());
        merged.putAll(EirB2cSampleFixtures.all());
        return Map.copyOf(merged);
    }

    // PDF document source for source=pdf. Default (blank base URL) = the in-memory fixture documents so
    // the whole download -> extract -> Invoice path stays exercisable now; when a bill-run-documents base
    // URL is configured, the real Galaxion adapter is wired instead (TASK-BE-063). Nothing else changes.
    private BillRunDocumentPort billRunDocumentPort(BillingBssProperties p) {
        if (p.billRunBaseUrl() == null || p.billRunBaseUrl().isBlank()) {
            if ("sample".equalsIgnoreCase(p.billRunSource())) {
                log.info("[BILLING-BSS] source=pdf — sample document source: real eir B2C sample PDFs on the "
                        + "classpath (download real bytes -> extractor), pair with pdf.source=eir-b2c (TASK-BE-066)");
                return new SampleEirB2cBillRunDocumentAdapter();
            }
            log.info("[BILLING-BSS] source=pdf — fixture document source (bill-run-documents base URL unset; "
                    + "real REST adapter + PDFBox parser deferred, OQ-003)");
            return new FixtureBillRunDocumentAdapter(mockInvoices());
        }
        log.info("[BILLING-BSS] source=pdf — real bill-run-documents adapter base={} user-type={} (OQ-003: "
                + "search lacks period/amount, so listDocuments is fail-closed)", p.billRunBaseUrl(), p.userType());
        RestClient restClient = restClient(p.billRunBaseUrl(), p.connectMs(), p.readMs());
        return new GalaxionBillRunDocumentAdapter(
                new RestBillRunDocumentAdapter(restClient), new GalaxionUser(p.userType(), p.userIdentifier()));
    }

    private static BssBillingPort eirAdapter(BillingBssProperties p, BackendTelemetry telemetry) {
        BillingEnquiryClient enquiry = new RestBillingEnquiryAdapter(
                restClient(p.enquiryBaseUrl(), p.connectMs(), p.readMs()));
        BillingServiceClient service = new RestBillingServiceAdapter(
                restClient(p.serviceBaseUrl(), p.connectMs(), p.readMs()));
        return new EirBssBillingAdapter(enquiry, service,
                Currency.getInstance(p.currency()), new GalaxionUser(p.userType(), p.userIdentifier()), telemetry);
    }

    private static RestClient restClient(String baseUrl, long connectMs, long readMs) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout((int) connectMs);
        factory.setReadTimeout((int) readMs);
        return RestClient.builder().requestFactory(factory).baseUrl(baseUrl).build();
    }

    // Invoice PDF extractor (ADR-0005). `fixture` (default) = synthetic extractor over the eir-00X +
    // B2C samples; `pdfbox` = the real Apache PDFBox extractor (TASK-BE-064) that reads text from the
    // PDF and parses the labeled invoice grammar (invoice-extraction-json.md). Selected via
    // VOICE_SUPPORT_BILLING_PDF_SOURCE. Default stays fixture so local/pilot behaviour is unchanged.
    @Bean
    public InvoicePdfExtractorPort invoicePdfExtractorPort(
            @Value("${voice-support.billing.pdf.source:fixture}") String source) {
        if ("pdfbox".equalsIgnoreCase(source)) {
            log.info("[BILLING-PDF] source=pdfbox — real Apache PDFBox extractor (generic labeled grammar)");
            return new PdfBoxInvoiceExtractorAdapter();
        }
        if ("eir-b2c".equalsIgnoreCase(source)) {
            log.info("[BILLING-PDF] source=eir-b2c — real Apache PDFBox extractor (eir B2C invoice layout)");
            return new PdfBoxInvoiceExtractorAdapter(new EirB2cInvoiceLayoutParser());
        }
        if (!"fixture".equalsIgnoreCase(source)) {
            log.warn("[BILLING-PDF] source={} unknown — using fixture extractor", source);
        }
        log.info("[BILLING-PDF] source=fixture — synthetic extractor (eir-00X + real eir B2C samples)");
        return new FixtureInvoicePdfExtractorAdapter(mockInvoices());
    }

    // Customer directory (ADR-0050, BR-002-1). `mock` (default) = in-memory pilot directory aligned
    // with the customer-eir-* fixtures; the real CRM/BSS directory registers later behind
    // CustomerDirectoryPort. Selected via VOICE_SUPPORT_BILLING_IDENTITY_SOURCE.
    @Bean
    public CustomerDirectoryPort customerDirectoryPort(
            @Value("${voice-support.billing.identity.source:mock}") String source) {
        if (!"mock".equalsIgnoreCase(source)) {
            log.warn("[BILLING-IDENTITY] source={} not available yet (real directory deferred) — using mock",
                    source);
        }
        log.info("[BILLING-IDENTITY] source=mock — in-memory pilot directory (customer-eir-001..006)");
        return new InMemoryCustomerDirectoryAdapter();
    }
}
