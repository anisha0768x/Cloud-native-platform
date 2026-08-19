// Mirrors Auth Service's schemas (services/auth-service/app/schemas/auth.py)
export interface UserResponse {
  id: string
  email: string
  full_name: string | null
  is_active: boolean
  roles: string[]
  permissions: string[]
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

// Mirrors Dashboard Service's schemas (services/dashboard-service/app/schemas/dashboards.py)
export interface ExecutiveDashboard {
  total_services: number
  services_by_status: Record<string, number>
  overall_health_percentage: number
  open_alerts_by_severity: Record<string, number>
  cluster_node_count: number
  cluster_deployment_count: number
  cluster_pod_count: number
  partial_errors: string[]
}

export interface ServiceHealthSummary {
  name: string
  status: string
  namespace: string
}

export interface InfrastructureDashboard {
  nodes: NodeInfo[]
  services_health: ServiceHealthSummary[]
  cluster_snapshot_trend: ClusterSnapshot[]
  partial_errors: string[]
}

export interface NodeInfo {
  name: string
  status: string
  cpu_capacity: string
  memory_capacity: string
  region: string | null
}

export interface PodInfo {
  name: string
  namespace: string
  node_name: string | null
  status: string
  restart_count: number
  service_name: string | null
}

export interface DeploymentInfo {
  name: string
  namespace: string
  desired_replicas: number
  available_replicas: number
  updated_replicas: number
}

export interface ScalingHistoryEntry {
  id: string
  namespace: string
  deployment_name: string
  from_replicas: number
  to_replicas: number
  triggered_by: string
  trigger_source: string
  created_at: string
}

export interface ClusterSnapshot {
  time: string
  node_count: number
  pod_count: number
  pods_running: number
  pods_pending: number
  pods_failed: number
  deployment_count: number
}

export interface KubernetesDashboard {
  nodes: NodeInfo[]
  pods: PodInfo[]
  deployments: DeploymentInfo[]
  recent_scaling_history: ScalingHistoryEntry[]
  partial_errors: string[]
}

// Standard platform error envelope (platform_common/exceptions/errors.py)
export interface ApiErrorResponse {
  error: {
    code: string
    message: string
    details: Record<string, unknown>
  }
}
