import { useState, useRef, useCallback } from 'react'

type ConnectionState = 'disconnected' | 'connected' | 'error'

interface UseVoiceWebSocketOptions {
  onTranscription: (text: string) => void
  onAnswer: (text: string) => void
  onAudio: (audio: ArrayBuffer) => void
  onError: (error: string) => void
}

export function useVoiceWebSocket(options: UseVoiceWebSocketOptions) {
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected')
  const wsRef = useRef<WebSocket | null>(null)

  const connect = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws/voice`

    const ws = new WebSocket(wsUrl)
    ws.binaryType = 'arraybuffer'

    ws.onopen = () => {
      setConnectionState('connected')
    }

    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        options.onAudio(event.data)
      } else {
        try {
          const message = JSON.parse(event.data)
          if (message.type === 'transcription') {
            options.onTranscription(message.text)
          } else if (message.type === 'answer') {
            options.onAnswer(message.text)
          } else if (message.error) {
            options.onError(message.error)
          }
        } catch {
          options.onError('Failed to parse server message')
        }
      }
    }

    ws.onerror = () => {
      setConnectionState('error')
      options.onError('WebSocket connection error')
    }

    ws.onclose = () => {
      setConnectionState('disconnected')
    }

    wsRef.current = ws
  }, [options])

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

  return { connectionState, connect, disconnect, sendAudio, sendEndOfSpeech }
}
