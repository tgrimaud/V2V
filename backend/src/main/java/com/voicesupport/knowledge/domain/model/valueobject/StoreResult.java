package com.voicesupport.knowledge.domain.model.valueobject;

// Outcome of storing one document's chunks (BUG-022). "attempted" is the number of embeddable
// (non-blank) chunks the store tried to write; "stored" is how many actually landed. They differ
// when a batch was skipped after an embedding timeout/error, so the sync can tell a fully-ingested
// document (commit its content_hash) from a partial/failed one (leave it uncommitted so the next
// idempotent run retries it instead of silently dropping the missing chunks from the RAG).
public record StoreResult(int stored, int attempted) {

    public static StoreResult of(int stored, int attempted) {
        return new StoreResult(stored, attempted);
    }

    public boolean isComplete() {
        return stored >= attempted;
    }

    public int skipped() {
        return Math.max(0, attempted - stored);
    }
}
