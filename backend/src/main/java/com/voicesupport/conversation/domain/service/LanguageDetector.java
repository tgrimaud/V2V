package com.voicesupport.conversation.domain.service;

import com.voicesupport.conversation.domain.model.valueobject.AnswerLanguage;

import java.util.List;
import java.util.Optional;

// Per-turn answer-language decision (TASK-BE-015): detect the language of the current question;
// when the question is too ambiguous to decide, keep the current conversation language (session
// stickiness, inferred from the most recent history turns) and otherwise fall back to the
// deployment default (English for the Eir pilot). One decision per turn, reused by the answer
// generation so the spoken reply matches the customer's language (BR1/BR2/BR3).
public class LanguageDetector {

    private final AnswerLanguage defaultLanguage;

    public LanguageDetector(AnswerLanguage defaultLanguage) {
        this.defaultLanguage = defaultLanguage == null ? AnswerLanguage.ENGLISH : defaultLanguage;
    }

    public AnswerLanguage resolve(String question, List<String> history) {
        return resolve(question, history, null);
    }

    // US-042: when the UI forces a language, that explicit choice wins over auto-detection and
    // session stickiness (a blank/unknown code falls back to the normal per-turn decision).
    public AnswerLanguage resolve(String question, List<String> history, String forcedCode) {
        if (forcedCode != null && !forcedCode.isBlank()) {
            return AnswerLanguage.fromCode(forcedCode);
        }
        return AnswerLanguage.detect(question)
                .or(() -> stickyLanguage(history))
                .orElse(defaultLanguage);
    }

    public AnswerLanguage defaultLanguage() {
        return defaultLanguage;
    }

    private Optional<AnswerLanguage> stickyLanguage(List<String> history) {
        if (history == null || history.isEmpty()) {
            return Optional.empty();
        }
        for (int i = history.size() - 1; i >= 0; i--) {
            Optional<AnswerLanguage> detected = AnswerLanguage.detect(history.get(i));
            if (detected.isPresent()) {
                return detected;
            }
        }
        return Optional.empty();
    }
}
