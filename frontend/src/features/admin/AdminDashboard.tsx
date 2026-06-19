import { useState, useEffect } from 'react'

interface Stats {
  total_conversations: number
  escalated_count: number
  escalation_rate_percent: number
  average_latency_ms: number
  resolution_rate_percent: number
}

interface ConversationEvent {
  conversationId: string
  channel: string
  question: string
  answer: string
  citationCount: number
  latencyMs: number
  escalated: boolean
  timestamp: string
}

export function AdminDashboard() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [events, setEvents] = useState<ConversationEvent[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetchData() {
      try {
        const [statsRes, eventsRes] = await Promise.all([
          fetch('/api/admin/stats'),
          fetch('/api/admin/events?limit=20')
        ])
        setStats(await statsRes.json())
        setEvents(await eventsRes.json())
      } catch (error) {
        console.error('Failed to load admin data:', error)
      } finally {
        setLoading(false)
      }
    }
    fetchData()
    const interval = setInterval(fetchData, 10000)
    return () => clearInterval(interval)
  }, [])

  if (loading) {
    return <div className="text-center p-8" style={{ color: 'var(--color-text-muted)' }}>Chargement...</div>
  }

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KpiCard label="Conversations" value={stats.total_conversations} />
          <KpiCard label="Latence moyenne" value={`${stats.average_latency_ms}ms`} />
          <KpiCard label="Taux résolution" value={`${stats.resolution_rate_percent}%`} accent="success" />
          <KpiCard label="Escalades" value={`${stats.escalation_rate_percent}%`} accent="warning" />
        </div>
      )}

      {/* Recent events */}
      <div className="rounded-xl overflow-hidden" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}>
        <div className="px-4 py-3 font-medium text-sm" style={{ borderBottom: '1px solid var(--color-border)' }}>
          Dernières conversations
        </div>
        <div className="divide-y" style={{ borderColor: 'var(--color-border)' }}>
          {events.length === 0 && (
            <div className="p-4 text-center text-sm" style={{ color: 'var(--color-text-muted)' }}>
              Aucune conversation enregistrée
            </div>
          )}
          {events.map((event, i) => (
            <div key={i} className="px-4 py-3 text-sm">
              <div className="flex items-center gap-2 mb-1">
                <span className="w-2 h-2 rounded-full" style={{
                  backgroundColor: event.escalated ? 'var(--color-warning)' : 'var(--color-success)'
                }} />
                <span className="font-medium" style={{ color: 'var(--color-text)' }}>
                  {event.question.length > 60 ? event.question.substring(0, 60) + '...' : event.question}
                </span>
                <span className="ml-auto text-xs" style={{ color: 'var(--color-text-muted)' }}>
                  {event.latencyMs}ms
                </span>
              </div>
              <div className="text-xs pl-4" style={{ color: 'var(--color-text-muted)' }}>
                {event.answer.length > 100 ? event.answer.substring(0, 100) + '...' : event.answer}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function KpiCard({ label, value, accent }: { label: string; value: string | number; accent?: 'success' | 'warning' }) {
  const accentColor = accent === 'success' ? 'var(--color-success)' :
                      accent === 'warning' ? 'var(--color-warning)' : 'var(--color-primary)'

  return (
    <div className="rounded-xl p-4" style={{ backgroundColor: 'var(--color-surface)', border: '1px solid var(--color-border)' }}>
      <div className="text-xs mb-1" style={{ color: 'var(--color-text-muted)' }}>{label}</div>
      <div className="text-2xl font-bold" style={{ color: accentColor }}>{value}</div>
    </div>
  )
}
