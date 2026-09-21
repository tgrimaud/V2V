package com.voicesupport.conversation.domain.service;

import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DisplayName("EvidenceContextTrimmer (prefill reduction, TASK-BE-033 lever 2)")
class EvidenceContextTrimmerTest {

    @Test
    @DisplayName("disabled by default (both budgets <= 0) returns the same list unchanged")
    void disabledIsIdentity() {
        // GIVEN a disabled trimmer and some evidence
        EvidenceContextTrimmer trimmer = EvidenceContextTrimmer.disabled();
        List<RetrievedEvidence> evidence = List.of(
                new RetrievedEvidence("some long passage that would otherwise be trimmed", "s1", "billing", 0.9));

        // WHEN trimming
        List<RetrievedEvidence> result = trimmer.trim(evidence);

        // THEN it is a no-op (same reference) and reports disabled
        assertFalse(trimmer.enabled());
        assertSame(evidence, result);
    }

    @Test
    @DisplayName("per-passage cap truncates on the last sentence boundary within the cap")
    void perPassageCapPrefersSentenceBoundary() {
        // GIVEN a per-passage cap of 30 chars
        EvidenceContextTrimmer trimmer = new EvidenceContextTrimmer(30, 0);
        List<RetrievedEvidence> evidence = List.of(new RetrievedEvidence(
                "First sentence. Second sentence that is quite long here.", "s1", "billing", 0.9));

        // WHEN trimming
        RetrievedEvidence out = trimmer.trim(evidence).get(0);

        // THEN it is cut just after the first sentence terminator, metadata preserved
        assertEquals("First sentence.", out.text());
        assertEquals("s1", out.sourceId());
        assertEquals("billing", out.domain());
        assertEquals(0.9, out.score());
    }

    @Test
    @DisplayName("per-passage cap falls back to a word boundary when no sentence terminator fits")
    void perPassageCapFallsBackToWordBoundary() {
        // GIVEN a small cap and a passage with no early sentence terminator
        EvidenceContextTrimmer trimmer = new EvidenceContextTrimmer(12, 0);
        List<RetrievedEvidence> evidence = List.of(
                new RetrievedEvidence("alpha beta gamma delta epsilon", "s1", "support", 0.7));

        // WHEN trimming
        RetrievedEvidence out = trimmer.trim(evidence).get(0);

        // THEN it never cuts mid-word (stops at the last whole word within the cap)
        assertEquals("alpha beta", out.text());
        assertTrue(out.text().length() <= 12);
    }

    @Test
    @DisplayName("a passage shorter than the cap is left unchanged")
    void shortPassageUnchanged() {
        // GIVEN a cap larger than the passage
        EvidenceContextTrimmer trimmer = new EvidenceContextTrimmer(200, 0);
        List<RetrievedEvidence> evidence = List.of(new RetrievedEvidence("short answer", "s1", "billing", 0.8));

        // WHEN trimming
        RetrievedEvidence out = trimmer.trim(evidence).get(0);

        // THEN the text is untouched
        assertEquals("short answer", out.text());
    }

    @Test
    @DisplayName("total context budget caps the sum and drops lower-ranked passages once exhausted")
    void totalBudgetDropsTail() {
        // GIVEN only a total-context budget of 18 chars
        EvidenceContextTrimmer trimmer = new EvidenceContextTrimmer(0, 18);
        List<RetrievedEvidence> evidence = List.of(
                new RetrievedEvidence("one two three four", "s1", "billing", 0.9),   // exactly 18 chars
                new RetrievedEvidence("this second passage should be dropped", "s2", "billing", 0.8));

        // WHEN trimming
        List<RetrievedEvidence> out = trimmer.trim(evidence);

        // THEN the budget is spent on the top-ranked passage and the tail is dropped
        assertEquals(1, out.size());
        assertEquals("one two three four", out.get(0).text());
        assertEquals("s1", out.get(0).sourceId());
    }

    @Test
    @DisplayName("null and empty inputs are returned as-is")
    void nullAndEmptyPassThrough() {
        // GIVEN an enabled trimmer
        EvidenceContextTrimmer trimmer = new EvidenceContextTrimmer(10, 0);

        // WHEN/THEN null and empty are handled without error
        assertSame(null, trimmer.trim(null));
        List<RetrievedEvidence> empty = List.of();
        assertSame(empty, trimmer.trim(empty));
    }
}
