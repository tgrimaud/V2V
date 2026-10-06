package com.voicesupport.knowledge.infrastructure.adapter.out.markdown;

import com.voicesupport.knowledge.domain.model.valueobject.SourceDocument;
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

class MarkdownFolderConnectorTest {

    private static void write(Path dir, String name, String content) throws IOException {
        Files.writeString(dir.resolve(name), content, StandardCharsets.UTF_8);
    }

    @Test
    void shouldReadDomainFromFrontMatterAndStripIt(@TempDir Path dir) throws IOException {
        // GIVEN a markdown file with YAML front-matter declaring a domain
        write(dir, "billing-faq.md", "---\ndomain: billing\nlanguage: fr\n---\n\n# Billing\n\nBody text.");
        MarkdownFolderConnector connector = new MarkdownFolderConnector(dir.toString(), "fr");

        // WHEN fetching all documents
        List<SourceDocument> docs = connector.fetchAll();

        // THEN the domain comes from the front-matter and the body excludes it
        assertEquals(1, docs.size());
        SourceDocument doc = docs.get(0);
        assertEquals("billing", doc.domain());
        assertEquals("billing-faq.md", doc.sourceId());
        assertEquals("markdown", doc.sourceType());
        assertFalse(doc.content().contains("domain: billing"));
        assertTrue(doc.content().contains("Body text."));
        assertNotNull(doc.contentHash());
    }

    @Test
    void shouldDefaultDomainToGeneralWhenFrontMatterAbsent(@TempDir Path dir) throws IOException {
        // GIVEN a markdown file without front-matter
        write(dir, "notes.md", "# Notes\n\nNo front matter here.");
        MarkdownFolderConnector connector = new MarkdownFolderConnector(dir.toString(), "fr");

        // WHEN fetching
        SourceDocument doc = connector.fetchAll().get(0);

        // THEN the domain falls back to "general"
        assertEquals("general", doc.domain());
    }

    @Test
    void shouldIgnoreNonMarkdownFilesAndSortByName(@TempDir Path dir) throws IOException {
        // GIVEN a folder mixing markdown and non-markdown files
        write(dir, "b.md", "# B\n\nBeta.");
        write(dir, "a.md", "# A\n\nAlpha.");
        write(dir, "ignore.txt", "not markdown");
        MarkdownFolderConnector connector = new MarkdownFolderConnector(dir.toString(), "fr");

        // WHEN fetching
        List<String> ids = connector.fetchAll().stream().map(SourceDocument::sourceId).toList();

        // THEN only markdown files are returned, ordered by name
        assertEquals(List.of("a.md", "b.md"), ids);
    }

    @Test
    void shouldReturnEmptyListWhenFolderMissing() {
        // GIVEN a path that does not exist
        MarkdownFolderConnector connector = new MarkdownFolderConnector("/no/such/kb/folder", "fr");

        // WHEN fetching THEN it degrades gracefully to an empty list
        assertTrue(connector.fetchAll().isEmpty());
    }

    @Test
    void shouldReadAudienceLanguageAndUrlFromFrontMatter(@TempDir Path dir) throws IOException {
        // GIVEN a file declaring audience, language and url (TASK-BE-069 unified canonical format)
        write(dir, "a.md", "---\ndomain: support\nlanguage: en\naudience: internal\n"
                + "url: https://www.eir.ie/x\n---\n\n# A\n\nBody.");
        MarkdownFolderConnector connector = new MarkdownFolderConnector(dir.toString(), "fr");

        // WHEN fetching
        SourceDocument doc = connector.fetchAll().get(0);

        // THEN audience/language/url come from the front-matter (language overrides the default)
        assertEquals("internal", doc.audience());
        assertEquals("en", doc.language());
        assertEquals("https://www.eir.ie/x", doc.url());
    }

    @Test
    void shouldDefaultAudienceToCustomerAndLanguageToConnectorDefault(@TempDir Path dir) throws IOException {
        // GIVEN a file with no audience/language front-matter (the hand-written KB case)
        write(dir, "a.md", "---\ndomain: billing\n---\n\n# A\n\nBody.");
        MarkdownFolderConnector connector = new MarkdownFolderConnector(dir.toString(), "fr");

        // WHEN fetching
        SourceDocument doc = connector.fetchAll().get(0);

        // THEN audience falls back to customer (ADR-0034) and language to the connector default
        assertEquals("customer", doc.audience());
        assertEquals("fr", doc.language());
    }

    @Test
    void shouldRecurseIntoSubfoldersWithRelativePathSourceId(@TempDir Path dir) throws IOException {
        // GIVEN a file at the root and one in a sub-corpus folder (knowledge-base/eir/)
        write(dir, "root.md", "# Root\n\nR.");
        Path sub = dir.resolve("eir");
        Files.createDirectories(sub);
        write(sub, "x.md", "---\ndomain: support\nlanguage: en\n---\n\n# X\n\nBody.");
        MarkdownFolderConnector connector = new MarkdownFolderConnector(dir.toString(), "fr");

        // WHEN fetching
        List<String> ids = connector.fetchAll().stream().map(SourceDocument::sourceId).toList();

        // THEN the sub-folder file is included with a folder-relative source_id (no collision)
        assertTrue(ids.contains("root.md"));
        assertTrue(ids.contains(Path.of("eir", "x.md").toString()));
    }
}
