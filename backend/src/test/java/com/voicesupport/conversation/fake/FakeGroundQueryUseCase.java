package com.voicesupport.conversation.fake;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;
import com.voicesupport.conversation.domain.model.valueobject.GroundingResult;
import com.voicesupport.conversation.domain.port.in.GroundQueryUseCase;

public class FakeGroundQueryUseCase implements GroundQueryUseCase {

    private GroundingResult nextResult;

    public String lastQuestion;
    public String lastDomain;
    public int lastTopK;
    public boolean lastAlreadyGreeted;
    public AnswerLanguage lastLanguage;
    public int callCount;

    public void setNextResult(GroundingResult nextResult) {
        this.nextResult = nextResult;
    }

    @Override
    public GroundingResult ground(String question, String domain, int topK, boolean alreadyGreeted,
            AnswerLanguage language) {
        this.lastQuestion = question;
        this.lastDomain = domain;
        this.lastTopK = topK;
        this.lastAlreadyGreeted = alreadyGreeted;
        this.lastLanguage = language;
        this.callCount++;
        return nextResult;
    }
}
