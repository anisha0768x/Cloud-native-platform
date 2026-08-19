import { useKubernetesDashboard } from '../hooks/useDashboards'
import { StatusBadge } from '../components/StatusBadge'
import { DataTable } from '../components/DataTable'
import { EmptyState, ErrorState, LoadingState, PartialErrorsNotice } from '../components/States'
import { getApiErrorMessage } from '../api/http'
import type { DeploymentInfo, PodInfo, ScalingHistoryEntry } from '../types/api'

export function KubernetesDashboardPage() {
  const { data, isLoading, isError, error, refetch } = useKubernetesDashboard()

  if (isLoading) return <LoadingState label="Loading cluster state" />
  if (isError) return <ErrorState message={getApiErrorMessage(error)} onRetry={() => refetch()} />
  if (!data) return null

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold">Kubernetes</h1>
        <p className="text-sm text-text-secondary">Pods, deployments, and recent scaling actions.</p>
      </div>

      <PartialErrorsNotice errors={data.partial_errors} />

      <section>
        <h2 className="mb-3 text-sm font-medium text-text-secondary">Deployments</h2>
        {data.deployments.length === 0 ? (
          <EmptyState message="No deployments found." />
        ) : (
          <DataTable<DeploymentInfo>
            keyFn={(d) => `${d.namespace}/${d.name}`}
            columns={[
              { header: 'Name', render: (d) => d.name, mono: true },
              { header: 'Namespace', render: (d) => d.namespace, mono: true },
              { header: 'Desired', render: (d) => d.desired_replicas, mono: true },
              { header: 'Available', render: (d) => d.available_replicas, mono: true },
              {
                header: 'Status',
                render: (d) => (
                  <StatusBadge status={d.available_replicas >= d.desired_replicas ? 'healthy' : 'degraded'} />
                ),
              },
            ]}
            rows={data.deployments}
          />
        )}
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium text-text-secondary">Pods ({data.pods.length})</h2>
        {data.pods.length === 0 ? (
          <EmptyState message="No pods found." />
        ) : (
          <DataTable<PodInfo>
            keyFn={(p) => p.name}
            columns={[
              { header: 'Name', render: (p) => p.name, mono: true },
              { header: 'Namespace', render: (p) => p.namespace, mono: true },
              { header: 'Node', render: (p) => p.node_name ?? '—', mono: true },
              { header: 'Restarts', render: (p) => p.restart_count, mono: true },
              { header: 'Status', render: (p) => <StatusBadge status={p.status} /> },
            ]}
            rows={data.pods}
          />
        )}
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium text-text-secondary">Recent scaling actions</h2>
        {data.recent_scaling_history.length === 0 ? (
          <EmptyState message="No scaling actions recorded yet." />
        ) : (
          <DataTable<ScalingHistoryEntry>
            keyFn={(s) => s.id}
            columns={[
              { header: 'Deployment', render: (s) => s.deployment_name, mono: true },
              { header: 'Change', render: (s) => `${s.from_replicas} → ${s.to_replicas}`, mono: true },
              { header: 'Trigger', render: (s) => s.trigger_source },
              { header: 'When', render: (s) => new Date(s.created_at).toLocaleString(), mono: true },
            ]}
            rows={data.recent_scaling_history}
          />
        )}
      </section>
    </div>
  )
}
