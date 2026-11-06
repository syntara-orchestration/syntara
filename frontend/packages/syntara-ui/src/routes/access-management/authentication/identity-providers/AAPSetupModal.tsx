import {
  Button,
  Form,
  FormHelperText,
  HelperText,
  HelperTextItem,
  MenuToggle,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  SelectList,
  SelectOption,
  Switch,
} from '@patternfly/react-core'
import type { MenuToggleElement } from '@patternfly/react-core'
import { useEffect, useState } from 'react'
import { useWatch } from 'react-hook-form'

import { identityProvidersClient } from '../../../../client'
import { SynForm } from '../../../../components/forms/SynForm'
import { SynFormField } from '../../../../components/forms/SynFormField'
import { SynTextField } from '../../../../components/forms/SynTextField'
import { SynSelect } from '../../../../components/SynSelect'
import { useBlurOnOpen } from '../../../../hooks/useBlurOnOpen'
import { useSynForm } from '../../../../hooks/useSynForm'
import { useAlerts } from '../../../../providers/alerts'

import { aapSetupSchema, type AAPSetupFormData, type AuthMethod } from './aapSetupSchema'

type AAPSetupModalProps = {
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
}

const authMethodOptions: ReadonlyArray<{ value: AuthMethod; label: string; description: string }> = [
  {
    value: 'token',
    label: 'Personal access token',
    description: 'Authenticate with a pre-generated token from Ansible Automation Platform',
  },
  {
    value: 'credentials',
    label: 'Platform admin credentials',
    description: 'Authenticate with a local Ansible Automation Platform admin username and password',
  },
]

function getAuthMethodLabel(value: AuthMethod): string {
  return authMethodOptions.find((o) => o.value === value)?.label ?? value
}

type AuthMethodToggleProps = Readonly<{
  toggleRef: React.Ref<MenuToggleElement>
  isOpen: boolean
  setIsOpen: React.Dispatch<React.SetStateAction<boolean>>
  value: AuthMethod
}>

function AuthMethodToggle({ toggleRef, isOpen, setIsOpen, value }: AuthMethodToggleProps) {
  return (
    <MenuToggle ref={toggleRef} onClick={() => setIsOpen((prev) => !prev)} isExpanded={isOpen} isFullWidth>
      {getAuthMethodLabel(value)}
    </MenuToggle>
  )
}

const defaultValues: AAPSetupFormData = {
  aap_url: '',
  organization: 'Default',
  auth_method: 'token',
  admin_username: '',
  admin_password: '',
  personal_access_token: '',
  insecure_skip_tls_verify: false,
}

