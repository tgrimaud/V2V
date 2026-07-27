package com.voicesupport.knowledge.fake;

import com.voicesupport.knowledge.domain.port.out.AudienceClassifierPort;

import java.util.ArrayList;
import java.util.List;

public class FakeAudienceClassifier implements AudienceClassifierPort {

    public String returns = "customer";
    public final List<String> classifiedTitles = new ArrayList<>();
    public String lastContent;

    @Override
    public String classify(String title, String content) {
        classifiedTitles.add(title);
        lastContent = content;
        return returns;
    }
}
