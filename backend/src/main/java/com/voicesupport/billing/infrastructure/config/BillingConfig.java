package com.voicesupport.billing.infrastructure.config;

import com.voicesupport.billing.domain.port.in.AssessComparisonReadinessUseCase;
import com.voicesupport.billing.domain.port.in.CompareInvoicesUseCase;
import com.voicesupport.billing.domain.port.in.ExplainBillingUseCase;
import com.voicesupport.billing.domain.port.in.ResolveCustomerIdentityUseCase;
import com.voicesupport.billing.domain.port.in.RetrieveComparableInvoicesUseCase;
import com.voicesupport.billing.domain.port.out.BssBillingPort;
import com.voicesupport.billing.domain.port.out.CustomerDirectoryPort;
import com.voicesupport.billing.domain.port.out.InvoicePdfExtractorPort;
import com.voicesupport.billing.domain.service.BillingExplanationComposer;
import com.voicesupport.billing.domain.service.BillingExplanationService;
import com.voicesupport.billing.domain.service.BillingIntentDetector;
import com.voicesupport.billing.domain.service.ComparableInvoiceService;
import com.voicesupport.billing.domain.service.ComparisonConfidenceService;
import com.voicesupport.billing.domain.service.CustomerIdentityService;
import com.voicesupport.billing.domain.service.InvoiceComparisonService;
import com.voicesupport.billing.infrastructure.adapter.out.bss.InMemoryBssBillingAdapter;
import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.BillingEnquiryClient;
import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.BillingEnquiryClient.GalaxionUser;
import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.BillingServiceClient;
import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.EirBssBillingAdapter;
import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.RestBillingEnquiryAdapter;
import com.voicesupport.billing.infrastructure.adapter.out.bss.eir.RestBillingServiceAdapter;
import com.voicesupport.billing.infrastructure.adapter.out.identity.InMemoryCustomerDirectoryAdapter;
import com.voicesupport.billing.infrastructure.adapter.out.pdf.FixtureInvoicePdfExtractorAdapter;
import com.voicesupport.billing.infrastructure.fixtures.BssBillingFixtures;
import com.voicesupport.shared.observability.BackendTelemetry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

import java.util.Arrays;
import java.util.Currency;
import java.util.List;

@Configuration
public class BillingConfig {

    private static final Logger log = LoggerFactory.getLogger(BillingConfig.class);

    // BSS billing source (ADR-0004). `mock` (default) = in-memory fixtures customer-eir-001..006 so
    // the billing chain runs before live access; `eir` = the real read-only adapter over the two Eir
    // services (TASK-BE-047), enabled once real access is validated. Selected via
    // VOICE_SUPPORT_BILLING_BSS_SOURCE.
    // Eir BSS settings (used only when source=eir). Defaults keep the mock source; the galaxion-user-*
    // headers default to SYSTEM for the pilot while identity -> header derivation is a follow-up
    // (coordination P4). Base URLs / currency / timeouts are env-tunable (VOICE_SUPPORT_BILLING_BSS_*).
    @Bean
    public BillingBssProperties billingBssProperties(
            @Value("${voice-support.billing.bss.source:mock}") String source,
            @Value("${voice-support.billing.bss.eir.enquiry-base-url:}") String enquiryBaseUrl,
            @Value("${voice-support.billing.bss.eir.service-base-url:}") String serviceBaseUrl,
            @Value("${voice-support.billing.bss.eir.currency:EUR}") String currency,
            @Value("${voice-support.billing.bss.eir.user-type:SYSTEM}") String userType,
            @Value("${voice-support.billing.bss.eir.user-identifier:SYSTEM}") String userIdentifier,
            @Value("${voice-support.billing.bss.eir.connect-ms:2000}") long connectMs,
            @Value("${voice-support.billing.bss.eir.read-ms:5000}") long readMs) {
        return new BillingBssProperties(source, enquiryBaseUrl, serviceBaseUrl, currency,
                userType, userIdentifier, connectMs, readMs);
    }

