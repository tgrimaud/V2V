package com.voicesupport.bdd.steps;

import com.voicesupport.knowledge.domain.model.valueobject.SourceDocument;
import com.voicesupport.knowledge.domain.model.valueobject.SyncReport;
import com.voicesupport.knowledge.domain.service.KnowledgeSyncService;
import com.voicesupport.knowledge.domain.service.TextChunker;
import com.voicesupport.knowledge.fake.FakeKnowledgeSourceConnector;
import com.voicesupport.knowledge.fake.FakeKnowledgeSourceStatePort;
import com.voicesupport.knowledge.fake.FakeSyncObserver;
import com.voicesupport.knowledge.fake.FakeVectorStorePort;
import io.cucumber.java.en.Given;
import io.cucumber.java.en.Then;
import io.cucumber.java.en.When;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

// BUG-022 acceptance: a failing/slow embedding on one article must neither abort the whole sync nor
// silently drop the article. "Available to the assistant" maps to the sync ledger commit (an
// uncommitted article is re-ingested next run, so it is not reliably live until committed).
public class KnowledgeSyncResilienceSteps {

    private static final String TYPE = "markdown";

    private final FakeVectorStorePort vectorStore = new FakeVectorStorePort();
    private final FakeKnowledgeSourceStatePort statePort = new FakeKnowledgeSourceStatePort();
    private final FakeSyncObserver observer = new FakeSyncObserver();
    private final List<SourceDocument> documents = new ArrayList<>();
    private final FakeKnowledgeSourceConnector connector =
            new FakeKnowledgeSourceConnector(TYPE, documents);
    private final KnowledgeSyncService service = new KnowledgeSyncService(
            List.of(connector), statePort, vectorStore, new TextChunker(500, 50), observer);

    private SyncReport report;

    private static SourceDocument article(String id) {
        return SourceDocument.create(TYPE, id, id, null, "# " + id + "\n\nBody for " + id + ".",
                "billing", "fr", Instant.EPOCH);
    }

    @Given("a knowledge article {string} that can be fully embedded")
    public void aKnowledgeArticleThatCanBeFullyEmbedded(String id) {
        documents.add(article(id));
        connector.setDocuments(documents);
    }

    @Given("a knowledge article {string} whose embedding partially fails")
    public void aKnowledgeArticleWhoseEmbeddingPartiallyFails(String id) {
        documents.add(article(id));
        connector.setDocuments(documents);
        vectorStore.partialOnSourceId = id;
        vectorStore.partialStored = 0; // worst case: every chunk skipped (would be a silent RAG gap)
    }

    @When("article {string} can be fully embedded again")
    public void articleCanBeFullyEmbeddedAgain(String id) {
        if (id.equals(vectorStore.partialOnSourceId)) {
            vectorStore.partialOnSourceId = null;
        }
    }

    @When("the corpus is synchronized")
    public void theCorpusIsSynchronized() {
        report = service.syncAll();
    }

    @Then("the synchronization completes without aborting")
    public void theSynchronizationCompletesWithoutAborting() {
        assertNotNull(report, "sync returned a report (it did not abort/throw)");
    }

    @Then("article {string} is available to the assistant")
    public void articleIsAvailableToTheAssistant(String id) {
        assertTrue(statePort.listSourceIds(TYPE).contains(id),
                "article " + id + " is committed to the sync ledger");
    }

    @Then("article {string} is not yet available to the assistant")
    public void articleIsNotYetAvailableToTheAssistant(String id) {
        assertFalse(statePort.listSourceIds(TYPE).contains(id),
                "partially stored article " + id + " must not be committed");
    }

    @Then("the partial ingestion of article {string} is reported for operators")
    public void thePartialIngestionIsReported(String id) {
        assertTrue(observer.skips.stream().anyMatch(skip -> skip.sourceId().equals(id)),
                "a batch-skipped event was emitted for " + id);
    }
}
