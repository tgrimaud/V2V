package com.voicesupport.conversation.application.service;

import com.voicesupport.conversation.domain.model.TokenStream;
import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.ConversationTurn;
import com.voicesupport.conversation.domain.model.valueobject.GeneratedAnswer;
import com.voicesupport.conversation.domain.model.valueobject.GuardrailDecision;
import com.voicesupport.conversation.domain.port.in.ConverseStreamUseCase;
import com.voicesupport.conversation.domain.port.in.ConverseUseCase;
import com.voicesupport.conversation.domain.port.out.ClarifyingQuestionGeneratorPort;
import com.voicesupport.conversation.domain.port.out.ConversationMemoryPort;
import com.voicesupport.conversation.domain.service.ConversationHistoryFormatter;
import com.voicesupport.conversation.domain.service.LanguageDetector;
import com.voicesupport.conversation.domain.service.OutputGuardrail;
import com.voicesupport.conversation.domain.service.ProblemOpenerDetector;
import com.voicesupport.shared.observability.BackendTelemetry;

import java.util.List;
import java.util.function.Consumer;

// US-043 / TASK-BE-071 (increment C): a bounded billing clarifying dialogue layered on top of the
// stateful converse / converse-stream pipelines. The TRIGGER and the BOUND are deterministic (never
// prompt trust); the follow-up WORDING comes from the LLM so it is natural and reacts to what the
// customer already said.
//
// Per turn: an under-specified billing opener (ProblemOpenerDetector BILLING — the TASK-BE-070 D
// signal) with a clarify streak below the configured max produces ONE LLM-worded clarifying question
// (DEC-002-vetted by the OutputGuardrail: a question states no amount, so it passes; a misbehaving
// amount or a blank falls back to the hand-off). At the cap, the assistant hands off to an advisor
// (ADR-0019) with the collected context already in memory — never another question. Any other turn
// (a real/answerable question, the customer's clarifying answer, an advisor request, off-topic...)
// flows to the normal pipeline unchanged.
//
// The clarify streak is DERIVED from conversation memory — the count of trailing turns whose stored
// question is still an under-specified billing opener — so no extra counter state is persisted (the
// turns ARE the memory); a non-opener turn (a real answer) ends the episode. max-questions <= 0
// disables the diagnostic (every turn PROCEEDs, keeping the TASK-BE-070 single canned clarify).
public class BillingDiagnosticConversationService implements ConverseUseCase, ConverseStreamUseCase {

    private enum Action { ASK_CLARIFY, ESCALATE_AT_CAP, PROCEED }

    private final ConverseUseCase answerDelegate;
    private final ConverseStreamUseCase streamDelegate;
    private final ConversationMemoryPort memory;
    private final ProblemOpenerDetector openerDetector;
    private final ClarifyingQuestionGeneratorPort clarifyGenerator;
    private final LanguageDetector languageDetector;
    private final OutputGuardrail outputGuardrail;
    private final BackendTelemetry telemetry;
    private final int maxQuestions;

    public BillingDiagnosticConversationService(
            ConverseUseCase answerDelegate,
            ConverseStreamUseCase streamDelegate,
            ConversationMemoryPort memory,
            ProblemOpenerDetector openerDetector,
            ClarifyingQuestionGeneratorPort clarifyGenerator,
            LanguageDetector languageDetector,
            OutputGuardrail outputGuardrail,
            BackendTelemetry telemetry,
            int maxQuestions) {
        this.answerDelegate = answerDelegate;
        this.streamDelegate = streamDelegate;
        this.memory = memory;
        this.openerDetector = openerDetector;
        this.clarifyGenerator = clarifyGenerator;
        this.languageDetector = languageDetector;
        this.outputGuardrail = outputGuardrail;
        this.telemetry = telemetry;
        this.maxQuestions = maxQuestions;
    }

    @Override
    public GeneratedAnswer converse(String transcript, String conversationId) {
        return converse(transcript, conversationId, null);
    }

    @Override
    public GeneratedAnswer converse(String transcript, String conversationId, String forcedLanguage) {
        if (decide(transcript, conversationId) == Action.PROCEED) {
            return answerDelegate.converse(transcript, conversationId, forcedLanguage);
        }
        List<ConversationTurn> prior = memory.recentTurns(conversationId);
        GeneratedAnswer answer = clarifyOrEscalate(transcript, prior, forcedLanguage);
        memory.append(conversationId, new ConversationTurn(transcript, answer.text()));
        return answer;
    }

    @Override
    public TokenStream converseStream(String transcript, String conversationId) {
        return converseStream(transcript, conversationId, null);
    }

    @Override
    public TokenStream converseStream(String transcript, String conversationId, String forcedLanguage) {
        if (decide(transcript, conversationId) == Action.PROCEED) {
            return streamDelegate.converseStream(transcript, conversationId, forcedLanguage);
        }
        return onChunk -> emitClarify(transcript, conversationId, forcedLanguage, onChunk);
    }

    private GeneratedAnswer emitClarify(
            String transcript, String conversationId, String forcedLanguage, Consumer<String> onChunk) {
        List<ConversationTurn> prior = memory.recentTurns(conversationId);
        GeneratedAnswer answer = clarifyOrEscalate(transcript, prior, forcedLanguage);
        onChunk.accept(answer.text());
        memory.append(conversationId, new ConversationTurn(transcript, answer.text()));
        return answer;
    }

    private Action decide(String transcript, String conversationId) {
        if (maxQuestions <= 0 || !isBillingOpener(transcript)) {
            return Action.PROCEED;
        }
        int streak = billingStreak(memory.recentTurns(conversationId));
        return streak < maxQuestions ? Action.ASK_CLARIFY : Action.ESCALATE_AT_CAP;
    }

    // Produces the LLM-worded clarifying question (DEC-002-vetted) when still under the cap, or the
    // advisor hand-off when the budget is exhausted (or the clarify is empty / voices an amount).
    private GeneratedAnswer clarifyOrEscalate(
            String transcript, List<ConversationTurn> prior, String forcedLanguage) {
        List<String> history = ConversationHistoryFormatter.format(prior);
        AnswerLanguage language = languageDetector.resolve(transcript, history, forcedLanguage);
        int streak = billingStreak(prior);
        if (streak < maxQuestions) {
            String question = clarifyGenerator.generateClarifyingQuestion(transcript, history, language);
            if (!outputGuardrail.check(question, List.of(), language).blocked()) {
                telemetry.recordBillingClarify("asked", language.code(), streak + 1);
                return GeneratedAnswer.fallback(question, GuardrailDecision.Verdict.CLARIFY);
            }
        }
        telemetry.recordBillingClarify("cap_escalated", language.code(), streak);
        return GeneratedAnswer.fallback(language.handoffSentence(), GuardrailDecision.Verdict.LOW_CONFIDENCE);
    }

    private boolean isBillingOpener(String text) {
        return openerDetector.detect(text)
                .filter(topic -> topic == ProblemOpenerDetector.Topic.BILLING)
                .isPresent();
    }

    private int billingStreak(List<ConversationTurn> prior) {
        int streak = 0;
        for (int i = prior.size() - 1; i >= 0; i--) {
            if (!isBillingOpener(prior.get(i).userText())) {
                break;
            }
            streak++;
        }
        return streak;
    }
}
