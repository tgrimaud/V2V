package com.voicesupport.conversation.domain.service;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.GuardrailDecision;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;

import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

// Post-LLM guardrail enforcing DEC-002: the assistant must never voice a specific billing
// amount that is not backed by source evidence. Any currency amount present in the answer
// but absent from the retrieved evidence is treated as fabricated -> the answer is dropped
// in favor of a safe hand-off. Grounded amounts (once BSS evidence carries them) pass through.
public class OutputGuardrail {

    private static final Pattern CURRENCY_AMOUNT = Pattern.compile(
            "(?i)(?:[€$£]\\s?\\d[\\d .,]*\\d|[€$£]\\s?\\d"
                    + "|\\d[\\d .,]*\\d\\s?(?:[€$£]|eur|euros?|dollars?|usd|gbp|cents?)"
                    + "|\\d\\s?(?:[€$£]|eur|euros?|dollars?|usd|gbp|cents?))");

    // The answer language is decided once per turn upstream and passed in so the hand-off wording
    // matches the language the LLM answered in (BUG-002), independent of the answer's own content.
    public GuardrailDecision check(String answer, List<RetrievedEvidence> evidence, AnswerLanguage language) {
        if (isNonAnswer(answer)) {
            return GuardrailDecision.lowConfidence(GuardrailMessages.lowConfidence(language));
        }
        Set<String> groundedAmounts = amountsIn(concatenate(evidence));
        for (String amount : amountsIn(answer)) {
            if (!groundedAmounts.contains(amount)) {
                return GuardrailDecision.ungrounded(GuardrailMessages.ungroundedAmount(language));
            }
        }
        return GuardrailDecision.pass();
    }

    // An empty answer, or an explicit "I don't have this, I transfer you to an advisor" refusal,
    // is a hand-off rather than a grounded answer: surface it as a safe fallback (grounded=false,
    // no confidence) instead of voicing it with a misleading confidence signal. Hand-off markers
    // are language-independent (TASK-BE-015) so an English refusal is caught like a French one.
    private boolean isNonAnswer(String answer) {
        if (answer == null || answer.isBlank()) {
            return true;
        }
        String normalized = answer.toLowerCase(Locale.ROOT);
        for (AnswerLanguage language : AnswerLanguage.values()) {
            for (String marker : language.handoffMarkers()) {
                if (normalized.contains(marker)) {
                    return true;
                }
            }
        }
        return false;
    }

    private Set<String> amountsIn(String text) {
        Matcher matcher = CURRENCY_AMOUNT.matcher(text);
        return matcher.results()
                .map(result -> canonical(result.group()))
                .filter(digits -> !digits.isEmpty())
                .collect(Collectors.toSet());
    }

    private String concatenate(List<RetrievedEvidence> evidence) {
        if (evidence == null || evidence.isEmpty()) {
            return "";
        }
        return evidence.stream().map(RetrievedEvidence::text).collect(Collectors.joining("\n"));
    }

    private String canonical(String amountToken) {
        return amountToken.replaceAll("[^0-9]", "");
    }
}
