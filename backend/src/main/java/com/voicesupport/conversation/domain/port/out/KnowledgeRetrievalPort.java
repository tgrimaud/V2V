package com.voicesupport.conversation.domain.port.out;

import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import java.util.List;

public interface KnowledgeRetrievalPort {

    List<RetrievedEvidence> retrieve(String query, String domain, int topK);
}
