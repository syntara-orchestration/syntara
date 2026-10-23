import type * as ExecutionPlaneAPI from '@syntara/contracts/src/execution-plane-api.js'

import { mockDate } from './mockDates'

type ExecutionTargetFacadeRead = ExecutionPlaneAPI.components['schemas']['ExecutionTargetFacadeRead']

/** EP `TargetStatus` values used by the seeded mock dataset. */
const STATUSES = ['active', 'bootstrapping', 'degraded', 'registering', 'failed', 'validating', 'draining'] as const
const REGIONS = ['us-west', 'us-east', 'eu-central', 'ap-south'] as const

/** Extra targets so default page size (20) has a next page for pagination tests. */
function buildExtraTargets(count: number): ExecutionTargetFacadeRead[] {
  return Array.from({ length: count }, (_, index) => {
    const n = index + 1
    const padded = String(n).padStart(2, '0')
    const idSuffix = String(100 + n).padStart(12, '0')
    const status = STATUSES[index % STATUSES.length]
    const region = REGIONS[index % REGIONS.length]
    return {
      id: `a1000000-0000-4000-8000-${idSuffix}`,
      cluster_id: `b1000000-0000-4000-8000-${idSuffix}`,
      name: `Worker Pool ${padded}`,
      backend_type: 'kubernetes',
      endpoint: `https://api.pool-${padded}.openshift.example.com:6443`,
      placement: {
        type: 'kubernetes' as const,
        namespace: `syntara-pool-${padded}`,
        node_selectors: [],
        tolerations: [],
      },
      status,
      enabled: index % 3 !== 0,
      is_default: false,
      status_message: status === 'active' ? null : `Status: ${status}`,
      labels: {
        region,
        env: index % 2 === 0 ? 'prod' : 'dev',
        pool: `pool-${padded}`,
      },
      created_at: mockDate.daysAgo1,
      last_ran_at: index % 4 === 0 ? mockDate.hoursAgo2 : null,
    }
  })
}

/** Seeded Execution Plane facade targets for mock API / visual regression / pagination. */
export const executionTargets: ExecutionTargetFacadeRead[] = [
  {
    id: 'a1000000-0000-4000-8000-000000000001',
    cluster_id: 'b1000000-0000-4000-8000-000000000001',
    name: 'Prod OpenShift West',
    backend_type: 'kubernetes',
    endpoint: 'https://api.west.openshift.example.com:6443',
    placement: {
      type: 'kubernetes',
      namespace: 'syntara-workers',
      node_selectors: ['workload=automation'],
      tolerations: [],
    },
    status: 'active',
    enabled: true,
    is_default: true,
    status_message: null,
    labels: {
      region: 'us-west',
      env: 'prod',
    },
    created_at: mockDate.daysAgo7,
    last_ran_at: mockDate.minutesAgo30,
  },
  {
    id: 'a1000000-0000-4000-8000-000000000002',
    cluster_id: 'b1000000-0000-4000-8000-000000000002',
    name: 'Staging OpenShift',
    backend_type: 'kubernetes',
    endpoint: 'https://api.staging.openshift.example.com:6443',
    placement: {
      type: 'kubernetes',
      namespace: 'syntara-staging',
      node_selectors: [],
      tolerations: [],
    },
    status: 'bootstrapping',
    enabled: true,
    is_default: false,
    status_message: 'Waiting for worker namespace readiness',
    labels: {
      region: 'us-east',
      env: 'staging',
    },
    created_at: mockDate.daysAgo2,
    last_ran_at: null,
  },
  ...buildExtraTargets(23),
]
