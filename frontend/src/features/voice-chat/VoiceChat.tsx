import { useState, useCallback, useEffect, useRef } from 'react'
import { useVoiceWebSocket } from './useVoiceWebSocket'
import { useVAD } from './useVAD'
import { useAudioQueue } from './useAudioQueue'
import { MessageList } from './MessageList'
import { ChatHeader } from './ChatHeader'
import { ServiceErrorBanner } from './ServiceErrorBanner'
import { labels, isLanguage } from './i18n'
import type { Language } from './i18n'

const GOODBYE_PATTERNS = [
  /merci\s*(au revoir|bonne journ[ée]e?|bien)/i,
  /au revoir/i,
  /bonne journ[ée]e?\s*$/i,
  /c'est tout\s*(merci|pour moi)?/i,
  /thank(s| you).*bye/i,
  /goodbye/i,
  /bye\s*bye/i,
  /that'?s all/i,
]

function isGoodbye(text: string): boolean {
  return GOODBYE_PATTERNS.some(p => p.test(text.trim()))
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  text: string
  timestamp: Date
  streaming?: boolean
  agentName?: string
  guardrailBlocked?: boolean
}

type VoiceState = 'idle' | 'listening' | 'recording' | 'processing' | 'speaking'

interface ServiceError {
  code: string
  message: string
  timestamp: number
}

const ERROR_LABELS: Record<string, string> = {
  STT_CREDITS_EXHAUSTED: '🎙️ Crédits Gradium épuisés — la reconnaissance vocale est indisponible. Utilisez le champ texte.',
  STT_AUTH_ERROR: '🎙️ Clé API Gradium invalide — vérifiez la configuration.',
  STT_UNREACHABLE: '🎙️ Service Gradium STT injoignable.',
  STT_ERROR: '🎙️ Erreur du service de reconnaissance vocale.',
  BACKEND_UNAVAILABLE: '⚙️ Backend indisponible — vérifiez que le serveur est démarré sur le port 8081.',
  LLM_AUTH_ERROR: '🤖 Clé API Mistral manquante ou invalide — vérifiez MISTRAL_API_KEY.',
  BACKEND_ERROR: '⚙️ Erreur du backend.',
  BRIDGE_DISCONNECTED: '🔌 Bridge vocal déconnecté — le mode voix est indisponible.',
}

