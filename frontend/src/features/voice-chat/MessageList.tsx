import { useRef, useEffect } from 'react'

interface Message {
  id: string
  role: 'user' | 'assistant'
  text: string
  timestamp: Date
  agentName?: string
  guardrailBlocked?: boolean
}

interface MessageListProps {
  messages: Message[]
  greeting: string
  hint: string
}

const AGENT_COLORS: Record<string, string> = {
  'Agent Support Technique': '#3b82f6',
  'Agent Facturation': '#10b981',
  'Agent Commercial': '#f59e0b',
}

function getAgentColor(agentName: string): string {
  return AGENT_COLORS[agentName] || '#6b7280'
}

export function MessageList({ messages, greeting, hint }: MessageListProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <div className="h-96 overflow-y-auto p-4 space-y-4">
      {messages.length === 0 && (
        <div className="h-full flex items-center justify-center text-center">
          <div>
            <div className="text-4xl mb-4" aria-hidden="true">🎙️</div>
            <p className="text-lg font-medium" style={{ color: 'var(--color-text)' }}>
              {greeting}
            </p>
            <p className="mt-2 text-sm" style={{ color: 'var(--color-text-muted)' }}>
              {hint}
            </p>
          </div>
        </div>
      )}
      {messages.map(msg => {
        const isGuardrail = msg.role === 'assistant' && msg.guardrailBlocked
        return (
          <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className="max-w-[80%]">
              {msg.role === 'assistant' && msg.agentName && (
                <div className="mb-1 flex items-center gap-1.5">
                  <span
                    className="inline-block w-2 h-2 rounded-full"
                    style={{ backgroundColor: getAgentColor(msg.agentName) }}
                  />
                  <span className="text-xs font-medium" style={{ color: getAgentColor(msg.agentName) }}>
                    {msg.agentName}
                  </span>
                </div>
              )}
              <div
                className="rounded-2xl px-4 py-3 text-sm"
                style={{
                  backgroundColor: isGuardrail
                    ? '#fef3c7'
                    : msg.role === 'user' ? 'var(--color-primary)' : '#f1f5f9',
                  color: isGuardrail
                    ? '#92400e'
                    : msg.role === 'user' ? 'white' : 'var(--color-text)',
                  border: isGuardrail ? '1px solid #f59e0b' : 'none',
                }}
              >
                {isGuardrail && (
                  <span className="inline-block mr-1.5 text-xs font-medium px-1.5 py-0.5 rounded"
                    style={{ backgroundColor: '#f59e0b', color: 'white' }}>
                    ⚠️ Confiance faible
                  </span>
                )}
                {msg.text}
              </div>
            </div>
          </div>
        )
      })}
      <div ref={messagesEndRef} />
    </div>
  )
}
