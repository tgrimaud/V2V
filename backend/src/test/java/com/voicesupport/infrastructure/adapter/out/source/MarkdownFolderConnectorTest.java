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
    void fetch_all_parses_domain_from_front_matter(@TempDir Path dir) throws IOException {
        // GIVEN
        Files.writeString(dir.resolve("billing-faq.md"),
                "---\ndomain: billing\nlanguage: fr\n---\n\n# Facturation\n\nContenu de facturation.");
        MarkdownFolderConnector connector = new MarkdownFolderConnector(dir.toString(), "fr");

        // WHEN
        List<SourceDocument> documents = connector.fetchAll();

        // THEN
        assertEquals(1, documents.size());
        SourceDocument document = documents.get(0);
        assertEquals("markdown", document.sourceType());
        assertEquals("billing-faq.md", document.sourceId());
        assertEquals("billing", document.domain());
        assertFalse(document.content().contains("domain: billing"));
        assertTrue(document.content().contains("Contenu de facturation."));
    }

    @Test
    void fetch_all_defaults_to_general_domain_when_no_front_matter(@TempDir Path dir) throws IOException {
        // GIVEN
        Files.writeString(dir.resolve("notes.md"), "# Titre\n\nUn contenu sans front-matter.");
        MarkdownFolderConnector connector = new MarkdownFolderConnector(dir.toString(), "fr");

        // WHEN
        List<SourceDocument> documents = connector.fetchAll();

        // THEN
        assertEquals("general", documents.get(0).domain());
        assertEquals("Titre", documents.get(0).title());
    }

    @Test
    void fetch_all_returns_empty_list_when_folder_missing() {
        // GIVEN
        MarkdownFolderConnector connector = new MarkdownFolderConnector("/path/does/not/exist", "fr");

        // WHEN / THEN
        assertTrue(connector.fetchAll().isEmpty());
    }

    @Test
    void fetch_all_computes_stable_hash_for_same_content(@TempDir Path dir) throws IOException {
        // GIVEN
        Files.writeString(dir.resolve("a.md"), "---\ndomain: support\n---\n\n# A\n\nContenu identique.");
        MarkdownFolderConnector connector = new MarkdownFolderConnector(dir.toString(), "fr");

        // WHEN
        String firstHash = connector.fetchAll().get(0).contentHash();
        String secondHash = connector.fetchAll().get(0).contentHash();

        // THEN
        assertEquals(firstHash, secondHash);
        assertNotNull(firstHash);
    }
}
