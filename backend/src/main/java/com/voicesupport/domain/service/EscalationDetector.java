package com.voicesupport.domain.service;

import java.util.Set;

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

    public boolean shouldEscalate(String userMessage) {
        String lower = userMessage.toLowerCase();
        return ESCALATION_KEYWORDS.stream().anyMatch(lower::contains);
    }

    public String getEscalationMessage() {
        return "Je comprends votre situation. Je vais vous mettre en relation avec " +
                "un conseiller spécialisé qui pourra vous aider davantage. " +
                "Merci de patienter quelques instants.";
    }
}
