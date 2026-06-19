import { useState, useRef, useCallback } from 'react'

export type RecordingState = 'idle' | 'recording' | 'processing'

interface UseAudioRecorderOptions {
  onAudioData: (data: ArrayBuffer) => void
  onRecordingComplete: () => void
}

export function useAudioRecorder(options: UseAudioRecorderOptions) {
  const [state, setState] = useState<RecordingState>('idle')
  const streamRef = useRef<MediaStream | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const processorRef = useRef<ScriptProcessorNode | null>(null)
  const chunksRef = useRef<Int16Array[]>([])
  const optionsRef = useRef(options)
  optionsRef.current = options

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true }
      })
      streamRef.current = stream

      const audioContext = new AudioContext({ sampleRate: 16000 })
      audioContextRef.current = audioContext

      const source = audioContext.createMediaStreamSource(stream)
      const processor = audioContext.createScriptProcessor(4096, 1, 1)
      processorRef.current = processor
      chunksRef.current = []

      processor.onaudioprocess = (event) => {
        const float32 = event.inputBuffer.getChannelData(0)
        const int16 = new Int16Array(float32.length)
        for (let i = 0; i < float32.length; i++) {
          const s = Math.max(-1, Math.min(1, float32[i]))
          int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF
        }
        chunksRef.current.push(int16)
      }

      source.connect(processor)
      processor.connect(audioContext.destination)
      setState('recording')
    } catch (error) {
      console.error('Failed to start recording:', error)
      setState('idle')
    }
  }, [])

  const stopRecording = useCallback(() => {
    if (processorRef.current) {
      processorRef.current.disconnect()
      processorRef.current = null
    }
    if (audioContextRef.current) {
      audioContextRef.current.close()
      audioContextRef.current = null
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop())
      streamRef.current = null
    }

    setState('processing')

    const totalLength = chunksRef.current.reduce((acc, c) => acc + c.length, 0)
    const pcm = new Int16Array(totalLength)
    let offset = 0
    for (const chunk of chunksRef.current) {
      pcm.set(chunk, offset)
      offset += chunk.length
    }
    chunksRef.current = []

    optionsRef.current.onAudioData(pcm.buffer)
    optionsRef.current.onRecordingComplete()
  }, [])

  const reset = useCallback(() => {
    setState('idle')
  }, [])

  return { state, startRecording, stopRecording, reset }
}