export function VoiceChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [voiceState, setVoiceState] = useState<VoiceState>('idle')
  const [textInput, setTextInput] = useState('')
  const [language, setLanguage] = useState<Language>('fr')
  const [vadActive, setVadActive] = useState(false)
  const [serviceError, setServiceError] = useState<ServiceError | null>(null)

  const t = labels[language]

  const { enqueue: enqueueAudio, clear: clearAudioQueue, flush: flushAudio, state: audioState } = useAudioQueue()

  useEffect(() => {
    if (audioState === 'playing' && voiceState !== 'speaking') {
      setVoiceState('speaking')
    } else if (audioState === 'idle' && voiceState === 'speaking') {
      setVoiceState(vadActive ? 'listening' : 'idle')
    }
  }, [audioState, voiceState, vadActive])

  const addMessage = useCallback((role: 'user' | 'assistant', text: string) => {
    setMessages(prev => [...prev, { id: crypto.randomUUID(), role, text, timestamp: new Date() }])
  }, [])

  const { connectionState, startCall, sendAudio, sendEndOfSpeech, sendBargeIn, sendLanguage } = useVoiceWebSocket({
    onTranscription: (text) => {
      setMessages(prev => {
        const lastMsg = prev[prev.length - 1]
        if (lastMsg && lastMsg.role === 'user' && lastMsg.streaming) {
          return prev.map((m, i) =>
            i === prev.length - 1 ? { ...m, text, streaming: false } : m
          )
        }
        return [...prev, { id: crypto.randomUUID(), role: 'user' as const, text, timestamp: new Date() }]
      })
      if (isGoodbye(text)) {
        setTimeout(() => handleEndConversation(), 1500)
      }
    },
    onAnswerStart: (agentName, guardrailBlocked) => {
      setMessages(prev => [...prev, {
        id: crypto.randomUUID(),
        role: 'assistant' as const,
        text: '',
        timestamp: new Date(),
        streaming: true,
        agentName: agentName || undefined,
        guardrailBlocked: guardrailBlocked || false,
      }])
    },
    onAnswer: (text) => {
      if (text) addMessage('assistant', text)
      setVoiceState(vadActive ? 'listening' : 'idle')
    },
    onAnswerChunk: (text) => {
      setMessages(prev => {
        const lastMsg = prev[prev.length - 1]
        if (lastMsg && lastMsg.role === 'assistant' && lastMsg.streaming) {
          return prev.map((m, i) =>
            i === prev.length - 1 ? { ...m, text: m.text + text } : m
          )
        }
        return [...prev, { id: crypto.randomUUID(), role: 'assistant' as const, text, timestamp: new Date(), streaming: true }]
      })
    },
    onAnswerDone: (_text, agentName) => {
      setMessages(prev => prev.map(m => m.streaming ? { ...m, streaming: false, agentName: agentName || m.agentName } : m))
      if (audioState !== 'playing') {
        setVoiceState(vadActive ? 'listening' : 'idle')
      }
    },
    onAudio: (audio) => {
      enqueueAudio(audio)
    },
    onLanguageChanged: (lang) => { if (isLanguage(lang)) setLanguage(lang) },
    onError: (error) => { console.error('Voice error:', error); setVoiceState(vadActive ? 'listening' : 'idle'); clearAudioQueue() },
    onServiceError: (code, message) => {
      setServiceError({ code, message, timestamp: Date.now() })
    },
  })

  useEffect(() => {
    if (connectionState === 'disconnected' || connectionState === 'error') {
      setServiceError({ code: 'BRIDGE_DISCONNECTED', message: 'Bridge disconnected', timestamp: Date.now() })
    } else if (connectionState === 'connected' && serviceError?.code === 'BRIDGE_DISCONNECTED') {
      setServiceError(null)
    }
  }, [connectionState])

  const { start: startVAD, stop: stopVAD, resetToListening } = useVAD({
    onSpeechStart: () => {
      if (voiceState === 'speaking') {
        flushAudio()
        sendBargeIn()
      }
      setVoiceState('recording')
    },
    onSpeechEnd: sendAudio,
    onSpeechEndComplete: () => {
      sendEndOfSpeech()
      setVoiceState('processing')
      setMessages(prev => [...prev, {
        id: crypto.randomUUID(),
        role: 'user' as const,
        text: language === 'fr' ? '...' : '...',
        timestamp: new Date(),
        streaming: true,
      }])
    },
  })

  const callStartedRef = useRef(false)

  const handleMicToggle = async () => {
    if (vadActive) {
      stopVAD()
      setVadActive(false)
      setVoiceState('idle')
    } else {
      await startVAD()
      setVadActive(true)
      setVoiceState('listening')
      // Trigger the scripted welcome only when the user actually starts the
      // call (this click is the user gesture that unblocks audio autoplay).
      // Once per call; handleEndConversation resets it so a new call greets.
      if (!callStartedRef.current) {
        callStartedRef.current = true
        startCall()
      }
    }
  }

  const handleLanguageChange = (lang: Language) => { setLanguage(lang); sendLanguage(lang) }

  const handleEndConversation = () => {
    if (vadActive) {
      stopVAD()
      setVadActive(false)
    }
    clearAudioQueue()
    setMessages([])
    setVoiceState('idle')
    setTextInput('')
    callStartedRef.current = false
  }

  const handleTextSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!textInput.trim()) return
    const question = textInput.trim()
    const langHint = language === 'en' ? ' (Please answer in English.)' : ''
    setTextInput('')
    addMessage('user', question)
    setVoiceState('processing')
    try {
      const response = await fetch('/api/conversation/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: question + langHint, conversation_id: 'web-text' }),
      })
      if (!response.ok) {
        if (response.status === 500) {
          const text = await response.text()
          if (text.includes('401') || text.includes('Unauthorized') || text.includes('mistral')) {
            setServiceError({ code: 'LLM_AUTH_ERROR', message: 'Mistral API key invalid', timestamp: Date.now() })
          } else {
            setServiceError({ code: 'BACKEND_ERROR', message: `Backend error (${response.status})`, timestamp: Date.now() })
          }
        }
        throw new Error(`HTTP ${response.status}`)
      }
      setServiceError(prev => prev?.code === 'LLM_AUTH_ERROR' || prev?.code === 'BACKEND_ERROR' ? null : prev)
      const data = await response.json()
      setMessages(prev => [...prev, {
        id: crypto.randomUUID(), role: 'assistant', text: data.answer,
        timestamp: new Date(), agentName: data.agent_name,
        guardrailBlocked: data.guardrail_blocked || false,
      }])
    } catch {
      addMessage('assistant', t.error)
    } finally {
      setVoiceState(vadActive ? 'listening' : 'idle')
      resetToListening()
    }
  }

  const stateLabel: Record<VoiceState, string> = {
    idle: t.idle,
    listening: language === 'fr' ? 'En écoute...' : 'Listening...',
    recording: language === 'fr' ? 'Parole détectée' : 'Speech detected',
    processing: t.processing,
    speaking: t.speaking,
  }

  const stateColor: Record<VoiceState, string> = {
    idle: 'var(--color-primary)',
    listening: 'var(--color-success)',
    recording: 'var(--color-recording)',
    processing: 'var(--color-processing)',
    speaking: 'var(--color-speaking)',
  }

  const micIcon = () => {
    if (vadActive) {
      if (voiceState === 'recording') return '🔴'
      if (voiceState === 'processing') return '⏳'
      if (voiceState === 'speaking') return '🔊'
      return '👂'
    }
    return '🎙️'
  }

  return (
    <div className="rounded-2xl shadow-lg overflow-hidden" style={{ backgroundColor: 'var(--color-surface)' }}>
      <ChatHeader
        connected={connectionState === 'connected'}
        statusLabel={t.disconnected}
        language={language}
        t={t}
        onLanguageChange={handleLanguageChange}
      />
      {serviceError && (
        <ServiceErrorBanner
          message={ERROR_LABELS[serviceError.code] || serviceError.message}
          onDismiss={() => setServiceError(null)}
        />
      )}
      <MessageList messages={messages} greeting={t.greeting} hint={t.hint} />
      <div className="p-4" style={{ borderTop: '1px solid var(--color-border)' }}>
        <div className="flex flex-col items-center mb-4">
          <div className="flex items-center gap-4">
            <button
              onClick={handleMicToggle}
              disabled={voiceState === 'processing'}
              className="relative w-16 h-16 rounded-full flex items-center justify-center text-white text-2xl transition-transform hover:scale-105 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed"
              style={{ backgroundColor: stateColor[voiceState] }}
              aria-label={vadActive ? (language === 'fr' ? 'Désactiver le micro' : 'Disable mic') : (language === 'fr' ? 'Activer le micro' : 'Enable mic')}
            >
              {(voiceState === 'listening' || voiceState === 'recording') && (
                <span className="absolute inset-0 rounded-full opacity-50" style={{ animation: 'pulse-ring 1.5s infinite', backgroundColor: stateColor[voiceState] }} />
              )}
              <span className="relative z-10" aria-hidden="true">{micIcon()}</span>
            </button>
            {messages.length > 0 && (
              <button
                onClick={handleEndConversation}
                disabled={voiceState === 'processing'}
                className="w-10 h-10 rounded-full flex items-center justify-center text-sm transition-transform hover:scale-105 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed"
                style={{ backgroundColor: 'var(--color-danger)', color: 'white' }}
                aria-label={t.endConversation}
                title={t.endConversation}
              >
                <span aria-hidden="true">✕</span>
              </button>
            )}
          </div>
          <span className="mt-2 text-xs" style={{ color: 'var(--color-text-muted)' }}>{stateLabel[voiceState]}</span>
        </div>
        <form onSubmit={handleTextSubmit} className="flex gap-2">
          <label htmlFor="voice-chat-input" className="sr-only">{t.placeholder}</label>
          <input
            id="voice-chat-input"
            type="text"
            value={textInput}
            onChange={e => setTextInput(e.target.value)}
            placeholder={t.placeholder}
            className="flex-1 px-4 py-2 rounded-full text-sm outline-none focus:ring-2 focus:ring-blue-500"
            style={{ border: '1px solid var(--color-border)' }}
            disabled={voiceState === 'processing'}
          />
          <button
            type="submit"
            disabled={!textInput.trim() || voiceState === 'processing'}
            className="px-4 py-2 rounded-full text-sm text-white font-medium disabled:opacity-50"
            style={{ backgroundColor: 'var(--color-primary)' }}
          >{t.send}</button>
        </form>
      </div>
    </div>
  )
}

