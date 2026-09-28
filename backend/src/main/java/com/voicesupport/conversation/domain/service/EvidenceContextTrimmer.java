package com.voicesupport.conversation.domain.service;

import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;

import java.util.ArrayList;
import java.util.List;

// Latency lever B / prefill reduction (TASK-BE-033, lever 2): caps how much retrieved KB text is
// fed to the LLM so the prompt prefill (a ~linear driver of time-to-first-token) shrinks. The
// trimmed evidence is used by BOTH the LLM prompt and the per-sentence OutputGuardrail (same list
// in the streaming/sync pipeline), so the DEC-002 "no amount outside the CONTEXT" property stays
// consistent — the model can only cite what it was shown, and the guardrail vets against the same
// text. The only trade-off is grounding RECALL (an answer living in a trimmed-off tail), which the
// benchmark measures. Truncation prefers a sentence boundary, then a word boundary, never mid-word.
// Disabled by default (both budgets <= 0 => identity), so behaviour is unchanged until tuned.
public class EvidenceContextTrimmer {

    private final int maxCharsPerPassage;
    private final int maxTotalChars;

    public EvidenceContextTrimmer(int maxCharsPerPassage, int maxTotalChars) {
        this.maxCharsPerPassage = maxCharsPerPassage;
        this.maxTotalChars = maxTotalChars;
    }

    // Convenience no-op instance for callers that do not tune the context budget (tests, sync
    // fixtures). Keeps trimming an explicit, opt-in production concern.
    public static EvidenceContextTrimmer disabled() {
        return new EvidenceContextTrimmer(0, 0);
    }

    public boolean enabled() {
        return maxCharsPerPassage > 0 || maxTotalChars > 0;
    }

    // Returns a trimmed copy (per-passage cap and/or a cumulative total-context budget); passages
    // keep their original order (retrieval relevance) and their sourceId/domain/score. Once the
    // total budget is exhausted the remaining lower-ranked passages are dropped.
    public List<RetrievedEvidence> trim(List<RetrievedEvidence> evidence) {
        if (evidence == null || evidence.isEmpty() || !enabled()) {
            return evidence;
        }
        List<RetrievedEvidence> out = new ArrayList<>(evidence.size());
        int remaining = maxTotalChars > 0 ? maxTotalChars : Integer.MAX_VALUE;
        for (RetrievedEvidence e : evidence) {
            if (remaining <= 0) {
                break;
            }
            String trimmed = truncateAtBoundary(e.text(), passageCap(remaining));
            out.add(new RetrievedEvidence(trimmed, e.sourceId(), e.domain(), e.score()));
            remaining -= trimmed.length();
        }
        return out;
    }

    private int passageCap(int remaining) {
        return maxCharsPerPassage > 0 ? Math.min(maxCharsPerPassage, remaining) : remaining;
    }

    private static String truncateAtBoundary(String text, int cap) {
        if (text == null) {
            return "";
        }
        if (text.length() <= cap) {
            return text;
        }
        String slice = text.substring(0, cap);
        int cut = lastBoundary(slice);
        if (cut > 0) {
            slice = slice.substring(0, cut);
        }
        return slice.strip();
    }

    // Last sentence terminator (inclusive) within the slice, else the last word boundary, else -1
    // (caller keeps the hard cap). Avoids feeding a half-word to the model.
    private static int lastBoundary(String slice) {
        int sentence = lastIndexOfAny(slice, ".!?\n");
        if (sentence >= 0) {
            return sentence + 1;
        }
        return slice.lastIndexOf(' ');
    }

    private static int lastIndexOfAny(String slice, String terminators) {
        int last = -1;
        for (int i = 0; i < slice.length(); i++) {
            if (terminators.indexOf(slice.charAt(i)) >= 0) {
                last = i;
            }
        }
        return last;
    }
}
