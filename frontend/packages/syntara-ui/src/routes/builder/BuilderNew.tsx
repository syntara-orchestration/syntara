import { useQueryClient } from '@tanstack/react-query'
import { ReactFlowProvider } from '@xyflow/react'
import { useEffect } from 'react'

import '@xyflow/react/dist/style.css'
import { workflowClient } from '../../client'
import { SynPageTitle } from '../../components/SynPageTitle'
import { detachPromise } from '../../utils/detachPromise'

import { BuilderContent } from './BuilderContent'
import { WORKFLOWS_LIST_PARAMS_FOR_DEFAULT_NAME } from './utils/workflowListQuery'

export default function BuilderNew() {
  const queryClient = useQueryClient()
  useEffect(() => {
    detachPromise(
      queryClient.prefetchQuery(
        workflowClient.queryOptions('get', '/workflows', WORKFLOWS_LIST_PARAMS_FOR_DEFAULT_NAME)
      )
    )
  }, [queryClient])

  return (
    <ReactFlowProvider>
      <SynPageTitle segments={['New Workflow', 'Workflows']} />
      <BuilderContent isNew={true} workflowId={null} />
    </ReactFlowProvider>
  )
}
