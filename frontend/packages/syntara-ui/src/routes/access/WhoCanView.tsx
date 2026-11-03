import {
  Alert,
  Button,
  Content,
  ContentVariants,
  Flex,
  FlexItem,
  Form,
  Spinner,
  Stack,
  StackItem,
  Truncate,
} from '@patternfly/react-core'
import { RhUiCaretLeftIcon, RhUiCaretRightIcon } from '@patternfly/react-icons'
import { Tbody, Td, Th, Thead, Tr } from '@patternfly/react-table'
import { useCallback, useMemo, useState } from 'react'
import { useWatch } from 'react-hook-form'

import { SynForm } from '../../components/forms/SynForm'
import { SynFormField } from '../../components/forms/SynFormField'
import { SynEmptyStateNoData } from '../../components/states/SynEmptyStateNoData'
import { SynErrorState } from '../../components/states/SynErrorState'
import { LinkCell } from '../../components/table/LinkCell'
import { SynScrollableTableContainer } from '../../components/table/SynScrollableTableContainer'
import { useSynForm } from '../../hooks/useSynForm'
import { getErrorMessage } from '../../utils/apiErrors'
import { getUserDetailPath } from '../access-management/accessManagementPaths'

import { accessClient } from './accessClient'
import { accessControlHelp } from './accessControlFieldHelp'
import type { AuthzExplorerQueryFormData } from './authzExplorerQuerySchema'
import { authzExplorerQuerySchema } from './authzExplorerQuerySchema'
import type { ResourceActionMap } from './canIUtils'
import { ProjectSelect } from './ProjectSelect'
import { ResourceIdSelect } from './ResourceIdSelect'
import { TypeaheadSelect } from './TypeaheadSelect'
import type { WhoCanUser } from './types'
import { useAllProjects } from './useAllProjects'

function WhoCanResults({
  users,
  action,
  resourceType,
  project,
  nextCursor,
  hasPrevPage,
  isPending,
  onNextPage,
  onPrevPage,
}: Readonly<{
  users: WhoCanUser[]
  action: string
  resourceType: string
  project: string
  nextCursor: string | null
  hasPrevPage: boolean
  isPending: boolean
  onNextPage: () => void
  onPrevPage: () => void
}>) {
  const projectSuffix = project ? ` in "${project}" project` : ''

  return (
    <>
      <StackItem>
        <Alert
          variant={users.length > 0 ? 'info' : 'warning'}
          title={
            users.length > 0
              ? `Users who can perform action "${action}" on resource "${resourceType}"${projectSuffix}`
              : `No users can perform action "${action}" on resource "${resourceType}"${projectSuffix}`
          }
          isInline
          isPlain
        />
      </StackItem>
      {users.length > 0 && (
        <SynScrollableTableContainer
          caption="Users with access"
          isStriped
          footerContent={
            <Flex
              justifyContent={{ default: 'justifyContentSpaceBetween' }}
              alignItems={{ default: 'alignItemsCenter' }}
            >
              <FlexItem>
                <Content component={ContentVariants.p}>
                  {users.length} {users.length === 1 ? 'user' : 'users'}
                </Content>
              </FlexItem>
              {(hasPrevPage || nextCursor) && (
                <Flex gap={{ default: 'gapSm' }}>
                  <Button
                    variant="plain"
                    isDisabled={!hasPrevPage || isPending}
                    onClick={onPrevPage}
                    aria-label="Previous page"
                  >
                    <RhUiCaretLeftIcon /> Previous
                  </Button>
                  <Button
                    variant="plain"
                    isDisabled={!nextCursor || isPending}
                    onClick={onNextPage}
                    aria-label="Next page"
                  >
                    Next <RhUiCaretRightIcon />
                  </Button>
                </Flex>
              )}
            </Flex>
          }
        >
          <Thead>
            <Tr>
              <Th>Username</Th>
            </Tr>
          </Thead>
          <Tbody>
            {users.map((u) => (
              <Tr key={u.id}>
                <Td dataLabel="Username">
                  <LinkCell href={getUserDetailPath(u.id)}>
                    <Truncate content={u.username} />
                  </LinkCell>
                </Td>
              </Tr>
            ))}
          </Tbody>
        </SynScrollableTableContainer>
      )}
    </>
  )
}