    @Bean
    public BssBillingPort bssBillingPort(BillingBssProperties properties, BackendTelemetry telemetry) {
        if ("eir".equalsIgnoreCase(properties.source())) {
            log.info("[BILLING-BSS] source=eir — enquiry={} service={} currency={} user-type={}",
                    properties.enquiryBaseUrl(), properties.serviceBaseUrl(),
                    properties.currency(), properties.userType());
            return eirAdapter(properties, telemetry);
        }
        if (!"mock".equalsIgnoreCase(properties.source())) {
            log.warn("[BILLING-BSS] source={} unknown — using mock fixtures", properties.source());
        }
        log.info("[BILLING-BSS] source=mock — in-memory fixtures (customer-eir-001..006)");
        return new InMemoryBssBillingAdapter(BssBillingFixtures.all());
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

    @Bean
    public RetrieveComparableInvoicesUseCase retrieveComparableInvoicesUseCase(BssBillingPort bssBillingPort) {
        return new ComparableInvoiceService(bssBillingPort);
    }

    @Bean
    public CompareInvoicesUseCase compareInvoicesUseCase() {
        return new InvoiceComparisonService();
    }

    // Confidence gate (TASK-BE-043). max-residual-ratio is the share of the total delta that may stay
    // unexplained and still be phrased (with a caveat) rather than escalated. Provisional 5% pending
    // OQ-002; tune via VOICE_SUPPORT_BILLING_CONFIDENCE_MAX_RESIDUAL_RATIO.
    @Bean
    public AssessComparisonReadinessUseCase assessComparisonReadinessUseCase(
            @Value("${voice-support.billing.confidence.max-residual-ratio:0.05}") double maxResidualRatio) {
        return new ComparisonConfidenceService(maxResidualRatio);
    }

    // Invoice PDF extractor (ADR-0005 fallback path). `fixture` (default) = synthetic extractor over
    // customer-eir-001..006; the real parser (e.g. PDFBox) registers under source=pdfbox once real
    // PDFs are available (TASK-BE-047-adjacent). Selected via VOICE_SUPPORT_BILLING_PDF_SOURCE.
    @Bean
    public InvoicePdfExtractorPort invoicePdfExtractorPort(
            @Value("${voice-support.billing.pdf.source:fixture}") String source) {
        if (!"fixture".equalsIgnoreCase(source)) {
            log.warn("[BILLING-PDF] source={} not available yet (real extractor is deferred) — using fixture extractor",
                    source);
        }
        log.info("[BILLING-PDF] source=fixture — synthetic extractor (customer-eir-001..006)");
        return new FixtureInvoicePdfExtractorAdapter(BssBillingFixtures.all());
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

    @Bean
    public ResolveCustomerIdentityUseCase resolveCustomerIdentityUseCase(CustomerDirectoryPort directory) {
        return new CustomerIdentityService(directory);
    }

    // Billing-explanation intent guard (ADR-0051 D2a). Deterministic FR/EN keyword set, env-tunable
    // via VOICE_SUPPORT_BILLING_INTENT_KEYWORDS (CSV) so it can be tuned per deployment without a code
    // change. Accent/case are folded by the detector, so keywords are written unaccented + lowercase.
    @Bean
    public BillingIntentDetector billingIntentDetector(
            @Value("${voice-support.billing.intent.keywords:"
                    + "facture,factures,facturation,montant,prelevement,tarif,augmente,augmentation,"
                    + "remise,invoice,bill,billing,charge,charged,amount,price,increase,discount}")
            String keywordsCsv) {
        List<String> keywords = Arrays.stream(keywordsCsv.split(","))
                .map(String::trim).filter(keyword -> !keyword.isBlank()).toList();
        return new BillingIntentDetector(keywords);
    }

    @Bean
    public BillingExplanationComposer billingExplanationComposer() {
        return new BillingExplanationComposer();
    }

    @Bean
    public ExplainBillingUseCase explainBillingUseCase(
            BillingIntentDetector billingIntentDetector,
            ResolveCustomerIdentityUseCase resolveCustomerIdentityUseCase,
            RetrieveComparableInvoicesUseCase retrieveComparableInvoicesUseCase,
            BssBillingPort bssBillingPort,
            CompareInvoicesUseCase compareInvoicesUseCase,
            AssessComparisonReadinessUseCase assessComparisonReadinessUseCase,
            BillingExplanationComposer billingExplanationComposer) {
        return new BillingExplanationService(
                billingIntentDetector, resolveCustomerIdentityUseCase, retrieveComparableInvoicesUseCase,
                bssBillingPort, compareInvoicesUseCase, assessComparisonReadinessUseCase,
                billingExplanationComposer);
    }
}
