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

  it('starts in idle state', () => {
    const { result } = renderHook(() => useAudioRecorder(defaultOptions))
    expect(result.current.state).toBe('idle')
  })

  it('transitions to recording state after startRecording', async () => {
    const { result } = renderHook(() => useAudioRecorder(defaultOptions))

    await act(async () => {
      await result.current.startRecording()
    })

    expect(result.current.state).toBe('recording')
  })

  it('transitions to processing and calls onAudioData on stopRecording', async () => {
    const { result } = renderHook(() => useAudioRecorder(defaultOptions))

    await act(async () => {
      await result.current.startRecording()
    })

    act(() => result.current.stopRecording())

    expect(result.current.state).toBe('processing')
    expect(defaultOptions.onAudioData).toHaveBeenCalled()
    expect(defaultOptions.onRecordingComplete).toHaveBeenCalled()
  })

  it('resets state to idle', async () => {
    const { result } = renderHook(() => useAudioRecorder(defaultOptions))

    await act(async () => {
      await result.current.startRecording()
    })
    act(() => result.current.stopRecording())
    act(() => result.current.reset())

    expect(result.current.state).toBe('idle')
  })

  it('stops media tracks and closes audio context on stop', async () => {
    const { result } = renderHook(() => useAudioRecorder(defaultOptions))

    await act(async () => {
      await result.current.startRecording()
    })
    act(() => result.current.stopRecording())

    expect(mockTrack.stop).toHaveBeenCalled()
    expect(mockClose).toHaveBeenCalled()
    expect(mockProcessorNode.disconnect).toHaveBeenCalled()
  })
})
