import { http } from './http'
import type { ExecutiveDashboard, InfrastructureDashboard, KubernetesDashboard } from '../types/api'

export async function fetchExecutiveDashboard(): Promise<ExecutiveDashboard> {
  const resp = await http.get<ExecutiveDashboard>('/api/v1/dashboards/executive')
  return resp.data
}

export async function fetchInfrastructureDashboard(): Promise<InfrastructureDashboard> {
  const resp = await http.get<InfrastructureDashboard>('/api/v1/dashboards/infrastructure')
  return resp.data
}

export async function fetchKubernetesDashboard(): Promise<KubernetesDashboard> {
  const resp = await http.get<KubernetesDashboard>('/api/v1/dashboards/kubernetes')
  return resp.data
}