export function AAPSetupModal({ isOpen, onClose, onSuccess }: Readonly<AAPSetupModalProps>) {
  useBlurOnOpen(isOpen)
  const { showSuccess } = useAlerts()
  const [isSelectOpen, setIsSelectOpen] = useState(false)

  const form = useSynForm({
    schema: aapSetupSchema,
    defaultValues,
    onClose,
  })
  const { control, handleSubmit, reset, setValue, handleError, handleClose } = form

  const authMethod = useWatch({ control, name: 'auth_method' })

  useEffect(() => {
    if (isOpen) {
      reset(defaultValues)
    }
  }, [isOpen, reset])

  const { mutate: setupAapOidc, isPending } = identityProvidersClient.useMutation(
    'post',
    '/identity_providers/setup_aap_oidc'
  )

  const onSubmit = (formData: AAPSetupFormData) => {
    const body =
      formData.auth_method === 'token'
        ? {
            aap_url: formData.aap_url,
            organization: formData.organization,
            personal_access_token: formData.personal_access_token,
            insecure_skip_tls_verify: formData.insecure_skip_tls_verify,
          }
        : {
            aap_url: formData.aap_url,
            organization: formData.organization,
            admin_username: formData.admin_username,
            admin_password: formData.admin_password,
            insecure_skip_tls_verify: formData.insecure_skip_tls_verify,
          }

    setupAapOidc(
      { body },
      {
        onSuccess: (data) => {
          showSuccess({
            title: 'Ansible Automation Platform identity provider created',
            description: `Provider "${data.name}" has been created and is ready to use.`,
          })
          handleClose()
          onSuccess()
        },
        onError: handleError({ title: 'Failed to add Ansible Automation Platform' }),
      }
    )
  }

  return (
    <Modal isOpen={isOpen} onClose={handleClose} variant="medium">
      <ModalHeader title="Add Ansible Automation Platform as a provider" />
      <ModalBody>
        <Form id="aap-setup-form" onSubmit={handleSubmit(onSubmit)}>
          <SynForm form={form}>
            <SynTextField
              name="aap_url"
              label="Ansible Automation Platform URL"
              fieldId="aap-url"
              placeholder="https://aap.example.com"
              isRequired
            />
            <SynTextField
              name="organization"
              label="Organization"
              fieldId="aap-organization"
              placeholder="Default"
              hint="Organization to create the OAuth2 application in"
              isRequired
            />
            <SynFormField<AAPSetupFormData, 'auth_method'>
              name="auth_method"
              label="Authentication method"
              fieldId="aap-auth-method"
            >
              {({ field }) => (
                <SynSelect
                  id="aap-auth-method"
                  isOpen={isSelectOpen}
                  selected={field.value}
                  popperProps={{ appendTo: 'inline' }}
                  onSelect={(_event, value) => {
                    const method = value as AuthMethod
                    field.onChange(method)
                    setIsSelectOpen(false)
                    if (method === 'credentials') {
                      setValue('personal_access_token', '')
                    } else {
                      setValue('admin_username', '')
                      setValue('admin_password', '')
                    }
                  }}
                  onOpenChange={setIsSelectOpen}
                  shouldFocusToggleOnSelect
                  toggle={(toggleRef) => (
                    <AuthMethodToggle
                      toggleRef={toggleRef}
                      isOpen={isSelectOpen}
                      setIsOpen={setIsSelectOpen}
                      value={field.value}
                    />
                  )}
                >
                  <SelectList>
                    {authMethodOptions.map((option) => (
                      <SelectOption
                        key={option.value}
                        value={option.value}
                        isSelected={field.value === option.value}
                        description={option.description}
                      >
                        {option.label}
                      </SelectOption>
                    ))}
                  </SelectList>
                </SynSelect>
              )}
            </SynFormField>
            {authMethod === 'credentials' ? (
              <>
                <SynTextField
                  name="admin_username"
                  label="Platform admin username"
                  fieldId="aap-admin-username"
                  placeholder="admin"
                  isRequired
                />
                <SynTextField
                  name="admin_password"
                  label="Platform admin password"
                  fieldId="aap-admin-password"
                  type="password"
                  autoComplete="off"
                  isRequired
                />
              </>
            ) : (
              <SynTextField
                name="personal_access_token"
                label="Personal access token"
                fieldId="aap-personal-access-token"
                type="password"
                autoComplete="off"
                isRequired
              />
            )}
            <SynFormField<AAPSetupFormData, 'insecure_skip_tls_verify'>
              name="insecure_skip_tls_verify"
              label="Disable TLS certificate verification"
              fieldId="aap-skip-tls"
              hideFormGroupLabel
              hideFooter
            >
              {({ field }) => (
                <>
                  <Switch
                    id="aap-skip-tls"
                    label="Disable TLS certificate verification"
                    isChecked={field.value}
                    onChange={(_event, checked) => field.onChange(checked)}
                    aria-label="Disable TLS certificate verification"
                  />
                  <FormHelperText>
                    <HelperText>
                      <HelperTextItem variant="warning">
                        When enabled, TLS certificate errors are ignored for all requests to this identity provider.
                        Only use this for testing or when connecting to providers with self-signed certificates.
                      </HelperTextItem>
                    </HelperText>
                  </FormHelperText>
                </>
              )}
            </SynFormField>
          </SynForm>
        </Form>
      </ModalBody>
      <ModalFooter>
        <Button variant="primary" type="submit" form="aap-setup-form" isDisabled={isPending} isLoading={isPending}>
          Add provider
        </Button>
        <Button variant="link" onClick={handleClose} isDisabled={isPending}>
          Cancel
        </Button>
      </ModalFooter>
    </Modal>
  )
}
