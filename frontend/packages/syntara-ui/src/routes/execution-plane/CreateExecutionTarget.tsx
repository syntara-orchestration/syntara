import { ActionGroup, Button, Form, Stack } from '@patternfly/react-core'
import { RhUiAddIcon } from '@patternfly/react-icons'
import { useNavigate } from '@tanstack/react-router'
import { useMemo } from 'react'

import { AppRoute } from '../../app/AppRoute'
import { breadcrumbsConfigureExecutionTarget } from '../../app/breadcrumbBuilders'
import { executionPlaneClient } from '../../client'
import { SynForm } from '../../components/forms/SynForm'
import { SynPage, SynPageBody } from '../../components/layout/SynPage'
import { SynPageHeader } from '../../components/layout/SynPageHeader'
import { SynPanel } from '../../components/layout/SynPanel'
import { useQueryState } from '../../components/states/useQueryState'
import { SynPageTitle } from '../../components/SynPageTitle'
import { useDirtyFormGuard } from '../../hooks/useDirtyFormGuard'
import { useFormMutationErrorHandler } from '../../hooks/useFormMutationErrorHandler'
import { useSynForm } from '../../hooks/useSynForm'
import { useAlerts } from '../../providers/alerts'
import { detachPromise } from '../../utils/detachPromise'
import { useDocLink } from '../../utils/docs/useDocLink'

import { CreateExecutionTargetFields } from './CreateExecutionTargetFields'
import { DEFAULT_EXECUTION_TARGET_HINT, FIRST_DEFAULT_EXECUTION_TARGET_HINT } from './executionTargetFieldHelp'
import styles from './ExecutionTargetForm.module.css'
import {
  EXECUTION_TARGET_FORM_DEFAULT_VALUES,
  executionTargetFormSchema,
  toExecutionTargetCreateBody,
  type ExecutionTargetFormData,
} from './executionTargetFormSchema'
import { useExecutionTargetClusterName } from './useExecutionTargetClusterName'

const PAGE_TITLE = 'Configure execution target'

export function CreateExecutionTarget() {
  const navigate = useNavigate()
  const docLink = useDocLink('executionPlane')
  const { showAlert } = useAlerts()
  const { clusterName, isClusterPending } = useExecutionTargetClusterName()

  const existingTargetsQuery = executionPlaneClient.useQuery('get', '/api/execution_plane/v1/execution_targets', {
    params: { query: { limit: 1, include_total: true } },
  })
  const existingTargetsQueryState = useQueryState(existingTargetsQuery, {
    title: 'Error loading execution targets',
    onRetry: () => detachPromise(existingTargetsQuery.refetch()),
  })

  // Only treat count as zero after a successful fetch — a failed query must not lock default.
  const existingTargetCount = existingTargetsQuery.isSuccess
    ? (existingTargetsQuery.data.total ?? existingTargetsQuery.data.resources.length)
    : undefined
  const isDefaultLocked = existingTargetCount === 0

  const formValues = useMemo(
    () => ({ ...EXECUTION_TARGET_FORM_DEFAULT_VALUES, isDefault: isDefaultLocked }),
    [isDefaultLocked]
  )

  const form = useSynForm({
    schema: executionTargetFormSchema,
    defaultValues: EXECUTION_TARGET_FORM_DEFAULT_VALUES,
    values: formValues,
    resetOptions: { keepDirtyValues: true },
  })
  const {
    handleSubmit,
    setError,
    reset,
    formState: { isDirty },
  } = form

  const { dismiss } = useDirtyFormGuard({
    isDirty,
    onDiscard: () => reset(),
    title: 'Discard unsaved changes?',
    body: 'You have unsaved changes to this execution target. Your changes will be lost if you leave.',
  })

  const handleError = useFormMutationErrorHandler<ExecutionTargetFormData>(setError)
  const { mutate: createTarget, isPending: isSaving } = executionPlaneClient.useMutation(
    'post',
    '/api/execution_plane/v1/execution_targets'
  )

  const onSubmit = (formData: ExecutionTargetFormData) => {
    const context = formData.name ? `Execution target "${formData.name}"` : undefined
    createTarget(
      { body: toExecutionTargetCreateBody(formData) },
      {
        onSuccess: (created) => {
          dismiss()
          showAlert({ title: 'Execution target configured', variant: 'success', autoDismiss: true })
          detachPromise(
            navigate({
              to: AppRoute.ExecutionPlane.Detail.replace(':executionTargetId', created.id),
            })
          )
        },
        onError: handleError({ title: 'Failed to configure execution target', context }),
      }
    )
  }

  const breadcrumbs = breadcrumbsConfigureExecutionTarget()

  if (existingTargetsQueryState) {
    return (
      <SynPage>
        <SynPageTitle segments={[PAGE_TITLE, 'Execution Plane']} />
        <SynPageHeader title={PAGE_TITLE} docLink={docLink} breadcrumbs={breadcrumbs} />
        <SynPageBody>
          <SynPanel isFullHeight>{existingTargetsQueryState}</SynPanel>
        </SynPageBody>
      </SynPage>
    )
  }

  return (
    <SynPage>
      <SynPageTitle segments={[PAGE_TITLE, 'Execution Plane']} />
      <SynPageHeader title={PAGE_TITLE} docLink={docLink} breadcrumbs={breadcrumbs} />
      <SynPageBody>
        <SynPanel
          isFullHeight
          isScrollable
          footer={
            <ActionGroup>
              <Button
                type="submit"
                form="execution-target-create-form"
                isLoading={isSaving}
                isDisabled={isSaving}
                icon={<RhUiAddIcon />}
              >
                Configure execution target
              </Button>
              <Button
                variant="link"
                onClick={
                  isSaving
                    ? undefined
                    : () => {
                        detachPromise(navigate({ to: AppRoute.ExecutionPlane.Root }))
                      }
                }
                isAriaDisabled={isSaving}
              >
                Cancel
              </Button>
            </ActionGroup>
          }
          panelMainBodyProps={{ className: styles.panelBody }}
        >
          <Stack className={styles.formStack}>
            <Form id="execution-target-create-form" onSubmit={handleSubmit(onSubmit)}>
              <SynForm form={form}>
                <CreateExecutionTargetFields
                  clusterName={clusterName}
                  isClusterPending={isClusterPending}
                  isDefaultLocked={isDefaultLocked}
                  defaultCheckboxHint={
                    isDefaultLocked ? FIRST_DEFAULT_EXECUTION_TARGET_HINT : DEFAULT_EXECUTION_TARGET_HINT
                  }
                />
              </SynForm>
            </Form>
          </Stack>
        </SynPanel>
      </SynPageBody>
    </SynPage>
  )
}