export function WhoCanView({ resourceTypes, actionsByResource }: Readonly<ResourceActionMap>) {
  const { projects } = useAllProjects()

  const form = useSynForm({
    schema: authzExplorerQuerySchema,
    defaultValues: { resourceType: '', action: '', resourceId: '', project: '' },
  })
  const { control, handleSubmit, setValue, getValues } = form

  const resourceType = useWatch({ control, name: 'resourceType', defaultValue: '' })
  const action = useWatch({ control, name: 'action', defaultValue: '' })
  const project = useWatch({ control, name: 'project', defaultValue: '' })

  const availableActions = useMemo(
    () => (resourceType ? (actionsByResource.get(resourceType) ?? []) : []),
    [resourceType, actionsByResource]
  )

  const resetDependentFields = (newResourceType: string) => {
    const actions = actionsByResource.get(newResourceType) ?? []
    const currentAction = getValues('action')
    if (actions.length === 1) {
      setValue('action', actions[0])
    } else if (!actions.includes(currentAction)) {
      setValue('action', '')
    }
    setValue('resourceId', '')
  }

  // Pagination state: track cursor history for previous page navigation
  const [cursorHistory, setCursorHistory] = useState<string[]>([])
  const [currentCursor, setCurrentCursor] = useState<string | undefined>(undefined)
  const [lastSubmittedFormData, setLastSubmittedFormData] = useState<AuthzExplorerQueryFormData | null>(null)

  const whoCanMutation = accessClient.useMutation('post', '/authz/who_can')

  const submitWithCursor = useCallback(
    (formData: AuthzExplorerQueryFormData, cursor?: string) => {
      whoCanMutation.mutate({
        body: {
          action: formData.action.trim(),
          resource_type: formData.resourceType.trim(),
          ...(formData.resourceId?.trim() && { resource_id: formData.resourceId.trim() }),
          ...(formData.project?.trim() && { resource_project: formData.project.trim() }),
          ...(cursor && { cursor }),
        },
      })
    },
    [whoCanMutation]
  )

  const onSubmit = handleSubmit((formData) => {
    setLastSubmittedFormData(formData)
    setCursorHistory([])
    setCurrentCursor(undefined)
    submitWithCursor(formData)
  })

  const nextCursor = whoCanMutation.data?.next ?? null
  const result: WhoCanUser[] | null = whoCanMutation.data?.resources ?? null

  const handleNextPage = useCallback(() => {
    if (!nextCursor || !lastSubmittedFormData) return
    setCursorHistory((prev) => [...prev, currentCursor ?? ''])
    setCurrentCursor(nextCursor)
    submitWithCursor(lastSubmittedFormData, nextCursor)
  }, [nextCursor, currentCursor, submitWithCursor, lastSubmittedFormData])

  const handlePrevPage = useCallback(() => {
    if (cursorHistory.length === 0 || !lastSubmittedFormData) return
    const prev = [...cursorHistory]
    const prevCursor = prev.pop()
    setCursorHistory(prev)
    setCurrentCursor(prevCursor === '' ? undefined : prevCursor)
    submitWithCursor(lastSubmittedFormData, prevCursor === '' ? undefined : prevCursor)
  }, [cursorHistory, submitWithCursor, lastSubmittedFormData])

  return (
    <Flex direction={{ default: 'row' }} gap={{ default: 'gapXl' }} alignItems={{ default: 'alignItemsFlexStart' }}>
      <FlexItem style={{ minWidth: 340, maxWidth: 400 }}>
        <Form onSubmit={onSubmit}>
          <SynForm form={form}>
            <SynFormField<AuthzExplorerQueryFormData, 'resourceType'>
              name="resourceType"
              label="Resource type"
              fieldId="who-can-resource-type"
              isRequired
              labelHelp={accessControlHelp.resourceType}
            >
              {({ field }) => (
                <TypeaheadSelect
                  id="who-can-resource-type"
                  ariaLabel="Resource type"
                  options={resourceTypes.map((rt) => ({ value: rt, label: rt }))}
                  selected={field.value}
                  onChange={(value) => {
                    field.onChange(value)
                    resetDependentFields(value)
                  }}
                  placeholder="Select a resource type"
                />
              )}
            </SynFormField>

            <SynFormField<AuthzExplorerQueryFormData, 'action'>
              name="action"
              label="Action"
              fieldId="who-can-action"
              isRequired
              labelHelp={accessControlHelp.action}
            >
              {({ field }) => (
                <TypeaheadSelect
                  id="who-can-action"
                  ariaLabel="Action"
                  options={availableActions.map((a) => ({ value: a, label: a }))}
                  selected={field.value}
                  onChange={field.onChange}
                  placeholder={resourceType ? 'Select an action' : 'Select a resource type first'}
                  isDisabled={!resourceType}
                />
              )}
            </SynFormField>

            <SynFormField<AuthzExplorerQueryFormData, 'project'>
              name="project"
              label="Project"
              fieldId="who-can-project"
              labelHelp={accessControlHelp.project}
            >
              {({ field }) => (
                <ProjectSelect
                  id="who-can-project"
                  value={field.value ?? ''}
                  onChange={field.onChange}
                  projects={projects}
                />
              )}
            </SynFormField>

            <SynFormField<AuthzExplorerQueryFormData, 'resourceId'>
              name="resourceId"
              label="Resource ID"
              fieldId="who-can-resource-id"
              labelHelp={accessControlHelp.resourceId}
            >
              {({ field }) => (
                <ResourceIdSelect resourceType={resourceType} value={field.value ?? ''} onChange={field.onChange} />
              )}
            </SynFormField>
          </SynForm>

          <Button
            variant="primary"
            type="submit"
            isDisabled={!resourceType.trim() || !action.trim()}
            isLoading={whoCanMutation.isPending}
          >
            Find users
          </Button>
        </Form>
      </FlexItem>

      <FlexItem grow={{ default: 'grow' }}>
        <Stack hasGutter>
          {whoCanMutation.isIdle && (
            <StackItem>
              <SynEmptyStateNoData
                title="Find who has access"
                description="Enter an action and resource type to see which users can perform it."
              />
            </StackItem>
          )}

          {whoCanMutation.isPending && (
            <StackItem>
              <Flex
                justifyContent={{ default: 'justifyContentCenter' }}
                style={{ padding: 'var(--pf-t--global--spacer--2xl)' }}
              >
                <Spinner size="lg" aria-label="Finding users" />
              </Flex>
            </StackItem>
          )}

          {whoCanMutation.isError && (
            <StackItem>
              <SynErrorState title="Query failed" message={getErrorMessage(whoCanMutation.error)} onRetry={onSubmit} />
            </StackItem>
          )}

          {result && (
            <WhoCanResults
              users={result}
              action={action}
              resourceType={resourceType}
              project={project ?? ''}
              nextCursor={nextCursor}
              hasPrevPage={cursorHistory.length > 0}
              isPending={whoCanMutation.isPending}
              onNextPage={handleNextPage}
              onPrevPage={handlePrevPage}
            />
          )}
        </Stack>
      </FlexItem>
    </Flex>
  )
}
