import { FormGroup, FormHelperText, HelperText, HelperTextItem, StackItem, TextInput } from '@patternfly/react-core'
import { RhUiErrorIcon } from '@patternfly/react-icons'
import type { CredentialsAPI } from '@syntara/contracts'
import { useMemo } from 'react'
import { Controller, useFormContext, useWatch } from 'react-hook-form'

import { credentialsClient } from '../../../client'
import { CredentialSelector } from '../components/CredentialSelector'
import { DroppableField } from '../panels/fields/DroppableField'

import type { ActionFormValues } from './actionFormSchema'
import { credentialHelpText } from './credentialSelectorHelpText'
import { nodeHelp } from './shared/nodeFieldHelp'

const CREDENTIAL_TYPE_URL = 'Secret URL'

// Matches CredentialSelector's query key structure for TanStack Query cache reuse
type CredentialQueryParams = CredentialsAPI.operations['list_credentials']['parameters']['query'] & {
  project_id?: string
}

export type ActionFormMethods = ReturnType<typeof useFormContext<ActionFormValues>>

export type HttpUrlFieldProps = Readonly<{
  register: ActionFormMethods['register']
  getValues: ActionFormMethods['getValues']
  setValue: ActionFormMethods['setValue']
  urlError?: { message?: string }
  isUrlManagedByCredential: boolean
  isDisabled: boolean
}>

// Exported for isolated accessibility testing (avoids PatternFly tab JSDOM issue in full-form tests)
export function HttpUrlField({
  register,
  getValues,
  setValue,
  urlError,
  isUrlManagedByCredential,
  isDisabled,
}: HttpUrlFieldProps) {
  const isFieldDisabled = isDisabled || isUrlManagedByCredential

  return (
    <FormGroup label="URL" labelHelp={nodeHelp.httpUrl} isRequired={!isUrlManagedByCredential} fieldId="action-url">
      <DroppableField
        onDropText={(text) => {
          const current = getValues('url')
          setValue('url', (current ?? '') + text)
        }}
        isDisabled={isFieldDisabled}
      >
        <TextInput
          {...register('url')}
          id="action-url"
          type="url"
          placeholder={isUrlManagedByCredential ? 'URL managed by credential' : 'https://api.example.com/endpoint'}
          validated={urlError ? 'error' : 'default'}
          isDisabled={isFieldDisabled}
        />
      </DroppableField>
      {isUrlManagedByCredential ? (
        <FormHelperText>
          <HelperText>
            <HelperTextItem>
              This value will be injected at execution time and is never stored in the workflow definition.
            </HelperTextItem>
          </HelperText>
        </FormHelperText>
      ) : (
        urlError && (
          <FormHelperText>
            <HelperText>
              <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
                {urlError.message}
              </HelperTextItem>
            </HelperText>
          </FormHelperText>
        )
      )}
    </FormGroup>
  )
}

type HttpCredentialSectionProps = Readonly<{
  control: ActionFormMethods['control']
  register: ActionFormMethods['register']
  getValues: ActionFormMethods['getValues']
  setValue: ActionFormMethods['setValue']
  urlError?: { message?: string }
  isVersionView: boolean
  projectId?: string
}>

/** Renders the credential selector and URL field for HTTP request nodes.
 *  Owns credential type queries and the isUrlManagedByCredential state. */
export function HttpCredentialSection({
  control,
  register,
  getValues,
  setValue,
  urlError,
  isVersionView,
  projectId,
}: HttpCredentialSectionProps) {
  const credentialId = useWatch({ control, name: 'credential_id' })
  const credentialQueryParams = useMemo<CredentialQueryParams>(
    () => (projectId ? { project_id: projectId } : {}),
    [projectId]
  )
  const { data: credsData, isPending: isCredsPending } = credentialsClient.useQuery('get', '/credentials', {
    params: { query: credentialQueryParams },
  })
  const { data: typesData, isPending: isTypesPending } = credentialsClient.useQuery('get', '/credential_types')
  const isUrlManagedByCredential = useMemo(() => {
    // Default to locked while loading to prevent a flash of an unlocked field
    // when the form opens with a pre-existing Secret URL credential_id.
    if (credentialId && (isCredsPending || isTypesPending)) return true
    const cred = credsData?.resources?.find((c) => c.id === credentialId)
    return typesData?.resources?.find((t) => t.id === cred?.credential_type_id)?.name === CREDENTIAL_TYPE_URL
  }, [credentialId, credsData, typesData, isCredsPending, isTypesPending])

  return (
    <>
      <StackItem>
        <Controller
          control={control}
          name="credential_id"
          render={({ field }) => (
            <CredentialSelector
              value={field.value ?? undefined}
              onChange={(newId) => {
                field.onChange(newId)
                // Clear URL when switching to a Secret URL credential so the locked
                // placeholder shows correctly instead of any previously typed value.
                const cred = credsData?.resources?.find((c) => c.id === newId)
                const typeName = typesData?.resources?.find((t) => t.id === cred?.credential_type_id)?.name
                if (typeName === CREDENTIAL_TYPE_URL) setValue('url', '')
              }}
              compatibleTypeNames={['HTTP Bearer Token', 'HTTP Basic Auth', CREDENTIAL_TYPE_URL]}
              label="Authentication credential"
              fieldId="action-credential"
              placeholder="Select credential"
              allowCreate
              isDisabled={isVersionView}
              projectId={projectId}
              helpText={credentialHelpText(
                'Select a stored credential to authenticate this request. Credentials securely store sensitive information like API tokens and passwords.'
              )}
            />
          )}
        />
      </StackItem>
      <StackItem>
        <HttpUrlField
          register={register}
          getValues={getValues}
          setValue={setValue}
          urlError={urlError}
          isUrlManagedByCredential={isUrlManagedByCredential}
          isDisabled={isVersionView}
        />
      </StackItem>
    </>
  )
}
