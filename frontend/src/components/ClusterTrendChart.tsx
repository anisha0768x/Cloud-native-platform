import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { ClusterSnapshot } from '../types/api'

export function ClusterTrendChart({ data }: { data: ClusterSnapshot[] }) {
  const chartData = data.map((point) => ({
    time: new Date(point.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    pods: point.pod_count,
    nodes: point.node_count,
  }))

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <XAxis
          dataKey="time"
          stroke="var(--color-text-muted)"
          fontSize={11}
          tickLine={false}
          axisLine={{ stroke: 'var(--color-border)' }}
        />
        <YAxis stroke="var(--color-text-muted)" fontSize={11} tickLine={false} axisLine={false} width={28} />
        <Tooltip
          contentStyle={{
            background: 'var(--color-surface)',
            border: '1px solid var(--color-border-strong)',
            borderRadius: 8,
            fontSize: 12,
          }}
          labelStyle={{ color: 'var(--color-text-secondary)' }}
        />
        <Line type="monotone" dataKey="pods" stroke="var(--color-accent)" strokeWidth={2} dot={false} name="Pods" />
        <Line
          type="monotone"
          dataKey="nodes"
          stroke="var(--color-text-muted)"
          strokeWidth={1.5}
          strokeDasharray="4 3"
          dot={false}
          name="Nodes"
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
