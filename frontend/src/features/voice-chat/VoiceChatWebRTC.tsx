import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ComponentProps } from 'react'
import { PipecatClient, RTVIEvent } from '@pipecat-ai/client-js'
import type { BotLLMTextData, TranscriptData } from '@pipecat-ai/client-js'
import { SmallWebRTCTransport } from '@pipecat-ai/small-webrtc-transport'
import {
  PipecatClientAudio,
  PipecatClientProvider,
  useRTVIClientEvent,
  usePipecatClient,
  usePipecatClientMicControl,
  usePipecatClientTransportState,
} from '@pipecat-ai/client-react'
import { MessageList } from './MessageList'
import { ChatHeader } from './ChatHeader'
import { ServiceErrorBanner } from './ServiceErrorBanner'
import { labels } from './i18n'
import type { Language } from './i18n'

const BOT_URL =
  (import.meta.env.VITE_BOT_URL as string | undefined) ?? 'http://localhost:7860'

interface UiMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  timestamp: Date
  agentName?: string
}

interface AgentNameMessage {
  type: 'agent_name'
  agent_name: string
}

function isAgentNameMessage(data: unknown): data is AgentNameMessage {
  return (
    typeof data === 'object' &&
    data !== null &&
    (data as { type?: unknown }).type === 'agent_name' &&
    typeof (data as { agent_name?: unknown }).agent_name === 'string'
  )
}

