import { ActionGroup, Button, Form, Stack } from '@patternfly/react-core'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from '@tanstack/react-router'
import { useMemo, useRef } from 'react'

import { AppRoute } from '../../app/AppRoute'
import { breadcrumbsEditExecutionTarget } from '../../app/breadcrumbBuilders'
import { executionPlaneClient } from '../../client'
import { SynForm } from '../../components/forms/SynForm'
import { SynPage, SynPageBody } from '../../components/layout/SynPage'
import { SynPageHeader } from '../../components/layout/SynPageHeader'
import { SynPanel } from '../../components/layout/SynPanel'
import { SynErrorState } from '../../components/states/SynErrorState'
import { useQueryState } from '../../components/states/useQueryState'
import { SynPageTitle } from '../../components/SynPageTitle'
import { useDirtyFormGuard } from '../../hooks/useDirtyFormGuard'
import { useFormMutationErrorHandler } from '../../hooks/useFormMutationErrorHandler'
import { useSynForm } from '../../hooks/useSynForm'
import { useAlerts } from '../../providers/alerts'
import { getValidationFieldErrors } from '../../utils/apiErrors'
import { detachPromise } from '../../utils/detachPromise'
import { useDocLink } from '../../utils/docs/useDocLink'

import { CreateExecutionTargetFields } from './CreateExecutionTargetFields'
import styles from './ExecutionTargetForm.module.css'
import {
  EXECUTION_TARGET_FORM_DEFAULT_VALUES,
  executionTargetFormSchema,
  toExecutionTargetFormErrorField,
  toExecutionTargetFormValues,
  toExecutionTargetUpdateBody,
  type ExecutionTargetFormData,
} from './executionTargetFormSchema'
import { useExecutionTargetClusterName } from './useExecutionTargetClusterName'

const PAGE_TITLE = 'Edit execution target'

export function EditExecutionTarget() {
  const { executionTargetId }: { executionTargetId?: string } = useParams({ strict: false })
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const docLink = useDocLink('executionPlane')
  const { showAlert } = useAlerts()
  const hasId = Boolean(executionTargetId?.length)

  const detailPath = AppRoute.ExecutionPlane.Detail.replace(':executionTargetId', executionTargetId ?? '')

  const targetQuery = executionPlaneClient.useQuery(
    'get',
    '/api/execution_plane/v1/execution_targets/{target_id}',
    {
      params: { path: { target_id: executionTargetId ?? '' } },
    },
    { enabled: hasId }
  )
  const target = targetQuery.data

  const { clusterName, isClusterPending } = useExecutionTargetClusterName()

  const formValues = useMemo(() => (target ? toExecutionTargetFormValues(target) : undefined), [target])

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
    formState: { isDirty, dirtyFields },
  } = form

  // Bumped on discard so an in-flight PATCH cannot still apply success/error side effects.
  const saveGenerationRef = useRef(0)

  const { dismiss } = useDirtyFormGuard({
    isDirty,
    onDiscard: () => {
      saveGenerationRef.current += 1
      reset()
    },
    title: 'Discard unsaved changes?',
    body: 'You have unsaved changes to this execution target. Your changes will be lost if you leave.',
  })

  const handleError = useFormMutationErrorHandler<ExecutionTargetFormData>(setError)
  const { mutate: updateTarget, isPending: isSaving } = executionPlaneClient.useMutation(
    'patch',
    '/api/execution_plane/v1/execution_targets/{target_id}'
  )

  const onSubmit = (formData: ExecutionTargetFormData) => {
    if (!executionTargetId) return

    const body = toExecutionTargetUpdateBody(formData, dirtyFields, target)
    if (Object.keys(body).length === 0) return

    const generation = saveGenerationRef.current
    const context = formData.name ? `Execution target "${formData.name}"` : undefined
    updateTarget(
      {
        params: { path: { target_id: executionTargetId } },
        body,
      },
      {
        onSuccess: (updated) => {
          if (generation !== saveGenerationRef.current) return
          dismiss()
          showAlert({ title: 'Execution target updated', variant: 'success', autoDismiss: true })
          detachPromise(
            (async () => {
              await queryClient.invalidateQueries({
                queryKey: ['get', '/api/execution_plane/v1/execution_targets/{target_id}'],
              })
              await queryClient.invalidateQueries({
                queryKey: ['get', '/api/execution_plane/v1/execution_targets'],
              })
              await navigate({
                to: AppRoute.ExecutionPlane.Detail.replace(':executionTargetId', updated.id),
              })
            })()
          )
        },
        onError: (error) => {
          if (generation !== saveGenerationRef.current) return
          for (const fieldError of getValidationFieldErrors(error)) {
            const field = toExecutionTargetFormErrorField(fieldError.field)
            if (!field) continue
            setError(field, { type: 'server', message: fieldError.message })
          }
          handleError({
            title: 'Failed to update execution target',
            context,
            mapValidationToFields: false,
          })(error)
        },
      }
    )
  }

  const breadcrumbs = breadcrumbsEditExecutionTarget(target?.name ?? 'Execution target', detailPath)
  const queryState = useQueryState(targetQuery, {
    title: 'Error loading execution target',
    onRetry: () => detachPromise(targetQuery.refetch()),
  })

  if (!hasId || queryState) {
    return (
      <SynPage>
        <SynPageTitle segments={[PAGE_TITLE, 'Execution Plane']} />
        <SynPageHeader title={PAGE_TITLE} breadcrumbs={breadcrumbs} docLink={docLink} />
        <SynPageBody>
          <SynPanel isFullHeight>
            {queryState ?? <SynErrorState title="Invalid execution target" message="No execution target ID provided" />}
          </SynPanel>
        </SynPageBody>
      </SynPage>
    )
  }

  if (!target) {
    return null
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
                form="execution-target-edit-form"
                isLoading={isSaving}
                isDisabled={isSaving || !isDirty}
              >
                Save execution target
              </Button>
              <Button
                variant="link"
                onClick={
                  isSaving
                    ? undefined
                    : () => {
                        detachPromise(navigate({ to: detailPath }))
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
            <Form
              id="execution-target-edit-form"
              onSubmit={(event) => {
                event.preventDefault()
                detachPromise(handleSubmit(onSubmit)())
              }}
            >
              <SynForm form={form}>
                <CreateExecutionTargetFields clusterName={clusterName} isClusterPending={isClusterPending} />
              </SynForm>
            </Form>
          </Stack>
        </SynPanel>
      </SynPageBody>
    </SynPage>
  )
}
