package com.voicesupport.conversation.domain.service;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.GuardrailDecision;
import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;

import java.math.BigDecimal;
import java.math.RoundingMode;
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

    // Canonical amount key = currency class + value normalized to 2 decimals. A bare digit-only
    // key (the previous "[^0-9]" strip) collided across magnitudes and formats: "€1.50" and "€150"
    // both became "150", so a fabricated amount could match a grounded one of a different value
    // (a DEC-002 bypass). Parsing to (currency, decimal value) closes that collision while making
    // the same amount in different locales match ("1,50 €" == "€1.50" == "EUR:1.50").
    private String canonical(String amountToken) {
        BigDecimal value = parseAmount(amountToken.replaceAll("[^0-9.,]", ""));
        if (value == null) {
            return "";
        }
        return currencyOf(amountToken) + ":" + value.setScale(2, RoundingMode.HALF_UP).toPlainString();
    }

    private String currencyOf(String token) {
        String lower = token.toLowerCase(Locale.ROOT);
        if (lower.contains("€") || lower.contains("eur") || lower.contains("euro")) {
            return "EUR";
        }
        if (lower.contains("$") || lower.contains("usd") || lower.contains("dollar")) {
            return "USD";
        }
        if (lower.contains("£") || lower.contains("gbp")) {
            return "GBP";
        }
        if (lower.contains("cent")) {
            return "CENT";
        }
        return "?";
    }

    // Locale-aware: with both separators the rightmost is the decimal one; a lone separator is a
    // decimal point only when it is unique and groups 1-2 trailing digits (e.g. "1,50"), otherwise
    // it is a thousands separator ("1,500", "1.234.567"). Ambiguity is resolved toward NOT merging
    // distinct-looking values, so the guardrail errs on the safe (block) side.
    private BigDecimal parseAmount(String number) {
        if (number == null || number.isBlank()) {
            return null;
        }
        boolean hasDot = number.indexOf('.') >= 0;
        boolean hasComma = number.indexOf(',') >= 0;
        String normalized;
        if (hasDot && hasComma) {
            char decimal = number.lastIndexOf('.') > number.lastIndexOf(',') ? '.' : ',';
            normalized = stripAllBut(number, decimal).replace(decimal, '.');
        } else if (hasDot || hasComma) {
            normalized = normalizeSingleSeparator(number, hasDot ? '.' : ',');
        } else {
            normalized = number;
        }
        try {
            return new BigDecimal(normalized);
        } catch (NumberFormatException ignored) {
            return null;
        }
    }

    private String normalizeSingleSeparator(String number, char separator) {
        int first = number.indexOf(separator);
        int last = number.lastIndexOf(separator);
        String trailing = number.substring(last + 1);
        boolean decimal = first == last && trailing.length() >= 1 && trailing.length() <= 2;
        return decimal ? number.replace(separator, '.') : stripSeparator(number, separator);
    }

    private String stripAllBut(String number, char keep) {
        char strip = keep == '.' ? ',' : '.';
        return stripSeparator(number, strip);
    }

    private String stripSeparator(String number, char separator) {
        return number.replace(String.valueOf(separator), "");
    }
}
