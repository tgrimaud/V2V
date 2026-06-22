import { useRef, useCallback, useState } from 'react'

type QueueState = 'idle' | 'playing'

export function useAudioQueue() {
  const [state, setState] = useState<QueueState>('idle')
  const audioContextRef = useRef<AudioContext | null>(null)
  const queueRef = useRef<ArrayBuffer[]>([])
  const playingRef = useRef(false)
  const currentSourceRef = useRef<AudioBufferSourceNode | null>(null)

  const getAudioContext = useCallback(() => {
    if (!audioContextRef.current) {
      audioContextRef.current = new AudioContext()
    }
    return audioContextRef.current
  }, [])

  const playNext = useCallback(async () => {
    if (queueRef.current.length === 0) {
      playingRef.current = false
      currentSourceRef.current = null
      setState('idle')
      return
    }

    playingRef.current = true
    setState('playing')

    const buffer = queueRef.current.shift()!
    const ctx = getAudioContext()

    if (ctx.state === 'suspended') {
      await ctx.resume()
    }

    try {
      const decoded = await ctx.decodeAudioData(buffer)
      const source = ctx.createBufferSource()
      currentSourceRef.current = source
      source.buffer = decoded
      source.connect(ctx.destination)
      source.onended = () => {
        if (currentSourceRef.current === source) {
          currentSourceRef.current = null
        }
        playNext()
      }
      source.start()
    } catch {
      currentSourceRef.current = null
      playNext()
    }
  }, [getAudioContext])

  const enqueue = useCallback((audioBuffer: ArrayBuffer) => {
    queueRef.current.push(audioBuffer)
    if (!playingRef.current) {
      playNext()
    }
  }, [playNext])

  const clear = useCallback(() => {
    queueRef.current = []
    if (currentSourceRef.current) {
      try { currentSourceRef.current.stop() } catch { /* already stopped */ }
      currentSourceRef.current = null
    }
    playingRef.current = false
    setState('idle')
  }, [])

  const flush = useCallback(() => {
    queueRef.current = []
    if (currentSourceRef.current) {
      try { currentSourceRef.current.stop() } catch { /* already stopped */ }
      currentSourceRef.current = null
    }
    playingRef.current = false
    setState('idle')
  }, [])

  return { enqueue, clear, flush, state }
}
