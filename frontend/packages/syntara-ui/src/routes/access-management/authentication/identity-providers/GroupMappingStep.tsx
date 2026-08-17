import {
  Alert,
  Button,
  Content,
  ContentVariants,
  ExpandableSection,
  Form,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  MenuToggle,
  type MenuToggleElement,
  SelectList,
  SelectOption,
  TextInput,
} from '@patternfly/react-core'
import { RhUiAddIcon, RhUiErrorIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import React, { useCallback, useEffect, useState } from 'react'
import { Controller, useFieldArray, useWatch, type Control, type UseFormSetValue } from 'react-hook-form'

import { NxSelect } from '../../../../components/NxSelect'
import { APP_TITLE } from '../../../../utils/appTitle'
import { useAllGroups } from '../../../access/useAllGroups'

import { GroupColumnLabel, IdpGroupValueColumnLabel } from './groupMappingFields'
import {
  actionColumnStyle,
  columnHeaderStyle,
  flexOneStyle,
  headerRowStyle,
  mappingRowStyle,
} from './groupMappingStyles'
import { nextKey, processDiscoveredGroups } from './groupMappingUtils'
import { type IdentityProviderFormData } from './identityProviderFormSchema'
import { idpHelp } from './idpFieldHelp'
import { useTestSignIn } from './useTestSignIn'

function NexusGroupSelect({
  value,
  onChange,
  onBlur,
  nexusGroups,
  ariaLabel,
  validated,
}: {
  value: string
  onChange: (value: string) => void
  onBlur?: () => void
  nexusGroups: { id?: string; name?: string }[]
  ariaLabel: string
  validated?: 'error' | 'default'
}) {
  const [isOpen, setIsOpen] = useState(false)
  const selectedLabel = nexusGroups.find((g) => g.id === value)?.name ?? value
  return (
    <NxSelect
      isOpen={isOpen}
      selected={value || undefined}
      onSelect={(_event, val) => {
        onChange(String(val))
        setIsOpen(false)
      }}
      onOpenChange={(open) => {
        setIsOpen(open)
        if (!open) onBlur?.()
      }}
      toggle={(toggleRef: React.Ref<MenuToggleElement>) => (
        <MenuToggle
          ref={toggleRef}
          onClick={() => setIsOpen((prev) => !prev)}
          isExpanded={isOpen}
          isFullWidth
          isPlaceholder={!value}
          status={validated === 'error' ? 'danger' : undefined}
          aria-label={ariaLabel}
        >
          {value ? selectedLabel : `Select a ${APP_TITLE} group...`}
        </MenuToggle>
      )}
    >
      <SelectList>
        {nexusGroups.map((g) => (
          <SelectOption key={g.id} value={g.id}>
            {g.name ?? g.id ?? ''}
          </SelectOption>
        ))}
      </SelectList>
    </NxSelect>
  )
}

type MappingEntryRowProps = {
  index: number
  control: Control<IdentityProviderFormData>
  nexusGroups: { id?: string; name?: string }[]
  onRemove: () => void
}

function MappingEntryRow({ index, control, nexusGroups, onRemove }: Readonly<MappingEntryRowProps>) {
  return (
    <div style={mappingRowStyle}>
      <Controller
        name={`groupMapping.entries.${index}.idpGroupValue`}
        control={control}
        render={({ field, fieldState }) => (
          <div style={flexOneStyle}>
            <TextInput
              aria-label={`IdP group value ${index + 1}`}
              placeholder="IdP group value"
              validated={fieldState.error ? 'error' : 'default'}
              {...field}
            />
          </div>
        )}
      />
      <Controller
        name={`groupMapping.entries.${index}.nexusGroupId`}
        control={control}
        render={({ field, fieldState }) => (
          <div style={flexOneStyle}>
            <NexusGroupSelect
              value={field.value}
              onChange={field.onChange}
              onBlur={field.onBlur}
              nexusGroups={nexusGroups}
              ariaLabel={`${APP_TITLE} group ${index + 1}`}
              validated={fieldState.error ? 'error' : 'default'}
            />
          </div>
        )}
      />
      <Button variant="plain" aria-label={`Remove mapping ${index + 1}`} onClick={onRemove} icon={<RhUiTrashIcon />} />
    </div>
  )
}

export type GroupMappingStepProps = {
  control: Control<IdentityProviderFormData>
  setValue: UseFormSetValue<IdentityProviderFormData>
  providerId?: string
}

/**
 * Group mapping step in the add/edit identity provider wizard form.
 *
 * Unlike `GroupMappingTab` (which uses raw `useState`), this component participates
 * in the parent's react-hook-form context via `control` and `useFieldArray`, so its
 * mapping data is submitted together with the rest of the provider form.
 *
 * The `useEffect` below lazily initializes the `groupMapping` sub-form when the user
 * first navigates to this wizard step. The schema marks `groupMapping` as nullable
 * because it is optional — if the user never visits this step, no group mapping is
 * submitted. Once they do visit, we seed it with defaults so `useFieldArray` has a
 * valid array to operate on.
 */
function signInAlertTitle(variant: string): string {
  if (variant === 'success') return 'Groups discovered'
  if (variant === 'danger') return 'Sign-in failed'
  return 'No groups found'
}

export function GroupMappingStep({ control, setValue, providerId }: Readonly<GroupMappingStepProps>) {
  const groupMapping = useWatch({ control, name: 'groupMapping' })
  const [signInAlert, setSignInAlert] = useState<{ variant: 'success' | 'warning' | 'danger'; message: string } | null>(
    null
  )

  // Lazily initialize the groupMapping sub-form when the user first reaches this step.
  // groupMapping is nullable in the schema because it is optional — only seeded on visit.
  useEffect(() => {
    if (!groupMapping) {
      setValue('groupMapping', { jmespathExpression: 'groups[*]', entries: [] })
    }
  }, [groupMapping, setValue])

  const { fields, append, remove, replace } = useFieldArray({ control, name: 'groupMapping.entries' })

  const { groups: nexusGroups } = useAllGroups()

  const handleTestResult = useCallback(
    (claims: Record<string, unknown>) => {
      const expression = groupMapping?.jmespathExpression ?? 'groups[*]'
      const currentEntries = (groupMapping?.entries ?? []).map((e) => ({
        key: nextKey(),
        ...e,
      }))
      const result = processDiscoveredGroups(claims, expression, currentEntries, nexusGroups)
      replace(result.newEntries.map(({ idpGroupValue, nexusGroupId }) => ({ idpGroupValue, nexusGroupId })))
      setSignInAlert({ variant: result.variant, message: result.message })
    },
    [groupMapping, nexusGroups, replace]
  )

  const handleTestError = useCallback(() => {
    setSignInAlert({
      variant: 'danger',
      message: 'Could not connect to the identity provider. Verify the provider is reachable and try again.',
    })
  }, [])

  const { openTestSignIn, isListening } = useTestSignIn({
    providerId,
    onResult: handleTestResult,
    onError: handleTestError,
  })

  return (
    <Form>
      {providerId && (
        <FormGroup fieldId="test-signin">
          <Button variant="secondary" onClick={openTestSignIn} isLoading={isListening} isDisabled={isListening}>
            {isListening ? 'Waiting for sign-in...' : 'Discover groups'}
          </Button>
          <FormHelperText>
            <HelperText>
              <HelperTextItem>
                Sign in to your identity provider to discover available groups and populate the mapping table below
              </HelperTextItem>
            </HelperText>
          </FormHelperText>
        </FormGroup>
      )}

      {signInAlert && (
        <Alert variant={signInAlert.variant} title={signInAlertTitle(signInAlert.variant)} isInline>
          {signInAlert.message}
        </Alert>
      )}

      <FormGroup label="Group mapping" fieldId="group-mapping-table">
        <FormHelperText>
          <HelperText>
            <HelperTextItem>
              {`Map IdP group values to ${APP_TITLE} groups. Use Discover groups to auto-populate, or add manually.`}
            </HelperTextItem>
          </HelperText>
        </FormHelperText>
        {fields.length > 0 && (
          <div style={headerRowStyle}>
            <Content component={ContentVariants.small} style={{ ...columnHeaderStyle, margin: 0 }}>
              <IdpGroupValueColumnLabel />
            </Content>
            <Content component={ContentVariants.small} style={{ ...columnHeaderStyle, margin: 0 }}>
              <GroupColumnLabel />
            </Content>
            <div style={actionColumnStyle} />
          </div>
        )}
        {fields.map((field, index) => (
          <MappingEntryRow
            key={field.id}
            index={index}
            control={control}
            nexusGroups={nexusGroups}
            onRemove={() => remove(index)}
          />
        ))}
        <Button variant="link" icon={<RhUiAddIcon />} onClick={() => append({ idpGroupValue: '', nexusGroupId: '' })}>
          Add mapping
        </Button>
      </FormGroup>

      <ExpandableSection toggleText="Advanced: Group Extraction Expression">
        <Controller
          name="groupMapping.jmespathExpression"
          control={control}
          render={({ field, fieldState }) => (
            <FormGroup
              label="Group extraction expression"
              fieldId="jmespath-expression"
              labelHelp={idpHelp.groupExtractionExpression}
            >
              <TextInput
                id="jmespath-expression"
                placeholder="groups[*]"
                validated={fieldState.error ? 'error' : 'default'}
                {...field}
                value={field.value ?? 'groups[*]'}
              />
              <FormHelperText>
                <HelperText>
                  <HelperTextItem
                    variant={fieldState.error ? 'error' : 'default'}
                    icon={fieldState.error ? <RhUiErrorIcon /> : undefined}
                  >
                    {fieldState.error?.message ?? 'JMESPath expression to extract group values from the ID token'}
                  </HelperTextItem>
                </HelperText>
              </FormHelperText>
            </FormGroup>
          )}
        />
      </ExpandableSection>
    </Form>
  )
}
