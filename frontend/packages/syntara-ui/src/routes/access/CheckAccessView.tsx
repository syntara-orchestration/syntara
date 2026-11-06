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
} from '@patternfly/react-core'
import { RhUiCheckCircleIcon, RhUiCloseCircleIcon, RhUiWarningIcon } from '@patternfly/react-icons'
import { useMemo } from 'react'
import { useWatch } from 'react-hook-form'

import { SynForm } from '../../components/forms/SynForm'
import { SynFormField } from '../../components/forms/SynFormField'
import { SynLabel } from '../../components/labels/SynLabel'
import { SynEmptyStateNoData } from '../../components/states/SynEmptyStateNoData'
import { SynErrorState } from '../../components/states/SynErrorState'
import { useSynForm } from '../../hooks/useSynForm'
import { getErrorMessage } from '../../utils/apiErrors'

import { accessClient } from './accessClient'
import { accessControlHelp } from './accessControlFieldHelp'
import type { AuthzExplorerQueryFormData } from './authzExplorerQuerySchema'
import { authzExplorerQuerySchema } from './authzExplorerQuerySchema'
import type { ResourceActionMap } from './canIUtils'
import { ProjectSelect } from './ProjectSelect'
import { ResourceIdSelect } from './ResourceIdSelect'
import { TypeaheadSelect } from './TypeaheadSelect'
import type { CanIResponse } from './types'
import { useAllProjects } from './useAllProjects'

function AccessResult({
  result,
  action,
  resourceType,
  projectName,
}: Readonly<{
  result: CanIResponse
  action: string
  resourceType: string
  projectName: string
}>) {
  const projectSuffix = projectName ? (
    <>
      {' '}
      in project <strong>{projectName}</strong>
    </>
  ) : (
    <> in any project</>
  )

  if (result.allowed) {
    return (
      <Stack hasGutter>
        <StackItem>
          <Alert variant="success" title="Access allowed" isInline customIcon={<RhUiCheckCircleIcon />}>
            You can <strong>{action}</strong> on <strong>{resourceType}</strong>
            {projectSuffix}
          </Alert>
        </StackItem>
        {result.matched_policy && (
          <StackItem>
            <Content component={ContentVariants.small}>
              Matched policy: <SynLabel color="grey">{result.matched_policy}</SynLabel>
            </Content>
          </StackItem>
        )}
      </Stack>
    )
  }

  return (
    <Stack hasGutter>
      <StackItem>
        <Alert
          variant={result.denied ? 'danger' : 'warning'}
          title={result.denied ? 'Access denied' : 'Access not granted'}
          isInline
          customIcon={result.denied ? <RhUiCloseCircleIcon /> : <RhUiWarningIcon />}
        >
          You cannot <strong>{action}</strong> on <strong>{resourceType}</strong>
          {projectSuffix}
        </Alert>
      </StackItem>
      {result.denial_reason && (
        <StackItem>
          <Content component={ContentVariants.small}>Reason: {result.denial_reason}</Content>
        </StackItem>
      )}
      {result.denied_by && (
        <StackItem>
          <Content component={ContentVariants.small}>
            Denied by: <SynLabel color="grey">{result.denied_by}</SynLabel>
          </Content>
        </StackItem>
      )}
      {result.matched_policy && (
        <StackItem>
          <Content component={ContentVariants.small}>
            Matched policy: <SynLabel color="grey">{result.matched_policy}</SynLabel>
          </Content>
        </StackItem>
      )}
    </Stack>
  )
}

export function CheckAccessView({ resourceTypes, actionsByResource }: Readonly<ResourceActionMap>) {
  const { projects } = useAllProjects()

  const form = useSynForm({
    schema: authzExplorerQuerySchema,
    defaultValues: { resourceType: '', action: '', resourceId: '', project: '' },
  })
  const { handleSubmit, control, setValue, getValues } = form

  const resourceType = useWatch({ control, name: 'resourceType', defaultValue: '' })

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

  const canIMutation = accessClient.useMutation('post', '/authz/can_i')

  const onSubmit = handleSubmit((formData) => {
    canIMutation.mutate({
      body: {
        action: formData.action.trim(),
        resource_type: formData.resourceType.trim(),
        ...(formData.resourceId?.trim() && { resource_id: formData.resourceId.trim() }),
        ...(formData.project?.trim() && { resource_project: formData.project.trim() }),
      },
    })
  })

  const action = useWatch({ control, name: 'action', defaultValue: '' })

  return (
    <Flex direction={{ default: 'row' }} gap={{ default: 'gapXl' }} alignItems={{ default: 'alignItemsFlexStart' }}>
      <FlexItem style={{ minWidth: 340, maxWidth: 400 }}>
        <Form onSubmit={onSubmit}>
          <SynForm form={form}>
            <SynFormField<AuthzExplorerQueryFormData, 'resourceType'>
              name="resourceType"
              label="Resource type"
              fieldId="can-i-resource-type"
              isRequired
              labelHelp={accessControlHelp.resourceType}
            >
              {({ field }) => (
                <TypeaheadSelect
                  id="can-i-resource-type"
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
              fieldId="can-i-action"
              isRequired
              labelHelp={accessControlHelp.action}
            >
              {({ field }) => (
                <TypeaheadSelect
                  id="can-i-action"
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
              fieldId="can-i-project"
              labelHelp={accessControlHelp.project}
            >
              {({ field }) => (
                <ProjectSelect
                  id="can-i-project"
                  value={field.value ?? ''}
                  onChange={field.onChange}
                  projects={projects}
                />
              )}
            </SynFormField>

            <SynFormField<AuthzExplorerQueryFormData, 'resourceId'>
              name="resourceId"
              label="Resource ID"
              fieldId="can-i-resource-id"
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
            isLoading={canIMutation.isPending}
          >
            Check access
          </Button>
        </Form>
      </FlexItem>

      <FlexItem grow={{ default: 'grow' }}>
        <Stack hasGutter>
          {canIMutation.isIdle && (
            <StackItem>
              <SynEmptyStateNoData
                title="Check access permissions"
                description="Select a resource type and action, then click Check access to verify your permissions."
              />
            </StackItem>
          )}

          {canIMutation.isPending && (
            <StackItem>
              <Flex
                justifyContent={{ default: 'justifyContentCenter' }}
                style={{ padding: 'var(--pf-t--global--spacer--2xl)' }}
              >
                <Spinner size="lg" aria-label="Checking access" />
              </Flex>
            </StackItem>
          )}

          {canIMutation.isError && (
            <StackItem>
              <SynErrorState
                title="Access check failed"
                message={getErrorMessage(canIMutation.error)}
                onRetry={onSubmit}
              />
            </StackItem>
          )}

          {canIMutation.data && canIMutation.variables && (
            <AccessResult
              result={canIMutation.data}
              action={canIMutation.variables.body.action}
              resourceType={canIMutation.variables.body.resource_type}
              projectName={canIMutation.variables.body.resource_project ?? ''}
            />
          )}
        </Stack>
      </FlexItem>
    </Flex>
  )
}
