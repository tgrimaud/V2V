import { useRef, useCallback, useState } from 'react'

type QueueState = 'idle' | 'playing'

export function useAudioQueue() {
  const [state, setState] = useState<QueueState>('idle')
  const audioContextRef = useRef<AudioContext | null>(null)
  const queueRef = useRef<ArrayBuffer[]>([])
  const playingRef = useRef(false)

  const getAudioContext = useCallback(() => {
    if (!audioContextRef.current) {
      audioContextRef.current = new AudioContext()
    }
    return audioContextRef.current
  }, [])

  const playNext = useCallback(async () => {
    if (queueRef.current.length === 0) {
      playingRef.current = false
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
      source.buffer = decoded
      source.connect(ctx.destination)
      source.onended = () => playNext()
      source.start()
    } catch {
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
    playingRef.current = false
    setState('idle')
  }, [])

  return { enqueue, clear, state }
}
