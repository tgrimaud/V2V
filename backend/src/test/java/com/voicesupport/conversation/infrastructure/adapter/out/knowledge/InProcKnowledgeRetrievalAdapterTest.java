package com.voicesupport.conversation.infrastructure.adapter.out.knowledge;

import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.fake.FakeKnowledgeRetrievalUseCase;
import com.voicesupport.knowledge.domain.model.valueobject.KnowledgeChunk;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

@DisplayName("InProc knowledge retrieval seam (ACL)")
class InProcKnowledgeRetrievalAdapterTest {

    @Test
    @DisplayName("maps knowledge chunks to conversation evidence through the ACL")
    void mapsChunksToEvidence() {
        // GIVEN a knowledge use case returning two chunks
        var fake = new FakeKnowledgeRetrievalUseCase();
        fake.setChunks(List.of(
                new KnowledgeChunk("proration explained", "billing-faq#1", "billing", 0.82),
                new KnowledgeChunk("late fee explained", "billing-faq#2", "billing", 0.71)));
        var adapter = new InProcKnowledgeRetrievalAdapter(fake);

        // WHEN the conversation context retrieves through the seam
        List<RetrievedEvidence> evidence = adapter.retrieve("why is my bill higher", "billing", 5);

        // THEN chunks are translated into the conversation domain model
        assertEquals(2, evidence.size());
        assertEquals("proration explained", evidence.get(0).text());
        assertEquals("billing-faq#1", evidence.get(0).sourceId());
        assertEquals("billing", evidence.get(0).domain());
        assertEquals(0.82, evidence.get(0).score());
    }

    @Test
    @DisplayName("honors the requested top-k limit")
    void honorsTopK() {
        // GIVEN three available chunks
        var fake = new FakeKnowledgeRetrievalUseCase();
        fake.setChunks(List.of(
                new KnowledgeChunk("a", "s1", "general", 0.9),
                new KnowledgeChunk("b", "s2", "general", 0.8),
                new KnowledgeChunk("c", "s3", "general", 0.7)));
        var adapter = new InProcKnowledgeRetrievalAdapter(fake);

        // WHEN retrieving with topK = 2
        List<RetrievedEvidence> evidence = adapter.retrieve("q", "general", 2);

        // THEN only two evidence items are returned
        assertEquals(2, evidence.size());
    }
}
