package com.voicesupport.conversation.domain.service;

import com.voicesupport.conversation.domain.model.valueobject.GuardrailDecision;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;

import java.util.List;
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

    public GuardrailDecision check(String question, String answer, List<RetrievedEvidence> evidence) {
        if (answer == null || answer.isBlank()) {
            return GuardrailDecision.pass();
        }
        Set<String> groundedAmounts = amountsIn(concatenate(evidence));
        for (String amount : amountsIn(answer)) {
            if (!groundedAmounts.contains(amount)) {
                return GuardrailDecision.ungrounded(GuardrailMessages.ungroundedAmount(safe(question)));
            }
        }
        return GuardrailDecision.pass();
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

    private String safe(String question) {
        return question == null ? "" : question;
    }
}
