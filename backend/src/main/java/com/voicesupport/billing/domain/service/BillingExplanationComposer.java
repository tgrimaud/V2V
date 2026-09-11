package com.voicesupport.billing.domain.service;

import com.voicesupport.billing.domain.model.BillingCause;
import com.voicesupport.billing.domain.model.BillingCauseType;
import com.voicesupport.billing.domain.model.ExplanationConfidence;
import com.voicesupport.billing.domain.model.ExplanationReadiness;
import com.voicesupport.billing.domain.model.InvoiceComparison;
import com.voicesupport.billing.domain.model.valueobject.Money;

import java.math.BigDecimal;
import java.util.Locale;

// Turns a deterministic comparison + confidence verdict into grounded, language-aware explanation
// text (TASK-BE-045, ADR-0051 D1a). Every currency amount it voices comes from the computed comparison
// (delta, per-cause impact, residual), so the downstream OutputGuardrail (DEC-002) passes: the LLM may
// only rephrase this text and can never introduce an amount that is not here. Also owns the safe
// operational / hand-off messages for the degraded branches, kept language-consistent with answers.
public class BillingExplanationComposer {

    public String compose(InvoiceComparison comparison, ExplanationReadiness readiness, String languageCode) {
        boolean fr = isFrench(languageCode);
        StringBuilder text = new StringBuilder(openingLine(comparison.totalDelta(), fr));
        for (BillingCause cause : comparison.causes()) {
            text.append(' ').append(causeLine(cause, fr));
        }
        if (readiness.confidence() == ExplanationConfidence.PARTIAL) {
            text.append(' ').append(residualLine(readiness.unexplainedAmount(), fr));
        }
        return text.toString().strip();
    }

    public String askReference(String languageCode) {
        return isFrench(languageCode)
                ? "Pour analyser votre facture, pouvez-vous me communiquer votre référence client ?"
                : "To review your bill, could you give me your customer reference?";
    }

    public String cannotVerify(String languageCode) {
        return isFrench(languageCode)
                ? "Je ne parviens pas à vérifier votre identité, je vous transfère à un conseiller."
                : "I can't verify your identity, I'll transfer you to an advisor.";
    }

    public String notEnoughData(String languageCode) {
        return isFrench(languageCode)
                ? "Je n'ai pas assez d'éléments pour comparer vos factures, je vous transfère à un conseiller."
                : "I don't have enough information to compare your bills, I'll transfer you to an advisor.";
    }

    public String notABillingRequest(String languageCode) {
        return isFrench(languageCode)
                ? "Je peux vous aider à comprendre votre facture. Sur quelle facture porte votre question ?"
                : "I can help you understand your bill. Which bill is your question about?";
    }

    private String openingLine(Money delta, boolean fr) {
        if (delta.isZero()) {
            return fr ? "Votre facture est identique au mois précédent."
                    : "Your bill is unchanged from last month.";
        }
        boolean increased = !delta.isNegative();
        if (fr) {
            return "Votre facture a " + (increased ? "augmenté" : "diminué") + " de " + money(delta.abs())
                    + " par rapport au mois précédent.";
        }
        return "Your bill " + (increased ? "increased" : "decreased") + " by " + money(delta.abs())
                + " compared with last month.";
    }

    private String causeLine(BillingCause cause, boolean fr) {
        String label = label(cause.type(), fr);
        if (fr) {
            return "En cause : " + label + " pour " + signed(cause.impact()) + ".";
        }
        return "This is due to " + label + " (" + signed(cause.impact()) + ").";
    }

    private String residualLine(Money residual, boolean fr) {
        if (fr) {
            return "Il reste " + money(residual.abs()) + " que je ne peux pas détailler précisément.";
        }
        return "A remaining " + money(residual.abs()) + " could not be fully detailed.";
    }

    private String signed(Money amount) {
        return (amount.isNegative() ? "-" : "+") + money(amount.abs());
    }

    private String money(Money amount) {
        BigDecimal value = BigDecimal.valueOf(amount.minorUnits(), 2);
        return value.toPlainString() + " " + symbol(amount);
    }

    private String symbol(Money amount) {
        return switch (amount.currency().getCurrencyCode()) {
            case "EUR" -> "€";
            case "USD" -> "$";
            case "GBP" -> "£";
            default -> amount.currency().getCurrencyCode();
        };
    }

    private String label(BillingCauseType type, boolean fr) {
        return switch (type) {
            case DISCOUNT_EXPIRY -> fr ? "la fin d'une remise" : "the end of a discount";
            case USAGE_OVERAGE -> fr ? "un dépassement de consommation" : "usage over your plan";
            case OPTION_CHANGE -> fr ? "un changement d'option" : "an option change";
            case PRORATION -> fr ? "un ajustement au prorata" : "a pro-rata adjustment";
            case TAX -> fr ? "une variation de taxe" : "a tax change";
            case ONE_OFF_FEE -> fr ? "des frais ponctuels" : "a one-off charge";
            case ADJUSTMENT -> fr ? "un ajustement" : "an adjustment";
            case UNEXPLAINED -> fr ? "une part non expliquée" : "an unexplained part";
        };
    }

    private boolean isFrench(String languageCode) {
        return languageCode != null && languageCode.strip().toLowerCase(Locale.ROOT).startsWith("fr");
    }
}
