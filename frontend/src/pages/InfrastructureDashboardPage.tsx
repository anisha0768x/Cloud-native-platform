import { useInfrastructureDashboard } from '../hooks/useDashboards'
import { StatusBadge } from '../components/StatusBadge'
import { DataTable } from '../components/DataTable'
import { ClusterTrendChart } from '../components/ClusterTrendChart'
import { EmptyState, ErrorState, LoadingState, PartialErrorsNotice } from '../components/States'
import { getApiErrorMessage } from '../api/http'
import type { NodeInfo, ServiceHealthSummary } from '../types/api'

export function InfrastructureDashboardPage() {
  const { data, isLoading, isError, error, refetch } = useInfrastructureDashboard()

  if (isLoading) return <LoadingState label="Loading infrastructure data" />
  if (isError) return <ErrorState message={getApiErrorMessage(error)} onRetry={() => refetch()} />
  if (!data) return null

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold">Infrastructure</h1>
        <p className="text-sm text-text-secondary">Nodes, service health, and cluster capacity over time.</p>
      </div>

      <PartialErrorsNotice errors={data.partial_errors} />

      <div className="rounded-lg border border-border bg-surface p-4">
        <h2 className="mb-3 text-sm font-medium text-text-secondary">Cluster trend (last 24h)</h2>
        {data.cluster_snapshot_trend.length === 0 ? (
          <EmptyState message="No snapshot history yet — the K8s Management Service captures one periodically." />
        ) : (
          <ClusterTrendChart data={data.cluster_snapshot_trend} />
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section>
          <h2 className="mb-3 text-sm font-medium text-text-secondary">Nodes</h2>
          {data.nodes.length === 0 ? (
            <EmptyState message="No nodes reported." />
          ) : (
            <DataTable<NodeInfo>
              keyFn={(n) => n.name}
              columns={[
                { header: 'Name', render: (n) => n.name, mono: true },
                { header: 'Status', render: (n) => <StatusBadge status={n.status} /> },
                { header: 'CPU', render: (n) => n.cpu_capacity, mono: true },
                { header: 'Memory', render: (n) => n.memory_capacity, mono: true },
              ]}
              rows={data.nodes}
            />
          )}
        </section>

        <section>
          <h2 className="mb-3 text-sm font-medium text-text-secondary">Service health</h2>
          {data.services_health.length === 0 ? (
            <EmptyState message="No services registered yet." />
          ) : (
            <DataTable<ServiceHealthSummary>
              keyFn={(s) => s.name}
              columns={[
                { header: 'Service', render: (s) => s.name, mono: true },
                { header: 'Namespace', render: (s) => s.namespace, mono: true },
                { header: 'Status', render: (s) => <StatusBadge status={s.status} /> },
              ]}
              rows={data.services_health}
            />
          )}
        </section>
      </div>
    </div>
  )
}
