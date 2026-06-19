import { useState } from 'react'
import { VoiceChat } from './features/voice-chat'
import { AdminDashboard } from './features/admin'

type View = 'chat' | 'admin'

function App() {
  const [view, setView] = useState<View>('chat')

  return (
    <div className="min-h-screen flex flex-col p-4">
      <header className="text-center mb-6">
        <h1 className="text-3xl font-bold" style={{ color: 'var(--color-text)' }}>
          Support Telecom
        </h1>
        <p className="mt-2" style={{ color: 'var(--color-text-muted)' }}>
          Assistant vocal — Posez votre question par la voix ou par écrit
        </p>
        <nav className="mt-4 flex justify-center gap-2">
          <button
            onClick={() => setView('chat')}
            className="px-4 py-2 rounded-full text-sm font-medium transition-colors"
            style={{
              backgroundColor: view === 'chat' ? 'var(--color-primary)' : 'transparent',
              color: view === 'chat' ? 'white' : 'var(--color-text-muted)',
              border: view === 'chat' ? 'none' : '1px solid var(--color-border)',
            }}
          >
            Chat vocal
          </button>
          <button
            onClick={() => setView('admin')}
            className="px-4 py-2 rounded-full text-sm font-medium transition-colors"
            style={{
              backgroundColor: view === 'admin' ? 'var(--color-primary)' : 'transparent',
              color: view === 'admin' ? 'white' : 'var(--color-text-muted)',
              border: view === 'admin' ? 'none' : '1px solid var(--color-border)',
            }}
          >
            Dashboard Admin
          </button>
        </nav>
      </header>
      <main className="w-full max-w-2xl mx-auto flex-1">
        {view === 'chat' ? <VoiceChat /> : <AdminDashboard />}
      </main>
    </div>
  )
}

export default App
