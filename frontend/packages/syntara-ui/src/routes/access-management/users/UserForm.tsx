import { zodResolver } from '@hookform/resolvers/zod'
import { ActionGroup, Alert, Button, Form, Stack, StackItem } from '@patternfly/react-core'
import { RhUiAddIcon } from '@patternfly/react-icons'
import { useNavigate } from '@tanstack/react-router'
import type { BaseSyntheticEvent, ReactNode } from 'react'
import type { Control } from 'react-hook-form'
import { useForm, useWatch } from 'react-hook-form'

import { AppRoute } from '../../../app/AppRoute'
import { breadcrumbsCreateUser, breadcrumbsEditUser, breadcrumbsUserFormLoading } from '../../../app/breadcrumbBuilders'
import type { AppBreadcrumbItem } from '../../../app/breadcrumbs/appBreadcrumbItem'
import { SynPage, SynPageBody } from '../../../components/layout/SynPage'
import { SynPageHeader } from '../../../components/layout/SynPageHeader'
import { SynPanel } from '../../../components/layout/SynPanel'
import { useQueryState } from '../../../components/states/useQueryState'
import { SynPageTitle } from '../../../components/SynPageTitle'
import { useDirtyFormGuard } from '../../../hooks/useDirtyFormGuard'
import { detachPromise } from '../../../utils/detachPromise'
import { useDocLink } from '../../../utils/docs/useDocLink'
import { userFormSchema, userCreateSchema, type UserFormData } from '../userFormSchema'

import { userDisplayName } from './userDisplayName'
import { UserFormFields } from './UserFormFields'
import { UserNotFoundState } from './UserNotFoundState'
import { useUserFormData } from './useUserFormData'
import { useUserFormSubmit } from './useUserFormSubmit'

type UserFormProps = {
  mode: 'create' | 'edit'
}

const DEFAULT_VALUES: UserFormData = {
  username: '',
  first_name: '',
  last_name: '',
  email: '',
  password: '',
  is_enabled: true,
  group_names: ['users'],
}

function PasswordWarningAlert({ isSelf }: Readonly<{ isSelf: boolean }>) {
  const title = isSelf ? 'You will be signed out' : 'User will be signed out'
  const description = isSelf
    ? 'Changing your own password will end all active sessions. You will need to sign in again with your new password.'
    : "Changing this user's password will revoke all their active sessions. They will need to sign in again."
  return (
    <StackItem>
      <Alert variant="warning" title={title} isInline>
        {description}
      </Alert>
    </StackItem>
  )
}

function userFormBreadcrumbTrail(
  isEdit: boolean,
  pageTitle: string,
  userId: string | undefined,
  user: { first_name: string; last_name?: string | null; username: string } | undefined
): AppBreadcrumbItem[] {
  if (!isEdit) {
    return breadcrumbsCreateUser()
  }
  const userBasePath = userId ? AppRoute.AccessManagement.UserDetail.replace(':userId', userId) : undefined
  const displayName = user ? userDisplayName(user) : undefined
  if (displayName && userBasePath) {
    return breadcrumbsEditUser(displayName, userBasePath)
  }
  return breadcrumbsUserFormLoading(pageTitle)
}

type UserFormMainPanelProps = {
  control: Control<UserFormData>
  isEdit: boolean
  isBuiltinUser: boolean
  isFederatedUser: boolean
  isSelf: boolean
  showPasswordWarning: boolean
  onFormSubmit: (event?: BaseSyntheticEvent) => Promise<void>
  footer: ReactNode
}

function UserFormMainPanel({
  control,
  isEdit,
  isBuiltinUser,
  isFederatedUser,
  isSelf,
  showPasswordWarning,
  onFormSubmit,
  footer,
}: Readonly<UserFormMainPanelProps>) {
  return (
    <SynPanel
      isFullHeight
      isScrollable
      footer={footer}
      panelMainBodyProps={{ style: { padding: 'var(--pf-t--global--spacer--xl)' } }}
    >
      <Stack hasGutter style={{ maxWidth: '600px' }}>
        {showPasswordWarning ? <PasswordWarningAlert isSelf={isSelf} /> : null}
        <StackItem>
          <Form id="user-form" onSubmit={onFormSubmit}>
            <UserFormFields
              control={control}
              isEdit={isEdit}
              isBuiltinUser={isBuiltinUser}
              isBuiltinSelf={isBuiltinUser && isSelf}
              isFederatedUser={isFederatedUser}
            />
          </Form>
        </StackItem>
      </Stack>
    </SynPanel>
  )
}

