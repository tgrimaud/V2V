package com.voicesupport.conversation.application.service;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.BillingExplanationRequest;
import com.voicesupport.conversation.domain.model.valueobject.BillingGrounding;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.model.valueobject.GuardrailDecision;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.domain.port.in.AnswerBillingQuestionUseCase;
import com.voicesupport.conversation.domain.port.out.AnswerGeneratorPort;
import com.voicesupport.conversation.domain.port.out.BillingExplanationPort;
import com.voicesupport.conversation.domain.service.LanguageDetector;
import com.voicesupport.conversation.domain.service.OutputGuardrail;

import java.util.List;

// Wires the deterministic billing explanation into the answer engine (TASK-BE-045, ADR-0051 D1a).
// It resolves the answer language once, asks the billing seam for the grounded result, then:
//  - answerable  -> rephrase the grounded text via the LLM and re-run the OutputGuardrail (DEC-002),
//                   so the LLM can only reword computed amounts and never introduce one;
//  - escalate    -> a safe hand-off carrying the backend-decided escalation reason (ADR-0019);
//  - otherwise   -> voice the safe operational message as-is (e.g. ask for a reference).
// DEC-002 holds by construction: the amounts are all decided in the billing context; the LLM only
// rephrases, and the guardrail blocks any amount not present in the injected grounded evidence.
public class BillingAnswerService implements AnswerBillingQuestionUseCase {

    private static final String EVIDENCE_SOURCE = "billing";
    private static final String EVIDENCE_DOMAIN = "billing";
    private static final double EVIDENCE_SCORE = 1.0;
    private static final double DEFAULT_CONFIDENCE = 0.8;

    private final BillingExplanationPort billingExplanationPort;
    private final AnswerGeneratorPort answerGenerator;
    private final OutputGuardrail outputGuardrail;
    private final LanguageDetector languageDetector;

    public BillingAnswerService(
            BillingExplanationPort billingExplanationPort,
            AnswerGeneratorPort answerGenerator,
            OutputGuardrail outputGuardrail,
            LanguageDetector languageDetector) {
        this.billingExplanationPort = billingExplanationPort;
        this.answerGenerator = answerGenerator;
        this.outputGuardrail = outputGuardrail;
        this.languageDetector = languageDetector;
    }

    @Override
    public GeneratedAnswer answer(BillingExplanationRequest request) {
        AnswerLanguage language = languageDetector.resolve(request.transcript(), List.of(), request.languageCode());
        BillingGrounding grounding = billingExplanationPort.explain(request.withLanguage(language.code()));
        if (!grounding.answerable()) {
            return unphrased(grounding);
        }
        return phrase(request.transcript(), grounding, language);
    }

    // A non-answerable grounding is voiced as-is (no LLM, no grounding claim): an escalation carries
    // its backend-decided reason so the by-reference hand-off can be prepared; otherwise it is a plain
    // safe fallback (e.g. asking for the customer reference).
    private GeneratedAnswer unphrased(BillingGrounding grounding) {
        if (grounding.escalate() && grounding.escalationReason() != null) {
            return GeneratedAnswer.escalated(grounding.text(), grounding.escalationReason());
        }
        return GeneratedAnswer.fallback(grounding.text());
    }

    private GeneratedAnswer phrase(String question, BillingGrounding grounding, AnswerLanguage language) {
        List<RetrievedEvidence> evidence = List.of(
                new RetrievedEvidence(grounding.text(), EVIDENCE_SOURCE, EVIDENCE_DOMAIN, EVIDENCE_SCORE));
        String worded = answerGenerator.generate(question, evidence, List.of(), language);
        GuardrailDecision decision = outputGuardrail.check(worded, evidence, language);
        if (decision.blocked()) {
            return GeneratedAnswer.fallback(decision.fallbackMessage(), decision.verdict());
        }
        return GeneratedAnswer.grounded(worded, confidenceOf(grounding));
    }

    private double confidenceOf(BillingGrounding grounding) {
        return grounding.confidence() != null ? grounding.confidence() : DEFAULT_CONFIDENCE;
    }
}
