package com.voicesupport.knowledge.infrastructure.adapter.out.csv;

import com.voicesupport.knowledge.domain.model.valueobject.SourceDocument;
import com.voicesupport.knowledge.fake.FakeAudienceClassifier;
import com.voicesupport.knowledge.fake.FakeDomainClassifier;
import com.voicesupport.knowledge.infrastructure.adapter.out.classifier.KeywordAudienceClassifierAdapter;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CsvArticleConnectorTest {

    private static final String HEADER = "document_id,title,content\r\n";

    private Path writeCsv(Path dir, String body) throws IOException {
        Path file = dir.resolve("articles.csv");
        Files.writeString(file, HEADER + body, StandardCharsets.UTF_8);
        return file;
    }

    @Test
    void shouldParseCleanHtmlAndClassifyDomain(@TempDir Path dir) throws IOException {
        // GIVEN a CSV article whose content is rich HTML with an embedded newline and escaped quotes
        String row = "196,\"Help & Support\",\"<p>First paragraph &amp; more.</p>\n"
                + "<p>Second <a href=\"\"http://x\"\">link</a> para.</p>\"";
        FakeDomainClassifier classifier = new FakeDomainClassifier();
        classifier.returns = "billing";
        CsvArticleConnector connector =
                new CsvArticleConnector(writeCsv(dir, row).toString(), "en", classifier, customerAudience());

        // WHEN fetching all documents
        List<SourceDocument> docs = connector.fetchAll();

        // THEN one document is produced with cleaned text, the CSV id, language and classified domain
        assertEquals(1, docs.size());
        SourceDocument doc = docs.get(0);
        assertEquals("196", doc.sourceId());
        assertEquals("csv-article", doc.sourceType());
        assertEquals("en", doc.language());
        assertEquals("billing", doc.domain());
        assertEquals("customer", doc.audience());
        assertNotNull(doc.contentHash());
        assertTrue(doc.content().contains("First paragraph & more."));
        assertTrue(doc.content().contains("Second link para."));
        assertFalse(doc.content().contains("<p>"));
        assertFalse(doc.content().contains("href"));
        assertTrue(doc.content().contains("\n\n"));
    }

    @Test
    void shouldPassCleanedTextToTheClassifierNotRawHtml(@TempDir Path dir) throws IOException {
        // GIVEN an article with HTML markup
        String row = "42,\"Router setup\",\"<h1>Wifi</h1><p>Reset your router.</p>\"";
        FakeDomainClassifier classifier = new FakeDomainClassifier();
        CsvArticleConnector connector =
                new CsvArticleConnector(writeCsv(dir, row).toString(), "en", classifier, customerAudience());

        // WHEN fetching
        connector.fetchAll();

        // THEN the classifier received plain text, never the raw markup
        assertFalse(classifier.lastContent.contains("<"));
        assertTrue(classifier.lastContent.contains("Reset your router."));
    }

    @Test
    void shouldSkipRowsWithBlankIdOrContent(@TempDir Path dir) throws IOException {
        // GIVEN a blank id row, an empty-content row and one valid row
        String body = ",\"No id\",\"<p>body</p>\"\r\n"
                + "7,\"Empty\",\"\"\r\n"
                + "8,\"Valid\",\"<p>Kept.</p>\"\r\n";
        CsvArticleConnector connector = new CsvArticleConnector(
                writeCsv(dir, body).toString(), "en", new FakeDomainClassifier(), customerAudience());

        // WHEN fetching
        List<String> ids = connector.fetchAll().stream().map(SourceDocument::sourceId).toList();

        // THEN only the valid row survives
        assertEquals(List.of("8"), ids);
    }

    @Test
    void shouldReturnEmptyListWhenFileMissing() {
        // GIVEN a path that does not exist
        CsvArticleConnector connector = new CsvArticleConnector(
                "/no/such/articles.csv", "en", new FakeDomainClassifier(), customerAudience());

        // WHEN fetching THEN it degrades gracefully to an empty list
        assertTrue(connector.fetchAll().isEmpty());
    }

    @Test
    void shouldExposeCsvArticleSourceType() {
        // GIVEN a connector
        CsvArticleConnector connector = new CsvArticleConnector(
                "/tmp/x.csv", "en", new FakeDomainClassifier(), customerAudience());

        // WHEN/THEN the source type is stable for the sync ledger
        assertEquals("csv-article", connector.sourceType());
    }

    @Test
    void shouldTagAgentDeskArticleAsInternalAudience(@TempDir Path dir) throws IOException {
        // GIVEN an agent/back-office article that names internal tooling (BUG-005: R6/ION, VAA)
        String row = "253,\"View Available Appointments (VAA)\","
                + "\"<p>Modify the appointment in R6/ION for Back Office agents only.</p>\"";
        CsvArticleConnector connector = new CsvArticleConnector(
                writeCsv(dir, row).toString(), "en", new FakeDomainClassifier(),
                new KeywordAudienceClassifierAdapter(List.of("back office", "r6/ion", "vaa")));

        // WHEN fetching
        SourceDocument doc = connector.fetchAll().get(0);

        // THEN it is tagged internal so the fail-closed retrieval filter excludes it from customers
        assertEquals("internal", doc.audience());
    }

    @Test
    void shouldKeepCustomerArticleAsCustomerAudience(@TempDir Path dir) throws IOException {
        // GIVEN a plain customer-facing billing article with no agent-desk markers
        String row = "196,\"Why did my bill increase?\",\"<p>Your monthly bill can change after a "
                + "discount ends or you use extra data.</p>\"";
        CsvArticleConnector connector = new CsvArticleConnector(
                writeCsv(dir, row).toString(), "en", new FakeDomainClassifier(),
                new KeywordAudienceClassifierAdapter(List.of("back office", "r6/ion", "vaa")));

        // WHEN fetching THEN it stays customer-facing
        assertEquals("customer", connector.fetchAll().get(0).audience());
    }

    private FakeAudienceClassifier customerAudience() {
        return new FakeAudienceClassifier();
    }
}
