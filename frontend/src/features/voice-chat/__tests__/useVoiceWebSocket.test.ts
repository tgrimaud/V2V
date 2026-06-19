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

  send(data: unknown) { this.sentMessages.push(data) }
  close() { this.readyState = MockWebSocket.CLOSED; this.onclose?.() }
  simulateOpen() { this.onopen?.() }
  simulateMessage(data: unknown) { this.onmessage?.({ data }) }
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
    onAnswerChunk: vi.fn(),
    onAnswerDone: vi.fn(),
    onAudio: vi.fn(),
    onError: vi.fn(),
    onLanguageChanged: vi.fn(),
  }

  it('should_set_connected_state_when_ws_opens', () => {
    // GIVEN
    const { result } = renderHook(() => useVoiceWebSocket(defaultOptions))

    // WHEN
    act(() => mockWsInstance.simulateOpen())

    // THEN
    expect(result.current.connectionState).toBe('connected')
  })

  it('should_dispatch_transcription_to_callback', () => {
    // GIVEN
    renderHook(() => useVoiceWebSocket(defaultOptions))
    act(() => mockWsInstance.simulateOpen())

    // WHEN
    act(() => mockWsInstance.simulateMessage(JSON.stringify({ type: 'transcription', text: 'Bonjour' })))

    // THEN
    expect(defaultOptions.onTranscription).toHaveBeenCalledWith('Bonjour')
  })

  it('should_dispatch_answer_to_callback', () => {
    // GIVEN
    renderHook(() => useVoiceWebSocket(defaultOptions))
    act(() => mockWsInstance.simulateOpen())

    // WHEN
    act(() => mockWsInstance.simulateMessage(JSON.stringify({ type: 'answer', text: 'Réponse' })))

    // THEN
    expect(defaultOptions.onAnswer).toHaveBeenCalledWith('Réponse')
  })

  it('should_dispatch_binary_audio_to_callback', () => {
    // GIVEN
    renderHook(() => useVoiceWebSocket(defaultOptions))
    act(() => mockWsInstance.simulateOpen())
    const audioData = new ArrayBuffer(100)

    // WHEN
    act(() => mockWsInstance.simulateMessage(audioData))

    // THEN
    expect(defaultOptions.onAudio).toHaveBeenCalledWith(audioData)
  })

  it('should_send_set_language_json_and_store_pending', () => {
    // GIVEN
    const { result } = renderHook(() => useVoiceWebSocket(defaultOptions))
    act(() => mockWsInstance.simulateOpen())

    // WHEN
    act(() => result.current.sendLanguage('en'))

    // THEN
    expect(mockWsInstance.sentMessages).toContainEqual(
      JSON.stringify({ type: 'set_language', language: 'en' })
    )
  })

  it('should_resend_language_on_reconnect', () => {
    // GIVEN
    const { result } = renderHook(() => useVoiceWebSocket(defaultOptions))
    act(() => mockWsInstance.simulateOpen())
    act(() => result.current.sendLanguage('en'))
    mockWsInstance.sentMessages = []

    // WHEN — simulate reconnection (new onopen)
    act(() => mockWsInstance.simulateOpen())

    // THEN
    expect(mockWsInstance.sentMessages).toContainEqual(
      JSON.stringify({ type: 'set_language', language: 'en' })
    )
  })

  it('should_send_END_OF_SPEECH_string', () => {
    // GIVEN
    const { result } = renderHook(() => useVoiceWebSocket(defaultOptions))
    act(() => mockWsInstance.simulateOpen())

    // WHEN
    act(() => result.current.sendEndOfSpeech())

    // THEN
    expect(mockWsInstance.sentMessages).toContain('END_OF_SPEECH')
  })

  it('should_set_disconnected_state_on_close', () => {
    // GIVEN
    const { result } = renderHook(() => useVoiceWebSocket(defaultOptions))
    act(() => mockWsInstance.simulateOpen())

    // WHEN
    act(() => mockWsInstance.close())

    // THEN
    expect(result.current.connectionState).toBe('disconnected')
  })

  it('should_dispatch_answer_chunk_to_callback', () => {
    // GIVEN
    renderHook(() => useVoiceWebSocket(defaultOptions))
    act(() => mockWsInstance.simulateOpen())

    // WHEN
    act(() => mockWsInstance.simulateMessage(JSON.stringify({ type: 'answer_chunk', text: 'Bonjour, ' })))

    // THEN
    expect(defaultOptions.onAnswerChunk).toHaveBeenCalledWith('Bonjour, ')
  })

  it('should_dispatch_answer_done_to_callback', () => {
    // GIVEN
    renderHook(() => useVoiceWebSocket(defaultOptions))
    act(() => mockWsInstance.simulateOpen())

    // WHEN
    act(() => mockWsInstance.simulateMessage(JSON.stringify({ type: 'answer_done', text: 'Full answer.' })))

    // THEN
    expect(defaultOptions.onAnswerDone).toHaveBeenCalledWith('Full answer.')
  })
})
