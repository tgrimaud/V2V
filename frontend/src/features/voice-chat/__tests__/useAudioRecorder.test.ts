import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useAudioRecorder } from '../useAudioRecorder'

const mockTrack = { stop: vi.fn() }
const mockStream = { getTracks: () => [mockTrack] }

const mockProcessorNode = {
  onaudioprocess: null as ((e: unknown) => void) | null,
  connect: vi.fn(),
  disconnect: vi.fn(),
}

const mockSourceNode = { connect: vi.fn() }
const mockClose = vi.fn()

beforeEach(() => {
  vi.unstubAllGlobals()

  class FakeAudioContext {
    sampleRate = 48000
    destination = {}
    createMediaStreamSource = vi.fn(() => mockSourceNode)
    createScriptProcessor = vi.fn(() => mockProcessorNode)
    close = mockClose
  }

  vi.stubGlobal('AudioContext', FakeAudioContext)
  Object.defineProperty(navigator, 'mediaDevices', {
    value: { getUserMedia: vi.fn(() => Promise.resolve(mockStream)) },
    configurable: true,
  })
  mockTrack.stop.mockClear()
  mockClose.mockClear()
  mockProcessorNode.disconnect.mockClear()
  mockProcessorNode.connect.mockClear()
  mockSourceNode.connect.mockClear()
})

describe('useAudioRecorder', () => {
  const defaultOptions = {
    onAudioData: vi.fn(),
    onRecordingComplete: vi.fn(),
  }

  it('should_start_in_idle_state', () => {
    // GIVEN
    const { result } = renderHook(() => useAudioRecorder(defaultOptions))

    // THEN
    expect(result.current.state).toBe('idle')
  })

  it('should_transition_to_recording_after_start', async () => {
    // GIVEN
    const { result } = renderHook(() => useAudioRecorder(defaultOptions))

    // WHEN
    await act(async () => { await result.current.startRecording() })

    // THEN
    expect(result.current.state).toBe('recording')
  })

  it('should_transition_to_processing_and_emit_audio_on_stop', async () => {
    // GIVEN
    const { result } = renderHook(() => useAudioRecorder(defaultOptions))
    await act(async () => { await result.current.startRecording() })

    // WHEN
    act(() => result.current.stopRecording())

    // THEN
    expect(result.current.state).toBe('processing')
    expect(defaultOptions.onAudioData).toHaveBeenCalled()
    expect(defaultOptions.onRecordingComplete).toHaveBeenCalled()
  })

  it('should_reset_state_to_idle', async () => {
    // GIVEN
    const { result } = renderHook(() => useAudioRecorder(defaultOptions))
    await act(async () => { await result.current.startRecording() })
    act(() => result.current.stopRecording())

    // WHEN
    act(() => result.current.reset())

    // THEN
    expect(result.current.state).toBe('idle')
  })

  it('should_release_media_resources_on_stop', async () => {
    // GIVEN
    const { result } = renderHook(() => useAudioRecorder(defaultOptions))
    await act(async () => { await result.current.startRecording() })

    // WHEN
    act(() => result.current.stopRecording())

    // THEN
    expect(mockTrack.stop).toHaveBeenCalled()
    expect(mockClose).toHaveBeenCalled()
    expect(mockProcessorNode.disconnect).toHaveBeenCalled()
  })
})
