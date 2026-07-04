package com.voicesupport.domain.model;

import java.util.List;

@FunctionalInterface
public interface TokenStream extends Iterable<String> {

    static TokenStream fromIterable(Iterable<String> tokens) {
        return tokens::iterator;
    }

    static TokenStream single(String token) {
        return () -> List.of(token).iterator();
    }
}
