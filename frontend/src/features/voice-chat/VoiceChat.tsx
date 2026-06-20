import { useState, useCallback } from 'react'
import { useVoiceWebSocket } from './useVoiceWebSocket'
import { useVAD } from './useVAD'
import { useAudioQueue } from './useAudioQueue'
import { MessageList } from './MessageList'
import { labels } from './i18n'
import type { Language, Labels } from './i18n'

interface Message {
  id: string
  role: 'user' | 'assistant'
  text: string
  timestamp: Date
  streaming?: boolean
}

type VoiceState = 'idle' | 'listening' | 'recording' | 'processing' | 'speaking'

export function VoiceChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [voiceState, setVoiceState] = useState<VoiceState>('idle')
  const [textInput, setTextInput] = useState('')
  const [language, setLanguage] = useState<Language>('fr')
  const [vadActive, setVadActive] = useState(false)

  const t = labels[language]

  const { enqueue: enqueueAudio, clear: clearAudioQueue, flush: flushAudio, state: audioState } = useAudioQueue()

  if (audioState === 'playing' && voiceState !== 'speaking') {
    setVoiceState('speaking')
  } else if (audioState === 'idle' && voiceState === 'speaking') {
    setVoiceState(vadActive ? 'listening' : 'idle')
  }

  const addMessage = useCallback((role: 'user' | 'assistant', text: string) => {
    setMessages(prev => [...prev, { id: crypto.randomUUID(), role, text, timestamp: new Date() }])
  }, [])

  const { connectionState, sendAudio, sendEndOfSpeech, sendBargeIn, sendLanguage } = useVoiceWebSocket({
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
    onAnswerDone: () => {
      setMessages(prev => prev.map(m => m.streaming ? { ...m, streaming: false } : m))
      if (audioState !== 'playing') {
        setVoiceState(vadActive ? 'listening' : 'idle')
      }
    },
    onAudio: (audio) => {
      enqueueAudio(audio)
    },
    onLanguageChanged: (lang) => setLanguage(lang as Language),
    onError: (error) => { console.error('Voice error:', error); setVoiceState(vadActive ? 'listening' : 'idle'); clearAudioQueue() },
  })

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

  const handleMicToggle = async () => {
    if (vadActive) {
      stopVAD()
      setVadActive(false)
      setVoiceState('idle')
    } else {
      await startVAD()
      setVadActive(true)
      setVoiceState('listening')
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
      const data = await response.json()
      addMessage('assistant', data.answer)
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
      <Header
        connectionState={connectionState}
        language={language}
        t={t}
        onLanguageChange={handleLanguageChange}
      />
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

function Header({ connectionState, language, t, onLanguageChange }: {
  connectionState: string; language: Language; t: Labels; onLanguageChange: (l: Language) => void
}) {
  return (
    <div className="px-4 py-2 flex items-center justify-between text-sm" style={{ borderBottom: '1px solid var(--color-border)' }}>
      <div className="flex items-center gap-2">
        <span className="w-2 h-2 rounded-full" aria-hidden="true" style={{
          backgroundColor: connectionState === 'connected' ? 'var(--color-success)' : 'var(--color-danger)'
        }} />
        <span style={{ color: 'var(--color-text-muted)' }}>{connectionState === 'connected' ? t.connected : t.disconnected}</span>
      </div>
      <div className="flex items-center gap-1 rounded-full p-0.5" role="group" aria-label="Language selection" style={{ backgroundColor: 'var(--color-border)' }}>
        {(['fr', 'en'] as const).map(lang => (
          <button
            key={lang}
            onClick={() => onLanguageChange(lang)}
            className="px-2.5 py-1 rounded-full text-xs font-medium transition-colors"
            aria-pressed={language === lang}
            style={{
              backgroundColor: language === lang ? 'var(--color-primary)' : 'transparent',
              color: language === lang ? 'white' : 'var(--color-text-muted)',
            }}
          >{lang.toUpperCase()}</button>
        ))}
      </div>
    </div>
  )
}
