package com.voicesupport.billing.domain.service;

import com.voicesupport.billing.domain.model.BillingExplanation;
import com.voicesupport.billing.domain.model.BillingExplanationOutcome;
import com.voicesupport.billing.domain.model.valueobject.BillingExplanationQuery;
import com.voicesupport.billing.domain.port.out.BssBillingPort;
import com.voicesupport.billing.infrastructure.adapter.out.bss.InMemoryBssBillingAdapter;
import com.voicesupport.billing.infrastructure.adapter.out.identity.InMemoryCustomerDirectoryAdapter;
import com.voicesupport.billing.infrastructure.fixtures.BssBillingFixtures;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

@DisplayName("BillingExplanationService (fail-closed billing chain)")
class BillingExplanationServiceTest {

    private static final String BILLING_QUESTION = "Pourquoi ma facture a augmenté ce mois-ci ?";

    private final BillingExplanationService service = newService();

    @Test
    void a_non_billing_question_is_not_a_billing_request_and_does_not_escalate() {
        // GIVEN a question with no billing keyword
        BillingExplanation explanation = service.explain(
                BillingExplanationQuery.of("web", "Comment configurer mon routeur ?", "EIR-1002", null, "fr"));

        // THEN it is flagged as not a billing request, without escalation, and does not leak data
        assertThat(explanation.outcome()).isEqualTo(BillingExplanationOutcome.NOT_A_BILLING_REQUEST);
        assertThat(explanation.escalate()).isFalse();
        assertThat(explanation.answerable()).isFalse();
    }

    @Test
    void a_missing_reference_asks_for_identity_and_escalates_fail_closed() {
        // GIVEN a billing question with no customer reference
        BillingExplanation explanation = service.explain(
                BillingExplanationQuery.of("web", BILLING_QUESTION, null, null, "fr"));

        // THEN identity is unresolved (BR-002-1), it escalates by-reference, and asks for a reference
        assertThat(explanation.outcome()).isEqualTo(BillingExplanationOutcome.IDENTITY_UNRESOLVED);
        assertThat(explanation.escalate()).isTrue();
        assertThat(explanation.escalationCode()).isEqualTo(BillingExplanation.CODE_IDENTITY_UNVERIFIED);
        assertThat(explanation.text()).contains("référence");
    }

    @Test
    void an_unknown_reference_does_not_grant_access() {
        // GIVEN a billing question with a reference the directory does not know
        BillingExplanation explanation = service.explain(
                BillingExplanationQuery.of("web", BILLING_QUESTION, "UNKNOWN-REF", null, "fr"));

        // THEN it fails closed to IDENTITY_UNRESOLVED
        assertThat(explanation.outcome()).isEqualTo(BillingExplanationOutcome.IDENTITY_UNRESOLVED);
        assertThat(explanation.escalate()).isTrue();
    }

    @Test
    void an_ambiguous_reference_does_not_grant_access() {
        // GIVEN the intentionally ambiguous reference (EIR-DUP -> two accounts)
        BillingExplanation explanation = service.explain(
                BillingExplanationQuery.of("web", BILLING_QUESTION, "EIR-DUP", null, "fr"));

        // THEN it fails closed (never guesses which account)
        assertThat(explanation.outcome()).isEqualTo(BillingExplanationOutcome.IDENTITY_UNRESOLVED);
        assertThat(explanation.escalate()).isTrue();
    }

    @Test
    void a_resolved_customer_with_an_expired_discount_gets_a_grounded_explanation() {
        // GIVEN the discount-expiry customer (EIR-1002 -> eir-002)
        BillingExplanation explanation = service.explain(
                BillingExplanationQuery.of("web", BILLING_QUESTION, "EIR-1002", null, "fr"));

        // THEN it is fully explained, answerable, not escalated, and the grounded text carries the amount
        assertThat(explanation.outcome()).isEqualTo(BillingExplanationOutcome.EXPLAINED);
        assertThat(explanation.answerable()).isTrue();
        assertThat(explanation.escalate()).isFalse();
        assertThat(explanation.text()).contains("5.00 €");
    }

    @Test
    void a_customer_with_a_single_invoice_has_not_enough_data_and_escalates() {
        // GIVEN the insufficient-data customer (EIR-1005 -> eir-005, one invoice only)
        BillingExplanation explanation = service.explain(
                BillingExplanationQuery.of("web", BILLING_QUESTION, "EIR-1005", null, "fr"));

        // THEN there is nothing to compare -> NOT_ENOUGH_DATA, escalate by-reference
        assertThat(explanation.outcome()).isEqualTo(BillingExplanationOutcome.NOT_ENOUGH_DATA);
        assertThat(explanation.escalate()).isTrue();
        assertThat(explanation.escalationCode()).isEqualTo(BillingExplanation.CODE_BILLING_UNEXPLAINED);
    }

    @Test
    void an_unusable_pair_of_invoices_has_not_enough_data_and_escalates() {
        // GIVEN the unusable customer (EIR-1006 -> eir-006, two invoices with no billed lines)
        BillingExplanation explanation = service.explain(
                BillingExplanationQuery.of("web", BILLING_QUESTION, "EIR-1006", null, "fr"));

        // THEN the confidence gate finds no usable lines -> NOT_ENOUGH_DATA, escalate
        assertThat(explanation.outcome()).isEqualTo(BillingExplanationOutcome.NOT_ENOUGH_DATA);
        assertThat(explanation.escalate()).isTrue();
    }

    @Test
    void a_nominal_customer_is_told_the_bill_is_unchanged() {
        // GIVEN the nominal customer (EIR-1001 -> eir-001, two identical invoices)
        BillingExplanation explanation = service.explain(
                BillingExplanationQuery.of("web", BILLING_QUESTION, "EIR-1001", null, "en"));

        // THEN it is explainable and answerable, stating the bill is unchanged
        assertThat(explanation.outcome()).isEqualTo(BillingExplanationOutcome.EXPLAINED);
        assertThat(explanation.answerable()).isTrue();
        assertThat(explanation.text()).contains("unchanged");
    }

    private static BillingExplanationService newService() {
        BssBillingPort bss = new InMemoryBssBillingAdapter(BssBillingFixtures.all());
        return new BillingExplanationService(
                new BillingIntentDetector(List.of("facture", "augmente", "invoice", "bill")),
                new CustomerIdentityService(new InMemoryCustomerDirectoryAdapter()),
                new ComparableInvoiceService(bss),
                bss,
                new InvoiceComparisonService(),
                new ComparisonConfidenceService(0.05),
                new BillingExplanationComposer());
    }
}
