export function LoadingState({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-12 text-sm text-text-secondary">
      <span className="h-3 w-3 animate-pulse rounded-full bg-accent" />
      {label}…
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-lg border border-down/30 bg-down/5 p-4 text-sm">
      <p className="font-medium text-down">Couldn't load this data</p>
      <p className="mt-1 text-text-secondary">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-3 rounded-md border border-border-strong px-3 py-1.5 text-xs font-medium text-text-primary hover:bg-surface-hover"
        >
          Try again
        </button>
      )}
    </div>
  )
}

export function EmptyState({ message }: { message: string }) {
  return <div className="py-8 text-center text-sm text-text-muted">{message}</div>
}

export function PartialErrorsNotice({ errors }: { errors: string[] }) {
  if (errors.length === 0) return null
  return (
    <div className="rounded-lg border border-degraded/30 bg-degraded/5 px-3 py-2 text-xs text-degraded">
      Some data is unavailable right now: {errors.join(', ')}. The rest of this dashboard still reflects live data.
    </div>
  )
}
