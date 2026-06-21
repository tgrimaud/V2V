package com.voicesupport.domain.port.out;

public interface VectorStorePort {

    void store(String content, String source, String section, int chunkIndex);

    void store(String content, String source, String section, int chunkIndex, String domain);
}
