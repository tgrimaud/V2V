package com.voicesupport.knowledge.infrastructure.adapter.out.csv;

import com.voicesupport.knowledge.domain.model.valueobject.SourceDocument;
import com.voicesupport.knowledge.domain.port.out.AudienceClassifierPort;
import com.voicesupport.knowledge.domain.port.out.DomainClassifierPort;
import com.voicesupport.knowledge.domain.port.out.KnowledgeSourceConnector;
import org.apache.commons.csv.CSVFormat;
import org.apache.commons.csv.CSVParser;
import org.apache.commons.csv.CSVRecord;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.io.Reader;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

// ADR-0030: ingests articles.csv (document_id,title,content with rich HTML). commons-csv
// handles the RFC-4180 fields (embedded newlines + escaped quotes); jsoup converts HTML to
// clean text before chunking/embedding; DomainClassifier assigns the (missing) domain.
public class CsvArticleConnector implements KnowledgeSourceConnector {

    public static final String SOURCE_TYPE = "csv-article";

    private static final Logger log = LoggerFactory.getLogger(CsvArticleConnector.class);
    private static final String COL_ID = "document_id";
    private static final String COL_TITLE = "title";
    private static final String COL_CONTENT = "content";
    private static final String INTERNAL_AUDIENCE = "internal";
    private static final String BLOCK_SELECTOR =
            "p, div, li, h1, h2, h3, h4, h5, h6, tr, blockquote, section, article";

    private final Path csvPath;
    private final String defaultLanguage;
    private final String sourceType;
    private final DomainClassifierPort domainClassifier;
    private final AudienceClassifierPort audienceClassifier;

    public CsvArticleConnector(
            String csvPath, String defaultLanguage,
            DomainClassifierPort domainClassifier, AudienceClassifierPort audienceClassifier) {
        this(csvPath, defaultLanguage, SOURCE_TYPE, domainClassifier, audienceClassifier);
    }

    // A parameterized source_type lets a second instance ingest a translated copy of the same
    // corpus (e.g. "csv-article-fr") without a source_id collision, since the idempotent sync
    // keys on (source_type, source_id) (TASK-BE-017).
    public CsvArticleConnector(
            String csvPath, String defaultLanguage, String sourceType,
            DomainClassifierPort domainClassifier, AudienceClassifierPort audienceClassifier) {
        this.csvPath = Path.of(csvPath);
        this.defaultLanguage = defaultLanguage;
        this.sourceType = sourceType;
        this.domainClassifier = domainClassifier;
        this.audienceClassifier = audienceClassifier;
    }

    @Override
    public String sourceType() {
        return sourceType;
    }

    @Override
    public List<SourceDocument> fetchAll() {
        if (!Files.isRegularFile(csvPath)) {
            log.warn("[KB-SYNC] csv article file not found: {}", csvPath.toAbsolutePath());
            return List.of();
        }
        try (Reader reader = Files.newBufferedReader(csvPath, StandardCharsets.UTF_8);
             CSVParser parser = csvFormat().parse(reader)) {
            return parseRecords(parser);
        } catch (IOException e) {
            throw new UncheckedIOException("Failed to read csv article file " + csvPath, e);
        }
    }

    private CSVFormat csvFormat() {
        return CSVFormat.DEFAULT.builder()
                .setHeader()
                .setSkipHeaderRecord(true)
                .setIgnoreSurroundingSpaces(true)
                .get();
    }

    private List<SourceDocument> parseRecords(CSVParser parser) {
        List<SourceDocument> documents = new ArrayList<>();
        for (CSVRecord record : parser) {
            SourceDocument document = toDocument(record);
            if (document != null) {
                documents.add(document);
            }
        }
        return documents;
    }

    private SourceDocument toDocument(CSVRecord record) {
        String sourceId = value(record, COL_ID);
        if (sourceId == null || sourceId.isBlank()) {
            log.warn("[KB-SYNC] skipping csv article with blank {} at line {}", COL_ID, record.getRecordNumber());
            return null;
        }
        String title = value(record, COL_TITLE);
        String content = htmlToText(value(record, COL_CONTENT));
        if (content.isBlank()) {
            return null;
        }
        String domain = domainClassifier.classify(title, content);
        String audience = audienceClassifier.classify(title, content);
        logAudience(sourceId, title, audience);
        return SourceDocument.create(
                sourceType, sourceId, title, null, content, domain, audience, defaultLanguage, Instant.now());
    }

    // ADR-0034/BUG-005: make the internal partition visible after a sync so the audience boundary
    // is auditable (how many agent-desk articles are excluded from the customer answer engine).
    private void logAudience(String sourceId, String title, String audience) {
        if (INTERNAL_AUDIENCE.equals(audience)) {
            log.info("[KB-SYNC] audience=internal source_type={} source_id={} title={}",
                    sourceType, sourceId, title);
        }
    }

    private String value(CSVRecord record, String column) {
        return record.isMapped(column) ? record.get(column) : null;
    }

    private String htmlToText(String html) {
        if (html == null || html.isBlank()) {
            return "";
        }
        Document doc = Jsoup.parse(html);
        doc.outputSettings().prettyPrint(false);
        doc.select("script, style").remove();
        doc.select("br").after("\\n");
        doc.select(BLOCK_SELECTOR).after("\\n\\n");
        return doc.text().replace("\\n", "\n").strip();
    }
}
