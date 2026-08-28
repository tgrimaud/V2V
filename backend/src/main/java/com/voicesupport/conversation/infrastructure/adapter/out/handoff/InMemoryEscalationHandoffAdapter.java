package com.voicesupport.conversation.infrastructure.adapter.out.handoff;

import com.voicesupport.conversation.domain.model.valueobject.EscalationHandoff;
import com.voicesupport.conversation.domain.model.valueobject.HandoffId;
import com.voicesupport.conversation.domain.port.out.EscalationHandoffPort;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

// Process-local, bounded store for audited escalation hand-offs (TASK-BE-036 / DEC-013). Mints an
// opaque UUID handoff_id on store and keeps at most `maxHandoffs` recent hand-offs in access-ordered
// LRU order; the eldest is evicted past the cap. Suitable for a single-node pilot — a shared store
// (Redis/DB) is a later concern, swappable behind EscalationHandoffPort. All access is synchronized
// on the backing map so concurrent turns stay consistent. Mirrors the BE-037 dedup adapter layout.
public class InMemoryEscalationHandoffAdapter implements EscalationHandoffPort {

    private final Map<String, EscalationHandoff> handoffs;

    public InMemoryEscalationHandoffAdapter(int maxHandoffs) {
        int cap = Math.max(1, maxHandoffs);
        this.handoffs = new LinkedHashMap<>(16, 0.75f, true) {
            @Override
            protected boolean removeEldestEntry(Map.Entry<String, EscalationHandoff> eldest) {
                return size() > cap;
            }
        };
    }

    @Override
    public HandoffId store(EscalationHandoff handoff) {
        HandoffId id = HandoffId.of(UUID.randomUUID().toString());
        synchronized (handoffs) {
            handoffs.put(id.value(), handoff);
        }
        return id;
    }

    @Override
    public Optional<EscalationHandoff> findById(HandoffId handoffId) {
        if (handoffId == null) {
            return Optional.empty();
        }
        synchronized (handoffs) {
            return Optional.ofNullable(handoffs.get(handoffId.value()));
        }
    }
}
