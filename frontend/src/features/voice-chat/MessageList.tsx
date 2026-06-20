import { useRef, useEffect } from 'react'

interface Message {
  id: string
  role: 'user' | 'assistant'
  text: string
  timestamp: Date
}

interface MessageListProps {
  messages: Message[]
  greeting: string
  hint: string
}

const GUARDRAIL_MARKERS = [
  "pas assez d'informations fiables",
  "sort de mon domaine de compétence",
  "outside my area of expertise",
  "don't have enough reliable information",
]

function isGuardrailMessage(text: string): boolean {
  return GUARDRAIL_MARKERS.some(marker => text.includes(marker))
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
        const guardrail = msg.role === 'assistant' && isGuardrailMessage(msg.text)
        return (
          <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className="max-w-[80%] rounded-2xl px-4 py-3 text-sm"
              style={{
                backgroundColor: guardrail
                  ? '#fef3c7'
                  : msg.role === 'user' ? 'var(--color-primary)' : '#f1f5f9',
                color: guardrail
                  ? '#92400e'
                  : msg.role === 'user' ? 'white' : 'var(--color-text)',
                border: guardrail ? '1px solid #f59e0b' : 'none',
              }}
            >
              {guardrail && (
                <span className="inline-block mr-1.5 text-xs font-medium px-1.5 py-0.5 rounded"
                  style={{ backgroundColor: '#f59e0b', color: 'white' }}>
                  ⚠️ Confiance faible
                </span>
              )}
              {msg.text}
            </div>
          </div>
        )
      })}
      <div ref={messagesEndRef} />
    </div>
  )
}
