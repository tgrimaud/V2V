import { useState, useRef, useCallback } from 'react'

export type RecordingState = 'idle' | 'recording' | 'processing'

interface UseAudioRecorderOptions {
  onAudioData: (data: ArrayBuffer) => void
  onRecordingComplete: () => void
}

export function useAudioRecorder(options: UseAudioRecorderOptions) {
  const [state, setState] = useState<RecordingState>('idle')
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true }
      })
      streamRef.current = stream

      const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' })
      mediaRecorderRef.current = mediaRecorder
      chunksRef.current = []

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data)
        }
      }

      mediaRecorder.onstop = async () => {
        setState('processing')
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        const buffer = await blob.arrayBuffer()
        options.onAudioData(buffer)
        options.onRecordingComplete()
      }

      mediaRecorder.start(100)
      setState('recording')
    } catch (error) {
      console.error('Failed to start recording:', error)
      setState('idle')
    }
  }, [options])

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop()
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop())
      streamRef.current = null
    }
  }, [])

  const reset = useCallback(() => {
    setState('idle')
  }, [])

  return { state, startRecording, stopRecording, reset }
}
