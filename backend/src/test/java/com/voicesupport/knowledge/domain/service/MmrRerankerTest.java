package com.voicesupport.knowledge.domain.service;

import com.voicesupport.knowledge.domain.model.valueobject.KnowledgeChunk;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DisplayName("MmrReranker (relevance vs redundancy diversity re-ranking)")
class MmrRerankerTest {

    private static KnowledgeChunk chunk(String id, String text, double score) {
        return new KnowledgeChunk(text, id, "support", score);
    }

    private List<String> ids(List<KnowledgeChunk> chunks) {
        return chunks.stream().map(KnowledgeChunk::sourceId).toList();
    }

    @Test
    @DisplayName("keeps the answer chunk that plain top-k would evict behind near-duplicate headers")
    void retainsAnswerChunkOverNearDuplicates() {
        // GIVEN three near-identical high-score header chunks and one distinct, slightly lower-score
        // answer chunk — plain top-2 by score would keep two headers and evict the answer (BUG-003)
        MmrReranker reranker = new MmrReranker(0.7);
        List<KnowledgeChunk> candidates = List.of(
                chunk("h1", "internet help internet help internet help", 0.82),
                chunk("h2", "internet help internet help internet help now", 0.81),
                chunk("h3", "internet help internet help internet help today", 0.805),
                chunk("ans", "reset your router by holding the power button to fix a slow connection", 0.80));

        // WHEN selecting the top-2 with MMR
        List<KnowledgeChunk> selected = reranker.rerank(candidates, 2);

        // THEN the distinct answer chunk survives instead of a second redundant header
        assertEquals(2, selected.size());
        assertTrue(ids(selected).contains("ans"), "answer chunk must be retained, got " + ids(selected));
    }

    @Test
    @DisplayName("always selects the single most relevant chunk first (preserves best evidence score)")
    void selectsMostRelevantFirst() {
        // GIVEN candidates in non-score order
        MmrReranker reranker = new MmrReranker(0.7);
        List<KnowledgeChunk> candidates = List.of(
                chunk("low", "some other topic entirely different words", 0.40),
                chunk("top", "the most relevant unique passage about billing", 0.91),
                chunk("mid", "another distinct passage about payments", 0.60));

        // WHEN re-ranking
        List<KnowledgeChunk> selected = reranker.rerank(candidates, 3);

        // THEN the highest-score chunk is selected first, so the confidence guardrail's best score holds
        assertEquals("top", selected.get(0).sourceId());
    }

    @Test
    @DisplayName("down-ranks an exact duplicate in favor of a distinct lower-score chunk")
    void downRanksExactDuplicate() {
        // GIVEN an exact duplicate of the top chunk plus a distinct chunk
        MmrReranker reranker = new MmrReranker(0.5);
        List<KnowledgeChunk> candidates = List.of(
                chunk("a", "wifi keeps dropping every few minutes on all devices", 0.90),
                chunk("a-dup", "wifi keeps dropping every few minutes on all devices", 0.89),
                chunk("b", "change the channel in the router admin page to reduce interference", 0.70));

        // WHEN selecting top-2
        List<KnowledgeChunk> selected = reranker.rerank(candidates, 2);

        // THEN the duplicate is dropped and the distinct chunk is kept
        assertEquals(List.of("a", "b"), ids(selected));
        assertFalse(ids(selected).contains("a-dup"));
    }

    @Test
    @DisplayName("returns all candidates (re-ordered) when top-k >= candidate count")
    void returnsAllWhenTopKExceedsSize() {
        MmrReranker reranker = new MmrReranker(0.7);
        List<KnowledgeChunk> candidates = List.of(
                chunk("a", "alpha unique text", 0.5),
                chunk("b", "beta different text", 0.9));

        List<KnowledgeChunk> selected = reranker.rerank(candidates, 10);

        assertEquals(2, selected.size());
        assertTrue(ids(selected).containsAll(List.of("a", "b")));
    }

    @Test
    @DisplayName("handles empty, single and non-positive top-k defensively")
    void handlesEdgeCases() {
        MmrReranker reranker = new MmrReranker(0.7);
        KnowledgeChunk one = chunk("a", "only one", 0.5);

        assertTrue(reranker.rerank(List.of(), 5).isEmpty());
        assertTrue(reranker.rerank(null, 5).isEmpty());
        assertTrue(reranker.rerank(List.of(one), 0).isEmpty());
        assertEquals(List.of("a"), ids(reranker.rerank(List.of(one), 3)));
    }

    @Test
    @DisplayName("clamps lambda into [0,1]")
    void clampsLambda() {
        assertEquals(1.0, new MmrReranker(2.5).lambda());
        assertEquals(0.0, new MmrReranker(-1.0).lambda());
        assertEquals(0.7, new MmrReranker(0.7).lambda());
    }
}
