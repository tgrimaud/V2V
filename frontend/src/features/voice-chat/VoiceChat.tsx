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
  const [language, setLanguage] = useState<'fr' | 'en'>('fr')
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

  const { connectionState, sendAudio, sendEndOfSpeech, sendLanguage } = useVoiceWebSocket({
    onTranscription: (text) => addMessage('user', text),
    onAnswer: (text) => {
      if (text) addMessage('assistant', text)
      setVoiceState('idle')
    },
    onAudio: playAudio,
    onLanguageChanged: (lang) => setLanguage(lang as 'fr' | 'en'),
    onError: (error) => {
      console.error('Voice error:', error)
      setVoiceState('idle')
    },
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

  const handleLanguageChange = (lang: 'fr' | 'en') => {
    setLanguage(lang)
    sendLanguage(lang)
  }

  const labels = {
    fr: {
      idle: 'Appuyez pour parler',
      recording: 'Écoute en cours...',
      processing: 'Réflexion...',
      speaking: 'Réponse en cours...',
      greeting: 'Bonjour ! Comment puis-je vous aider ?',
      hint: 'Posez votre question sur votre box, forfait ou connexion',
      placeholder: 'Ou tapez votre question ici...',
      send: 'Envoyer',
      connected: 'Connecté',
      disconnected: 'Déconnecté',
    },
    en: {
      idle: 'Press to speak',
      recording: 'Listening...',
      processing: 'Thinking...',
      speaking: 'Speaking...',
      greeting: 'Hello! How can I help you?',
      hint: 'Ask about your router, plan, or connection',
      placeholder: 'Or type your question here...',
      send: 'Send',
      connected: 'Connected',
      disconnected: 'Disconnected',
    },
  }

  const t = labels[language]

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
    idle: t.idle,
    recording: t.recording,
    processing: t.processing,
    speaking: t.speaking,
  }

  return (
    <div className="rounded-2xl shadow-lg overflow-hidden" style={{ backgroundColor: 'var(--color-surface)' }}>
      {/* Connection indicator + Language selector */}
      <div className="px-4 py-2 flex items-center justify-between text-sm" style={{ borderBottom: '1px solid var(--color-border)' }}>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full" style={{
            backgroundColor: connectionState === 'connected' ? 'var(--color-success)' : 'var(--color-danger)'
          }} />
          <span style={{ color: 'var(--color-text-muted)' }}>
            {connectionState === 'connected' ? t.connected : t.disconnected}
          </span>
        </div>
        <div className="flex items-center gap-1 rounded-full p-0.5" style={{ backgroundColor: 'var(--color-border)' }}>
          <button
            onClick={() => handleLanguageChange('fr')}
            className="px-2.5 py-1 rounded-full text-xs font-medium transition-colors"
            style={{
              backgroundColor: language === 'fr' ? 'var(--color-primary)' : 'transparent',
              color: language === 'fr' ? 'white' : 'var(--color-text-muted)',
            }}
          >
            FR
          </button>
          <button
            onClick={() => handleLanguageChange('en')}
            className="px-2.5 py-1 rounded-full text-xs font-medium transition-colors"
            style={{
              backgroundColor: language === 'en' ? 'var(--color-primary)' : 'transparent',
              color: language === 'en' ? 'white' : 'var(--color-text-muted)',
            }}
          >
            EN
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="h-96 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="h-full flex items-center justify-center text-center">
            <div>
              <div className="text-4xl mb-4">🎙️</div>
              <p className="text-lg font-medium" style={{ color: 'var(--color-text)' }}>
                {t.greeting}
              </p>
              <p className="mt-2 text-sm" style={{ color: 'var(--color-text-muted)' }}>
                {t.hint}
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
            placeholder={t.placeholder}
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
            {t.send}
          </button>
        </form>
      </div>
    </div>
  )
}
