import { AlertTriangle, Boxes, HeartPulse, Server } from 'lucide-react'
import { useExecutiveDashboard } from '../hooks/useDashboards'
import { StatCard } from '../components/StatCard'
import { ErrorState, LoadingState, PartialErrorsNotice } from '../components/States'
import { getApiErrorMessage } from '../api/http'

export function ExecutiveDashboardPage() {
  const { data, isLoading, isError, error, refetch } = useExecutiveDashboard()

  if (isLoading) return <LoadingState label="Loading executive overview" />
  if (isError) return <ErrorState message={getApiErrorMessage(error)} onRetry={() => refetch()} />
  if (!data) return null

  const healthTone = data.overall_health_percentage >= 90 ? 'healthy' : data.overall_health_percentage >= 70 ? 'degraded' : 'down'
  const openAlertCount = Object.values(data.open_alerts_by_severity).reduce((a, b) => a + b, 0)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold">Executive overview</h1>
        <p className="text-sm text-text-secondary">Platform-wide health, at a glance.</p>
      </div>

      <PartialErrorsNotice errors={data.partial_errors} />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Overall health"
          value={`${data.overall_health_percentage}%`}
          sublabel={`${data.total_services} services`}
          icon={<HeartPulse className="h-4 w-4" />}
          tone={healthTone}
        />
        <StatCard
          label="Open alerts"
          value={openAlertCount}
          sublabel={Object.entries(data.open_alerts_by_severity).map(([sev, count]) => `${count} ${sev}`).join(', ') || 'None'}
          icon={<AlertTriangle className="h-4 w-4" />}
          tone={openAlertCount > 0 ? 'degraded' : 'healthy'}
        />
        <StatCard
          label="Cluster nodes"
          value={data.cluster_node_count}
          icon={<Server className="h-4 w-4" />}
        />
        <StatCard
          label="Running pods"
          value={data.cluster_pod_count}
          sublabel={`${data.cluster_deployment_count} deployments`}
          icon={<Boxes className="h-4 w-4" />}
        />
      </div>

      <div className="rounded-lg border border-border bg-surface p-4">
        <h2 className="mb-3 text-sm font-medium text-text-secondary">Services by status</h2>
        <div className="flex gap-2">
          {Object.entries(data.services_by_status).length === 0 && (
            <span className="text-sm text-text-muted">No services registered yet.</span>
          )}
          {Object.entries(data.services_by_status).map(([status, count]) => (
            <div key={status} className="flex-1 rounded-md border border-border bg-bg px-3 py-2 text-center">
              <div className="font-mono text-xl font-semibold">{count}</div>
              <div className="mt-0.5 text-xs capitalize text-text-secondary">{status}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