function UserFormEditNotFoundPage({ onBack, onRetry }: Readonly<{ onBack: () => void; onRetry: () => void }>) {
  return (
    <SynPage>
      <SynPageHeader title="Edit User" breadcrumbs={breadcrumbsUserFormLoading('Edit user')} />
      <SynPageBody>
        <SynPanel isFullHeight>
          <UserNotFoundState onBack={onBack} onRetry={onRetry} />
        </SynPanel>
      </SynPageBody>
    </SynPage>
  )
}

function UserFormEditBusyPage({ pageTitle, children }: Readonly<{ pageTitle: string; children: ReactNode }>) {
  return (
    <SynPage>
      <SynPageHeader title={pageTitle} breadcrumbs={breadcrumbsUserFormLoading(pageTitle)} />
      <SynPageBody>
        <SynPanel isFullHeight>{children}</SynPanel>
      </SynPageBody>
    </SynPage>
  )
}

export function UserForm({ mode }: Readonly<UserFormProps>) {
  const navigate = useNavigate()
  const isEdit = mode === 'edit'
  const usersDocLink = useDocLink(isEdit ? 'users' : 'createUser')
  const pageTitle = isEdit ? 'Edit User' : 'Create User'
  const submitLabel = isEdit ? 'Save' : 'Create user'

  const { userId, isValidId, userQuery, isBuiltinUser, isFederatedUser, isSelf, formValues } = useUserFormData(isEdit)

  const schema = isEdit ? userFormSchema : userCreateSchema
  const {
    control,
    handleSubmit,
    setError,
    formState: { isDirty },
    reset,
  } = useForm<UserFormData>({
    resolver: zodResolver(schema, undefined, { mode: 'sync' }),
    defaultValues: formValues ?? DEFAULT_VALUES,
    values: isEdit && formValues ? formValues : undefined,
  })

  const navigateBack = () => detachPromise(navigate({ to: AppRoute.AccessManagement.Users }))

  const { dismiss } = useDirtyFormGuard({
    isDirty,
    onDiscard: () => reset(),
    title: 'Discard unsaved changes?',
    body: 'You have unsaved changes to this user. Your changes will be lost if you leave.',
  })

  const { onSubmit, isSaving } = useUserFormSubmit({
    isEdit,
    isValidId,
    userId,
    isBuiltinUser,
    isFederatedUser,
    isSelf,
    setError,
    navigateBack: () => {
      dismiss()
      navigateBack()
    },
  })

  const passwordValue = useWatch({ control, name: 'password' })
  const showPasswordWarning = isEdit && !isFederatedUser && !!passwordValue

  const refetchUser = userQuery.refetch
  const queryState = useQueryState(userQuery, {
    title: 'Error loading user',
    onRetry: () => {
      detachPromise(refetchUser())
    },
  })
  if (isEdit && userQuery.error) {
    return (
      <UserFormEditNotFoundPage
        onBack={navigateBack}
        onRetry={() => {
          detachPromise(refetchUser())
        }}
      />
    )
  }
  if (isEdit && queryState) {
    return <UserFormEditBusyPage pageTitle={pageTitle}>{queryState}</UserFormEditBusyPage>
  }

  const formBreadcrumbs = userFormBreadcrumbTrail(isEdit, pageTitle, userId, userQuery.data)

  return (
    <SynPage>
      <SynPageTitle segments={[pageTitle, 'Users']} />
      <SynPageHeader title={pageTitle} docLink={usersDocLink} breadcrumbs={formBreadcrumbs} />
      <SynPageBody>
        <UserFormMainPanel
          control={control}
          isEdit={isEdit}
          isBuiltinUser={isBuiltinUser}
          isFederatedUser={isFederatedUser}
          isSelf={isSelf}
          showPasswordWarning={showPasswordWarning}
          onFormSubmit={handleSubmit(onSubmit)}
          footer={
            <ActionGroup>
              <Button
                type="submit"
                form="user-form"
                isLoading={isSaving}
                isDisabled={isSaving}
                icon={isEdit ? undefined : <RhUiAddIcon />}
              >
                {submitLabel}
              </Button>
              <Button variant="link" onClick={navigateBack}>
                Cancel
              </Button>
            </ActionGroup>
          }
        />
      </SynPageBody>
    </SynPage>
  )
}
