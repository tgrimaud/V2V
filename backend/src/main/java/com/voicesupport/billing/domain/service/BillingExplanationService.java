package com.voicesupport.billing.domain.service;

import com.voicesupport.billing.domain.model.BillingExplanation;
import com.voicesupport.billing.domain.model.ExplanationConfidence;
import com.voicesupport.billing.domain.model.ExplanationReadiness;
import com.voicesupport.billing.domain.model.IdentityResolution;
import com.voicesupport.billing.domain.model.Invoice;
import com.voicesupport.billing.domain.model.InvoiceComparison;
import com.voicesupport.billing.domain.model.valueobject.AccountId;
import com.voicesupport.billing.domain.model.valueobject.BillingExplanationQuery;
import com.voicesupport.billing.domain.model.valueobject.IdentityClaim;
import com.voicesupport.billing.domain.model.valueobject.InvoiceId;
import com.voicesupport.billing.domain.model.valueobject.InvoiceSummary;
import com.voicesupport.billing.domain.port.in.AssessComparisonReadinessUseCase;
import com.voicesupport.billing.domain.port.in.CompareInvoicesUseCase;
import com.voicesupport.billing.domain.port.in.ExplainBillingUseCase;
import com.voicesupport.billing.domain.port.in.ResolveCustomerIdentityUseCase;
import com.voicesupport.billing.domain.port.in.RetrieveComparableInvoicesUseCase;
import com.voicesupport.billing.domain.port.out.BssBillingPort;

import java.util.Iterator;
import java.util.List;
import java.util.Objects;

// Orchestrates the billing explanation chain fail-closed (TASK-BE-045, ADR-0051): intent guard ->
// identity (BR-002-1) -> comparable invoices -> deterministic comparison -> confidence gate (BR-003,
// DEC-002) -> grounded text. Pure domain: it depends only on billing ports/services, never on the
// answer engine or Spring, so DEC-002 (the LLM never computes amounts) holds by construction — the
// amounts are all decided here. V1 compares the two most recent invoices; the query's invoiceId is
// reserved for future targeted selection.
public class BillingExplanationService implements ExplainBillingUseCase {

    private static final int MIN_COMPARABLE_INVOICES = 2;
    private static final double CONFIDENCE_FULL = 0.9;
    private static final double CONFIDENCE_PARTIAL = 0.6;

    private final BillingIntentDetector intentDetector;
    private final ResolveCustomerIdentityUseCase resolveIdentity;
    private final RetrieveComparableInvoicesUseCase retrieveComparable;
    private final BssBillingPort bss;
    private final CompareInvoicesUseCase compare;
    private final AssessComparisonReadinessUseCase assess;
    private final BillingExplanationComposer composer;

    public BillingExplanationService(
            BillingIntentDetector intentDetector,
            ResolveCustomerIdentityUseCase resolveIdentity,
            RetrieveComparableInvoicesUseCase retrieveComparable,
            BssBillingPort bss,
            CompareInvoicesUseCase compare,
            AssessComparisonReadinessUseCase assess,
            BillingExplanationComposer composer) {
        this.intentDetector = intentDetector;
        this.resolveIdentity = resolveIdentity;
        this.retrieveComparable = retrieveComparable;
        this.bss = bss;
        this.compare = compare;
        this.assess = assess;
        this.composer = composer;
    }

    @Override
    public BillingExplanation explain(BillingExplanationQuery query) {
        Objects.requireNonNull(query, "query must not be null");
        String language = query.languageCode();
        if (!intentDetector.isBillingExplanationRequest(query.transcript())) {
            return BillingExplanation.notABillingRequest(composer.notABillingRequest(language));
        }
        if (!query.hasReference()) {
            return BillingExplanation.identityUnresolved(composer.askReference(language));
        }
        IdentityResolution identity = resolveIdentity.resolve(new IdentityClaim(query.channel(), query.reference()));
        if (!identity.canAccessBilling()) {
            return BillingExplanation.identityUnresolved(composer.cannotVerify(language));
        }
        return explainForAccount(identity.account(), language);
    }

    private BillingExplanation explainForAccount(AccountId account, String language) {
        List<InvoiceSummary> summaries = retrieveComparable.availableInvoices(account);
        if (summaries.size() < MIN_COMPARABLE_INVOICES) {
            return BillingExplanation.notEnoughData(composer.notEnoughData(language));
        }
        InvoiceComparison comparison = compareTwoMostRecent(account, summaries);
        ExplanationReadiness readiness = assess.assess(comparison);
        return fromReadiness(comparison, readiness, language);
    }

    // Summaries are most-recent-first (RetrieveComparableInvoicesUseCase contract): current is the
    // latest, previous the one before. Uses an iterator (never index access) per the code guidelines.
    private InvoiceComparison compareTwoMostRecent(AccountId account, List<InvoiceSummary> summaries) {
        Iterator<InvoiceSummary> iterator = summaries.iterator();
        Invoice current = fetch(account, iterator.next().id());
        Invoice previous = fetch(account, iterator.next().id());
        return compare.compare(previous, current);
    }

    private Invoice fetch(AccountId account, InvoiceId invoiceId) {
        return bss.fetchInvoice(account, invoiceId)
                .orElseThrow(() -> new IllegalStateException("listed invoice not fetchable: " + invoiceId.value()));
    }

    private BillingExplanation fromReadiness(
            InvoiceComparison comparison, ExplanationReadiness readiness, String language) {
        if (readiness.confidence() == ExplanationConfidence.EXPLAINABLE) {
            return BillingExplanation.explained(composer.compose(comparison, readiness, language), CONFIDENCE_FULL);
        }
        if (readiness.confidence() == ExplanationConfidence.PARTIAL) {
            return BillingExplanation.partiallyExplained(
                    composer.compose(comparison, readiness, language), CONFIDENCE_PARTIAL);
        }
        return BillingExplanation.notEnoughData(composer.notEnoughData(language));
    }
}
