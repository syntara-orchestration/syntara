import type * as ExecutionPlaneAPI from '@syntara/contracts/src/execution-plane-api.js'

import { mockDate } from './mockDates'

type ExecutionTargetFacadeRead = ExecutionPlaneAPI.components['schemas']['ExecutionTargetFacadeRead']

/** Seeded Execution Plane facade targets for mock API / visual regression. */
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
    status: 'ready',
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
    status: 'provisioning',
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
]
