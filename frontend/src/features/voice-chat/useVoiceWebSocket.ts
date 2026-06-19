import { useState, useRef, useCallback, useEffect } from 'react'

type ConnectionState = 'disconnected' | 'connected' | 'error'

interface UseVoiceWebSocketOptions {
  onTranscription: (text: string) => void
  onAnswer: (text: string) => void
  onAudio: (audio: ArrayBuffer) => void
  onError: (error: string) => void
  onLanguageChanged?: (language: string) => void
}

export function useVoiceWebSocket(options: UseVoiceWebSocketOptions) {
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected')
  const wsRef = useRef<WebSocket | null>(null)
  const optionsRef = useRef(options)
  optionsRef.current = options
  const pendingLanguageRef = useRef<string | null>(null)

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN || wsRef.current?.readyState === WebSocket.CONNECTING) {
      return
    }

    const voiceAgentUrl = import.meta.env.VITE_VOICE_AGENT_URL ?? 'ws://localhost:8765'

    const ws = new WebSocket(voiceAgentUrl)
    ws.binaryType = 'arraybuffer'

    ws.onopen = () => {
      setConnectionState('connected')
      if (pendingLanguageRef.current) {
        ws.send(JSON.stringify({ type: 'set_language', language: pendingLanguageRef.current }))
      }
    }

    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        optionsRef.current.onAudio(event.data)
      } else {
        try {
          const message = JSON.parse(event.data)
          if (message.type === 'transcription') {
            optionsRef.current.onTranscription(message.text)
          } else if (message.type === 'answer') {
            optionsRef.current.onAnswer(message.text)
          } else if (message.type === 'language_changed') {
            optionsRef.current.onLanguageChanged?.(message.language)
          } else if (message.error) {
            optionsRef.current.onError(message.error)
          }
        } catch {
          optionsRef.current.onError('Failed to parse server message')
        }
      }
    }

    ws.onerror = () => {
      setConnectionState('error')
      optionsRef.current.onError('WebSocket connection error')
    }

    ws.onclose = () => {
      setConnectionState('disconnected')
    }

    wsRef.current = ws
  }, [])

  const disconnect = useCallback(() => {
    wsRef.current?.close()
    wsRef.current = null
    setConnectionState('disconnected')
  }, [])

  const sendAudio = useCallback((data: ArrayBuffer) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(data)
    }
  }, [])

  const sendEndOfSpeech = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send('END_OF_SPEECH')
    }
  }, [])

  const sendLanguage = useCallback((language: string) => {
    pendingLanguageRef.current = language
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'set_language', language }))
    }
  }, [])

  useEffect(() => {
    connect()
    return () => disconnect()
  }, [connect, disconnect])

  return { connectionState, connect, disconnect, sendAudio, sendEndOfSpeech, sendLanguage }
}
