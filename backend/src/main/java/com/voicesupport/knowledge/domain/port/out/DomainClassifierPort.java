package com.voicesupport.knowledge.domain.port.out;

public interface DomainClassifierPort {

    String classify(String title, String content);
}
