package com.voicesupport.bdd.steps;

import com.voicesupport.knowledge.domain.model.valueobject.SyncReport;
import com.voicesupport.knowledge.domain.service.KnowledgeSyncService;
import com.voicesupport.knowledge.domain.service.TextChunker;
import com.voicesupport.knowledge.fake.FakeAudienceClassifier;
import com.voicesupport.knowledge.fake.FakeDomainClassifier;
import com.voicesupport.knowledge.fake.FakeKnowledgeSourceStatePort;
import com.voicesupport.knowledge.fake.FakeSyncObserver;
import com.voicesupport.knowledge.fake.FakeVectorStorePort;
import com.voicesupport.knowledge.infrastructure.adapter.out.csv.CsvArticleConnector;
import io.cucumber.java.en.Given;
import io.cucumber.java.en.Then;
import io.cucumber.java.en.When;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class CsvKnowledgeIngestionSteps {

    private static final String HEADER = "document_id,title,content\r\n";

    private final FakeVectorStorePort vectorStore = new FakeVectorStorePort();
    private final FakeKnowledgeSourceStatePort statePort = new FakeKnowledgeSourceStatePort();
    private final FakeDomainClassifier classifier = new FakeDomainClassifier();
    private final FakeAudienceClassifier audienceClassifier = new FakeAudienceClassifier();
    private final Path csvFile = createCsvFile();
    private final CsvArticleConnector connector =
            new CsvArticleConnector(csvFile.toString(), "en", classifier, audienceClassifier);
    private final KnowledgeSyncService service =
            new KnowledgeSyncService(
                    List.of(connector), statePort, vectorStore, new TextChunker(500, 50), new FakeSyncObserver());

    private SyncReport report;

    private static Path createCsvFile() {
        try {
            Path file = Files.createTempFile("qa-articles", ".csv");
            Files.writeString(file, HEADER, StandardCharsets.UTF_8);
            return file;
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    private void appendRow(String id, String title, String content) {
        String line = id + "," + quote(title) + "," + quote(content) + "\r\n";
        try {
            Files.writeString(csvFile, line, StandardCharsets.UTF_8, StandardOpenOption.APPEND);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    private String quote(String value) {
        return "\"" + value.replace("\"", "\"\"") + "\"";
    }

    @Given("an operator CSV article {string} classified as {string} with HTML content:")
    public void anOperatorCsvArticleClassifiedAs(String id, String domain, String html) {
        classifier.returns = domain;
        appendRow(id, "Article " + id, html);
    }

    @Given("an operator CSV corpus with a blank-id row, an empty-content row and one valid row")
    public void anOperatorCsvCorpusWithBlankAndValidRows() {
        appendRow("", "No id", "<p>orphan</p>");
        appendRow("7", "Empty", "");
        appendRow("8", "Valid", "<p>Kept.</p>");
    }

    @Given("the operator knowledge base has already been synchronized")
    public void theOperatorKnowledgeBaseHasAlreadyBeenSynchronized() {
        service.syncAll();
    }

    @When("the operator knowledge base is synchronized")
    public void theOperatorKnowledgeBaseIsSynchronized() {
        report = service.syncAll();
    }

    @Then("the article is ingested under the {string} source")
    public void theArticleIsIngestedUnderTheSource(String sourceType) {
        assertTrue(vectorStore.storedChunks.stream().anyMatch(chunk -> chunk.startsWith(sourceType + "/")));
    }

    @Then("the stored content is plain text without HTML tags")
    public void theStoredContentIsPlainTextWithoutHtmlTags() {
        assertFalse(vectorStore.storedChunkContents.isEmpty());
        assertTrue(vectorStore.storedChunkContents.stream().noneMatch(content -> content.contains("<")));
    }

    @Then("the stored operator content carries the {string} domain")
    public void theStoredOperatorContentCarriesTheDomain(String domain) {
        assertFalse(vectorStore.storedChunkDomains.isEmpty());
        assertTrue(vectorStore.storedChunkDomains.stream().allMatch(domain::equals));
    }

    @Then("no operator article is ingested")
    public void noOperatorArticleIsIngested() {
        assertEquals(0, report.ingested());
    }

    @Then("{int} operator article is ingested")
    public void operatorArticlesAreIngested(int expected) {
        assertEquals(expected, report.ingested());
    }
}
