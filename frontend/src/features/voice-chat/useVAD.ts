import { useRef, useCallback, useState, useEffect } from 'react'
import { MicVAD } from '@ricky0123/vad-web'

export type VADState = 'off' | 'listening' | 'speaking' | 'processing'

interface UseVADOptions {
  onSpeechStart?: () => void
  onSpeechEnd: (audioData: ArrayBuffer) => void
  onSpeechEndComplete: () => void
}

export function useVAD(options: UseVADOptions) {
  const [state, setState] = useState<VADState>('off')
  const vadRef = useRef<MicVAD | null>(null)
  const optionsRef = useRef(options)
  optionsRef.current = options

  const start = useCallback(async () => {
    if (vadRef.current) return

    try {
      const vad = await MicVAD.new({
        baseAssetPath: '/',
        onnxWASMBasePath: 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.27.0/dist/',
        model: 'v5',
        startOnLoad: false,
        redemptionMs: 300,
        onSpeechStart: () => {
          setState('speaking')
          optionsRef.current.onSpeechStart?.()
        },
        onSpeechEnd: (audio: Float32Array) => {
          setState('processing')
          const int16 = float32ToInt16(audio)
          optionsRef.current.onSpeechEnd(int16.buffer)
          optionsRef.current.onSpeechEndComplete()
        },
      })

      vadRef.current = vad
      vad.start()
      setState('listening')
    } catch (error) {
      console.error('[VAD] Failed to initialize:', error)
      setState('off')
    }
  }, [])

  const stop = useCallback(() => {
    if (vadRef.current) {
      vadRef.current.pause()
      vadRef.current.destroy()
      vadRef.current = null
    }
    setState('off')
  }, [])

  const resetToListening = useCallback(() => {
    setState('listening')
  }, [])

  useEffect(() => {
    return () => {
      if (vadRef.current) {
        vadRef.current.pause()
        vadRef.current.destroy()
        vadRef.current = null
      }
    }
  }, [])

  return { state, start, stop, resetToListening }
}

function float32ToInt16(float32: Float32Array): Int16Array {
  const int16 = new Int16Array(float32.length)
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i] ?? 0))
    int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF
  }
  return int16
}
