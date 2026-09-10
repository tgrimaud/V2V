package com.voicesupport.billing.infrastructure.config;

import com.voicesupport.billing.domain.port.in.AssessComparisonReadinessUseCase;
import com.voicesupport.billing.domain.port.in.CompareInvoicesUseCase;
import com.voicesupport.billing.domain.port.in.RetrieveComparableInvoicesUseCase;
import com.voicesupport.billing.domain.port.out.BssBillingPort;
import com.voicesupport.billing.domain.service.ComparableInvoiceService;
import com.voicesupport.billing.domain.service.ComparisonConfidenceService;
import com.voicesupport.billing.domain.service.InvoiceComparisonService;
import com.voicesupport.billing.infrastructure.adapter.out.bss.InMemoryBssBillingAdapter;
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
}
