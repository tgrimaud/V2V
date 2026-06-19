import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useVoiceWebSocket } from '../useVoiceWebSocket'

class MockWebSocket {
  static OPEN = 1
  static CONNECTING = 0
  static CLOSED = 3

  readyState = MockWebSocket.OPEN
  binaryType = ''
  onopen: (() => void) | null = null
  onmessage: ((event: { data: unknown }) => void) | null = null
  onerror: (() => void) | null = null
  onclose: (() => void) | null = null
  sentMessages: unknown[] = []

  send(data: unknown) {
    this.sentMessages.push(data)
  }

  close() {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.()
  }

  simulateOpen() {
    this.onopen?.()
  }

  simulateMessage(data: unknown) {
    this.onmessage?.({ data })
  }
}

let mockWsInstance: MockWebSocket

beforeEach(() => {
  vi.unstubAllGlobals()
  mockWsInstance = new MockWebSocket()
  vi.stubGlobal('WebSocket', class extends MockWebSocket {
    constructor() {
      super()
      Object.assign(mockWsInstance, this)
      Object.setPrototypeOf(mockWsInstance, Object.getPrototypeOf(this))
      return mockWsInstance
    }
  })
})

describe('useVoiceWebSocket', () => {
  const defaultOptions = {
    onTranscription: vi.fn(),
    onAnswer: vi.fn(),
    onAudio: vi.fn(),
    onError: vi.fn(),
    onLanguageChanged: vi.fn(),
  }

  it('connects on mount and sets state to connected', () => {
    const { result } = renderHook(() => useVoiceWebSocket(defaultOptions))

    act(() => mockWsInstance.simulateOpen())

    expect(result.current.connectionState).toBe('connected')
  })

  it('dispatches transcription messages to onTranscription', () => {
    renderHook(() => useVoiceWebSocket(defaultOptions))
    act(() => mockWsInstance.simulateOpen())

    act(() => {
      mockWsInstance.simulateMessage(JSON.stringify({ type: 'transcription', text: 'Bonjour' }))
    })

    expect(defaultOptions.onTranscription).toHaveBeenCalledWith('Bonjour')
  })

  it('dispatches answer messages to onAnswer', () => {
    renderHook(() => useVoiceWebSocket(defaultOptions))
    act(() => mockWsInstance.simulateOpen())

    act(() => {
      mockWsInstance.simulateMessage(JSON.stringify({ type: 'answer', text: 'Réponse' }))
    })

    expect(defaultOptions.onAnswer).toHaveBeenCalledWith('Réponse')
  })

  it('dispatches binary messages to onAudio', () => {
    renderHook(() => useVoiceWebSocket(defaultOptions))
    act(() => mockWsInstance.simulateOpen())

    const audioData = new ArrayBuffer(100)
    act(() => mockWsInstance.simulateMessage(audioData))

    expect(defaultOptions.onAudio).toHaveBeenCalledWith(audioData)
  })

  it('sendLanguage sends set_language JSON message', () => {
    const { result } = renderHook(() => useVoiceWebSocket(defaultOptions))
    act(() => mockWsInstance.simulateOpen())

    act(() => result.current.sendLanguage('en'))

    expect(mockWsInstance.sentMessages).toContainEqual(
      JSON.stringify({ type: 'set_language', language: 'en' })
    )
  })

  it('sendEndOfSpeech sends END_OF_SPEECH string', () => {
    const { result } = renderHook(() => useVoiceWebSocket(defaultOptions))
    act(() => mockWsInstance.simulateOpen())

    act(() => result.current.sendEndOfSpeech())

    expect(mockWsInstance.sentMessages).toContain('END_OF_SPEECH')
  })

  it('sets state to disconnected on close', () => {
    const { result } = renderHook(() => useVoiceWebSocket(defaultOptions))
    act(() => mockWsInstance.simulateOpen())

    act(() => mockWsInstance.close())

    expect(result.current.connectionState).toBe('disconnected')
  })
})
