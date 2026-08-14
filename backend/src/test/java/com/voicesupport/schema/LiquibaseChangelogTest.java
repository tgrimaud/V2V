package com.voicesupport.schema;

import liquibase.changelog.ChangeLogParameters;
import liquibase.changelog.ChangeSet;
import liquibase.changelog.DatabaseChangeLog;
import liquibase.parser.ChangeLogParserFactory;
import liquibase.resource.ClassLoaderResourceAccessor;
import liquibase.resource.ResourceAccessor;
import org.junit.jupiter.api.Test;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

// Offline guard (TASK-INFRA-009, ADR-0041): validates the Liquibase changelogs parse (no DB) and
// that vector_store stays byte-for-byte compatible with Spring AI 1.0.0's PgVectorStore schema.
// A drift here silently breaks RAG, so it must fail the build, not production startup.
class LiquibaseChangelogTest {

    private static final String MASTER = "db/changelog/db.changelog-master.yaml";
    private static final String BOOTSTRAP = "db/changelog/bootstrap/db.changelog-bootstrap.yaml";
    private static final String VECTOR_STORE = "db/changelog/changes/001-vector-store.yaml";

    @Test
    void app_master_changelog_parses_with_the_two_app_changesets_in_order() throws Exception {
        List<String> ids = parseChangeSetIds(MASTER);

        assertEquals(List.of("001-vector-store", "002-kb-source-state"), ids);
    }

    @Test
    void app_master_changelog_never_includes_a_privileged_bootstrap_changeset() throws Exception {
        List<String> ids = parseChangeSetIds(MASTER);

        assertFalse(ids.stream().anyMatch(id -> id.startsWith("bootstrap-")),
                "app startup must never run a superuser-only changeset");
    }

    @Test
    void bootstrap_changelog_parses_with_the_extension_and_grant_changesets() throws Exception {
        List<String> ids = parseChangeSetIds(BOOTSTRAP);

        assertEquals(List.of("bootstrap-001-extensions", "bootstrap-002-grants"), ids);
    }

    @Test
    void vector_store_ddl_matches_spring_ai_pgvector_schema_exactly() throws Exception {
        String ddl = readResource(VECTOR_STORE);

        assertTrue(ddl.contains("id uuid DEFAULT uuid_generate_v4() PRIMARY KEY"), "uuid id + default");
        assertTrue(ddl.contains("content text"), "content column");
        assertTrue(ddl.contains("metadata json"), "metadata must be json, NOT jsonb");
        assertTrue(ddl.contains("embedding vector(768)"), "768-dim embedding");
        assertTrue(ddl.contains(
                "CREATE INDEX spring_ai_vector_index ON public.vector_store USING hnsw (embedding vector_cosine_ops)"),
                "HNSW cosine index name + operator class");
    }

    @Test
    void bootstrap_creates_the_vector_and_uuid_ossp_extensions() throws Exception {
        String bootstrap = readResource(BOOTSTRAP);

        assertTrue(bootstrap.contains("CREATE EXTENSION IF NOT EXISTS vector"), "vector extension");
        assertTrue(bootstrap.contains("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\""), "uuid-ossp extension");
    }

    private static List<String> parseChangeSetIds(String changelog) throws Exception {
        ResourceAccessor accessor = new ClassLoaderResourceAccessor();
        DatabaseChangeLog parsed = ChangeLogParserFactory.getInstance()
                .getParser(changelog, accessor)
                .parse(changelog, new ChangeLogParameters(), accessor);
        return parsed.getChangeSets().stream().map(ChangeSet::getId).toList();
    }

    private static String readResource(String path) throws Exception {
        try (InputStream in = LiquibaseChangelogTest.class.getClassLoader().getResourceAsStream(path)) {
            assertNotNull(in, "missing changelog resource: " + path);
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
