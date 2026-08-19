import { useQuery } from '@tanstack/react-query'
import { fetchExecutiveDashboard, fetchInfrastructureDashboard, fetchKubernetesDashboard } from '../api/dashboards'

// Poll interval matches Dashboard Service's own CACHE_TTL_SECONDS default
// (Module 7) — polling faster than the cache refreshes would just
// re-fetch the same cached response and waste a round trip; polling
// slower would show stale data longer than the backend actually holds it.
const POLL_INTERVAL_MS = 15_000

export function useExecutiveDashboard() {
  return useQuery({
    queryKey: ['dashboard', 'executive'],
    queryFn: fetchExecutiveDashboard,
    refetchInterval: POLL_INTERVAL_MS,
  })
}

export function useInfrastructureDashboard() {
  return useQuery({
    queryKey: ['dashboard', 'infrastructure'],
    queryFn: fetchInfrastructureDashboard,
    refetchInterval: POLL_INTERVAL_MS,
  })
}

export function useKubernetesDashboard() {
  return useQuery({
    queryKey: ['dashboard', 'kubernetes'],
    queryFn: fetchKubernetesDashboard,
    refetchInterval: POLL_INTERVAL_MS,
  })
}
