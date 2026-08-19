import type { ReactNode } from 'react'

interface StatCardProps {
  label: string
  value: string | number
  sublabel?: string
  icon?: ReactNode
  tone?: 'default' | 'healthy' | 'degraded' | 'down'
}

const TONE_TEXT: Record<NonNullable<StatCardProps['tone']>, string> = {
  default: 'text-text-primary',
  healthy: 'text-healthy',
  degraded: 'text-degraded',
  down: 'text-down',
}

export function StatCard({ label, value, sublabel, icon, tone = 'default' }: StatCardProps) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-text-secondary">{label}</span>
        {icon && <span className="text-text-muted">{icon}</span>}
      </div>
      <div className={`mt-2 font-mono text-2xl font-semibold ${TONE_TEXT[tone]}`}>{value}</div>
      {sublabel && <div className="mt-1 text-xs text-text-muted">{sublabel}</div>}
    </div>
  )
}
