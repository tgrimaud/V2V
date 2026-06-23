package com.voicesupport.infrastructure.adapter.out.persistence;

import java.io.Serializable;
import java.util.Objects;

public class KbSourceStateId implements Serializable {

    private String sourceType;
    private String sourceId;

    public KbSourceStateId() {
    }

    public KbSourceStateId(String sourceType, String sourceId) {
        this.sourceType = sourceType;
        this.sourceId = sourceId;
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) {
            return true;
        }
        if (!(o instanceof KbSourceStateId that)) {
            return false;
        }
        return Objects.equals(sourceType, that.sourceType) && Objects.equals(sourceId, that.sourceId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(sourceType, sourceId);
    }
}
