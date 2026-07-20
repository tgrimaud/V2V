package com.voicesupport.conversation.fake;

import com.voicesupport.conversation.domain.model.valueobject.RetrievedEvidence;
import com.voicesupport.conversation.domain.port.out.StreamingAnswerGeneratorPort;

import java.util.List;
import java.util.function.Consumer;

public class FakeStreamingAnswerGeneratorPort implements StreamingAnswerGeneratorPort {

    private List<String> tokens = List.of();

    public int callCount;
    public List<RetrievedEvidence> lastEvidence = List.of();
    public List<String> lastHistory = List.of();

    public void setNextTokens(List<String> tokens) {
        this.tokens = List.copyOf(tokens);
    }

    public void setNextAnswer(String text) {
        this.tokens = List.of(text);
    }

    @Override
    public void generate(
            String question, List<RetrievedEvidence> evidence, List<String> history, Consumer<String> onToken) {
        this.callCount++;
        this.lastEvidence = List.copyOf(evidence);
        this.lastHistory = List.copyOf(history);
        for (String token : tokens) {
            onToken.accept(token);
        }
    }
}
