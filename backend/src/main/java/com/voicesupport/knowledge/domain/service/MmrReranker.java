package com.voicesupport.knowledge.domain.service;

import com.voicesupport.knowledge.domain.model.valueobject.KnowledgeChunk;

import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

// Maximal Marginal Relevance (TASK-BE-028, BUG-003): greedy re-selection over the over-fetched
// dense candidates that balances query relevance against redundancy, so near-duplicate header /
// fragment chunks stop evicting the answer-bearing chunk from the final top-K. Relevance is the
// dense similarity score already carried by each chunk; redundancy is a store-independent lexical
// (Jaccard token-set) proxy, because the vector store does not return candidate embeddings — the
// proxy catches the observed failure (identical/near-identical fragments crowding the top-K)
// without a second embedding round-trip. Pure domain, deterministic, unit-testable with no store.
public class MmrReranker {

    private final double lambda;

    // lambda in [0,1]: 1 = pure relevance (no diversity), 0 = pure diversity. Clamped defensively.
    public MmrReranker(double lambda) {
        this.lambda = Math.max(0.0, Math.min(1.0, lambda));
    }

    public double lambda() {
        return lambda;
    }

    // Greedy MMR: pick the most relevant candidate first (empty selection → redundancy 0), then
    // iteratively the candidate maximizing lambda*relevance - (1-lambda)*maxSimToSelected, until
    // topK are chosen or candidates run out. The single most relevant chunk is always selected
    // first, so the best evidence score seen by the confidence guardrail is preserved.
    public List<KnowledgeChunk> rerank(List<KnowledgeChunk> candidates, int topK) {
        if (candidates == null || topK <= 0) {
            return List.of();
        }
        if (candidates.size() <= 1) {
            return List.copyOf(candidates);
        }
        List<KnowledgeChunk> remaining = new ArrayList<>(candidates);
        List<Set<String>> tokens = new ArrayList<>(remaining.stream().map(c -> tokenize(c.text())).toList());
        List<KnowledgeChunk> selected = new ArrayList<>();
        List<Set<String>> selectedTokens = new ArrayList<>();
        int limit = Math.min(topK, remaining.size());
        while (selected.size() < limit) {
            int best = bestCandidate(remaining, tokens, selectedTokens);
            selected.add(remaining.remove(best));
            selectedTokens.add(tokens.remove(best));
        }
        return List.copyOf(selected);
    }

    private int bestCandidate(List<KnowledgeChunk> remaining, List<Set<String>> tokens, List<Set<String>> selected) {
        int best = 0;
        double bestScore = -Double.MAX_VALUE;
        for (int i = 0; i < remaining.size(); i++) {
            double score = lambda * remaining.get(i).score() - (1.0 - lambda) * maxSimilarity(tokens.get(i), selected);
            if (score > bestScore) {
                bestScore = score;
                best = i;
            }
        }
        return best;
    }

    private static double maxSimilarity(Set<String> candidate, List<Set<String>> selected) {
        double max = 0.0;
        for (Set<String> chosen : selected) {
            max = Math.max(max, jaccard(candidate, chosen));
        }
        return max;
    }

    private static double jaccard(Set<String> a, Set<String> b) {
        if (a.isEmpty() || b.isEmpty()) {
            return 0.0;
        }
        long intersection = a.stream().filter(b::contains).count();
        long union = a.size() + b.size() - intersection;
        return union == 0 ? 0.0 : (double) intersection / union;
    }

    private static Set<String> tokenize(String text) {
        if (text == null || text.isBlank()) {
            return Set.of();
        }
        String folded = Normalizer.normalize(text.toLowerCase(Locale.ROOT), Normalizer.Form.NFD)
                .replaceAll("\\p{M}+", "");
        String[] words = folded.replaceAll("[^a-z0-9]+", " ").strip().split(" ");
        Set<String> tokens = new HashSet<>();
        for (String word : words) {
            if (!word.isBlank()) {
                tokens.add(word);
            }
        }
        return tokens;
    }
}
