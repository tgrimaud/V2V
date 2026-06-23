interface ServiceErrorBannerProps {
  message: string
  onDismiss: () => void
}

export function ServiceErrorBanner({ message, onDismiss }: ServiceErrorBannerProps) {
  return (
    <div
      role="alert"
      className="px-4 py-2 flex items-center justify-between text-sm"
      style={{
        backgroundColor: 'var(--color-danger-bg)',
        borderBottom: '1px solid var(--color-danger-border)',
        color: 'var(--color-danger-text)',
      }}
    >
      <span>{message}</span>
      <button
        onClick={onDismiss}
        className="ml-2 text-xs font-bold hover:opacity-70"
        aria-label="Dismiss"
      >
        ✕
      </button>
    </div>
  )
}
