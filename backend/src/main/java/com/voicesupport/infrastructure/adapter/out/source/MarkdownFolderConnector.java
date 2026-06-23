package com.voicesupport.infrastructure.adapter.out.source;

import com.voicesupport.domain.model.SourceDocument;
import com.voicesupport.domain.port.out.KnowledgeSourceConnector;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.yaml.snakeyaml.Yaml;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Stream;

public class MarkdownFolderConnector implements KnowledgeSourceConnector {

    public static final String SOURCE_TYPE = "markdown";

    private static final Logger log = LoggerFactory.getLogger(MarkdownFolderConnector.class);
    private static final Pattern FRONT_MATTER =
            Pattern.compile("^---\\s*\\R(.*?)\\R---\\s*\\R(.*)$", Pattern.DOTALL);

    private final Path folder;
    private final String defaultLanguage;

    public MarkdownFolderConnector(String folderPath, String defaultLanguage) {
        this.folder = Path.of(folderPath);
        this.defaultLanguage = defaultLanguage;
    }

    @Override
    public String sourceType() {
        return SOURCE_TYPE;
    }

    @Override
    public List<SourceDocument> fetchAll() {
        if (!Files.isDirectory(folder)) {
            log.warn("[KB-SYNC] markdown folder not found: {}", folder.toAbsolutePath());
            return List.of();
        }
        try (Stream<Path> files = Files.list(folder)) {
            return files
                    .filter(path -> path.getFileName().toString().endsWith(".md"))
                    .sorted()
                    .map(this::toDocument)
                    .filter(Objects::nonNull)
                    .toList();
        } catch (IOException e) {
            throw new UncheckedIOException("Failed to list markdown folder " + folder, e);
        }
    }

    private SourceDocument toDocument(Path path) {
        try {
            String raw = Files.readString(path, StandardCharsets.UTF_8);
            ParsedMarkdown parsed = parseFrontMatter(raw);
            String sourceId = path.getFileName().toString();
            String title = parsed.title != null ? parsed.title : firstHeading(parsed.body, sourceId);
            Instant updatedAt = Files.getLastModifiedTime(path).toInstant();
            return SourceDocument.create(
                    SOURCE_TYPE, sourceId, title, null,
                    parsed.body, parsed.domain, defaultLanguage, updatedAt);
        } catch (IOException e) {
            log.warn("[KB-SYNC] skipping unreadable markdown file {}: {}", path, e.getMessage());
            return null;
        }
    }

    private ParsedMarkdown parseFrontMatter(String raw) {
        Matcher matcher = FRONT_MATTER.matcher(raw);
        if (!matcher.matches()) {
            return new ParsedMarkdown(null, null, raw);
        }
        Object loaded = new Yaml().load(matcher.group(1));
        Map<String, Object> data = loaded instanceof Map<?, ?> map ? castMap(map) : Map.of();
        return new ParsedMarkdown(asString(data.get("domain")), asString(data.get("title")), matcher.group(2));
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> castMap(Map<?, ?> map) {
        return (Map<String, Object>) map;
    }

    private String asString(Object value) {
        return value != null ? value.toString().trim() : null;
    }

    private String firstHeading(String body, String fallback) {
        for (String line : body.split("\n")) {
            if (line.startsWith("# ")) {
                return line.substring(2).trim();
            }
        }
        return fallback;
    }

    private record ParsedMarkdown(String domain, String title, String body) {
    }
}
