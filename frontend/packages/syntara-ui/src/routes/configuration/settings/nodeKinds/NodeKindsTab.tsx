import { Content, ContentVariants, Flex, FlexItem, Stack, StackItem, Switch, Title } from '@patternfly/react-core'
import { Table, Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import { useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'

import { DisabledWithTooltip } from '../../../../components/DisabledWithTooltip'
import { SynLabel } from '../../../../components/labels/SynLabel'
import { useQueryState } from '../../../../components/states/useQueryState'
import type { NodeKindCategory } from '../../../../hooks/useNodeKindsQuery'
import {
  NODE_KINDS_QUERY_PATH,
  useNodeKindsQuery,
  useSetNodeKindEnabledMutation,
} from '../../../../hooks/useNodeKindsQuery'
import { useAlerts } from '../../../../providers/alerts'
import { getErrorMessage } from '../../../../utils/apiErrors'
import { detachPromise } from '../../../../utils/detachPromise'

import { nodeKindSwitchTooltip } from './nodeKindSwitchTooltip'
import { useOptimisticNodeKindEnabled } from './useOptimisticNodeKindEnabled'

const CATEGORY_LABELS: Record<NodeKindCategory, string> = {
  trigger: 'Trigger',
  flow_control: 'Flow control',
  action: 'Action',
}

const ACTION_LABELS: Record<string, string> = {
  write: 'Write',
  execute: 'Execute',
}

type NodeKindsTabProps = {
  /** The caller holds `setting:write` and may flip the kill switch. */
  readonly canWrite: boolean
}

/**
 * Registry of every workflow node kind with the platform-wide kill switch (F-14).
 *
 * Disabling a kind is not a permission: it applies to every principal, admins
 * included. The "Can be denied for" column shows which actions a deny-effect
 * policy may target for that kind.
 */
export function NodeKindsTab({ canWrite }: NodeKindsTabProps) {
  const queryClient = useQueryClient()
  const { showError, showSuccess } = useAlerts()
  const { query, nodeKinds: serverNodeKinds } = useNodeKindsQuery()
  const { mutateAsync: setEnabled } = useSetNodeKindEnabledMutation()

  const queryState = useQueryState(query, {
    title: 'Error loading node kinds',
    onRetry: () => detachPromise(query.refetch()),
  })

  const handleSuccess = useCallback(
    async (kind: string, enabled: boolean) => {
      showSuccess({ title: enabled ? `Enabled ${kind} nodes` : `Disabled ${kind} nodes` })
      await queryClient.invalidateQueries({ queryKey: ['get', NODE_KINDS_QUERY_PATH] })
    },
    [queryClient, showSuccess]
  )

  const handleError = useCallback(
    (title: string, error: unknown) => {
      showError({ title, description: getErrorMessage(error) })
    },
    [showError]
  )

  const { nodeKinds, setNodeKindEnabled } = useOptimisticNodeKindEnabled({
    nodeKinds: serverNodeKinds,
    setEnabled,
    onSuccess: handleSuccess,
    onError: handleError,
  })

  if (queryState) return queryState

  return (
    <Stack hasGutter>
      <StackItem>
        <Title headingLevel="h2" size="lg">
          Node kinds
        </Title>
        <Content component={ContentVariants.small}>
          Switching a node kind off removes it from the workflow builder for everyone, administrators included, and
          blocks saving, publishing and launching workflows that still contain it.
        </Content>
      </StackItem>
      <StackItem>
        <Table aria-label="Node kinds" variant="compact">
          <Thead>
            <Tr>
              <Th>Node kind</Th>
              <Th>Category</Th>
              <Th>Enabled</Th>
              <Th>Can be denied for</Th>
            </Tr>
          </Thead>
          <Tbody>
            {nodeKinds.map((nodeKind) => {
              const tooltip = nodeKindSwitchTooltip(nodeKind, canWrite)
              return (
                <Tr key={nodeKind.kind}>
                  <Td dataLabel="Node kind">{nodeKind.kind}</Td>
                  <Td dataLabel="Category">
                    <SynLabel>{CATEGORY_LABELS[nodeKind.category]}</SynLabel>
                  </Td>
                  <Td dataLabel="Enabled">
                    <DisabledWithTooltip isDisabled={tooltip !== null} content={tooltip ?? ''}>
                      <Switch
                        id={`node-kind-enabled-${nodeKind.kind}`}
                        aria-label={`Enable ${nodeKind.kind} nodes`}
                        label={nodeKind.enabled ? 'Enabled' : 'Disabled'}
                        isChecked={nodeKind.enabled}
                        isDisabled={tooltip !== null}
                        onChange={(_event, checked) => setNodeKindEnabled(nodeKind.kind, checked)}
                      />
                    </DisabledWithTooltip>
                  </Td>
                  <Td dataLabel="Can be denied for">
                    {nodeKind.deniable_actions.length === 0 ? (
                      <Content component={ContentVariants.small}>Never denied</Content>
                    ) : (
                      <Flex gap={{ default: 'gapXs' }}>
                        {nodeKind.deniable_actions.map((action) => (
                          <FlexItem key={action}>
                            <SynLabel color="blue">{ACTION_LABELS[action] ?? action}</SynLabel>
                          </FlexItem>
                        ))}
                      </Flex>
                    )}
                  </Td>
                </Tr>
              )
            })}
          </Tbody>
        </Table>
      </StackItem>
    </Stack>
  )
}
