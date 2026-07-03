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
    void classify_routes_to_billing_on_invoice_question() {
        // GIVEN / WHEN
        AgentProfile result = classifier.classify("Je ne comprends pas ma facture ce mois-ci", null);

        // THEN
        assertEquals("billing", result.id());
    }

    @Test
    void classify_routes_to_support_on_connectivity_question() {
        // GIVEN / WHEN
        AgentProfile result = classifier.classify("Ma connexion internet est très lente", null);

        // THEN
        assertEquals("support", result.id());
    }

    @Test
    void classify_routes_to_commercial_on_subscription_question() {
        // GIVEN / WHEN
        AgentProfile result = classifier.classify("Je voudrais souscrire à une nouvelle offre fibre", null);

        // THEN
        assertEquals("commercial", result.id());
    }

    @Test
    void classify_falls_back_to_current_agent_when_ambiguous() {
        // GIVEN / WHEN
        AgentProfile result = classifier.classify("j'ai un problème", "billing");

        // THEN
        assertEquals("billing", result.id());
    }

    @Test
    void classify_falls_back_to_default_when_no_current_agent() {
        // GIVEN / WHEN
        AgentProfile result = classifier.classify("bonjour", null);

        // THEN
        assertEquals("support", result.id());
    }

    @Test
    void classify_switches_agent_when_new_intent_is_clear() {
        // GIVEN / WHEN
        AgentProfile result = classifier.classify(
                "En fait je voudrais déménager et garder mon numéro avec la portabilité", "support");

        // THEN
        assertEquals("commercial", result.id());
    }

    @Test
    void classify_detects_billing_payment_keywords() {
        // GIVEN / WHEN
        AgentProfile result = classifier.classify("Mon prélèvement a été rejeté par la banque", null);

        // THEN
        assertEquals("billing", result.id());
    }

    @Test
    void classify_detects_support_wifi_keywords() {
        // GIVEN / WHEN
        AgentProfile result = classifier.classify("Le wifi ne fonctionne pas dans la chambre", null);

        // THEN
        assertEquals("support", result.id());
    }

    @Test
    void classify_detects_commercial_tv_option() {
        // GIVEN / WHEN
        AgentProfile result = classifier.classify("Quels sont les bouquets TV sport disponibles ?", null);

        // THEN
        assertEquals("commercial", result.id());
    }

    @Test
    void classify_sticks_to_current_agent_on_follow_up() {
        // GIVEN / WHEN
        AgentProfile result = classifier.classify("ok et quoi d'autre ?", "commercial");

        // THEN
        assertEquals("commercial", result.id());
    }
}
