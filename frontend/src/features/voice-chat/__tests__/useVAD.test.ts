import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useVAD } from '../useVAD'

const mockVADInstance = {
  start: vi.fn(),
  pause: vi.fn(),
  destroy: vi.fn(),
}

vi.mock('@ricky0123/vad-web', () => ({
  MicVAD: {
    new: vi.fn(() => Promise.resolve(mockVADInstance)),
  },
}))

beforeEach(() => {
  mockVADInstance.start.mockClear()
  mockVADInstance.pause.mockClear()
  mockVADInstance.destroy.mockClear()
})

describe('useVAD', () => {
  const defaultOptions = {
    onSpeechStart: vi.fn(),
    onSpeechEnd: vi.fn(),
    onSpeechEndComplete: vi.fn(),
  }

  it('should_start_in_off_state', () => {
    // GIVEN
    const { result } = renderHook(() => useVAD(defaultOptions))

    // THEN
    expect(result.current.state).toBe('off')
  })

  it('should_transition_to_listening_after_start', async () => {
    // GIVEN
    const { result } = renderHook(() => useVAD(defaultOptions))

    // WHEN
    await act(async () => { await result.current.start() })

    // THEN
    expect(result.current.state).toBe('listening')
    expect(mockVADInstance.start).toHaveBeenCalled()
  })

  it('should_transition_to_off_after_stop', async () => {
    // GIVEN
    const { result } = renderHook(() => useVAD(defaultOptions))
    await act(async () => { await result.current.start() })

    // WHEN
    act(() => result.current.stop())

    // THEN
    expect(result.current.state).toBe('off')
    expect(mockVADInstance.pause).toHaveBeenCalled()
    expect(mockVADInstance.destroy).toHaveBeenCalled()
  })

  it('should_reset_to_listening_state', async () => {
    // GIVEN
    const { result } = renderHook(() => useVAD(defaultOptions))
    await act(async () => { await result.current.start() })

    // WHEN
    act(() => result.current.resetToListening())

    // THEN
    expect(result.current.state).toBe('listening')
  })

  it('should_not_create_duplicate_vad_on_double_start', async () => {
    // GIVEN
    const { MicVAD } = await import('@ricky0123/vad-web')
    const { result } = renderHook(() => useVAD(defaultOptions))
    await act(async () => { await result.current.start() })
    const callCount = vi.mocked(MicVAD.new).mock.calls.length

    // WHEN
    await act(async () => { await result.current.start() })

    // THEN — MicVAD.new not called again
    expect(vi.mocked(MicVAD.new).mock.calls.length).toBe(callCount)
  })
})
