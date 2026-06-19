import { useState, useCallback, useRef, useEffect } from 'react'
import { useVoiceWebSocket } from './useVoiceWebSocket'
import { useAudioRecorder } from './useAudioRecorder'

interface Message {
  id: string
  role: 'user' | 'assistant'
  text: string
  timestamp: Date
}

type VoiceState = 'idle' | 'recording' | 'processing' | 'speaking'

export function VoiceChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [voiceState, setVoiceState] = useState<VoiceState>('idle')
  const [textInput, setTextInput] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const audioContextRef = useRef<AudioContext | null>(null)

  const addMessage = useCallback((role: 'user' | 'assistant', text: string) => {
    setMessages(prev => [...prev, {
      id: crypto.randomUUID(),
      role,
      text,
      timestamp: new Date()
    }])
  }, [])

  const playAudio = useCallback(async (audioBuffer: ArrayBuffer) => {
    try {
      if (!audioContextRef.current) {
        audioContextRef.current = new AudioContext()
      }
      const ctx = audioContextRef.current
      const decoded = await ctx.decodeAudioData(audioBuffer)
      const source = ctx.createBufferSource()
      source.buffer = decoded
      source.connect(ctx.destination)
      source.onended = () => setVoiceState('idle')
      setVoiceState('speaking')
      source.start()
    } catch {
      setVoiceState('idle')
    }
  }, [])

  const { connectionState, connect, disconnect, sendAudio, sendEndOfSpeech } = useVoiceWebSocket({
    onTranscription: (text) => addMessage('user', text),
    onAnswer: (text) => addMessage('assistant', text),
    onAudio: playAudio,
    onError: (error) => console.error('Voice error:', error),
  })

  const { state: recorderState, startRecording, stopRecording, reset: resetRecorder } = useAudioRecorder({
    onAudioData: sendAudio,
    onRecordingComplete: () => {
      sendEndOfSpeech()
      setVoiceState('processing')
    }
  })

  useEffect(() => {
    if (recorderState === 'recording') setVoiceState('recording')
  }, [recorderState])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    connect()
    return () => disconnect()
  }, [connect, disconnect])

  const handleMicClick = () => {
    if (voiceState === 'recording') {
      stopRecording()
    } else if (voiceState === 'idle') {
      startRecording()
    }
  }

  const handleTextSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!textInput.trim()) return

    const question = textInput.trim()
    setTextInput('')
    addMessage('user', question)
    setVoiceState('processing')

    try {
      const response = await fetch('/api/conversation/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, conversation_id: 'web-text' })
      })
      const data = await response.json()
      addMessage('assistant', data.answer)
    } catch {
      addMessage('assistant', 'Désolé, une erreur est survenue. Veuillez réessayer.')
    } finally {
      setVoiceState('idle')
      resetRecorder()
    }
  }

  const stateColors: Record<VoiceState, string> = {
    idle: 'var(--color-primary)',
    recording: 'var(--color-recording)',
    processing: 'var(--color-processing)',
    speaking: 'var(--color-speaking)',
  }

  const stateLabels: Record<VoiceState, string> = {
    idle: 'Appuyez pour parler',
    recording: 'Écoute en cours...',
    processing: 'Réflexion...',
    speaking: 'Réponse en cours...',
  }

  return (
    <div className="rounded-2xl shadow-lg overflow-hidden" style={{ backgroundColor: 'var(--color-surface)' }}>
      {/* Connection indicator */}
      <div className="px-4 py-2 flex items-center gap-2 text-sm" style={{ borderBottom: '1px solid var(--color-border)' }}>
        <span className="w-2 h-2 rounded-full" style={{
          backgroundColor: connectionState === 'connected' ? 'var(--color-success)' : 'var(--color-danger)'
        }} />
        <span style={{ color: 'var(--color-text-muted)' }}>
          {connectionState === 'connected' ? 'Connecté' : 'Déconnecté'}
        </span>
      </div>

      {/* Messages */}
      <div className="h-96 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="h-full flex items-center justify-center text-center">
            <div>
              <div className="text-4xl mb-4">🎙️</div>
              <p className="text-lg font-medium" style={{ color: 'var(--color-text)' }}>
                Bonjour ! Comment puis-je vous aider ?
              </p>
              <p className="mt-2 text-sm" style={{ color: 'var(--color-text-muted)' }}>
                Posez votre question sur votre box, forfait ou connexion
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

      {/* Voice button + text input */}
      <div className="p-4" style={{ borderTop: '1px solid var(--color-border)' }}>
        {/* Voice state indicator */}
        <div className="flex flex-col items-center mb-4">
          <button
            onClick={handleMicClick}
            disabled={voiceState === 'processing' || voiceState === 'speaking'}
            className="relative w-16 h-16 rounded-full flex items-center justify-center text-white text-2xl transition-transform hover:scale-105 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed"
            style={{ backgroundColor: stateColors[voiceState] }}
            aria-label={stateLabels[voiceState]}
          >
            {voiceState === 'recording' && (
              <span
                className="absolute inset-0 rounded-full"
                style={{ animation: 'pulse-ring 1.5s infinite', backgroundColor: stateColors[voiceState] }}
              />
            )}
            <span className="relative z-10">
              {voiceState === 'recording' ? '⏹' : voiceState === 'processing' ? '⏳' : voiceState === 'speaking' ? '🔊' : '🎙️'}
            </span>
          </button>
          <span className="mt-2 text-xs" style={{ color: 'var(--color-text-muted)' }}>
            {stateLabels[voiceState]}
          </span>
        </div>

        {/* Text input fallback */}
        <form onSubmit={handleTextSubmit} className="flex gap-2">
          <input
            type="text"
            value={textInput}
            onChange={e => setTextInput(e.target.value)}
            placeholder="Ou tapez votre question ici..."
            className="flex-1 px-4 py-2 rounded-full text-sm outline-none focus:ring-2 focus:ring-blue-500"
            style={{
              border: '1px solid var(--color-border)',
            }}
            disabled={voiceState === 'processing'}
          />
          <button
            type="submit"
            disabled={!textInput.trim() || voiceState === 'processing'}
            className="px-4 py-2 rounded-full text-sm text-white font-medium disabled:opacity-50"
            style={{ backgroundColor: 'var(--color-primary)' }}
          >
            Envoyer
          </button>
        </form>
      </div>
    </div>
  )
}
