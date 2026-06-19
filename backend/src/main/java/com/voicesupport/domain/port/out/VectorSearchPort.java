package com.voicesupport.domain.port.out;

import com.voicesupport.domain.model.Citation;

import java.util.List;

public interface VectorSearchPort {

    List<Citation> searchRelevant(String query, int topK);
}
