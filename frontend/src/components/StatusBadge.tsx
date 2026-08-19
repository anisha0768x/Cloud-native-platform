const STATUS_STYLES: Record<string, { bg: string; text: string; dot: string }> = {
  healthy: { bg: 'bg-healthy/10', text: 'text-healthy', dot: 'bg-healthy' },
  running: { bg: 'bg-healthy/10', text: 'text-healthy', dot: 'bg-healthy' },
  ready: { bg: 'bg-healthy/10', text: 'text-healthy', dot: 'bg-healthy' },
  degraded: { bg: 'bg-degraded/10', text: 'text-degraded', dot: 'bg-degraded' },
  pending: { bg: 'bg-degraded/10', text: 'text-degraded', dot: 'bg-degraded' },
  down: { bg: 'bg-down/10', text: 'text-down', dot: 'bg-down' },
  failed: { bg: 'bg-down/10', text: 'text-down', dot: 'bg-down' },
  notready: { bg: 'bg-down/10', text: 'text-down', dot: 'bg-down' },
}

const DEFAULT_STYLE = { bg: 'bg-unknown/10', text: 'text-unknown', dot: 'bg-unknown' }

export function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status.toLowerCase()] ?? DEFAULT_STYLE
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${style.bg} ${style.text}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
      {status}
    </span>
  )
}
