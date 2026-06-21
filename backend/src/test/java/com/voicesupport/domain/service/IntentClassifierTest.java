package com.voicesupport.domain.service;

import com.voicesupport.domain.model.AgentProfile;
import com.voicesupport.domain.model.AgentRegistry;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class IntentClassifierTest {

    private IntentClassifier classifier;

    @BeforeEach
    void setUp() {
        AgentRegistry registry = new AgentRegistry(
                List.of(AgentProfile.support(), AgentProfile.billing(), AgentProfile.commercial()),
                "support"
        );
        classifier = new IntentClassifier(registry);
    }

    @Test
    void shouldRouteToBillingOnInvoiceQuestion() {
        AgentProfile result = classifier.classify("Je ne comprends pas ma facture ce mois-ci", null);
        assertEquals("billing", result.id());
    }

    @Test
    void shouldRouteToSupportOnConnectivityQuestion() {
        AgentProfile result = classifier.classify("Ma connexion internet est très lente", null);
        assertEquals("support", result.id());
    }

    @Test
    void shouldRouteToCommercialOnSubscriptionQuestion() {
        AgentProfile result = classifier.classify("Je voudrais souscrire à une nouvelle offre fibre", null);
        assertEquals("commercial", result.id());
    }

    @Test
    void shouldFallbackToCurrentAgentWhenAmbiguous() {
        AgentProfile result = classifier.classify("j'ai un problème", "billing");
        assertEquals("billing", result.id());
    }

    @Test
    void shouldFallbackToDefaultWhenNoCurrentAgent() {
        AgentProfile result = classifier.classify("bonjour", null);
        assertEquals("support", result.id());
    }

    @Test
    void shouldSwitchAgentWhenNewIntentIsClear() {
        AgentProfile result = classifier.classify(
                "En fait je voudrais déménager et garder mon numéro avec la portabilité", "support");
        assertEquals("commercial", result.id());
    }

    @Test
    void shouldDetectBillingPaymentKeywords() {
        AgentProfile result = classifier.classify("Mon prélèvement a été rejeté par la banque", null);
        assertEquals("billing", result.id());
    }

    @Test
    void shouldDetectSupportWifiKeywords() {
        AgentProfile result = classifier.classify("Le wifi ne fonctionne pas dans la chambre", null);
        assertEquals("support", result.id());
    }

    @Test
    void shouldDetectCommercialTvOption() {
        AgentProfile result = classifier.classify("Quels sont les bouquets TV sport disponibles ?", null);
        assertEquals("commercial", result.id());
    }

    @Test
    void shouldStickToCurrentAgentOnFollowUp() {
        AgentProfile result = classifier.classify("ok et quoi d'autre ?", "commercial");
        assertEquals("commercial", result.id());
    }
}
