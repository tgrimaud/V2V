package com.voicesupport.infrastructure.adapter.out.source;

import com.voicesupport.domain.model.SourceDocument;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class MarkdownFolderConnectorTest {

    @Test
    void shouldParseDomainFromFrontMatter(@TempDir Path dir) throws IOException {
        Files.writeString(dir.resolve("billing-faq.md"),
                "---\ndomain: billing\nlanguage: fr\n---\n\n# Facturation\n\nContenu de facturation.");
        MarkdownFolderConnector connector = new MarkdownFolderConnector(dir.toString(), "fr");

        List<SourceDocument> documents = connector.fetchAll();

        assertEquals(1, documents.size());
        SourceDocument document = documents.get(0);
        assertEquals("markdown", document.sourceType());
        assertEquals("billing-faq.md", document.sourceId());
        assertEquals("billing", document.domain());
        assertFalse(document.content().contains("domain: billing"));
        assertTrue(document.content().contains("Contenu de facturation."));
    }

    @Test
    void shouldDefaultToGeneralDomainWhenNoFrontMatter(@TempDir Path dir) throws IOException {
        Files.writeString(dir.resolve("notes.md"), "# Titre\n\nUn contenu sans front-matter.");
        MarkdownFolderConnector connector = new MarkdownFolderConnector(dir.toString(), "fr");

        List<SourceDocument> documents = connector.fetchAll();

        assertEquals("general", documents.get(0).domain());
        assertEquals("Titre", documents.get(0).title());
    }

    @Test
    void shouldReturnEmptyListWhenFolderMissing() {
        MarkdownFolderConnector connector = new MarkdownFolderConnector("/path/does/not/exist", "fr");

        assertTrue(connector.fetchAll().isEmpty());
    }

    @Test
    void shouldComputeStableHashForSameContent(@TempDir Path dir) throws IOException {
        Files.writeString(dir.resolve("a.md"), "---\ndomain: support\n---\n\n# A\n\nContenu identique.");
        MarkdownFolderConnector connector = new MarkdownFolderConnector(dir.toString(), "fr");

        String firstHash = connector.fetchAll().get(0).contentHash();
        String secondHash = connector.fetchAll().get(0).contentHash();

        assertEquals(firstHash, secondHash);
        assertNotNull(firstHash);
    }
}
