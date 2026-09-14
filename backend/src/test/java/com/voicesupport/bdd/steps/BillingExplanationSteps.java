package com.voicesupport.bdd.steps;

import com.voicesupport.billing.domain.port.in.ExplainBillingUseCase;
import com.voicesupport.billing.domain.port.out.BssBillingPort;
import com.voicesupport.billing.domain.service.BillingExplanationComposer;
import com.voicesupport.billing.domain.service.BillingExplanationService;
import com.voicesupport.billing.domain.service.BillingIntentDetector;
import com.voicesupport.billing.domain.service.ComparableInvoiceService;
import com.voicesupport.billing.domain.service.ComparisonConfidenceService;
import com.voicesupport.billing.domain.service.CustomerIdentityService;
import com.voicesupport.billing.domain.service.InvoiceComparisonService;
import com.voicesupport.billing.infrastructure.adapter.out.bss.InMemoryBssBillingAdapter;
import com.voicesupport.billing.infrastructure.adapter.out.identity.InMemoryCustomerDirectoryAdapter;
import com.voicesupport.billing.infrastructure.fixtures.BssBillingFixtures;
import com.voicesupport.conversation.application.service.BillingAnswerService;
import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.BillingExplanationRequest;
import com.voicesupport.conversation.domain.model.valueobject.EscalationReason;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.port.out.BillingExplanationPort;
import com.voicesupport.conversation.domain.service.LanguageDetector;
import com.voicesupport.conversation.domain.service.OutputGuardrail;
import com.voicesupport.conversation.fake.FakeAnswerGeneratorPort;
import com.voicesupport.conversation.infrastructure.adapter.out.billing.InProcBillingExplanationAdapter;
import com.voicesupport.shared.observability.BackendTelemetry;
import io.cucumber.java.Before;
import io.cucumber.java.en.Given;
import io.cucumber.java.en.Then;
import io.cucumber.java.en.When;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class BillingExplanationSteps {

    private FakeAnswerGeneratorPort generator;
    private BillingAnswerService service;
    private String reference;
    private GeneratedAnswer answer;
    private String llmReply;

    @Before
    public void setUp() {
        BssBillingPort bss = new InMemoryBssBillingAdapter(BssBillingFixtures.all());
        ExplainBillingUseCase explainBilling = new BillingExplanationService(
                new BillingIntentDetector(List.of("facture", "augmente", "invoice", "bill")),
                new CustomerIdentityService(new InMemoryCustomerDirectoryAdapter()),
                new ComparableInvoiceService(bss), bss,
                new InvoiceComparisonService(), new ComparisonConfidenceService(0.05),
                new BillingExplanationComposer());
        BillingExplanationPort port = new InProcBillingExplanationAdapter(
                explainBilling, new BackendTelemetry(new SimpleMeterRegistry()));
        generator = new FakeAnswerGeneratorPort();
        service = new BillingAnswerService(
                port, generator, new OutputGuardrail(), new LanguageDetector(AnswerLanguage.FRENCH));
        reference = null;
        answer = null;
        llmReply = null;
    }

    @Given("a customer whose recent discount expired")
    public void aCustomerWhoseDiscountExpired() {
        reference = "EIR-1002";
    }

    @Given("a customer whose bill did not change")
    public void aCustomerWhoseBillDidNotChange() {
        reference = "EIR-1001";
    }

    @Given("a customer reference that matches no account")
    public void aReferenceMatchingNoAccount() {
        reference = "UNKNOWN-REF";
    }

    @Given("a customer reference that matches several accounts")
    public void aReferenceMatchingSeveralAccounts() {
        reference = "EIR-DUP";
    }

    @Given("a customer with a single invoice on file")
    public void aCustomerWithASingleInvoice() {
        reference = "EIR-1005";
    }

    @Given("a customer whose two invoices have no billable lines")
    public void aCustomerWithUnusableInvoices() {
        reference = "EIR-1006";
    }

    @Given("the language model rephrases the explanation as {string}")
    public void theLanguageModelRephrasesAs(String reply) {
        this.llmReply = reply;
        generator.setNextAnswer(reply);
    }

    @Given("the language model would fabricate {string}")
    public void theLanguageModelWouldFabricate(String reply) {
        this.llmReply = reply;
        generator.setNextAnswer(reply);
    }

    @When("the customer asks why their bill increased")
    public void asksWhyBillIncreased() {
        answer = service.answer(request("Pourquoi ma facture a augmenté ce mois-ci ?"));
    }

    @When("the customer asks how much they must pay")
    public void asksHowMuchTheyMustPay() {
        answer = service.answer(request("Combien vais-je payer sur ma facture ?"));
    }

    @When("the customer asks a question unrelated to billing")
    public void asksAnUnrelatedQuestion() {
        answer = service.answer(request("Quel temps fera-t-il demain ?"));
    }

    @Then("the assistant voices a grounded explanation")
    public void voicesAGroundedExplanation() {
        assertTrue(answer.grounded(), "expected a grounded explanation");
    }

    @Then("the explanation mentions {string}")
    public void theExplanationMentions(String fragment) {
        assertTrue(answer.text().contains(fragment), "expected the explanation to mention " + fragment);
    }

    @Then("the assistant does not escalate")
    public void doesNotEscalate() {
        assertFalse(answer.requiresEscalation(), "expected no escalation");
    }

    @Then("the assistant does not voice that answer")
    public void doesNotVoiceThatAnswer() {
        assertFalse(answer.grounded(), "expected a non-grounded fallback");
        if (llmReply != null) {
            assertFalse(llmReply.equals(answer.text()), "the raw LLM reply must not be voiced");
        }
    }

    @Then("the assistant hands the customer to an advisor")
    public void handsToAnAdvisor() {
        assertTrue(answer.text().toLowerCase().contains("conseiller"),
                "expected a hand-off to a human advisor");
    }

    @Then("the assistant asks the customer to identify without revealing any billing amount")
    public void asksToIdentifyWithoutBillingData() {
        assertFalse(answer.grounded(), "expected a non-grounded identity request");
        assertFalse(answer.text().contains("€"), "an identity request must not reveal any amount");
    }

    @Then("the assistant escalates the identity for a human advisor")
    public void escalatesIdentity() {
        assertTrue(answer.requiresEscalation(), "expected an escalation");
        assertEquals(EscalationReason.IDENTITY_UNVERIFIED, answer.escalation());
    }

    @Then("the assistant escalates because the bill cannot be explained")
    public void escalatesBillingUnexplained() {
        assertTrue(answer.requiresEscalation(), "expected an escalation");
        assertEquals(EscalationReason.BILLING_UNEXPLAINED, answer.escalation());
    }

    @Then("the assistant redirects to a billing question without calling the language model")
    public void redirectsWithoutCallingTheLlm() {
        assertFalse(answer.grounded(), "expected a non-grounded redirect");
        assertFalse(answer.requiresEscalation(), "a redirect must not escalate");
        assertEquals(0, generator.callCount, "the LLM must not be called for a non-billing question");
    }

    private BillingExplanationRequest request(String transcript) {
        return new BillingExplanationRequest(transcript, reference, null, null, "web", "conv-qa", "corr-qa");
    }
}
