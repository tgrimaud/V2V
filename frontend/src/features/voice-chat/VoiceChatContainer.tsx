import { useState } from 'react'
import { VoiceChat } from './VoiceChat'
import { VoiceChatWebRTC } from './VoiceChatWebRTC'

type TransportMode = 'ws' | 'webrtc'

/**
 * Wraps the two channel-unification strategies behind a single toggle:
 *  - Strategy A (`ws`):     custom WebSocket bridge (`bridge_server`, :8765)
 *  - Strategy B (`webrtc`): unified Pipecat bot (`agent/bot.py`, :7860)
 *
 * Each strategy is a self-contained component so switching cleanly mounts /
 * unmounts it (respecting the rules of hooks and releasing the mic / peer
 * connection when leaving strategy B).
 */
export function VoiceChatContainer() {
  const [mode, setMode] = useState<TransportMode>('ws')

  return (
    <div>
      <div
        className="flex items-center gap-1 rounded-full p-0.5 mb-3 mx-auto w-fit"
        role="group"
        aria-label="Transport mode"
        style={{ backgroundColor: 'var(--color-border)' }}
      >
        <ModeButton active={mode === 'ws'} onClick={() => setMode('ws')} label="Solution A · WebSocket" />
        <ModeButton active={mode === 'webrtc'} onClick={() => setMode('webrtc')} label="Solution B · WebRTC" />
      </div>
      {mode === 'ws' ? <VoiceChat /> : <VoiceChatWebRTC />}
    </div>
  )
}

function ModeButton({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button
      onClick={onClick}
      className="px-3 py-1 rounded-full text-xs font-medium transition-colors"
      aria-pressed={active}
      style={{
        backgroundColor: active ? 'var(--color-primary)' : 'transparent',
        color: active ? 'white' : 'var(--color-text-muted)',
      }}
    >
      {label}
    </button>
  )
}
