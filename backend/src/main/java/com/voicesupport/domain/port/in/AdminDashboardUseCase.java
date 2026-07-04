package com.voicesupport.domain.port.in;

import com.voicesupport.domain.model.AdminStats;
import com.voicesupport.domain.model.ConversationEvent;
import com.voicesupport.domain.model.TopQuestion;

import java.util.List;

public interface AdminDashboardUseCase {

    AdminStats getStats();

    List<ConversationEvent> getEvents(int limit);

    List<TopQuestion> getTopQuestions();
}
