package com.voicesupport.domain.service;

import java.util.Set;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

public class EscalationDetector {

    private static final Set<String> ESCALATION_KEYWORDS = Set.of(
            "résiliation", "résilier", "annuler mon abonnement",
            "réclamation", "rembourser", "remboursement",
            "technicien", "déplacement",
            "données personnelles", "rgpd", "supprimer mes données",
            "piratage", "piraté", "usurpation",
            "parler à un humain", "conseiller", "un vrai conseiller",
            "pas satisfait", "inacceptable", "scandaleux"
    );

    // Whole-word matching avoids substring false positives (e.g. "déconseiller"
    // would match a raw `contains("conseiller")`).
    private static final Set<Pattern> ESCALATION_PATTERNS = ESCALATION_KEYWORDS.stream()
            .map(keyword -> Pattern.compile(
                    "\\b" + Pattern.quote(keyword) + "\\b",
                    Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CHARACTER_CLASS))
            .collect(Collectors.toUnmodifiableSet());

    public boolean shouldEscalate(String userMessage) {
        return ESCALATION_PATTERNS.stream()
                .anyMatch(pattern -> pattern.matcher(userMessage).find());
    }

    public String getEscalationMessage() {
        return "Je comprends votre situation. Je vais vous mettre en relation avec " +
                "un conseiller spécialisé qui pourra vous aider davantage. " +
                "Merci de patienter quelques instants.";
    }
}
