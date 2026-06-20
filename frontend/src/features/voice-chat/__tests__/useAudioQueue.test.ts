import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useAudioQueue } from '../useAudioQueue'

const mockBufferSource = {
  buffer: null as AudioBuffer | null,
  connect: vi.fn(),
  start: vi.fn(),
  stop: vi.fn(),
  onended: null as (() => void) | null,
}

const mockDecodeAudioData = vi.fn()

beforeEach(() => {
  vi.unstubAllGlobals()
  mockBufferSource.connect.mockClear()
  mockBufferSource.start.mockClear()
  mockBufferSource.stop.mockClear()
  mockBufferSource.onended = null
  mockDecodeAudioData.mockReset()

  class FakeAudioContext {
    state = 'running'
    destination = {}
    resume = vi.fn(() => Promise.resolve())
    decodeAudioData = mockDecodeAudioData.mockResolvedValue({ duration: 1 } as AudioBuffer)
    createBufferSource = vi.fn(() => ({ ...mockBufferSource, onended: null }))
  }

  vi.stubGlobal('AudioContext', FakeAudioContext)
})

describe('useAudioQueue', () => {
  it('should_start_in_idle_state', () => {
    // GIVEN
    const { result } = renderHook(() => useAudioQueue())

    // THEN
    expect(result.current.state).toBe('idle')
  })

  it('should_clear_queue_and_reset_state', async () => {
    // GIVEN
    const { result } = renderHook(() => useAudioQueue())
    const buffer = new ArrayBuffer(10)

    // WHEN
    await act(async () => { result.current.enqueue(buffer) })
    act(() => result.current.clear())

    // THEN
    expect(result.current.state).toBe('idle')
  })

  it('should_flush_queue_and_stop_current_source', async () => {
    // GIVEN
    const { result } = renderHook(() => useAudioQueue())
    const buffer = new ArrayBuffer(10)

    // WHEN
    await act(async () => { result.current.enqueue(buffer) })
    act(() => result.current.flush())

    // THEN
    expect(result.current.state).toBe('idle')
  })
})
