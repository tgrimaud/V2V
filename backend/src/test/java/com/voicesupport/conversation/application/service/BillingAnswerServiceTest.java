package com.voicesupport.conversation.application.service;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.BillingExplanationRequest;
import com.voicesupport.conversation.domain.model.valueobject.BillingGrounding;
import com.voicesupport.conversation.domain.model.valueobject.EscalationReason;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.domain.port.out.AnswerGeneratorPort;
import com.voicesupport.conversation.domain.port.out.BillingExplanationPort;
import com.voicesupport.conversation.domain.service.LanguageDetector;
import com.voicesupport.conversation.domain.service.OutputGuardrail;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

@DisplayName("BillingAnswerService (billing explanation through the answer engine)")
class BillingAnswerServiceTest {

    private static final String QUESTION = "Why did my bill go up this month?";
    private static final String GROUNDED = "Your bill increased by 5.00 €.";

    @Test
    void an_answerable_explanation_is_rephrased_and_passes_the_guardrail() {
        // GIVEN an answerable grounded explanation and an LLM that only rewords its amount
        RecordingBillingPort port = new RecordingBillingPort(BillingGrounding.answerable(GROUNDED, 0.9));
        BillingAnswerService service = service(port, (q, ev, h, l) -> "Your bill went up by 5.00 € this month.");

        // WHEN the billing question is answered
        GeneratedAnswer answer = service.answer(request(QUESTION, null));

        // THEN the answer is grounded with the explanation confidence and did not escalate
        assertThat(answer.grounded()).isTrue();
        assertThat(answer.confidence()).isEqualTo(0.9);
        assertThat(answer.requiresEscalation()).isFalse();
        assertThat(answer.text()).contains("5.00 €");
    }

    @Test
    void resolves_the_answer_language_before_calling_the_billing_seam() {
        // GIVEN an English question and a port that records the request it receives
        RecordingBillingPort port = new RecordingBillingPort(BillingGrounding.answerable(GROUNDED, 0.9));
        BillingAnswerService service = service(port, (q, ev, h, l) -> "Your bill went up by 5.00 €.");

        // WHEN it is answered
        service.answer(request(QUESTION, null));

        // THEN the resolved language code is passed to the billing seam (so composition matches it)
        assertThat(port.lastRequest.languageCode()).isEqualTo("en");
    }

    @Test
    void an_llm_introduced_amount_is_blocked_and_escalates_dec_002() {
        // GIVEN an answerable explanation but an LLM that fabricates an amount not in the evidence
        RecordingBillingPort port = new RecordingBillingPort(BillingGrounding.answerable(GROUNDED, 0.9));
        BillingAnswerService service = service(port, (q, ev, h, l) -> "Your bill is now 99.00 €.");

        // WHEN it is answered
        GeneratedAnswer answer = service.answer(request(QUESTION, null));

        // THEN the output guardrail (DEC-002) blocks it into a non-grounded, escalating hand-off
        assertThat(answer.grounded()).isFalse();
        assertThat(answer.requiresEscalation()).isTrue();
    }

    @Test
    void an_escalating_grounding_yields_an_escalated_answer_without_the_llm() {
        // GIVEN a fail-closed identity escalation (no LLM should be invoked)
        RecordingBillingPort port = new RecordingBillingPort(
                BillingGrounding.escalate("Please give me your reference.", EscalationReason.IDENTITY_UNVERIFIED));
        RecordingGenerator generator = new RecordingGenerator("should not be used");
        BillingAnswerService service = service(port, generator);

        // WHEN it is answered
        GeneratedAnswer answer = service.answer(request(QUESTION, null));

        // THEN the answer escalates with the billing reason and the LLM was never called
        assertThat(answer.requiresEscalation()).isTrue();
        assertThat(answer.escalation()).isEqualTo(EscalationReason.IDENTITY_UNVERIFIED);
        assertThat(answer.grounded()).isFalse();
        assertThat(generator.calls).isZero();
    }

    @Test
    void a_plain_operational_message_is_a_non_escalating_fallback() {
        // GIVEN a non-answerable, non-escalating operational message
        RecordingBillingPort port = new RecordingBillingPort(
                BillingGrounding.message("Which bill is your question about?"));
        BillingAnswerService service = service(port, (q, ev, h, l) -> "unused");

        // WHEN it is answered
        GeneratedAnswer answer = service.answer(request(QUESTION, null));

        // THEN it is a safe fallback that does not escalate
        assertThat(answer.grounded()).isFalse();
        assertThat(answer.requiresEscalation()).isFalse();
        assertThat(answer.text()).contains("Which bill");
    }

    private static BillingAnswerService service(BillingExplanationPort port, AnswerGeneratorPort generator) {
        return new BillingAnswerService(port, generator, new OutputGuardrail(),
                new LanguageDetector(AnswerLanguage.ENGLISH));
    }

    private static BillingExplanationRequest request(String transcript, String language) {
        return new BillingExplanationRequest(transcript, "EIR-1002", null, language, "web", "conv-1", "corr-1");
    }

    private static final class RecordingBillingPort implements BillingExplanationPort {
        private final BillingGrounding grounding;
        private BillingExplanationRequest lastRequest;

        private RecordingBillingPort(BillingGrounding grounding) {
            this.grounding = grounding;
        }

        @Override
        public BillingGrounding explain(BillingExplanationRequest request) {
            this.lastRequest = request;
            return grounding;
        }
    }

    private static final class RecordingGenerator implements AnswerGeneratorPort {
        private final String reply;
        private int calls;

        private RecordingGenerator(String reply) {
            this.reply = reply;
        }

        @Override
        public String generate(String question, List<RetrievedEvidence> evidence, List<String> history,
                AnswerLanguage language) {
            calls++;
            return reply;
        }
    }
}
