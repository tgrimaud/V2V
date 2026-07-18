package com.voicesupport.bdd.steps;

import com.voicesupport.knowledge.domain.model.valueobject.SourceDocument;
import com.voicesupport.knowledge.domain.model.valueobject.SyncReport;
import com.voicesupport.knowledge.domain.service.KnowledgeSyncService;
import com.voicesupport.knowledge.domain.service.TextChunker;
import com.voicesupport.knowledge.fake.FakeKnowledgeSourceConnector;
import com.voicesupport.knowledge.fake.FakeKnowledgeSourceStatePort;
import com.voicesupport.knowledge.fake.FakeVectorStorePort;
import io.cucumber.java.en.Given;
import io.cucumber.java.en.Then;
import io.cucumber.java.en.When;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class KnowledgeIngestionSteps {

    private static final String TYPE = "markdown";

    private final FakeVectorStorePort vectorStore = new FakeVectorStorePort();
    private final FakeKnowledgeSourceStatePort statePort = new FakeKnowledgeSourceStatePort();
    private final FakeKnowledgeSourceConnector connector =
            new FakeKnowledgeSourceConnector(TYPE, new ArrayList<>());
    private final KnowledgeSyncService service =
            new KnowledgeSyncService(List.of(connector), statePort, vectorStore, new TextChunker(500, 50));

    private SyncReport report;

    private static SourceDocument article(String id, String body, String domain) {
        return SourceDocument.create(TYPE, id, id, null, body, domain, "fr", Instant.EPOCH);
    }

    @Given("an empty knowledge base")
    public void anEmptyKnowledgeBase() {
        connector.setDocuments(new ArrayList<>());
    }

    @Given("the source provides {int} articles")
    public void theSourceProvidesArticles(int count) {
        List<SourceDocument> docs = new ArrayList<>();
        String[] ids = {"a.md", "b.md", "c.md", "d.md", "e.md"};
        for (int i = 0; i < count; i++) {
            docs.add(article(ids[i], "# Article " + i + "\n\nBody " + i + ".", "billing"));
        }
        connector.setDocuments(docs);
    }

    @Given("the source provides an article with no domain tag")
    public void theSourceProvidesAnArticleWithNoDomainTag() {
        connector.setDocuments(List.of(article("untagged.md", "# Untagged\n\nBody.", null)));
    }

    @Given("the knowledge base has already been synchronized")
    public void theKnowledgeBaseHasAlreadyBeenSynchronized() {
        service.syncAll();
    }

    @When("the knowledge base is synchronized")
    public void theKnowledgeBaseIsSynchronized() {
        report = service.syncAll();
    }

    @When("article {string} is edited and the knowledge base is synchronized")
    public void articleIsEditedAndSynchronized(String id) {
        connector.setDocuments(List.of(article(id, "# Edited\n\nRevised body for " + id + ".", "billing")));
        report = service.syncAll();
    }

    @When("article {string} is removed from the source and the knowledge base is synchronized")
    public void articleIsRemovedAndSynchronized(String removedId) {
        List<SourceDocument> remaining = new ArrayList<>();
        for (SourceDocument doc : connector.fetchAll()) {
            if (!doc.sourceId().equals(removedId)) {
                remaining.add(doc);
            }
        }
        connector.setDocuments(remaining);
        report = service.syncAll();
    }

    @Then("{int} articles are ingested")
    public void articlesAreIngested(int expected) {
        assertEquals(expected, report.ingested());
    }

    @Then("{int} article is ingested")
    public void articleIsIngested(int expected) {
        assertEquals(expected, report.ingested());
    }

    @Then("{int} articles are skipped")
    public void articlesAreSkipped(int expected) {
        assertEquals(expected, report.skipped());
    }

    @Then("{int} article is deleted")
    public void articleIsDeleted(int expected) {
        assertEquals(expected, report.deleted());
    }

    @Then("the previous content of {string} is removed before re-ingestion")
    public void previousContentIsRemovedBeforeReingestion(String id) {
        assertTrue(vectorStore.deletedSources.contains(TYPE + "/" + id));
    }

    @Then("{string} is no longer present in the knowledge base")
    public void isNoLongerPresent(String id) {
        assertFalse(statePort.listSourceIds(TYPE).contains(id));
        assertTrue(vectorStore.deletedSources.contains(TYPE + "/" + id));
    }

    @Then("the stored content carries the {string} domain")
    public void theStoredContentCarriesTheDomain(String domain) {
        assertFalse(vectorStore.storedChunkDomains.isEmpty());
        assertTrue(vectorStore.storedChunkDomains.stream().allMatch(domain::equals));
    }
}
