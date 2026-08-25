import type { UseFormSetError } from 'react-hook-form'

import { useFormMutationErrorHandler } from '../../../hooks/useFormMutationErrorHandler'
import { useAlerts } from '../../../providers/alerts'
import { useAuthStore } from '../../../stores/useAuthStore'
import { accessClient } from '../../access/accessClient'
import { logoutWithAlert } from '../logoutWithAlert'
import type { UserFormData } from '../userFormSchema'

type UseUserFormSubmitOptions = {
  isEdit: boolean
  isValidId: boolean
  userId: string
  isBuiltinUser: boolean
  isFederatedUser: boolean
  isSelf: boolean
  setError: UseFormSetError<UserFormData>
  navigateBack: () => void
}

export function useUserFormSubmit({
  isEdit,
  isValidId,
  userId,
  isBuiltinUser,
  isFederatedUser,
  isSelf,
  setError,
  navigateBack,
}: UseUserFormSubmitOptions) {
  const { showAlert } = useAlerts()
  const handleError = useFormMutationErrorHandler<UserFormData>(setError)
  const { mutate: createUser, isPending: isCreating } = accessClient.useMutation('post', '/users')
  const { mutate: updateUser, isPending: isUpdating } = accessClient.useMutation('patch', '/users/{user_id}')
  const logout = useAuthStore((s) => s.logout)
  const isSaving = isCreating || isUpdating

  const handleUpdateSuccess = () => {
    showAlert({ title: 'User updated', variant: 'success', autoDismiss: true })
    navigateBack()
  }

  const handlePasswordChangeSuccess = () => {
    if (isSelf) {
      logoutWithAlert(logout, showAlert, 'Password changed — signing out')
    } else {
      showAlert({
        title: 'User updated',
        description: 'Password changed — all active sessions for this user have been revoked.',
        variant: 'success',
        autoDismiss: true,
      })
      navigateBack()
    }
  }

  const onSubmit = (formData: UserFormData) => {
    const context = formData.username ? `User "${formData.username}"` : undefined
    if (isEdit && isValidId) {
      // undefined omits the field from the PATCH body (no change)
      const email = formData.email || undefined
      updateUser(
        {
          params: { path: { user_id: userId } },
          body: {
            ...(isBuiltinUser
              ? {}
              : {
                  username: formData.username,
                  first_name: formData.first_name || undefined,
                  last_name: formData.last_name || undefined,
                  email,
                }),
            ...(formData.password && !isFederatedUser && (!isBuiltinUser || isSelf)
              ? { password: formData.password }
              : {}),
          },
        },
        {
          onSuccess: () => {
            if (formData.password) {
              handlePasswordChangeSuccess()
              return
            }
            handleUpdateSuccess()
          },
          onError: handleError({ title: 'Failed to update user', context }),
        }
      )
    } else {
      // null explicitly sets "no email" in the POST body
      const email = formData.email || null
      createUser(
        {
          body: {
            username: formData.username,
            email,
            first_name: formData.first_name || null,
            last_name: formData.last_name || null,
            password: formData.password ?? '',
            is_enabled: formData.is_enabled,
            group_names: formData.group_names,
          },
        },
        {
          onSuccess: () => {
            showAlert({ title: 'User created', variant: 'success', autoDismiss: true })
            navigateBack()
          },
          onError: handleError({ title: 'Failed to create user', context }),
        }
      )
    }
  }

  return { onSubmit, isSaving }
}
