package com.voicesupport.conversation.fake;

import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.domain.port.out.AnswerGeneratorPort;

import java.util.List;

public class FakeAnswerGeneratorPort implements AnswerGeneratorPort {

    private String nextAnswer = "Réponse générée à partir du contexte.";

    public String lastQuestion;
    public List<RetrievedEvidence> lastEvidence;
    public List<String> lastHistory;
    public int callCount;

    public void setNextAnswer(String nextAnswer) {
        this.nextAnswer = nextAnswer;
    }

    @Override
    public String generate(String question, List<RetrievedEvidence> evidence, List<String> history) {
        this.lastQuestion = question;
        this.lastEvidence = evidence;
        this.lastHistory = history;
        this.callCount++;
        return nextAnswer;
    }
}
