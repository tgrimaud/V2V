package com.voicesupport.knowledge.domain.port.out;

public interface AudienceClassifierPort {

    String classify(String title, String content);
}
