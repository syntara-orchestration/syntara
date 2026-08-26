import { Content, ContentVariants, StackItem } from '@patternfly/react-core'

import { SynPageBody } from '../../components/layout/SynPage'
import { SynPanelContentStack } from '../../components/layout/SynPanelContentStack'
import { useQueryState } from '../../components/states/useQueryState'
import { detachPromise } from '../../utils/detachPromise'

import { useResourceActions } from './useResourceActions'
import { WhoCanView } from './WhoCanView'

export function CheckAccessTab() {
  const { resourceTypes, actionsByResource, isLoading, error, refetch } = useResourceActions()

  const resourceActionsQueryState = useQueryState(
    { isPending: isLoading, error },
    { title: 'Error loading resource actions', onRetry: () => detachPromise(refetch()) }
  )

  return (
    <SynPanelContentStack>
      <StackItem>
        <Content component={ContentVariants.p} style={{ marginBottom: 'var(--pf-t--global--spacer--md)' }}>
          Look up which users and groups have access to a specific resource and what actions they can perform on it. Use
          this page to quickly audit permissions without navigating through individual assignments.
        </Content>
      </StackItem>

      <SynPageBody style={{ overflow: 'auto' }}>
        {resourceActionsQueryState ?? (
          <WhoCanView resourceTypes={resourceTypes} actionsByResource={actionsByResource} />
        )}
      </SynPageBody>
    </SynPanelContentStack>
  )
}
