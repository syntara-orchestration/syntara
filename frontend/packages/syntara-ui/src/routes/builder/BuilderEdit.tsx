import type { WorkflowWithVersion } from '@syntara/contracts'
import { useParams, useRouterState } from '@tanstack/react-router'
import { ReactFlowProvider } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useMemo } from 'react'

import { executionsClient, workflowClient } from '../../client'
import { SynPage, SynPageBody } from '../../components/layout/SynPage'
import { SynPageHeader } from '../../components/layout/SynPageHeader'
import { SynPanel } from '../../components/layout/SynPanel'
import { SynErrorState } from '../../components/states/SynErrorState'
import { SynLoadingState } from '../../components/states/SynLoadingState'
import { SynPageTitle } from '../../components/SynPageTitle'

import { BuilderContent } from './BuilderContent'
import type { ExecutionCopyData } from './hooks/useExecutionCopyToEditor'

export default function BuilderEdit() {
  const { workflowId: workflowIdParam }: { workflowId: string } = useParams({ strict: false })
  const workflowId = workflowIdParam ?? null
  const searchParams = useRouterState({ select: (s) => s.location.searchStr.replace(/^\?/, '') })
  const parsedParams = useMemo(() => {
    const p = new URLSearchParams(searchParams)
    return {
      fromExecution: p.get('fromExecution'),
      linkExecution: p.get('linkExecution'),
      version: p.get('version'),
    }
  }, [searchParams])
  const parsedVersion = parsedParams.version ? Number.parseInt(parsedParams.version, 10) : null
  const initialViewVersion =
    parsedVersion !== null && Number.isFinite(parsedVersion) && parsedVersion > 0 ? parsedVersion : null
  const executionIdParam = parsedParams.fromExecution ?? parsedParams.linkExecution

  // Fetch existing workflow - always refetch on mount to ensure fresh data
  const workflowQuery = workflowClient.useQuery(
    'get',
    '/workflows/{workflow_id}',
    {
      params: { path: { workflow_id: workflowId ?? '' } },
    },
    {
      enabled: !!workflowId,
      refetchOnMount: 'always',
      refetchOnWindowFocus: false,
    }
  )

  const executionQuery = executionsClient.useQuery(
    'get',
    '/executions/{execution_id}',
    {
      params: {
        path: { execution_id: executionIdParam ?? '' },
        query: { include: 'workflow_definition' },
      },
    },
    { enabled: !!executionIdParam }
  )

  const executionCopy = useMemo((): ExecutionCopyData | undefined => {
    if (!executionIdParam || !executionQuery.data) return undefined
    const exec = executionQuery.data
    const wfDef = exec.workflow_definition as Record<string, unknown> | undefined
    if (!wfDef) return undefined
    return {
      executionId: executionIdParam,
      workflowDefinition: wfDef,
      preserveWorkflow: !!parsedParams.linkExecution,
    }
  }, [executionIdParam, executionQuery.data, parsedParams.linkExecution])

  // Show loading/error states only on initial load, not during refetch
  // This prevents unmounting the component (and losing ButtonEdges) when refetching after save
  const { error, isLoading } = workflowQuery

  if (error) {
    return (
      <SynPage>
        <SynPageTitle segments={['Error loading workflow', 'Workflows']} />
        <SynPageHeader title="Error loading workflow" />
        <SynPageBody>
          <SynPanel isFullHeight>
            <SynErrorState title="Error loading workflow" message={error} />
          </SynPanel>
        </SynPageBody>
      </SynPage>
    )
  }

  // Use isLoading instead of isPending to distinguish initial load from refetch
  // isLoading = true only on first fetch, isPending = true on both initial and refetch
  if (isLoading) {
    return (
      <SynPage>
        <SynPageTitle segments={['Loading workflow', 'Workflows']} />
        <SynPageHeader title="Loading workflow" />
        <SynPageBody>
          <SynPanel isFullHeight>
            <SynLoadingState />
          </SynPanel>
        </SynPageBody>
      </SynPage>
    )
  }

  return (
    <ReactFlowProvider key={workflowId}>
      <BuilderContent
        workflow={workflowQuery.data as WorkflowWithVersion}
        isNew={false}
        workflowId={workflowId}
        executionCopy={executionCopy}
        initialViewVersion={initialViewVersion}
      />
    </ReactFlowProvider>
  )
}
