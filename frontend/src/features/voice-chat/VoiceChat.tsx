import { useState, useCallback, useRef } from 'react'
import { useVoiceWebSocket } from './useVoiceWebSocket'
import { useAudioRecorder } from './useAudioRecorder'
import { MessageList } from './MessageList'
import { labels } from './i18n'
import type { Language } from './i18n'

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
  const [language, setLanguage] = useState<Language>('fr')
  const audioContextRef = useRef<AudioContext | null>(null)
  const answerTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const t = labels[language]

  const addMessage = useCallback((role: 'user' | 'assistant', text: string) => {
    setMessages(prev => [...prev, { id: crypto.randomUUID(), role, text, timestamp: new Date() }])
  }, [])

  const playAudio = useCallback(async (audioBuffer: ArrayBuffer) => {
    try {
      if (!audioContextRef.current) audioContextRef.current = new AudioContext()
      const ctx = audioContextRef.current
      if (ctx.state === 'suspended') await ctx.resume()
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
      answerTimeoutRef.current = setTimeout(() => {
        setVoiceState((cur) => cur === 'processing' ? 'idle' : cur)
      }, 500)
    },
    onAudio: (audio) => {
      if (answerTimeoutRef.current) {
        clearTimeout(answerTimeoutRef.current)
        answerTimeoutRef.current = null
      }
      playAudio(audio)
    },
    onLanguageChanged: (lang) => setLanguage(lang as Language),
    onError: (error) => { console.error('Voice error:', error); setVoiceState('idle') },
  })

  const { state: recorderState, startRecording, stopRecording, reset: resetRecorder } = useAudioRecorder({
    onAudioData: sendAudio,
    onRecordingComplete: () => { sendEndOfSpeech(); setVoiceState('processing') },
  })

  if (recorderState === 'recording' && voiceState !== 'recording') setVoiceState('recording')

  const handleLanguageChange = (lang: Language) => { setLanguage(lang); sendLanguage(lang) }

  const handleMicClick = () => {
    if (voiceState === 'recording') stopRecording()
    else if (voiceState === 'idle') startRecording()
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
      setVoiceState('idle')
      resetRecorder()
    }
  }

  const stateColor: Record<VoiceState, string> = {
    idle: 'var(--color-primary)', recording: 'var(--color-recording)',
    processing: 'var(--color-processing)', speaking: 'var(--color-speaking)',
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
          <button
            onClick={handleMicClick}
            disabled={voiceState === 'processing' || voiceState === 'speaking'}
            className="relative w-16 h-16 rounded-full flex items-center justify-center text-white text-2xl transition-transform hover:scale-105 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed"
            style={{ backgroundColor: stateColor[voiceState] }}
            aria-label={t[voiceState]}
          >
            {voiceState === 'recording' && (
              <span className="absolute inset-0 rounded-full" style={{ animation: 'pulse-ring 1.5s infinite', backgroundColor: stateColor[voiceState] }} />
            )}
            <span className="relative z-10" aria-hidden="true">
              {voiceState === 'recording' ? '⏹' : voiceState === 'processing' ? '⏳' : voiceState === 'speaking' ? '🔊' : '🎙️'}
            </span>
          </button>
          <span className="mt-2 text-xs" style={{ color: 'var(--color-text-muted)' }}>{t[voiceState]}</span>
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
  connectionState: string; language: Language; t: typeof labels['fr']; onLanguageChange: (l: Language) => void
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
