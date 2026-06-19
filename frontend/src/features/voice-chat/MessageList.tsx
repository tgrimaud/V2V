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
      {messages.map(msg => (
        <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
          <div
            className="max-w-[80%] rounded-2xl px-4 py-3 text-sm"
            style={{
              backgroundColor: msg.role === 'user' ? 'var(--color-primary)' : '#f1f5f9',
              color: msg.role === 'user' ? 'white' : 'var(--color-text)',
            }}
          >
            {msg.text}
          </div>
        </div>
      ))}
      <div ref={messagesEndRef} />
    </div>
  )
}
