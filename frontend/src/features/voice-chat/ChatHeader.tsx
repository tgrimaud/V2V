import type { Language, Labels } from './i18n'

interface ChatHeaderProps {
  connected: boolean
  statusLabel: string
  language: Language
  t: Labels
  onLanguageChange: (language: Language) => void
}

const LANGUAGES: readonly Language[] = ['fr', 'en']

export function ChatHeader({ connected, statusLabel, language, t, onLanguageChange }: ChatHeaderProps) {
  return (
    <div
      className="px-4 py-2 flex items-center justify-between text-sm"
      style={{ borderBottom: '1px solid var(--color-border)' }}
    >
      <div className="flex items-center gap-2">
        <span
          className="w-2 h-2 rounded-full"
          aria-hidden="true"
          style={{ backgroundColor: connected ? 'var(--color-success)' : 'var(--color-danger)' }}
        />
        <span style={{ color: 'var(--color-text-muted)' }}>
          {connected ? t.connected : statusLabel}
        </span>
      </div>
      <div
        className="flex items-center gap-1 rounded-full p-0.5"
        role="group"
        aria-label="Language selection"
        style={{ backgroundColor: 'var(--color-border)' }}
      >
        {LANGUAGES.map((lang) => (
          <button
            key={lang}
            onClick={() => onLanguageChange(lang)}
            className="px-2.5 py-1 rounded-full text-xs font-medium transition-colors"
            aria-pressed={language === lang}
            style={{
              backgroundColor: language === lang ? 'var(--color-primary)' : 'transparent',
              color: language === lang ? 'white' : 'var(--color-text-muted)',
            }}
          >
            {lang.toUpperCase()}
          </button>
        ))}
      </div>
    </div>
  )
}