function newId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`
}

// The bot streams whole sentences as separate botLlmText events. Join them with
// a single space so they don't collide (e.g. "Bonjour.Pouvez-vous" → "Bonjour.
// Pouvez-vous"), while avoiding double spaces around existing whitespace.
function appendChunk(existing: string, chunk: string): string {
  if (!existing) return chunk
  const needsSpace = !/\s$/.test(existing) && !/^\s/.test(chunk)
  return needsSpace ? `${existing} ${chunk}` : `${existing}${chunk}`
}

/**
 * Strategy B client: drives the unified Pipecat bot (agent/bot.py) over WebRTC.
 *
 * Unlike strategy A (the WebSocket bridge), the Pipecat transport owns the mic
 * capture, server-side Silero VAD/endpointing and bot-audio playback. We only
 * render the connection lifecycle and the merged conversation stream.
 */
export function VoiceChatWebRTC() {
  const client = useMemo(
    () =>
      new PipecatClient({
        transport: new SmallWebRTCTransport(),
        enableMic: true,
        enableCam: false,
      }),
    [],
  )

  useEffect(() => {
    return () => {
      void client.disconnect()
    }
  }, [client])

  // client-react (built with Parcel) inlines its own copy of the client-js
  // types, so its `PipecatClient` is nominally distinct from the one we import
  // from @pipecat-ai/client-js. Cast to the exact prop type the provider
  // expects rather than to `never`, keeping the rest of the call site typed.
  type ProviderClient = ComponentProps<typeof PipecatClientProvider>['client']

  return (
    <PipecatClientProvider client={client as unknown as ProviderClient}>
      <VoiceChatWebRTCInner />
      <PipecatClientAudio />
    </PipecatClientProvider>
  )
}

function VoiceChatWebRTCInner() {
  const client = usePipecatClient()
  const transportState = usePipecatClientTransportState()
  const { enableMic, isMicEnabled } = usePipecatClientMicControl()

  const [language, setLanguage] = useState<Language>('fr')
  const [error, setError] = useState<string | null>(null)
  const [messages, setMessages] = useState<UiMessage[]>([])
  // id of the assistant bubble currently being streamed (between
  // botLlmStarted and botLlmStopped). null when no answer is in flight.
  const activeAssistantId = useRef<string | null>(null)
  // agent name received (via server message) before its bubble exists; applied
  // to the next assistant bubble that opens.
  const pendingAgentName = useRef<string | null>(null)
  const t = labels[language]

  const isConnected = transportState === 'connected' || transportState === 'ready'
  const isConnecting =
    transportState === 'connecting' ||
    transportState === 'authenticating' ||
    transportState === 'initializing'

  // Build one chat bubble per turn from discrete RTVI events. Using the raw
  // events (rather than usePipecatConversation, which merges consecutive
  // same-role turns into a single bubble) keeps every user utterance and every
  // assistant answer as its own message.
  const handleUserTranscript = useCallback((data: TranscriptData) => {
    if (!data.final) return
    const text = data.text.trim()
    if (!text) return
    // A new user turn closes any assistant bubble still marked active.
    activeAssistantId.current = null
    setMessages(prev => {
      // Drop a trailing empty assistant bubble left by a barge-in that cut the
      // bot off before its first word (no LLMFullResponseEnd was emitted).
      const last = prev[prev.length - 1]
      const pruned =
        last && last.role === 'assistant' && last.text.length === 0
          ? prev.slice(0, -1)
          : prev
      return [...pruned, { id: newId(), role: 'user', text, timestamp: new Date() }]
    })
  }, [])

  const handleBotStarted = useCallback(() => {
    const id = newId()
    activeAssistantId.current = id
    const agentName = pendingAgentName.current ?? undefined
    pendingAgentName.current = null
    setMessages(prev => [
      ...prev,
      { id, role: 'assistant', text: '', timestamp: new Date(), agentName },
    ])
  }, [])

  // The bot forwards the routed agent (Facturation / Support / Commercial) as a
  // server message; attach it to the active assistant bubble so MessageList can
  // render the same colored agent badge as strategy A.
  const handleServerMessage = useCallback((data: unknown) => {
    if (!isAgentNameMessage(data)) return
    const agentName = data.agent_name
    const id = activeAssistantId.current
    setMessages(prev => {
      if (id && prev.some(m => m.id === id)) {
        return prev.map(m => (m.id === id ? { ...m, agentName } : m))
      }
      pendingAgentName.current = agentName
      return prev
    })
  }, [])

  const handleBotText = useCallback((data: BotLLMTextData) => {
    const chunk = data.text
    if (!chunk) return
    const id = activeAssistantId.current
    setMessages(prev => {
      if (id) {
        return prev.map(m =>
          m.id === id ? { ...m, text: appendChunk(m.text, chunk) } : m,
        )
      }
      // Safety net: text without a preceding botLlmStarted.
      const newAssistantId = newId()
      activeAssistantId.current = newAssistantId
      return [
        ...prev,
        { id: newAssistantId, role: 'assistant', text: chunk, timestamp: new Date() },
      ]
    })
  }, [])

  const handleBotStopped = useCallback(() => {
    activeAssistantId.current = null
  }, [])

  useRTVIClientEvent(RTVIEvent.UserTranscript, handleUserTranscript)
  useRTVIClientEvent(RTVIEvent.BotLlmStarted, handleBotStarted)
  useRTVIClientEvent(RTVIEvent.BotLlmText, handleBotText)
  useRTVIClientEvent(RTVIEvent.BotLlmStopped, handleBotStopped)
  useRTVIClientEvent(RTVIEvent.ServerMessage, handleServerMessage)

  const handleConnect = useCallback(async () => {
    setError(null)
    setMessages([])
    activeAssistantId.current = null
    pendingAgentName.current = null
    try {
      await client?.connect({ webrtcUrl: `${BOT_URL}/api/offer` })
    } catch (err) {
      console.error('WebRTC connect failed:', err)
      setError(
        language === 'fr'
          ? `Connexion au bot impossible (${BOT_URL}). Vérifiez qu'il tourne sur le port 7860.`
          : `Cannot connect to the bot (${BOT_URL}). Check it is running on port 7860.`,
      )
    }
  }, [client, language])

  const handleDisconnect = useCallback(async () => {
    try {
      await client?.disconnect()
    } catch (err) {
      console.error('WebRTC disconnect failed:', err)
    }
  }, [client])

  const statusLabel = (() => {
    if (isConnected) return language === 'fr' ? 'En conversation' : 'In conversation'
    if (isConnecting) return language === 'fr' ? 'Connexion...' : 'Connecting...'
    if (transportState === 'error') return language === 'fr' ? 'Erreur' : 'Error'
    return language === 'fr' ? 'Déconnecté' : 'Disconnected'
  })()

  return (
    <div
      className="rounded-2xl shadow-lg overflow-hidden"
      style={{ backgroundColor: 'var(--color-surface)' }}
    >
      <ChatHeader
        connected={isConnected}
        statusLabel={statusLabel}
        language={language}
        t={t}
        onLanguageChange={setLanguage}
      />

      {error && (
        <ServiceErrorBanner message={error} onDismiss={() => setError(null)} />
      )}

      <MessageList messages={messages} greeting={t.greeting} hint={t.hint} />

      <div className="p-4" style={{ borderTop: '1px solid var(--color-border)' }}>
        <div className="flex flex-col items-center gap-3">
          {!isConnected ? (
            <button
              onClick={handleConnect}
              disabled={isConnecting}
              className="px-6 py-3 rounded-full text-sm font-medium text-white transition-transform hover:scale-105 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed"
              style={{ backgroundColor: 'var(--color-primary)' }}
            >
              <span aria-hidden="true">🎙️ </span>
              {isConnecting
                ? language === 'fr'
                  ? 'Connexion...'
                  : 'Connecting...'
                : language === 'fr'
                  ? 'Démarrer la conversation'
                  : 'Start conversation'}
            </button>
          ) : (
            <div className="flex items-center gap-3">
              <button
                onClick={() => enableMic(!isMicEnabled)}
                className="w-14 h-14 rounded-full flex items-center justify-center text-white text-xl transition-transform hover:scale-105 active:scale-95"
                style={{
                  backgroundColor: isMicEnabled ? 'var(--color-success)' : 'var(--color-text-muted)',
                }}
                aria-label={
                  isMicEnabled
                    ? language === 'fr'
                      ? 'Couper le micro'
                      : 'Mute mic'
                    : language === 'fr'
                      ? 'Activer le micro'
                      : 'Unmute mic'
                }
                title={isMicEnabled ? 'Micro actif' : 'Micro coupé'}
              >
                <span aria-hidden="true">{isMicEnabled ? '🎤' : '🔇'}</span>
              </button>
              <button
                onClick={handleDisconnect}
                className="px-5 py-2 rounded-full text-sm font-medium text-white transition-transform hover:scale-105 active:scale-95"
                style={{ backgroundColor: 'var(--color-danger)' }}
              >
                {language === 'fr' ? 'Raccrocher' : 'Hang up'}
              </button>
            </div>
          )}
          <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            {statusLabel}
          </span>
          <span className="text-[11px]" style={{ color: 'var(--color-text-muted)' }}>
            {language === 'fr'
              ? 'Solution B · WebRTC (VAD serveur Silero, STT streaming)'
              : 'Strategy B · WebRTC (server Silero VAD, streaming STT)'}
          </span>
        </div>
      </div>
    </div>
  )
}

