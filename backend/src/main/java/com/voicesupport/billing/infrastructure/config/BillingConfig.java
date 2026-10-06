package com.voicesupport.billing.infrastructure.config;

import com.voicesupport.billing.domain.port.in.AssessComparisonReadinessUseCase;
import com.voicesupport.billing.domain.port.in.CompareInvoicesUseCase;
import com.voicesupport.billing.domain.port.in.ExplainBillingUseCase;
import com.voicesupport.billing.domain.port.in.ResolveCustomerIdentityUseCase;
import com.voicesupport.billing.domain.port.in.RetrieveComparableInvoicesUseCase;
import com.voicesupport.billing.domain.port.out.BssBillingPort;
import com.voicesupport.billing.domain.port.out.CustomerDirectoryPort;
import com.voicesupport.billing.domain.service.BillingExplanationComposer;
import com.voicesupport.billing.domain.service.BillingExplanationService;
import com.voicesupport.billing.domain.service.BillingIntentDetector;
import com.voicesupport.billing.domain.service.ComparableInvoiceService;
import com.voicesupport.billing.domain.service.ComparisonConfidenceService;
import com.voicesupport.billing.domain.service.CustomerIdentityService;
import com.voicesupport.billing.domain.service.InvoiceComparisonService;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.Arrays;
import java.util.List;

// Domain use-case wiring for billing (hexagonal: services exposed as @Bean, pure domain stays
// Spring-free). The out-adapter selection (BSS source, PDF extractor, bill-run documents, customer
// directory) lives in BillingAdapterConfig; the BSS source/eir/pdf settings bean stays here as the
// single @Value binding point consumed across both configs.
@Configuration
public class BillingConfig {

    // BSS billing source (ADR-0004/0005). `mock` (default) = in-memory fixtures customer-eir-001..006
    // so the billing chain runs before live access; `eir` = the real read-only adapter over the two
    // Eir services (structured JSON, TASK-BE-047); `pdf` = the PDF evidence path (TASK-BE-062) that
    // downloads the invoice document and parses it via InvoicePdfExtractorPort, regenerating the same
    // domain Invoice. All three sit behind BssBillingPort so switching is a single config change,
    // VOICE_SUPPORT_BILLING_BSS_SOURCE, with no impact on the comparison engine. The galaxion-user-*
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
            @Value("${voice-support.billing.bss.eir.read-ms:5000}") long readMs,
            @Value("${voice-support.billing.bss.billrun.base-url:}") String billRunBaseUrl,
            @Value("${voice-support.billing.bss.billrun.source:fixture}") String billRunSource) {
        return new BillingBssProperties(source, enquiryBaseUrl, serviceBaseUrl, currency,
                userType, userIdentifier, connectMs, readMs, billRunBaseUrl, billRunSource);
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

    @Bean
    public ResolveCustomerIdentityUseCase resolveCustomerIdentityUseCase(CustomerDirectoryPort directory) {
        return new CustomerIdentityService(directory);
    }

    // Billing-explanation intent guard (ADR-0052 D2a). Deterministic FR/EN keyword set, env-tunable
    // via VOICE_SUPPORT_BILLING_INTENT_KEYWORDS (CSV) so it can be tuned per deployment without a code
    // change. Accent/case are folded by the detector, so keywords are written unaccented + lowercase.
    @Bean
    public BillingIntentDetector billingIntentDetector(
            @Value("${voice-support.billing.intent.keywords:"
                    + "facture,factures,facturation,montant,prelevement,tarif,augmente,augmentation,"
                    + "remise,paye,paie,payer,paiement,prix,coute,cher,"
                    + "invoice,bill,billing,charge,charged,amount,price,increase,discount}")
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
