package com.voicesupport.billing.infrastructure.config;

import com.voicesupport.billing.domain.port.in.AssessComparisonReadinessUseCase;
import com.voicesupport.billing.domain.port.in.CompareInvoicesUseCase;
import com.voicesupport.billing.domain.port.in.ResolveCustomerIdentityUseCase;
import com.voicesupport.billing.domain.port.in.RetrieveComparableInvoicesUseCase;
import com.voicesupport.billing.domain.port.out.BssBillingPort;
import com.voicesupport.billing.domain.port.out.CustomerDirectoryPort;
import com.voicesupport.billing.domain.port.out.InvoicePdfExtractorPort;
import com.voicesupport.billing.domain.service.ComparableInvoiceService;
import com.voicesupport.billing.domain.service.ComparisonConfidenceService;
import com.voicesupport.billing.domain.service.CustomerIdentityService;
import com.voicesupport.billing.domain.service.InvoiceComparisonService;
import com.voicesupport.billing.infrastructure.adapter.out.bss.InMemoryBssBillingAdapter;
import com.voicesupport.billing.infrastructure.adapter.out.identity.InMemoryCustomerDirectoryAdapter;
import com.voicesupport.billing.infrastructure.adapter.out.pdf.FixtureInvoicePdfExtractorAdapter;
import com.voicesupport.billing.infrastructure.fixtures.BssBillingFixtures;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BillingConfig {

    private static final Logger log = LoggerFactory.getLogger(BillingConfig.class);

    // BSS billing source (ADR-0004). `mock` (default) = in-memory fixtures customer-eir-001..006 so
    // the billing chain runs before live access; the real read-only billing-api adapter (TASK-BE-047)
    // will register under source=billing-api once OQ-003 access is confirmed. Selected via
    // VOICE_SUPPORT_BILLING_BSS_SOURCE.
    @Bean
    public BssBillingPort bssBillingPort(
            @Value("${voice-support.billing.bss.source:mock}") String source) {
        if (!"mock".equalsIgnoreCase(source)) {
            log.warn("[BILLING-BSS] source={} not available yet (real adapter is TASK-BE-047) — using mock fixtures",
                    source);
        }
        log.info("[BILLING-BSS] source=mock — in-memory fixtures (customer-eir-001..006)");
        return new InMemoryBssBillingAdapter(BssBillingFixtures.all());
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
}
